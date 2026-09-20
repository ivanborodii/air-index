#!/usr/bin/env python3
"""CITI-2026 Phase 7 — metrics, uncertainty, window sensitivity, compute cost.

Reads Phase 6's persisted test-set predictions (no refitting). Computes,
per (pair, window, feature_set, method):

  - Macro-F1, balanced accuracy (row-level, standard sklearn).
  - Fault-detection recall: row-level recall restricted to truly-faulted
    rows (y=1).
  - False-event rate: among rows that are NOT a true fault (y=0) but ARE
    inside a Phase 3 weak-labelled real event, the fraction the method
    still predicts as a fault -- "real changes wrongly attributed to
    faults", read directly from the brief.
  - Event-level evaluation: matches each TRUE fault instance (Phase 4 log,
    test split, this pair's 2 channels) against the method's predictions
    within a +/-W-sample tolerance (a detector built on a W-sample causal
    window cannot possibly react before roughly W samples have elapsed,
    so a stricter zero-tolerance match would unfairly penalise every
    method by a fixed, mechanical amount unrelated to detection quality).
    Event-level recall = fraction of true instances with >=1 matching
    predicted-positive sample nearby.
  - Detection latency for gradual_shift specifically: samples from fault
    onset to the first predicted-positive sample within that instance's
    own window (undetected instances excluded from the latency average,
    counted separately as a miss rate).

Bootstrap 95% CIs use TWO different resampling units, disclosed
separately, not silently mixed:
  - fault-detection recall & event-level recall: resampled BY FAULT
    INSTANCE (the brief's literal instruction) -- these metrics are
    naturally defined over the set of instances.
  - macro-F1 & balanced accuracy: resampled BY WHOLE TEST DAY -- these
    metrics need both classes, and "day" is this project's existing,
    already-validated block unit (Phase 4's own split unit) for handling
    within-day autocorrelation; there is no equally natural "instance" unit
    for negative-class rows outside real/injected events.

Compute cost: Phase 6's own per-fit timing, named to the Raspberry Pi 5.

Explicit target check: does feature set (b) or (c) exceed the ~27%
gradual-shift recall ceiling given in the brief for single-channel
baselines? Reported against BOTH that external figure and this project's
own measured single-channel-rule baseline, so the comparison never rests
on the external number alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, f1_score, recall_score

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase7"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase7_metrics.md"

PAIR_CHANNELS = {
    "temperature": ["scd_temp_c", "bme_temp_c"],
    "humidity": ["scd_humidity_pct", "bme_humidity_pct"],
}
N_BOOTSTRAP = 1000
BOOT_SEED = 42
EXTERNAL_GRADUAL_SHIFT_CEILING = 0.27


def event_level_recall_and_matches(instances: pd.DataFrame, pred_df: pd.DataFrame, window: int) -> np.ndarray:
    """For each instance, True if >=1 predicted-positive sample in pred_df
    falls within [start_ts - W*30s, end_ts + W*30s]."""
    tol = pd.Timedelta(seconds=window * 30)
    pos_ts = pred_df.loc[pred_df["y_pred"] == 1, "ts"].to_numpy()
    pos_ts = np.sort(pos_ts)
    detected = np.zeros(len(instances), dtype=bool)
    for i, (_, inst) in enumerate(instances.iterrows()):
        lo = np.datetime64(inst["start_ts"] - tol)
        hi = np.datetime64(inst["end_ts"] + tol)
        lo_idx = np.searchsorted(pos_ts, lo, side="left")
        hi_idx = np.searchsorted(pos_ts, hi, side="right")
        detected[i] = hi_idx > lo_idx
    return detected


def gradual_shift_latency(instances: pd.DataFrame, pred_df: pd.DataFrame) -> tuple[list, int]:
    pred_sorted = pred_df.sort_values("ts")
    pos_ts = pred_sorted.loc[pred_sorted["y_pred"] == 1, "ts"].to_numpy()
    pos_ts = np.sort(pos_ts)
    latencies = []
    n_missed = 0
    for _, inst in instances.iterrows():
        start, end = np.datetime64(inst["start_ts"]), np.datetime64(inst["end_ts"])
        lo_idx = np.searchsorted(pos_ts, start, side="left")
        hi_idx = np.searchsorted(pos_ts, end, side="right")
        if hi_idx > lo_idx:
            first_detect = pos_ts[lo_idx]
            latency_s = (first_detect - start) / np.timedelta64(1, "s")
            latencies.append(latency_s)
        else:
            n_missed += 1
    return latencies, n_missed


def instance_row_counts(instances: pd.DataFrame, sub: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised, ONE-TIME (not per-bootstrap-iteration) per-instance
    (total_rows, tp_rows) via searchsorted on sub's sorted ts."""
    ts_sorted = np.sort(sub["ts"].to_numpy())
    y_pred_by_ts = sub.set_index("ts")["y_pred"].sort_index()
    total = np.zeros(len(instances), dtype=np.int64)
    tp = np.zeros(len(instances), dtype=np.int64)
    for i, (_, inst) in enumerate(instances.iterrows()):
        lo = np.searchsorted(ts_sorted, np.datetime64(inst["start_ts"]), side="left")
        hi = np.searchsorted(ts_sorted, np.datetime64(inst["end_ts"]), side="right")
        total[i] = hi - lo
        if hi > lo:
            window_ts = ts_sorted[lo:hi]
            tp[i] = int(y_pred_by_ts.reindex(window_ts).sum())
    return total, tp


