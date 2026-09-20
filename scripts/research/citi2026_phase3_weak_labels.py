#!/usr/bin/env python3
"""CITI-2026 Phase 3 — weak event labels from independent channels only.

Independent channels used: CO2, PM2.5, PM10, pressure. `gas_resistance_ohm`
is excluded per the Phase 0 resolution (11.2% coverage, unusable). Nothing
here reads scd_temp_c/bme_temp_c/scd_humidity_pct/bme_humidity_pct or their
derived absolute-humidity columns — this is the whole point: labels for
"a real microclimate event happened" must come from channels that are NOT
the ones later phases test for faults, or the benchmark would be circular.

Method (a robust local-outlier detector in the same generalised-Hampel-
filter family already used and cited in the sibling iaq_hfis project —
Pearson/Neuvo/Astola/Gabbouj, "Generalized Hampel Filters"):

  1. Per day (never across a day boundary or a large gap), per channel:
     rolling median (centered window W) as the local baseline, then rolling
     MAD (median of |x - rolling_median|, same window) as the local scale
     -- the standard two-pass approximation to a rolling MAD, not an exact
     per-window recomputation (documented, not silently assumed).
  2. Robust deviation score = |x - median| / (1.4826 * MAD), the usual
     Hampel-identifier normalisation (1.4826 makes MAD a consistent
     estimator of sigma for a Gaussian).
  3. A sample is a CANDIDATE if score > THRESHOLD (literature-typical
     default 3.0, same status as the sibling project's undecided Hampel
     parameters -- provisional, disclosed, not tuned against anything here).
  4. A candidate run becomes a real EVENT only once it has persisted for
     >= MIN_PERSISTENCE_SAMPLES consecutive samples -- filters single-
     sample noise/transients, keeping only SUSTAINED deviations (a
     deliberate choice: this paper's synthetic faults injected later
     include short spikes, so weak labels of "real change" are defined to
     be the sustained kind, disclosed as a design decision, not hidden).
  5. A sample is a weak-labelled event if ANY independent channel has an
     active event at that time. Contiguous positive samples are grouped
     into event intervals with the triggering channel(s) and peak score.

Rows already flagged `hardcheck_fail_<channel>` (Phase 0) are treated as
missing for THIS channel's baseline/detection (never allowed to seed or
count as an event, never allowed to corrupt the local baseline) -- a known
sensor-range violation is not a "real microclimate event" by definition.
"""

from __future__ import annotations

import glob
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase3"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase3_weak_labels.md"

INDEPENDENT_CHANNELS = ["co2_ppm", "mass_pm2_5", "mass_pm10", "pressure_hpa"]
# 241 samples = ~120 min, centered. Chosen empirically, not from a
# literature default: an initial 21-sample (~10.5 min) window was tried
# first and rejected -- it made every detected "event" only 2-5.5 min long
# (max, over 415 events), because a centered median/MAD baseline with a
# window comparable to real event duration ADAPTS INTO the event as it
# progresses, so only the rising edge clears the threshold. A real cooking/
# ventilation event lasting up to ~30-50 min stays a MINORITY (<=~25%) of a
# 120-min window, so the median stays anchored to the true background and
# the whole sustained event clears threshold, not just its edge.
ROLL_WINDOW = 241
MIN_PERIODS = ROLL_WINDOW // 2 + 1
SCORE_THRESHOLD = 3.0         # literature-typical Hampel default; provisional
MIN_PERSISTENCE_SAMPLES = 4   # 2 min: sustained, not a transient blip


def robust_deviation_score(x: pd.Series) -> pd.Series:
    roll_med = x.rolling(ROLL_WINDOW, center=True, min_periods=MIN_PERIODS).median()
    abs_dev = (x - roll_med).abs()
    roll_mad = abs_dev.rolling(ROLL_WINDOW, center=True, min_periods=MIN_PERIODS).median()
    scale = 1.4826 * roll_mad
    with np.errstate(divide="ignore", invalid="ignore"):
        score = abs_dev / scale
    return score.where(scale > 0)


