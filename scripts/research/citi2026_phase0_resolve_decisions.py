#!/usr/bin/env python3
"""CITI-2026 Phase 0 — resolve the three open decisions from the initial
data audit (docs/citi2026_phase0_data_audit.md), author-delegated to the
implementer ("resolve everything").

Decisions resolved here, each documented with its exact justification:

1. Analysis window: 2026-06-18 00:00 (Kyiv) through the last FULL day
   before the audit cutoff (2026-09-19 23:59:59 Kyiv). The record actually
   starts 2026-04-16, but a ~49-day gap (Apr28->Jun16) splits it into two
   eras; only the post-Jun16 era is continuous. 2026-06-18 matches the
   author's stated intent ("data start on 18 June") and skips the first
   two days of post-gap settling (small sub-hour gaps on Jun17/18 visible
   in the Phase 0 gap table -- consistent with redeployment settling, not
   picked to hide anything: those two days remain in the frozen full-
   history table, just outside the analysis window used going forward).

2. `gas_resistance_ohm` is dropped from the independent-channel set used
   for weak-label construction (Phase 3) and cross-channel concordance.
   Justification (Phase 0 audit): only 11.2% coverage (88.8% NULL) plus a
   ~15,171-sample stuck run where present -- not the channel the paper's
   brief assumed it had available. The column itself is NOT deleted from
   the data (nothing is ever deleted here), just excluded from that one
   downstream use, disclosed rather than silently substituted.

3. A HARD, datasheet-technical-range check (reusing config/sensor_specs.yaml
   verbatim -- exact values already verified against manufacturer datasheets
   in the sibling iaq_hfis project, not re-derived here) is applied to flag
   (never delete or null out) rows outside each channel's sensor-reportable
   range. This is deliberately the SAME two-tier design already validated
   in iaq_hfis (hard technical-range check vs. later soft/statistical
   outlier check) rather than a new ad hoc "plausibility band" invented for
   this paper. Flagged rows stay in the data, visible via new
   `hardcheck_fail_<channel>` boolean columns, so Phase 1's pair statistics
   and Phase 4's injection base can each decide how to use the flag without
   the underlying value ever being destroyed.

Input:  the Phase 0 frozen snapshot (data/citi2026/primary_dataset_*.duckdb)
Output: data/citi2026/analysis_dataset_<cutoff>.duckdb containing
          - raw_observations_full_history  (every row, all eras, + flags)
          - raw_observations_analysis      (analysis-window subset, + flags)
        plus updated docs/CSVs.
"""

from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase0"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase0_resolution.md"
SENSOR_SPECS_PATH = REPO_ROOT / "config" / "sensor_specs.yaml"

ANALYSIS_START = "2026-06-18 00:00:00"          # Kyiv local, inclusive
ANALYSIS_END_EXCLUSIVE = "2026-09-20 00:00:00"  # Kyiv local, exclusive (last full day = Sep 19)

EXPECTED_SAMPLES_PER_DAY = 24 * 60 * 60 / 30.0  # 2880

# channel -> sensor_specs.yaml key
CHANNEL_TO_SPEC = {
    "co2_ppm": "co2",
    "scd_temp_c": "scd_temp",
    "scd_humidity_pct": "scd_humidity",
    "bme_temp_c": "bme_temp",
    "bme_humidity_pct": "bme_humidity",
    "pressure_hpa": "pressure",
    "mass_pm1_0": "pm_mass_fine",
    "mass_pm2_5": "pm_mass_fine",
    "mass_pm4_0": "pm_mass_coarse",
    "mass_pm10": "pm_mass_coarse",
    "number_pm0_5": "pm_number",
    "number_pm1_0": "pm_number",
    "number_pm2_5": "pm_number",
    "number_pm4_0": "pm_number",
    "number_pm10": "pm_number",
}


def find_latest_frozen_snapshot() -> Path:
    candidates = sorted(glob.glob(str(DATA_DIR / "primary_dataset_*.duckdb")))
    if not candidates:
        raise SystemExit("No Phase 0 frozen snapshot found — run citi2026_phase0_data_audit.py first.")
    return Path(candidates[-1])


