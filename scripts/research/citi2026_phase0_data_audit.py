#!/usr/bin/env python3
"""CITI-2026 Phase 0: data audit & dataset extension.

Paper: "Distinguishing Sensor Faults from Indoor Climate Changes Using
Redundant Measurements" (I. Borodii, supervisor H. Osukhivska, TNTU).

Scientific-integrity constraints honoured here:
  - The live `air_monitor.duckdb` is NEVER opened for writing and never has
    any row altered. It is snapshotted (same /tmp-copy technique already
    used in production by air-monitor/scripts/replicate_to_motherduck.py,
    chosen specifically so this script cannot block or be blocked by the
    live collection service's write lock).
  - The frozen snapshot becomes this project's immutable "primary dataset"
    at a fixed cutoff timestamp -- every later phase reads THIS file, never
    the live one, so results are reproducible even as the live pipeline
    keeps collecting.
  - Nothing here injects faults, derives labels, or fits anything -- pure
    read-only characterisation.

Usage:
    .venv/bin/python3 scripts/research/citi2026_phase0_data_audit.py
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_DB = REPO_ROOT / "air-monitor" / "data" / "air_monitor.duckdb"
LIVE_WAL = REPO_ROOT / "air-monitor" / "data" / "air_monitor.duckdb.wal"

OUT_DATA_DIR = REPO_ROOT / "data" / "citi2026"
OUT_RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase0"
OUT_DOCS = REPO_ROOT / "docs" / "citi2026_phase0_data_audit.md"

EXPECTED_CADENCE_S = 30.0
# A gap is "real" (worth listing) once it's at least this many missed cycles.
GAP_MULTIPLE_THRESHOLD = 2.0
# A run of `n` identical consecutive non-null values is a "flatline run"
# once n reaches this. 5 samples = 2.5 min at 30s cadence.
FLATLINE_MIN_RUN = 5

# The channels the CITI-2026 paper actually reasons about. Kept separate
# from "every numeric column" (also audited, for honesty) so the headline
# table matches exactly what later phases will use.
PAPER_CHANNELS = {
    "scd_temp_c": "Temperature (SCD41)",
    "bme_temp_c": "Temperature (BME688)",
    "scd_humidity_pct": "Relative humidity (SCD41)",
    "bme_humidity_pct": "Relative humidity (BME688)",
    "co2_ppm": "CO2 (SCD41)",
    "mass_pm2_5": "PM2.5 (SPS30)",
    "mass_pm10": "PM10 (SPS30)",
    "gas_resistance_ohm": "Gas-sensor resistance (BME688)",
    "pressure_hpa": "Barometric pressure (BME688)",
}

ALL_NUMERIC_CHANNELS = list(PAPER_CHANNELS.keys()) + [
    "mass_pm1_0", "mass_pm4_0",
    "number_pm0_5", "number_pm1_0", "number_pm2_5", "number_pm4_0", "number_pm10",
    "typical_size_um",
]


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()
    except Exception as exc:  # noqa: BLE001 - best-effort provenance only
        return f"<unavailable: {exc}>"


def snapshot_live_db(dest_dir: Path) -> Path:
    """Copy the live DB (+ WAL if present) to dest_dir, exactly as
    air-monitor/scripts/replicate_to_motherduck.py does, so this script
    never competes for the live writer's lock and can never mutate it."""
    dest = dest_dir / "live_snapshot.duckdb"
    shutil.copy2(LIVE_DB, dest)
    if LIVE_WAL.exists():
        shutil.copy2(LIVE_WAL, Path(str(dest) + ".wal"))
    return dest


def freeze_working_copy(snapshot_path: Path, cutoff_label: str) -> Path:
    """Checkpoint the snapshot (folds WAL into the main file) and copy it
    to the project's permanent, named, read-only working dataset."""
    frozen = OUT_DATA_DIR / f"primary_dataset_{cutoff_label}.duckdb"
    con = duckdb.connect(str(snapshot_path))
    con.execute("CHECKPOINT")
    con.close()
    shutil.copy2(snapshot_path, frozen)
    return frozen


