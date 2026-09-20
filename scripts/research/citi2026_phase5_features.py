#!/usr/bin/env python3
"""CITI-2026 Phase 5 — causal feature sets, built per redundant pair.

Classification target is defined at the PAIR level (temperature pair,
humidity pair): y(t) = 1 if EITHER channel of the pair has an active
injected fault at t (Phase 4's `<channel>_fault_active` OR'd together).
This matches the paper's own mechanism -- you have two sensors and want to
know if the pair disagrees because of a fault -- and keeps Phase 6/7's
"one-out-of-two comparator" baseline meaningful (it inherently operates on
pairs, not lone channels).

All features are CAUSAL (trailing window [t-W+1, t], pandas' `.rolling()`
default alignment, no `center=True` anywhere) and computed separately
PER DAY (never bridging a day boundary or the excluded Sep13/14 gap) --
the first W-1 (single-channel) or up to 2W-2 (two-pass MAD) rows of each
day are necessarily NaN and dropped, disclosed as a small, expected
"warm-up" loss, not silently imputed.

Four feature sets (nested, per the brief):
  (a) single-channel only:  per-channel rolling {mean, std, min, max,
      last_delta, MAD} x 2 channels = 12 features.
  (b) (a) + cross-channel:  + {diff, rolling diff mean, rolling diff std,
      diff z-score vs the Phase 1 GLOBAL reference bias/MAD, rolling
      correlation, and a boolean flag for when correlation is undefined --
      zero variance in-window, e.g. inside a stuck_value fault} = 18 features.
  (c) (b) + absolute-humidity concordance: + {AH diff (from each module's
      OWN currently-faulted T & RH), rolling AH diff mean/std, AH diff
      z-score vs the Phase 2 GLOBAL reference, same undefined-correlation flag} = 24 features. Applies to
      BOTH pairs (not just humidity) -- AH is a joint function of T and
      RH, so a fault in either channel of either module corrupts its own
      module's AH, which is exactly the signal being added here.
  (d) cross-channel only: the same 6 cross features as (b), WITHOUT (a)'s
      per-channel features -- tests whether cross-channel comparison alone
      (no view of a channel's own shape) is sufficient.

Windows: 5, 10, 20 samples (2.5/5/10 min). Reads Phase 4's
`observations_injected` table (the faulted signal, day_split, ground
truth) plus Phase 1/2's overall-stats CSVs (frozen reference constants,
not recomputed per window).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase5"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase5_features.md"

WINDOWS = [5, 10, 20]

PAIRS = {
    "temperature": ("scd_temp_c", "bme_temp_c"),
    "humidity": ("scd_humidity_pct", "bme_humidity_pct"),
}

FEATURE_SETS = {
    "a_single_only": ["single_a", "single_b"],
    "b_single_plus_cross": ["single_a", "single_b", "cross"],
    "c_plus_ah": ["single_a", "single_b", "cross", "ah_cross"],
    "d_cross_only": ["cross"],
}


def per_channel_features(x: pd.Series, day: pd.Series, w: int, suffix: str) -> pd.DataFrame:
    out = {}
    roll_mean, roll_std, roll_min, roll_max, roll_mad, last_delta = [], [], [], [], [], []
    for _, g in x.groupby(day):
        r = g.rolling(w, min_periods=w)
        roll_mean.append(r.mean())
        roll_std.append(r.std())
        roll_min.append(r.min())
        roll_max.append(r.max())
        med = r.median()
        abs_dev = (g - med).abs()
        roll_mad.append(abs_dev.rolling(w, min_periods=w).median())
        last_delta.append(g.diff())
    out[f"{suffix}_roll_mean"] = pd.concat(roll_mean).sort_index()
    out[f"{suffix}_roll_std"] = pd.concat(roll_std).sort_index()
    out[f"{suffix}_roll_min"] = pd.concat(roll_min).sort_index()
    out[f"{suffix}_roll_max"] = pd.concat(roll_max).sort_index()
    out[f"{suffix}_roll_mad"] = pd.concat(roll_mad).sort_index()
    out[f"{suffix}_last_delta"] = pd.concat(last_delta).sort_index()
    return pd.DataFrame(out)


def cross_features(a: pd.Series, b: pd.Series, day: pd.Series, w: int, ref_bias: float, ref_mad: float, prefix: str) -> pd.DataFrame:
    diff = a - b
    out = {f"{prefix}_diff": diff}
    roll_mean, roll_std, roll_corr, corr_undefined = [], [], [], []
    for (_, ga), (_, gb) in zip(a.groupby(day), b.groupby(day)):
        gd = ga - gb
        roll_mean.append(gd.rolling(w, min_periods=w).mean())
        roll_std.append(gd.rolling(w, min_periods=w).std())
        std_a = ga.rolling(w, min_periods=w).std()
        std_b = gb.rolling(w, min_periods=w).std()
        corr = ga.rolling(w, min_periods=w).corr(gb)
        # A zero-variance window (e.g. inside a stuck_value fault -- exactly
        # the rows most important to KEEP for detecting that fault type)
        # makes Pearson correlation mathematically undefined (0/0), which
        # pandas/floating-point sometimes renders as inf rather than NaN
        # (caught empirically: RandomForest rejected the first feature
        # build with "Input X contains infinity"). Treated as "no
        # detectable linear relationship" (corr=0), NOT dropped -- dropping
        # would silently delete the stuck_value positive-class rows this
        # benchmark exists to evaluate. Genuine warm-up (std itself still
        # NaN, insufficient window yet) is left NaN, same as every other
        # feature, and dropped downstream like any other warm-up row.
        undefined = ((std_a == 0) | (std_b == 0)) & std_a.notna() & std_b.notna()
        corr = corr.where(~undefined, 0.0)
        roll_corr.append(corr)
        corr_undefined.append(undefined)
    out[f"{prefix}_roll_diff_mean"] = pd.concat(roll_mean).sort_index()
    out[f"{prefix}_roll_diff_std"] = pd.concat(roll_std).sort_index()
    out[f"{prefix}_roll_corr"] = pd.concat(roll_corr).sort_index()
    out[f"{prefix}_roll_corr_undefined"] = pd.concat(corr_undefined).sort_index()
    denom = ref_mad if ref_mad > 0 else 1.0
    out[f"{prefix}_diff_zscore"] = (diff - ref_bias) / denom
    return pd.DataFrame(out)


def main() -> None:
    con = duckdb.connect(str(DATA_DIR / "injected_dataset.duckdb"), read_only=True)
    df = con.execute("SELECT * FROM observations_injected ORDER BY ts").df()
    con.close()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    phase1 = pd.read_csv(REPO_ROOT / "research_results" / "citi2026" / "phase1" / "pair_characterisation_overall.csv")
    phase2 = pd.read_csv(REPO_ROOT / "research_results" / "citi2026" / "phase2" / "rh_vs_ah_concordance.csv")
    ref = {
        "temperature": (phase1.loc[phase1.pair == "temperature", "bias_mean"].iloc[0],
                         phase1.loc[phase1.pair == "temperature", "mad_of_diff"].iloc[0]),
        "humidity": (phase1.loc[phase1.pair == "humidity", "bias_mean"].iloc[0],
                      phase1.loc[phase1.pair == "humidity", "mad_of_diff"].iloc[0]),
        "ah": (phase2.loc[phase2.basis == "absolute_humidity_gm3", "bias_mean"].iloc[0],
               phase2.loc[phase2.basis == "absolute_humidity_gm3", "mad_of_diff"].iloc[0]),
    }

    # AH computed from each module's OWN currently-faulted T and RH (same
    # formula as Phase 2), so a fault in either channel corrupts its
    # module's AH -- exactly the signal feature set (c) needs.
    def ah(t, rh):
        es = 6.112 * np.exp(17.62 * t / (243.12 + t))
        e = es * rh / 100.0
        return 216.7 * e / (t + 273.15)

    df["scd_ah_faulted"] = ah(df["scd_temp_c_faulted"], df["scd_humidity_pct_faulted"])
    df["bme_ah_faulted"] = ah(df["bme_temp_c_faulted"], df["bme_humidity_pct_faulted"])

    manifest_rows = []
    feat_out = duckdb.connect(str(DATA_DIR / "features.duckdb"))

    for pair_name, (ch_a, ch_b) in PAIRS.items():
        a_col, b_col = f"{ch_a}_faulted", f"{ch_b}_faulted"
        y = (df[f"{ch_a}_fault_active"] | df[f"{ch_b}_fault_active"]).astype(int)
        ref_bias, ref_mad = ref[pair_name]
        ah_bias, ah_mad = ref["ah"]

        for w in WINDOWS:
            single_a = per_channel_features(df[a_col], df["day"], w, "a")
            single_b = per_channel_features(df[b_col], df["day"], w, "b")
            cross = cross_features(df[a_col], df[b_col], df["day"], w, ref_bias, ref_mad, "cross")
            ah_cross = cross_features(df["scd_ah_faulted"], df["bme_ah_faulted"], df["day"], w, ah_bias, ah_mad, "ah")

            feat_df = pd.concat([single_a, single_b, cross, ah_cross], axis=1)
            feat_df["a_value"] = df[a_col]
            feat_df["b_value"] = df[b_col]
            feat_df["y"] = y
            feat_df["day"] = df["day"]
            feat_df["day_split"] = df["day_split"]
            feat_df["ts"] = df["ts"]

            n_before = len(feat_df)
            # rolling correlation over a zero-variance window (e.g. inside a
            # stuck_value fault, or a genuinely flat real reading) divides
            # by zero and yields +/-inf rather than NaN in pandas -- caught
            # empirically when RandomForest rejected the first feature
            # build with "Input X contains infinity". Treat inf the same
            # as NaN: warm-up-style row drop, not a silent fill.
            feat_df = feat_df.replace([np.inf, -np.inf], np.nan)
            feat_df = feat_df.dropna().reset_index(drop=True)
            n_after = len(feat_df)

            table_name = f"features_{pair_name}_w{w}"
            feat_out.register("feat_df_tmp", feat_df)
            feat_out.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM feat_df_tmp")

            manifest_rows.append({
                "pair": pair_name, "window": w, "n_rows_before_dropna": n_before,
                "n_rows_after_dropna": n_after, "n_dropped_warmup": n_before - n_after,
                "positive_rate": float(feat_df["y"].mean()), "n_features_full": feat_df.shape[1] - 6,
                "table": table_name,
            })
            print(f"{pair_name} w={w}: {n_after:,} rows after warm-up drop "
                  f"({n_before - n_after} dropped), positive rate={feat_df['y'].mean():.4f}")

    feat_out.execute("CHECKPOINT")
    feat_out.close()

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(RESULTS_DIR / "feature_build_manifest.csv", index=False)

    feature_set_cols = {
        name: {"single_a": [c for c in ["a_roll_mean","a_roll_std","a_roll_min","a_roll_max","a_roll_mad","a_last_delta"]],
               "single_b": [c for c in ["b_roll_mean","b_roll_std","b_roll_min","b_roll_max","b_roll_mad","b_last_delta"]],
               "cross": [c for c in ["cross_diff","cross_roll_diff_mean","cross_roll_diff_std","cross_roll_corr","cross_roll_corr_undefined","cross_diff_zscore"]],
               "ah_cross": [c for c in ["ah_diff","ah_roll_diff_mean","ah_roll_diff_std","ah_roll_corr","ah_roll_corr_undefined","ah_diff_zscore"]]}
        for name in FEATURE_SETS
    }
    import json
    with open(RESULTS_DIR / "feature_set_definitions.json", "w") as f:
        json.dump({name: {k: feature_set_cols[name][k] for k in parts} for name, parts in FEATURE_SETS.items()}, f, indent=2)

    lines = []
    lines.append("# CITI-2026 Phase 5 — Causal Feature Sets")
    lines.append("")
    lines.append("Target: pair-level fault presence, y(t) = OR of both channels' Phase 4 ground-truth "
                  "fault-active flags. All features causal (trailing window, per-day, never bridging a "
                  "day boundary).")
    lines.append("")
    lines.append("## Build manifest")
    lines.append("")
    lines.append("| pair | window | rows (after warm-up drop) | dropped (warm-up) | positive rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, r in manifest.iterrows():
        lines.append(f"| {r['pair']} | {r['window']} | {r['n_rows_after_dropna']:,} | "
                      f"{r['n_dropped_warmup']:,} | {r['positive_rate']:.4f} |")
    lines.append("")
    lines.append("## Feature sets")
    lines.append("")
    lines.append("- **(a) single-channel only**: 12 features (6 rolling stats x 2 channels)")
    lines.append("- **(b) single + cross-channel**: (a) + 6 cross features = 18")
    lines.append("- **(c) + absolute-humidity concordance**: (b) + 6 AH-cross features = 24 "
                  "(applies to BOTH pairs, not just humidity -- AH is a joint function of T and RH)")
    lines.append("- **(d) cross-channel only**: the 6 cross features alone")
    lines.append("")
    lines.append("Exact column lists: `research_results/citi2026/phase5/feature_set_definitions.json`. "
                  "Per-(pair,window) tables in `data/citi2026/features.duckdb` "
                  "(`features_<pair>_w<W>`, gitignored, rebuildable from this script).")

    DOCS_OUT.write_text("\n".join(lines))
    print(f"\nDoc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