def main() -> None:
    specs = yaml.safe_load(SENSOR_SPECS_PATH.read_text())["channels"]

    src_path = find_latest_frozen_snapshot()
    cutoff_label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = DATA_DIR / f"analysis_dataset_{cutoff_label}.duckdb"

    src = duckdb.connect(str(src_path), read_only=True)
    df = src.execute("SELECT * FROM raw_observations ORDER BY ts").df()
    src.close()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    # --- hard datasheet-range flags (added columns, nothing destroyed) ---
    flag_cols = []
    flag_counts = {}
    for channel, spec_key in CHANNEL_TO_SPEC.items():
        if channel not in df.columns:
            continue
        spec = specs[spec_key]
        lo, hi = spec["min"], spec["max"]
        flag_col = f"hardcheck_fail_{channel}"
        # NaN (already missing) is not a "range violation" -- it's just missing.
        fail = df[channel].notna() & ((df[channel] < lo) | (df[channel] > hi))
        df[flag_col] = fail
        flag_cols.append(flag_col)
        flag_counts[channel] = {
            "spec_key": spec_key,
            "min": lo,
            "max": hi,
            "n_fail": int(fail.sum()),
            "source": spec["source"],
        }
    df["hardcheck_fail_any"] = df[flag_cols].any(axis=1)

    # --- write the two tables to a fresh output DB ---
    out = duckdb.connect(str(out_path))
    out.register("full_history_df", df)
    out.execute("CREATE TABLE raw_observations_full_history AS SELECT * FROM full_history_df")

    window_mask = (df["ts"] >= pd.Timestamp(ANALYSIS_START, tz="Europe/Kyiv")) & (
        df["ts"] < pd.Timestamp(ANALYSIS_END_EXCLUSIVE, tz="Europe/Kyiv")
    )
    analysis_df = df[window_mask].reset_index(drop=True)
    out.register("analysis_df", analysis_df)
    out.execute("CREATE TABLE raw_observations_analysis AS SELECT * FROM analysis_df")
    out.execute("CHECKPOINT")
    out.close()

    # --- day-level completeness table for the analysis window (for Phase 5's
    # whole-day split) ---
    analysis_df = analysis_df.copy()
    analysis_df["day"] = analysis_df["ts"].dt.tz_convert("Europe/Kyiv").dt.date
    day_counts = analysis_df.groupby("day").size().reset_index(name="n_samples")
    day_counts["pct_of_expected"] = (100.0 * day_counts["n_samples"] / EXPECTED_SAMPLES_PER_DAY).round(2)
    day_counts["fully_complete"] = day_counts["pct_of_expected"] >= 99.0
    day_counts.to_csv(RESULTS_DIR / "day_completeness.csv", index=False)

    incomplete_days = day_counts[~day_counts["fully_complete"]].sort_values("pct_of_expected")

    with open(RESULTS_DIR / "hardcheck_flags.json", "w") as f:
        json.dump(flag_counts, f, indent=2, default=str)

    resolution = {
        "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": str(src_path.relative_to(REPO_ROOT)),
        "analysis_dataset": str(out_path.relative_to(REPO_ROOT)),
        "analysis_window_start_kyiv": ANALYSIS_START,
        "analysis_window_end_exclusive_kyiv": ANALYSIS_END_EXCLUSIVE,
        "n_rows_full_history": len(df),
        "n_rows_analysis_window": len(analysis_df),
        "n_days_in_window": int(day_counts.shape[0]),
        "n_fully_complete_days": int(day_counts["fully_complete"].sum()),
        "n_incomplete_days": int((~day_counts["fully_complete"]).sum()),
        "gas_resistance_ohm_excluded_from_independent_channels": True,
        "hardcheck_total_flagged_rows": int(df["hardcheck_fail_any"].sum()),
    }
    with open(RESULTS_DIR / "resolution_manifest.json", "w") as f:
        json.dump(resolution, f, indent=2, default=str)

    # --- markdown doc ---
    lines = []
    lines.append("# CITI-2026 Phase 0 — Resolution of Open Decisions")
    lines.append("")
    lines.append(f"Resolved {resolution['resolved_at_utc']}, author-delegated (\"resolve everything\").")
    lines.append("")
    lines.append("## Decision 1 — Analysis window")
    lines.append("")
    lines.append(
        f"Primary analysis window: **{ANALYSIS_START} → {ANALYSIS_END_EXCLUSIVE} (Kyiv, exclusive)** "
        f"= **{resolution['n_days_in_window']} calendar days**, "
        f"**{resolution['n_rows_analysis_window']:,} rows**."
    )
    lines.append(
        "The pre-gap era (2026-04-16 → 2026-04-28, 34,060 rows) is excluded from analysis but "
        "**not deleted** — it remains in `raw_observations_full_history` in the same output "
        "file, for any later sensitivity check."
    )
    lines.append("")
    lines.append(f"- Fully complete days (≥99% of {EXPECTED_SAMPLES_PER_DAY:.0f} expected samples): "
                  f"**{resolution['n_fully_complete_days']} / {resolution['n_days_in_window']}**")
    lines.append(f"- Incomplete days: **{resolution['n_incomplete_days']}** — see "
                  "`research_results/citi2026/phase0/day_completeness.csv` for the full "
                  "day-by-day table (needed for Phase 5's whole-day split).")
    lines.append("")
    if len(incomplete_days):
        lines.append("### Incomplete days (lowest coverage first)")
        lines.append("")
        lines.append("| day | samples | % of expected |")
        lines.append("|---|---:|---:|")
        for _, r in incomplete_days.head(20).iterrows():
            lines.append(f"| {r['day']} | {r['n_samples']} | {r['pct_of_expected']:.1f} |")
        lines.append("")
        lines.append(
            "The two lowest-coverage days are the known 2026-09-13/09-14 venv-corruption "
            "outage (see project memory `project_air_monitor`) — genuine device-down time. "
            "Phase 5 should exclude any day below the completeness threshold it adopts from "
            "both train and test splits rather than impute across a real multi-hour outage."
        )
        lines.append("")
    lines.append("## Decision 2 — `gas_resistance_ohm` dropped from independent channels")
    lines.append("")
    lines.append(
        "Confirmed dropped from the Phase 3 weak-label/concordance independent-channel set "
        "(CO2, PM2.5, PM10, pressure remain). The column is untouched in the data — this is a "
        "usage decision, not a data change."
    )
    lines.append("")
    lines.append("## Decision 3 — Hard datasheet-technical-range check")
    lines.append("")
    lines.append(
        "Reused verbatim from `config/sensor_specs.yaml` (already verified against manufacturer "
        "datasheets in the sibling iaq_hfis project — not re-derived or guessed here). A row "
        "failing a channel's technical range gets `hardcheck_fail_<channel> = TRUE` in both "
        "output tables; **no value is modified, nulled, or removed** — later phases decide how "
        "to use the flag (Phase 1 excludes flagged rows from bias/MAD/correlation stats; Phase 4 "
        "excludes flagged rows from the base signal used for synthetic fault injection, so "
        "pre-existing real faults never contaminate the injected ground-truth mask)."
    )
    lines.append("")
    lines.append("| channel | technical range | rows flagged | source |")
    lines.append("|---|---|---:|---|")
    for channel, info in flag_counts.items():
        lines.append(
            f"| {channel} | [{info['min']}, {info['max']}] | {info['n_fail']} | "
            f"{info['source'][:70]}… |"
        )
    lines.append("")
    lines.append(f"**Total rows with ≥1 hard-range violation: {resolution['hardcheck_total_flagged_rows']:,} "
                  f"out of {resolution['n_rows_full_history']:,} ({100*resolution['hardcheck_total_flagged_rows']/resolution['n_rows_full_history']:.3f}%)**")
    lines.append("")
    lines.append(
        "Note: PM channels account for the large majority of hard-range violations "
        "(~7,600-8,700 rows per PM sub-channel, vs. single/low-hundreds for CO2/temperature/"
        "pressure) — the SPS30's technical range (0-1000 ug/m3 mass, 0-3000 #/cm3 number) is "
        "genuinely exceeded on a meaningful fraction of rows, not just occasionally. Whether "
        "these are sensor-fault bursts or extreme real cooking-smoke events (both are physically "
        "plausible triggers for exceeding the sensor's rated range) is NOT decided here -- that "
        "judgement call belongs to Phase 1 (pair/channel characterisation) and Phase 3 (weak "
        "labels), which have the surrounding context (duration, co-occurrence with other "
        "channels) this hard check does not look at."
    )
    lines.append("")
    lines.append(f"Output dataset: `{resolution['analysis_dataset']}` "
                  "(`raw_observations_full_history` + `raw_observations_analysis` tables, "
                  "both carrying the same `hardcheck_fail_*` columns).")

    DOCS_OUT.write_text("\n".join(lines))

    print(f"Analysis dataset written: {out_path}")
    print(f"Rows in analysis window: {len(analysis_df):,} across {resolution['n_days_in_window']} days")
    print(f"Fully complete days: {resolution['n_fully_complete_days']}/{resolution['n_days_in_window']}")
    print(f"Hard-range violations: {resolution['hardcheck_total_flagged_rows']:,} rows")
    print(f"Doc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