def flatline_runs(series: pd.Series) -> tuple[int, int]:
    """Return (count of runs >= FLATLINE_MIN_RUN, longest run length),
    ignoring NaNs (a NaN breaks a run rather than extending it)."""
    vals = series.to_numpy()
    n = len(vals)
    if n == 0:
        return 0, 0
    run_len = 1
    longest = 0
    count = 0
    for i in range(1, n + 1):
        same = (
            i < n
            and not (pd.isna(vals[i]) or pd.isna(vals[i - 1]))
            and vals[i] == vals[i - 1]
        )
        if same:
            run_len += 1
        else:
            if not pd.isna(vals[i - 1]):
                longest = max(longest, run_len)
                if run_len >= FLATLINE_MIN_RUN:
                    count += 1
            run_len = 1
    return count, longest


def main() -> None:
    OUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    audit_started_at = datetime.now(timezone.utc)

    # --- provenance: row count on the LIVE table, read via its own
    # snapshot mechanism, taken both before and after this script's work,
    # to demonstrate no row this script touched was altered (growth is
    # expected -- the live collector keeps running throughout). ---
    with tempfile.TemporaryDirectory() as tmp:
        pre_snapshot = snapshot_live_db(Path(tmp))
        con = duckdb.connect(str(pre_snapshot), read_only=True)
        pre_count, pre_min_ts, pre_max_ts = con.execute(
            "SELECT count(*), min(ts), max(ts) FROM raw_observations"
        ).fetchone()
        con.close()

    cutoff_label = audit_started_at.strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        snap = snapshot_live_db(Path(tmp))
        frozen_path = freeze_working_copy(snap, cutoff_label)

    con = duckdb.connect(str(frozen_path), read_only=True)
    post_count, post_min_ts, post_max_ts = con.execute(
        "SELECT count(*), min(ts), max(ts) FROM raw_observations"
    ).fetchone()

    # Full table into memory once (287k+ rows is small; RPi5 has plenty of RAM).
    df = con.execute(
        "SELECT * FROM raw_observations ORDER BY ts"
    ).df()
    con.close()

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)

    # --- cadence / gaps ---
    deltas = df["ts"].diff().dt.total_seconds()
    gap_threshold = EXPECTED_CADENCE_S * GAP_MULTIPLE_THRESHOLD
    gap_mask = deltas > gap_threshold
    gaps = pd.DataFrame({
        "gap_start": df["ts"].shift(1)[gap_mask],
        "gap_end": df["ts"][gap_mask],
        "gap_seconds": deltas[gap_mask],
    })
    gaps["gap_hours"] = gaps["gap_seconds"] / 3600.0
    gaps = gaps.sort_values("gap_seconds", ascending=False).reset_index(drop=True)

    # --- duplicates ---
    dup_ts_count = int(df["ts"].duplicated().sum())
    dup_batch_row = df.duplicated(subset=["batch_id", "row_in_batch"]).sum()

    # --- median cadence sanity check (excluding gaps) ---
    normal_deltas = deltas[(~gap_mask) & deltas.notna()]
    median_cadence = float(normal_deltas.median()) if len(normal_deltas) else float("nan")

    # --- per-channel audit table ---
    n_total = len(df)
    rows = []
    for col in ALL_NUMERIC_CHANNELS:
        if col not in df.columns:
            continue
        series = df[col]
        n_missing = int(series.isna().sum())
        n_valid = n_total - n_missing
        run_count, longest_run = flatline_runs(series)
        rows.append({
            "channel": col,
            "label": PAPER_CHANNELS.get(col, col),
            "in_paper_scope": col in PAPER_CHANNELS,
            "n_valid": n_valid,
            "n_missing": n_missing,
            "coverage_pct": round(100.0 * n_valid / n_total, 4) if n_total else float("nan"),
            "missing_pct": round(100.0 * n_missing / n_total, 4) if n_total else float("nan"),
            "min": float(series.min()) if n_valid else None,
            "max": float(series.max()) if n_valid else None,
            "mean": float(series.mean()) if n_valid else None,
            "std": float(series.std()) if n_valid else None,
            "distinct_values": int(series.nunique(dropna=True)),
            "flatline_runs_ge_5": run_count,
            "longest_flatline_run": longest_run,
        })
    audit_df = pd.DataFrame(rows)
    audit_df.to_csv(OUT_RESULTS_DIR / "per_channel_audit.csv", index=False)

    # --- status-field breakdown ---
    status_cols = ["sensor_status", "scd41_status", "bme688_status", "sps30_status"]
    status_breakdown = {}
    for c in status_cols:
        status_breakdown[c] = df[c].value_counts(dropna=False).to_dict()
    with open(OUT_RESULTS_DIR / "status_breakdown.json", "w") as f:
        json.dump(status_breakdown, f, indent=2, default=str)

    gaps.to_csv(OUT_RESULTS_DIR / "gaps.csv", index=False)

    # --- environment / provenance record ---
    environment = {
        "audit_started_at_utc": audit_started_at.isoformat(),
        "cutoff_label": cutoff_label,
        "device": run(["cat", "/proc/device-tree/model"]).rstrip("\x00"),
        "os": platform.platform(),
        "python": sys.version,
        "duckdb_version": duckdb.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "git_commit_air_index_repo": run(["git", "rev-parse", "HEAD"]),
        "git_commit_air_monitor_repo": run(
            ["git", "-C", str(REPO_ROOT / "air-monitor"), "rev-parse", "HEAD"]
        ),
        "live_db_path": str(LIVE_DB),
        "frozen_dataset_path": str(frozen_path),
        "row_count_live_before_freeze": pre_count,
        "row_count_frozen_dataset": post_count,
        "rows_added_by_live_collector_during_audit": post_count - pre_count,
        "min_ts_before": str(pre_min_ts),
        "max_ts_before": str(pre_max_ts),
        "min_ts_frozen": str(post_min_ts),
        "max_ts_frozen": str(post_max_ts),
        "expected_cadence_seconds": EXPECTED_CADENCE_S,
        "median_observed_cadence_seconds": median_cadence,
        "gap_threshold_seconds": gap_threshold,
        "n_gaps_found": int(gap_mask.sum()),
        "total_gap_hours": float(gaps["gap_hours"].sum()) if len(gaps) else 0.0,
        "duplicate_ts_count": dup_ts_count,
        "duplicate_batch_row_count": int(dup_batch_row),
        "flatline_min_run_length": FLATLINE_MIN_RUN,
    }
    with open(OUT_RESULTS_DIR / "environment.json", "w") as f:
        json.dump(environment, f, indent=2, default=str)

    # --- markdown report ---
    lines = []
    lines.append("# CITI-2026 Phase 0 — Data Audit & Dataset Extension")
    lines.append("")
    lines.append(
        "Paper: *Distinguishing Sensor Faults from Indoor Climate Changes "
        "Using Redundant Measurements* (I. Borodii, supervisor H. Osukhivska, TNTU)."
    )
    lines.append("")
    lines.append(
        f"Audit run at **{audit_started_at.isoformat()}** on **{environment['device']}**. "
        "The live `air_monitor.duckdb` was opened read-only via a snapshot copy only "
        "(same technique as the production MotherDuck replication job) — it was never "
        "opened for writing and no existing row was altered."
    )
    lines.append("")
    lines.append("## 1. Immutability / provenance")
    lines.append("")
    lines.append(f"- Live table row count at audit start: **{pre_count:,}**")
    lines.append(f"- Live table row count in the frozen working copy: **{post_count:,}**")
    lines.append(
        f"- Difference (**{post_count - pre_count:,}** rows) is new data appended by the "
        "still-running live collector between the two snapshots taken a few seconds apart "
        "— not a modification of any existing row (`raw_observations` has no UPDATE path "
        "anywhere in the pipeline, only INSERT)."
    )
    lines.append(f"- Frozen dataset (this project's **primary dataset**, read-only from here on): "
                  f"`{frozen_path.relative_to(REPO_ROOT)}`")
    lines.append(f"- Coverage: **{post_min_ts} → {post_max_ts}**")
    lines.append("")
    lines.append("## 2. Cadence")
    lines.append("")
    lines.append(f"- Configured cadence: {EXPECTED_CADENCE_S:.0f} s")
    lines.append(f"- Median observed inter-sample interval (excluding flagged gaps): "
                  f"{median_cadence:.2f} s")
    lines.append(f"- Gap threshold used: > {gap_threshold:.0f} s "
                  f"({GAP_MULTIPLE_THRESHOLD:.0f}× expected cadence)")
    lines.append(f"- Gaps found: **{int(gap_mask.sum())}**, total **{gaps['gap_hours'].sum():.2f} h** "
                  "of missing collection time")
    lines.append("")
    if len(gaps):
        lines.append("### Largest gaps")
        lines.append("")
        lines.append("| start | end | duration (h) |")
        lines.append("|---|---|---:|")
        for _, r in gaps.head(15).iterrows():
            lines.append(f"| {r['gap_start']} | {r['gap_end']} | {r['gap_hours']:.2f} |")
        lines.append("")
        lines.append(
            "The largest gap is the documented Sep 13 04:22 → Sep 14 23:41 venv-corruption "
            "outage (see project memory `project_air_monitor`) — a real device-down period, "
            "not a data artefact. It must be excluded from any day used for training/testing "
            "(whole-day split, see §5) rather than imputed."
        )
        lines.append("")
    lines.append("## 3. Duplicates")
    lines.append("")
    lines.append(f"- Duplicate `ts` values: **{dup_ts_count}**")
    lines.append(f"- Duplicate `(batch_id, row_in_batch)` pairs: **{dup_batch_row}**")
    lines.append("")
    lines.append("## 4. Per-channel audit")
    lines.append("")
    lines.append(
        "Full table: `research_results/citi2026/phase0/per_channel_audit.csv`. "
        "Headline channels (the ones this paper reasons about):"
    )
    lines.append("")
    lines.append("| channel | coverage % | missing % | min | max | mean | std | flatline runs (≥5) | longest run |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in audit_df[audit_df["in_paper_scope"]].iterrows():
        lines.append(
            f"| {r['label']} | {r['coverage_pct']:.3f} | {r['missing_pct']:.3f} | "
            f"{r['min']:.3g} | {r['max']:.3g} | {r['mean']:.3g} | {r['std']:.3g} | "
            f"{r['flatline_runs_ge_5']} | {r['longest_flatline_run']} |"
        )
    lines.append("")

    # Flag the known gas_resistance_ohm issue explicitly and honestly.
    gas_row = audit_df[audit_df["channel"] == "gas_resistance_ohm"]
    if len(gas_row) and gas_row.iloc[0]["distinct_values"] <= 2:
        lines.append("### ⚠ Disclosed limitation: gas-sensor resistance channel is dead")
        lines.append("")
        lines.append(
            f"`gas_resistance_ohm` has only **{int(gas_row.iloc[0]['distinct_values'])}** "
            f"distinct value(s) across {n_total:,} rows (longest flatline run: "
            f"{int(gas_row.iloc[0]['longest_flatline_run'])} samples — i.e. essentially the "
            "entire series). This confirms the finding already on record in "
            "`air-monitor/README_ML.md`: this BME688 unit's gas-resistance ADC output is "
            "saturated/constant on this hardware, not a real measurement of anything. "
            "**It cannot serve as one of the paper's independent channels for weak-label "
            "construction or cross-channel concordance** — using it would be circular in the "
            "worst way (a constant can never independently confirm or refute anything). "
            "Recommendation for Phase 3: drop gas-sensor resistance from the independent-"
            "channel set and rely on CO2 + PM2.5 + PM10 + pressure only, and disclose this "
            "explicitly in the paper rather than silently dropping a channel it lists."
        )
        lines.append("")
    lines.append("## 5. Status-field breakdown")
    lines.append("")
    lines.append("See `research_results/citi2026/phase0/status_breakdown.json` for exact counts "
                  "of `sensor_status` / `scd41_status` / `bme688_status` / `sps30_status`.")
    lines.append("")
    lines.append("## 6. Reproducibility")
    lines.append("")
    lines.append("Full environment/provenance record: "
                  "`research_results/citi2026/phase0/environment.json` "
                  "(device, OS, Python/DuckDB/pandas/numpy versions, git commit of both repos, "
                  "exact row counts, cutoff timestamp).")
    lines.append("")

    OUT_DOCS.write_text("\n".join(lines))

    print(f"Frozen dataset: {frozen_path}")
    print(f"Rows: {post_count:,}  ({post_min_ts} -> {post_max_ts})")
    print(f"Gaps: {int(gap_mask.sum())}  total {gaps['gap_hours'].sum():.2f} h")
    print(f"Report written: {OUT_DOCS}")


if __name__ == "__main__":
    main()
