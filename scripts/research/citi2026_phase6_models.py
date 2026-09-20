#!/usr/bin/env python3
"""CITI-2026 Phase 6 — models & baselines.

Fits 3 sklearn classifiers (LogisticRegression, DecisionTreeClassifier,
RandomForestClassifier) on each of the 4 Phase 5 feature sets, for each of
2 pairs x 3 windows = 6 (pair, window) combinations -- 72 fits total, same
day-level train/test split (Phase 4) and same three models across every
feature set, per the brief's fairness requirement.

Two RULE-BASED baselines (no fitting, evaluated on the same test rows):
  - single_channel_rule: uses ONLY channel "a" (the SCD41 member of the
    pair) -- flags a fault if |a_value - a_roll_mean| / (1.4826*a_roll_mad)
    > 3 (same threshold convention as Phase 3's independent-channel
    detector). Represents "what if you trusted one sensor alone and looked
    for its own statistical anomalies" -- no redundancy exploited.
  - one_out_of_two_comparator: flags a fault if the pair's cross_diff_zscore
    (already computed in Phase 5 against the Phase 1 GLOBAL reference
    bias/MAD) exceeds 3 in absolute value -- exploits the redundant pair
    directly via disagreement, no ML.

All test-set predictions (not just summary metrics) are persisted so
Phase 7 can compute event-level/bootstrap/latency metrics without
refitting anything.
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase6"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase6_models.md"

PAIRS = ["temperature", "humidity"]
WINDOWS = [5, 10, 20]
RULE_THRESHOLD = 3.0
SEED = 42

FEATURE_SET_COLS = {
    "a_single_only": ["a_roll_mean", "a_roll_std", "a_roll_min", "a_roll_max", "a_roll_mad", "a_last_delta",
                       "b_roll_mean", "b_roll_std", "b_roll_min", "b_roll_max", "b_roll_mad", "b_last_delta"],
    "b_single_plus_cross": None,   # filled below
    "c_plus_ah": None,
    "d_cross_only": ["cross_diff", "cross_roll_diff_mean", "cross_roll_diff_std",
                      "cross_roll_corr", "cross_roll_corr_undefined", "cross_diff_zscore"],
}
CROSS_COLS = ["cross_diff", "cross_roll_diff_mean", "cross_roll_diff_std",
              "cross_roll_corr", "cross_roll_corr_undefined", "cross_diff_zscore"]
AH_COLS = ["ah_diff", "ah_roll_diff_mean", "ah_roll_diff_std",
           "ah_roll_corr", "ah_roll_corr_undefined", "ah_diff_zscore"]
FEATURE_SET_COLS["b_single_plus_cross"] = FEATURE_SET_COLS["a_single_only"] + CROSS_COLS
FEATURE_SET_COLS["c_plus_ah"] = FEATURE_SET_COLS["a_single_only"] + CROSS_COLS + AH_COLS

PRED_COLUMNS = ["ts", "day", "pair", "window", "feature_set", "method", "y", "y_pred", "y_score"]
PRED_COLUMNS_SQL = ["ts", "day", "pair", '"window"', "feature_set", "method", "y", "y_pred", "y_score"]

MODELS = {
    "logistic_regression": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=SEED)),
    "decision_tree": lambda: DecisionTreeClassifier(random_state=SEED, max_depth=12),
    "random_forest": lambda: RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=-1),
}


def main() -> None:
    con = duckdb.connect(str(DATA_DIR / "features.duckdb"), read_only=True)
    pred_out = duckdb.connect(str(DATA_DIR / "phase6_predictions.duckdb"))
    summary_rows = []
    timing_rows = []
    first_write = True

    for pair in PAIRS:
        for w in WINDOWS:
            df = con.execute(f"SELECT * FROM features_{pair}_w{w}").df()
            train = df[df.day_split == "train"].reset_index(drop=True)
            test = df[df.day_split == "test"].reset_index(drop=True)

            base_frame = test[["ts", "day", "y", "a_value", "b_value",
                                "cross_diff_zscore", "a_roll_mean", "a_roll_mad"]].copy()
            base_frame["pair"] = pair
            base_frame["window"] = w

            # --- rule baselines (test only, no fitting) ---
            single_z = (base_frame["a_value"] - base_frame["a_roll_mean"]).abs() / (1.4826 * base_frame["a_roll_mad"])
            single_pred = (single_z > RULE_THRESHOLD).astype(int)
            comparator_pred = (base_frame["cross_diff_zscore"].abs() > RULE_THRESHOLD).astype(int)

            for method_name, pred, proba in [
                ("baseline_single_channel_rule", single_pred, single_z),
                ("baseline_one_out_of_two_comparator", comparator_pred, base_frame["cross_diff_zscore"].abs()),
            ]:
                out = base_frame[["ts", "day", "pair", "window", "y"]].copy()
                out["feature_set"] = "n/a"
                out["method"] = method_name
                out["y_pred"] = pred.to_numpy()
                out["y_score"] = proba.to_numpy()
                out = out[PRED_COLUMNS]
                pred_out.register("out_tmp", out)
                if first_write:
                    pred_out.execute("CREATE TABLE predictions AS SELECT * FROM out_tmp")
                    first_write = False
                else:
                    pred_out.execute(f"INSERT INTO predictions ({','.join(PRED_COLUMNS_SQL)}) "
                                      f"SELECT {','.join(PRED_COLUMNS_SQL)} FROM out_tmp")
                f1 = f1_score(out["y"], out["y_pred"], average="macro")
                summary_rows.append({"pair": pair, "window": w, "feature_set": "n/a",
                                      "method": method_name, "n_test": len(out), "macro_f1": f1})

            # --- ML models, one per feature set ---
            for fs_name, cols in FEATURE_SET_COLS.items():
                X_train, y_train = train[cols], train["y"]
                X_test, y_test = test[cols], test["y"]
                for model_name, model_factory in MODELS.items():
                    clf = model_factory()
                    t0 = time.time()
                    clf.fit(X_train, y_train)
                    fit_s = time.time() - t0
                    t0 = time.time()
                    y_pred = clf.predict(X_test)
                    y_score = clf.predict_proba(X_test)[:, 1] if hasattr(clf, "predict_proba") else y_pred.astype(float)
                    predict_s = time.time() - t0

                    out = test[["ts", "day", "y"]].copy()
                    out["pair"] = pair
                    out["window"] = w
                    out["feature_set"] = fs_name
                    out["method"] = model_name
                    out["y_pred"] = y_pred
                    out["y_score"] = y_score
                    out = out[PRED_COLUMNS]
                    pred_out.register("out_tmp", out)
                    pred_out.execute(f"INSERT INTO predictions ({','.join(PRED_COLUMNS_SQL)}) "
                                      f"SELECT {','.join(PRED_COLUMNS_SQL)} FROM out_tmp")

                    f1 = f1_score(y_test, y_pred, average="macro")
                    summary_rows.append({"pair": pair, "window": w, "feature_set": fs_name,
                                          "method": model_name, "n_test": len(out), "macro_f1": f1})
                    timing_rows.append({"pair": pair, "window": w, "feature_set": fs_name,
                                         "method": model_name, "n_train": len(train),
                                         "fit_seconds": fit_s, "predict_seconds": predict_s})
                    print(f"{pair} w={w} {fs_name:20s} {model_name:20s} macro_f1={f1:.4f} "
                          f"fit={fit_s:.1f}s")

    con.close()
    pred_out.execute("CHECKPOINT")
    pred_out.close()

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(RESULTS_DIR / "model_summary_quicklook.csv", index=False)
    timing = pd.DataFrame(timing_rows)
    timing.to_csv(RESULTS_DIR / "fit_timing_raspberry_pi5.csv", index=False)

    lines = []
    lines.append("# CITI-2026 Phase 6 — Models & Baselines")
    lines.append("")
    lines.append(
        f"3 models (LogisticRegression, DecisionTree, RandomForest) x 4 feature sets x "
        f"2 pairs x 3 windows = {3*4*2*3} fits, plus 2 rule-based baselines x 2 pairs x 3 "
        f"windows = {2*2*3} baseline evaluations. Same day-level train/test split "
        f"(Phase 4, seed={SEED}) for every combination. All test-set predictions persisted "
        f"to `data/citi2026/phase6_predictions.duckdb` (`predictions` table) for Phase 7."
    )
    lines.append("")
    lines.append("**This is a quicklook (macro-F1 only) — full metrics, uncertainty, and the "
                  "explicit ceiling-comparison target check are Phase 7's job, not repeated here.**")
    lines.append("")
    def df_to_md_table(d: pd.DataFrame, index_label: str) -> list[str]:
        d = d.reset_index()
        header = "| " + " | ".join(str(c) for c in d.columns) + " |"
        sep = "|" + "|".join("---" for _ in d.columns) + "|"
        rows = ["| " + " | ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in row) + " |"
                for row in d.itertuples(index=False)]
        return [header, sep] + rows

    lines.append("## Quicklook: macro-F1 by pair / window / feature set / method")
    lines.append("")
    pivot = summary.pivot_table(index=["pair", "window", "method"], columns="feature_set", values="macro_f1")
    lines.extend(df_to_md_table(pivot.round(4), "pair/window/method"))
    lines.append("")
    lines.append("## Fit timing (Raspberry Pi 5 Model B Rev 1.0)")
    lines.append("")
    agg = timing.groupby("method").agg(mean_fit_s=("fit_seconds", "mean"), max_fit_s=("fit_seconds", "max"))
    lines.extend(df_to_md_table(agg.round(2), "method"))
    lines.append("")
    lines.append(f"Full per-combination timing: `research_results/citi2026/phase6/fit_timing_raspberry_pi5.csv`.")

    DOCS_OUT.write_text("\n".join(lines))
    print(f"\nDoc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