def bootstrap_from_arrays(values_num: np.ndarray, values_den: np.ndarray, rng) -> tuple:
    """Generic instance-level bootstrap: resamples instance indices with
    replacement and recomputes sum(num)/sum(den) each time. Pass
    values_den=ones for a plain proportion (e.g. event-level recall)."""
    n = len(values_num)
    if n == 0:
        return float("nan"), float("nan")
    idx = np.arange(n)
    stats = np.empty(N_BOOTSTRAP)
    for b in range(N_BOOTSTRAP):
        sample_idx = rng.choice(idx, size=n, replace=True)
        den = values_den[sample_idx].sum()
        stats[b] = values_num[sample_idx].sum() / den if den > 0 else np.nan
    return float(np.nanpercentile(stats, 2.5)), float(np.nanpercentile(stats, 97.5))


def per_day_confusion_counts(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("day")
    return pd.DataFrame({
        "tp": g.apply(lambda d: int(((d["y"] == 1) & (d["y_pred"] == 1)).sum()), include_groups=False),
        "fn": g.apply(lambda d: int(((d["y"] == 1) & (d["y_pred"] == 0)).sum()), include_groups=False),
        "fp": g.apply(lambda d: int(((d["y"] == 0) & (d["y_pred"] == 1)).sum()), include_groups=False),
        "tn": g.apply(lambda d: int(((d["y"] == 0) & (d["y_pred"] == 0)).sum()), include_groups=False),
    })


def macro_f1_and_bal_acc_from_counts(tp, fn, fp, tn) -> tuple[float, float]:
    with np.errstate(divide="ignore", invalid="ignore"):
        r1 = tp / (tp + fn) if (tp + fn) > 0 else np.nan
        p1 = tp / (tp + fp) if (tp + fp) > 0 else np.nan
        f1_1 = 2 * p1 * r1 / (p1 + r1) if (p1 and r1 and (p1 + r1) > 0) else 0.0
        r0 = tn / (tn + fp) if (tn + fp) > 0 else np.nan
        p0 = tn / (tn + fn) if (tn + fn) > 0 else np.nan
        f1_0 = 2 * p0 * r0 / (p0 + r0) if (p0 and r0 and (p0 + r0) > 0) else 0.0
    macro_f1 = np.nanmean([f1_0, f1_1])
    bal_acc = np.nanmean([r0, r1])
    return macro_f1, bal_acc


def bootstrap_by_day_from_counts(counts: pd.DataFrame, rng) -> tuple:
    n_days = len(counts)
    if n_days == 0:
        return (np.nan, np.nan), (np.nan, np.nan)
    tp_a, fn_a, fp_a, tn_a = (counts["tp"].to_numpy(), counts["fn"].to_numpy(),
                              counts["fp"].to_numpy(), counts["tn"].to_numpy())
    idx = np.arange(n_days)
    f1_stats = np.empty(N_BOOTSTRAP)
    bal_stats = np.empty(N_BOOTSTRAP)
    for b in range(N_BOOTSTRAP):
        s = rng.choice(idx, size=n_days, replace=True)
        f1_stats[b], bal_stats[b] = macro_f1_and_bal_acc_from_counts(
            tp_a[s].sum(), fn_a[s].sum(), fp_a[s].sum(), tn_a[s].sum()
        )
    f1_ci = (float(np.nanpercentile(f1_stats, 2.5)), float(np.nanpercentile(f1_stats, 97.5)))
    bal_ci = (float(np.nanpercentile(bal_stats, 2.5)), float(np.nanpercentile(bal_stats, 97.5)))
    return f1_ci, bal_ci


def main() -> None:
    con = duckdb.connect(str(DATA_DIR / "phase6_predictions.duckdb"), read_only=True)
    preds = con.execute('SELECT * FROM predictions').df()
    con.close()
    # Normalise to tz-naive UTC (same instants) everywhere below: a tz-aware
    # pandas column's .to_numpy() returns an object array of Timestamps, and
    # np.datetime64() on a single tz-aware Timestamp silently drops its tz --
    # mixing the two raises "offset-naive vs offset-aware". Stripping tz once,
    # up front, on every timestamp column keeps all downstream comparisons on
    # plain vectorised datetime64[ns] arrays.
    preds["ts"] = pd.to_datetime(preds["ts"], utc=True).dt.tz_localize(None)

    fault_log = pd.read_csv(
        REPO_ROOT / "research_results" / "citi2026" / "phase4" / "fault_injection_log.csv",
        parse_dates=["start_ts", "end_ts"],
    )
    fault_log["start_ts"] = fault_log["start_ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    fault_log["end_ts"] = fault_log["end_ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    events = pd.read_csv(
        REPO_ROOT / "research_results" / "citi2026" / "phase3" / "event_intervals.csv",
        parse_dates=["start_ts", "end_ts"],
    )
    events["start_ts"] = events["start_ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    events["end_ts"] = events["end_ts"].dt.tz_convert("UTC").dt.tz_localize(None)

    rng = np.random.default_rng(BOOT_SEED)
    combos = preds[["pair", "window", "feature_set", "method"]].drop_duplicates()

    def in_any_real_event(ts_array: np.ndarray) -> np.ndarray:
        flags = np.zeros(len(ts_array), dtype=bool)
        for _, ev in events.iterrows():
            flags |= (ts_array >= np.datetime64(ev["start_ts"])) & (ts_array <= np.datetime64(ev["end_ts"]))
        return flags

    rows = []
    for _, combo in combos.iterrows():
        pair, window, fs, method = combo["pair"], combo["window"], combo["feature_set"], combo["method"]
        sub = preds[(preds.pair == pair) & (preds.window == window) &
                    (preds.feature_set == fs) & (preds.method == method)].copy()

        macro_f1 = f1_score(sub["y"], sub["y_pred"], average="macro")
        bal_acc = balanced_accuracy_score(sub["y"], sub["y_pred"])
        fault_recall = recall_score(sub["y"], sub["y_pred"], pos_label=1, zero_division=0)

        real_event_mask = in_any_real_event(sub["ts"].to_numpy())
        neg_in_event = sub[(sub["y"] == 0) & real_event_mask]
        false_event_rate = float(neg_in_event["y_pred"].mean()) if len(neg_in_event) else float("nan")

        channels = PAIR_CHANNELS[pair]
        instances = fault_log[(fault_log.channel.isin(channels)) & (fault_log.split == "test")]
        detected = event_level_recall_and_matches(instances, sub, window)
        event_level_recall = float(detected.mean()) if len(detected) else float("nan")

        gs_instances = instances[instances.fault_type == "gradual_shift"]
        latencies, n_missed = gradual_shift_latency(gs_instances, sub)
        gs_recall = (len(gs_instances) - n_missed) / len(gs_instances) if len(gs_instances) else float("nan")

        # --- bootstrap CIs (resampled BY FAULT INSTANCE, using arrays
        # precomputed ONCE above -- NOT recomputed on every one of the
        # 1000 resamples, which would be far too slow on an RPi5) ---
        if len(instances):
            total_rows_arr, tp_rows_arr = instance_row_counts(instances, sub)
            recall_ci = bootstrap_from_arrays(tp_rows_arr, total_rows_arr, rng)
            event_recall_ci = bootstrap_from_arrays(detected.astype(int), np.ones(len(detected)), rng)
        else:
            recall_ci = event_recall_ci = (np.nan, np.nan)

        day_counts = per_day_confusion_counts(sub)
        f1_ci, bal_acc_ci = bootstrap_by_day_from_counts(day_counts, rng)

        rows.append({
            "pair": pair, "window": window, "feature_set": fs, "method": method,
            "n_test": len(sub), "macro_f1": macro_f1, "macro_f1_ci_lo": f1_ci[0], "macro_f1_ci_hi": f1_ci[1],
            "balanced_accuracy": bal_acc, "balanced_accuracy_ci_lo": bal_acc_ci[0], "balanced_accuracy_ci_hi": bal_acc_ci[1],
            "fault_detection_recall": fault_recall, "fault_recall_ci_lo": recall_ci[0], "fault_recall_ci_hi": recall_ci[1],
            "false_event_rate": false_event_rate,
            "event_level_recall": event_level_recall, "event_recall_ci_lo": event_recall_ci[0], "event_recall_ci_hi": event_recall_ci[1],
            "n_true_instances_test": len(instances),
            "gradual_shift_recall": gs_recall, "n_gradual_shift_instances": len(gs_instances),
            "gradual_shift_median_latency_s": float(np.median(latencies)) if latencies else float("nan"),
            "gradual_shift_n_missed": n_missed,
        })
        print(f"{pair} w={window} {fs:20s} {method:32s} f1={macro_f1:.3f} "
              f"fault_recall={fault_recall:.3f} event_recall={event_level_recall:.3f} "
              f"gs_recall={gs_recall if gs_recall==gs_recall else float('nan'):.3f}")

    results = pd.DataFrame(rows)
    results.to_csv(RESULTS_DIR / "full_metrics.csv", index=False)

    timing = pd.read_csv(REPO_ROOT / "research_results" / "citi2026" / "phase6" / "fit_timing_raspberry_pi5.csv")

    # --- explicit target check ---
    baseline_gs = results[results.method == "baseline_single_channel_rule"]
    own_ceiling = float(baseline_gs["gradual_shift_recall"].mean()) if len(baseline_gs) else float("nan")
    bc_rows = results[(results.feature_set.isin(["b_single_plus_cross", "c_plus_ah"])) &
                       (results.method.isin(["logistic_regression", "decision_tree", "random_forest"]))]
    exceeds_external = bc_rows[bc_rows.gradual_shift_recall > EXTERNAL_GRADUAL_SHIFT_CEILING]
    exceeds_own = bc_rows[bc_rows.gradual_shift_recall > own_ceiling]

    lines = []
    lines.append("# CITI-2026 Phase 7 — Metrics, Uncertainty, Window Sensitivity, Compute Cost")
    lines.append("")
    lines.append(f"Bootstrap: {N_BOOTSTRAP} resamples, seed={BOOT_SEED}. Recall/event-level metrics "
                  "resampled BY FAULT INSTANCE; macro-F1/balanced-accuracy resampled BY WHOLE TEST DAY "
                  "(disclosed as two different, deliberately chosen resampling units — see script docstring).")
    lines.append("")
    lines.append("## Full results")
    lines.append("")
    lines.append("Full table (all pairs/windows/feature sets/methods, every metric + CI): "
                  "`research_results/citi2026/phase7/full_metrics.csv`.")
    lines.append("")

    lines.append("## Window-size sensitivity (macro-F1, random_forest, feature set c)")
    lines.append("")
    sens = results[(results.method == "random_forest") & (results.feature_set == "c_plus_ah")]
    lines.append("| pair | window | macro F1 | 95% CI | fault recall | event recall |")
    lines.append("|---|---:|---:|---|---:|---:|")
    for _, r in sens.sort_values(["pair", "window"]).iterrows():
        lines.append(f"| {r['pair']} | {r['window']} | {r['macro_f1']:.4f} | "
                      f"[{r['macro_f1_ci_lo']:.4f}, {r['macro_f1_ci_hi']:.4f}] | "
                      f"{r['fault_detection_recall']:.4f} | {r['event_level_recall']:.4f} |")
    lines.append("")

    lines.append("## Explicit target check: gradual-shift recall vs. the ~27% single-channel ceiling")
    lines.append("")
    lines.append(f"- External reference ceiling (given in the brief): **{EXTERNAL_GRADUAL_SHIFT_CEILING:.0%}**")
    lines.append(f"- This project's OWN measured single-channel-rule baseline gradual-shift recall "
                  f"(mean across pairs/windows): **{own_ceiling:.1%}**")
    lines.append(f"- Feature-set (b)/(c) model x pair x window combinations exceeding the EXTERNAL "
                  f"27% figure: **{len(exceeds_external)} / {len(bc_rows)}**")
    lines.append(f"- Feature-set (b)/(c) model x pair x window combinations exceeding THIS project's "
                  f"OWN single-channel baseline: **{len(exceeds_own)} / {len(bc_rows)}**")
    lines.append("")
    if len(exceeds_own) < len(bc_rows):
        lines.append(
            "**Not a universal win, stated plainly**: not every (b)/(c) combination beats even this "
            "project's own single-channel baseline on gradual-shift recall — see "
            "`full_metrics.csv` for exactly which combinations do and don't, rather than only "
            "reporting the favourable aggregate."
        )
    lines.append("")

    lines.append("## Compute cost (Raspberry Pi 5 Model B Rev 1.0)")
    lines.append("")
    agg = timing.groupby("method").agg(mean_fit_s=("fit_seconds", "mean"), max_fit_s=("fit_seconds", "max"),
                                        mean_predict_s=("predict_seconds", "mean"))
    lines.append("| method | mean fit (s) | max fit (s) | mean predict (s) |")
    lines.append("|---|---:|---:|---:|")
    for method, r in agg.iterrows():
        lines.append(f"| {method} | {r['mean_fit_s']:.2f} | {r['max_fit_s']:.2f} | {r['mean_predict_s']:.4f} |")
    lines.append("")
    lines.append("All timings measured directly on the deployment device (Raspberry Pi 5 Model B Rev 1.0) — "
                  "not a development machine.")
    lines.append("")

    lines.append("## False-event rate (real changes wrongly attributed to faults)")
    lines.append("")
    fer = results.groupby("method")["false_event_rate"].mean().sort_values()
    lines.append("| method | mean false-event rate across all pair/window/feature-set combos |")
    lines.append("|---|---:|")
    for method, v in fer.items():
        lines.append(f"| {method} | {v:.4f} |")
    lines.append("")

    DOCS_OUT.write_text("\n".join(lines))
    print(f"\nDoc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