def sustained_runs(flag: pd.Series, min_len: int) -> pd.Series:
    """Keep only True-runs of length >= min_len; shorter runs become False."""
    grp = (flag != flag.shift()).cumsum()
    run_len = flag.groupby(grp).transform("size")
    return flag & (run_len >= min_len)


def find_latest_analysis_dataset() -> Path:
    candidates = sorted(glob.glob(str(DATA_DIR / "analysis_dataset_*.duckdb")))
    if not candidates:
        raise SystemExit("No Phase 0 analysis dataset found.")
    return Path(candidates[-1])


def main() -> None:
    ds_path = find_latest_analysis_dataset()
    con = duckdb.connect(str(ds_path), read_only=True)
    cols = ["ts"] + INDEPENDENT_CHANNELS + [f"hardcheck_fail_{c}" for c in INDEPENDENT_CHANNELS]
    df = con.execute(f"SELECT {', '.join(cols)} FROM raw_observations_analysis ORDER BY ts").df()
    con.close()

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["day"] = df["ts"].dt.tz_convert("Europe/Kyiv").dt.date

    event_col_per_channel = {}
    score_col_per_channel = {}

    for channel in INDEPENDENT_CHANNELS:
        flag_col = f"hardcheck_fail_{channel}"
        masked = df[channel].where(~df[flag_col])

        scores = []
        candidates = []
        for _, day_df in df.assign(_masked=masked).groupby("day", sort=True):
            s = robust_deviation_score(day_df["_masked"])
            scores.append(s)
            candidates.append(s > SCORE_THRESHOLD)
        score_series = pd.concat(scores).sort_index()
        candidate_series = pd.concat(candidates).sort_index().fillna(False)

        # persistence, computed per-day (never bridges a day boundary)
        event_series = pd.Series(False, index=df.index)
        for day, day_idx in df.groupby("day", sort=True).groups.items():
            event_series.loc[day_idx] = sustained_runs(candidate_series.loc[day_idx], MIN_PERSISTENCE_SAMPLES)

        event_col_per_channel[channel] = event_series
        score_col_per_channel[channel] = score_series

    events_df = pd.DataFrame(event_col_per_channel)
    scores_df = pd.DataFrame(score_col_per_channel)

    df["any_independent_event"] = events_df.any(axis=1)
    df["triggering_channels"] = events_df.apply(
        lambda row: ",".join([c for c in INDEPENDENT_CHANNELS if row[c]]), axis=1
    )
    df["peak_score"] = scores_df.max(axis=1)

    # --- group contiguous True runs into event intervals ---
    flag = df["any_independent_event"]
    grp = (flag != flag.shift()).cumsum()
    intervals = []
    for _, block in df.groupby(grp):
        if not block["any_independent_event"].iloc[0]:
            continue
        triggers = sorted(set(",".join(block["triggering_channels"]).split(",")) - {""})
        intervals.append({
            "start_ts": block["ts"].iloc[0],
            "end_ts": block["ts"].iloc[-1],
            "duration_samples": len(block),
            "duration_minutes": len(block) * 30 / 60.0,
            "triggering_channels": ",".join(triggers),
            "peak_score": float(block["peak_score"].max()),
        })
    events_table = pd.DataFrame(intervals)
    events_table.to_csv(RESULTS_DIR / "event_intervals.csv", index=False)

    coverage_pct = 100.0 * flag.sum() / len(flag)
    per_channel_event_samples = {c: int(events_df[c].sum()) for c in INDEPENDENT_CHANNELS}
    per_channel_event_pct = {c: round(100.0 * v / len(df), 4) for c, v in per_channel_event_samples.items()}

    summary = {
        "n_total_samples": len(df),
        "n_event_samples": int(flag.sum()),
        "coverage_pct": round(coverage_pct, 4),
        "n_events": len(events_table),
        "median_duration_minutes": float(events_table["duration_minutes"].median()) if len(events_table) else None,
        "p90_duration_minutes": float(events_table["duration_minutes"].quantile(0.9)) if len(events_table) else None,
        "max_duration_minutes": float(events_table["duration_minutes"].max()) if len(events_table) else None,
        "per_channel_event_samples": per_channel_event_samples,
        "per_channel_event_pct_of_all_samples": per_channel_event_pct,
        "rule_params": {
            "roll_window_samples": ROLL_WINDOW,
            "score_threshold_mad_units": SCORE_THRESHOLD,
            "min_persistence_samples": MIN_PERSISTENCE_SAMPLES,
        },
    }
    import json
    with open(RESULTS_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    lines = []
    lines.append("# CITI-2026 Phase 3 — Weak Event Labels")
    lines.append("")
    lines.append(
        "Built entirely from independent channels — CO2, PM2.5, PM10, pressure "
        "(`gas_resistance_ohm` excluded per Phase 0). No temperature/humidity channel is read "
        "here, by design: this label is the ground truth Phase 6/7 use to check whether a "
        "classifier confuses a real event with an injected fault, so it must never be derived "
        "from the same channels being classified."
    )
    lines.append("")
    lines.append(f"- Rolling window: {ROLL_WINDOW} samples (~{ROLL_WINDOW*30/60:.1f} min), centered, per-day only")
    lines.append(f"- Deviation score threshold: {SCORE_THRESHOLD} (robust-MAD units, literature-typical "
                  "Hampel default — provisional, not tuned against anything in this project)")
    lines.append(f"- Minimum persistence to count as a sustained event: {MIN_PERSISTENCE_SAMPLES} samples "
                  f"({MIN_PERSISTENCE_SAMPLES*30/60:.1f} min) — filters transient blips/single-sample noise")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Total samples: {summary['n_total_samples']:,}")
    lines.append(f"- Samples inside a weak-labelled event: {summary['n_event_samples']:,} "
                  f"(**{summary['coverage_pct']:.2f}%** of the analysis window)")
    lines.append(f"- Distinct events: {summary['n_events']:,}")
    if summary['median_duration_minutes'] is not None:
        lines.append(f"- Duration: median {summary['median_duration_minutes']:.1f} min, "
                      f"p90 {summary['p90_duration_minutes']:.1f} min, "
                      f"max {summary['max_duration_minutes']:.1f} min")
    lines.append("")
    lines.append("### Per-channel contribution")
    lines.append("")
    lines.append("| channel | event samples | % of all samples |")
    lines.append("|---|---:|---:|")
    for c in INDEPENDENT_CHANNELS:
        lines.append(f"| {c} | {summary['per_channel_event_samples'][c]:,} | "
                      f"{summary['per_channel_event_pct_of_all_samples'][c]:.3f}% |")
    lines.append("")
    lines.append(
        "Full interval table (start/end/duration/triggering channel/peak score): "
        "`research_results/citi2026/phase3/event_intervals.csv`."
    )
    lines.append("")
    lines.append("## Disclosed limitations")
    lines.append("")
    lines.append(
        "- All four independent channels share the SAME rolling window and threshold, for "
        "simplicity — CO2/pressure move on slower timescales than PM cooking-smoke spikes, so a "
        "single window is a compromise, not independently tuned per channel."
    )
    lines.append(
        "- Threshold=3.0 and persistence=4 samples are literature-typical, not calibrated "
        "against any ground truth (there is none available) — same epistemic status as the "
        "sibling iaq_hfis project's still-open Hampel parameters."
    )
    lines.append(
        "- Rows failing Phase 0's hard-range check are excluded from event detection for that "
        "channel (masked, not deleted) — a known-impossible reading can never itself become a "
        "\"real event\", and cannot corrupt the local median/MAD baseline used to detect real "
        "events nearby in time."
    )

    DOCS_OUT.write_text("\n".join(lines))
    print(f"Events: {summary['n_events']}, coverage: {summary['coverage_pct']:.2f}%")
    print(f"Doc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
