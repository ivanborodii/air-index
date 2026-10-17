"""Stage 07: training and forecasting (task section 8).

Work unit = (scheme, fold, h, method, target). Targets:
  reg_I        approach (a), regression of I(t+h)            -- formula (10)
  clf_I        approach (a), classification of class(t+h)    -- formula (10)
  ind_<x>      approach (b), regression of indicator x(t+h)  -- formula (11)
Every unit writes its predictions + a JSON record (incl. resource use of
tuning, final fit and test prediction); finished units are skipped on
restart. Training-row fraction and tuning subsample: protocol.yaml.

Usage: s07_forecast.py [--scheme S1|S2] [--h 1 3 6] [--methods ...]
"""

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

from common import HORIZONS_FORECAST, SEED, WORK, main_config, results_dir, stage_timer
from iaq_index.config import INDICATORS
from iaq_index.scores import class_from_score
from models import (METHODS, ResourceMonitor, fit_model, grid, inner_splits_s1, inner_splits_s2, predict, split_masks,
                    subsample_train, tune)

PRED_DIR = WORK / "preds"
MODEL_DIR = WORK / "models"
PROTOCOL = yaml.safe_load((Path(__file__).with_name("protocol.yaml")).read_text())
N_GROUPS = 5


def homes_groups(homes: list[str]) -> list[list[str]]:
    p = results_dir() / "groups.json"
    if p.exists():
        return json.loads(p.read_text())["groups"]
    rng = np.random.default_rng(SEED)
    groups = [sorted(g.tolist()) for g in np.array_split(rng.permutation(sorted(homes)), N_GROUPS)]
    p.write_text(json.dumps({"seed": SEED, "n_groups": N_GROUPS, "groups": groups}, indent=2))
    return groups


def folds(scheme: str, homes: list[str]):
    if scheme == "S1":
        return [(0, homes, homes)]
    groups = homes_groups(homes)
    return [(i, sorted(set(homes) - set(g)), g) for i, g in enumerate(groups)]


def targets() -> list[tuple[str, str, str]]:
    """(target name, task, source column prefix)."""
    return [("reg_I", "reg", "I"), ("clf_I", "clf", "I")] + [(f"ind_{x}", "reg", x) for x in INDICATORS]


def run_unit(scheme, fold, h, method, tname, task, src, df, fcols, tr, te, log, save_model):
    tag = f"{scheme}_f{fold}_h{h}_{method}_{tname}"
    out_pred, out_meta = PRED_DIR / f"{tag}.parquet", PRED_DIR / f"{tag}.json"
    if out_meta.exists():
        return
    ycol = f"{src}__h{h}"
    y_all = df[ycol].to_numpy(dtype=float)
    if task == "clf":
        y_all = class_from_score(y_all)
    X = df[fcols].to_numpy(dtype=np.float32)
    Xtr, ytr = X[tr], y_all[tr]
    if task == "clf":
        ytr = ytr.astype(int)
    clip = (0.0, 100.0) if src == "I" else None
    tr_df = df.loc[tr, ["home", "time"]].reset_index(drop=True)
    splits = inner_splits_s1(tr_df["time"].to_numpy()) if scheme == "S1" else inner_splits_s2(tr_df, h)
    frac = PROTOCOL["tuning_subsample"]

    with ResourceMonitor() as mon_tune:
        best, table = tune(method, task, Xtr, ytr, splits, clip, subsample=frac)
    with ResourceMonitor() as mon_fit:
        est = fit_model(method, task, best, Xtr, ytr)
    Xte = X[te]
    with ResourceMonitor() as mon_pred:
        pred = predict(est, task, Xte, clip)
    t_tune, t_fit = mon_tune.wall_seconds, mon_fit.wall_seconds
    model_bytes = None
    if save_model:
        MODEL_DIR.mkdir(exist_ok=True)
        mp = MODEL_DIR / f"{tag}.joblib"
        joblib.dump(est, mp)
        model_bytes = mp.stat().st_size
    pd.DataFrame({"home": df.loc[te, "home"].to_numpy(), "time": df.loc[te, "time"].to_numpy(),
                  "y_true": y_all[te], "y_pred": pred}).to_parquet(out_pred, index=False)
    meta = {"scheme": scheme, "fold": fold, "h": h, "method": method, "target": tname, "task": task,
            "n_train": int(tr.sum()), "n_test": int(te.sum()), "search_space": repr(grid(method, task)),
            "cv_scores": table.to_dict("records"), "best_params": repr(best),
            "train_fraction": PROTOCOL["train_fraction"], "tuning_subsample": frac,
            "tuning_seconds": round(t_tune, 2), "final_fit_seconds": round(t_fit, 2),
            "test_predict_seconds": round(mon_pred.wall_seconds, 3),
            "test_predict_us_per_row": round(1e6 * mon_pred.wall_seconds / max(1, len(Xte)), 3),
            **mon_tune.record("tune"), **mon_fit.record("fit"), **mon_pred.record("predict"),
            "model_bytes": model_bytes, "finished": time.strftime("%Y-%m-%d %H:%M:%S")}
    out_meta.write_text(json.dumps(meta, indent=2))
    log.info("%s best=%s tune=%.0fs fit=%.0fs n_train=%d n_test=%d", tag, best, t_tune, t_fit, tr.sum(), te.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", nargs="*", default=["S1", "S2"])
    ap.add_argument("--h", nargs="*", type=int, default=list(HORIZONS_FORECAST))
    ap.add_argument("--methods", nargs="*", default=METHODS)
    ap.add_argument("--targets", nargs="*", default=None)
    args = ap.parse_args()
    PRED_DIR.mkdir(exist_ok=True)
    with stage_timer("s07_forecast") as log:
        cfg = main_config()
        info = json.loads((WORK / "features_info.json").read_text())
        fcols = info["feature_columns"]
        feats = pd.read_parquet(WORK / "features.parquet")
        allh = pd.read_parquet(WORK / "hourly_index_all.parquet", columns=["home", "time"])
        span = allh.groupby("home")["time"].agg(["min", "max"])
        span["cut"] = span["min"] + 0.75 * (span["max"] - span["min"])
        span.to_csv(WORK / "time_cuts.csv")
        homes = sorted(span.index)
        for scheme in args.scheme:
            for h in args.h:
                # samples need I at t (features) and at t+h; test also needs I(t+h-24)
                # so every method and both naive baselines share one test set
                df = feats[feats[f"I__h{h}"].notna()].reset_index(drop=True)
                for fold, h_train, h_test in folds(scheme, homes):
                    tr, te = split_masks(df, h_train, h_test, span, h)
                    tr = subsample_train(df, tr, PROTOCOL["train_fraction"])
                    te &= df[f"I__h{h}_lag24"].notna().to_numpy()
                    for method in args.methods:
                        for tname, task, src in targets():
                            if args.targets and tname not in args.targets:
                                continue
                            run_unit(scheme, fold, h, method, tname, task, src, df, fcols, tr, te, log,
                                     save_model=(scheme == "S1"))


if __name__ == "__main__":
    main()
