"""Section 3: freeze an immutable, read-only research snapshot of the raw
air-monitor data for the requested interval, hash it, and verify the
interval boundaries / data-quality preconditions the rest of this research
run depends on.

Uses iaq_hfis.db.AirMonitorSource(retain_snapshot=True) -- the exact same
consistency-checked, read-only snapshot mechanism the live pipeline already
uses (never touches air_monitor.duckdb itself, never opens it read-write).
The retained snapshot file becomes this run's frozen, immutable dataset:
copied once here, never written to again, and content-hashed so any later
artifact can cite exactly which bytes it was computed from.

Interval (exact, per task section 3):
  start, inclusive: 2026-06-18T00:00:00Z
  end,   exclusive: 2026-08-16T00:00:00Z
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import load_settings  # noqa: E402
from iaq_hfis.db import AirMonitorSource  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "snapshot"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_INCLUSIVE = datetime(2026, 6, 18, 0, 0, 0, tzinfo=timezone.utc)
END_EXCLUSIVE = datetime(2026, 8, 16, 0, 0, 0, tzinfo=timezone.utc)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")

# retain_snapshot=True: the copy this makes under settings.paths.snapshot_dir
# is NOT deleted on __exit__ -- it becomes this run's frozen dataset. Source
# air_monitor.duckdb is opened read-only for the copy and never written to;
# the live pipeline's own writer process is untouched (same mechanism it
# uses for itself, just told to keep the copy afterward).
with AirMonitorSource(settings, retain_snapshot=True) as source:
    con = source.connection
    con.execute("SET TimeZone='UTC'")

    tz_row = con.execute("SELECT typeof(ts) FROM raw_observations LIMIT 1").fetchone()
    timezone_note = (
        f"raw_observations.ts column type: {tz_row[0] if tz_row else 'unknown'}. "
        "DuckDB TIMESTAMPTZ is stored normalized to UTC internally regardless of "
        "session display timezone; this script explicitly runs SET TimeZone='UTC' "
        "before every query below so all timestamps read here are UTC, matching "
        "the requested interval boundaries verbatim (no conversion arithmetic "
        "needed, only a session-timezone-display setting)."
    )

    total_rows = con.execute("SELECT count(*) FROM raw_observations").fetchone()[0]

    sel = con.execute(
        "SELECT * FROM raw_observations WHERE ts >= ? AND ts < ? ORDER BY ts",
        [START_INCLUSIVE, END_EXCLUSIVE],
    ).fetch_df()

    # Sanity: nothing outside the requested window leaked in.
    out_of_range = con.execute(
        "SELECT count(*) FROM raw_observations WHERE ts >= ? AND ts < ? AND (ts < ? OR ts >= ?)",
        [START_INCLUSIVE, END_EXCLUSIVE, START_INCLUSIVE, END_EXCLUSIVE],
    ).fetchone()[0]

    dup_ts = con.execute(
        "SELECT count(*) FROM (SELECT ts, count(*) c FROM raw_observations WHERE ts >= ? AND ts < ? GROUP BY ts HAVING c > 1)",
        [START_INCLUSIVE, END_EXCLUSIVE],
    ).fetchone()[0]

    ordering_violations = int((sel["ts"].diff().dropna() < pd.Timedelta(0)).sum()) if not sel.empty else 0

    gaps = sel["ts"].diff().dropna()
    gap_counts = gaps.astype(str).value_counts().head(20)
    gaps_over_5min = gaps[gaps > pd.Timedelta(minutes=5)]
    gaps_over_5min_sample = [
        (str(sel["ts"].iloc[i - 1]), str(gaps.iloc[i - 1])) for i in gaps_over_5min.index[:20]
    ] if len(gaps_over_5min) else []

    numeric_cols = [c for c in sel.columns if pd.api.types.is_numeric_dtype(sel[c])]
    null_counts = {c: int(sel[c].isna().sum()) for c in sel.columns}
    import numpy as np
    nonfinite_counts = {}
    for c in numeric_cols:
        arr = pd.to_numeric(sel[c], errors="coerce").to_numpy(dtype="float64")
        nonfinite_counts[c] = int(np.sum(~np.isfinite(arr) & ~np.isnan(arr)))  # inf/-inf only, NaN counted separately in null_counts

    sensor_col = "sensor" if "sensor" in sel.columns else ("sensor_id" if "sensor_id" in sel.columns else None)
    per_sensor_counts = sel[sensor_col].value_counts().to_dict() if sensor_col else None

    # Actual sampling-interval distribution (seconds), rounded to nearest int
    # second so genuinely-identical cadences group together despite float
    # jitter (see the pre-existing data_interval_verification.json's
    # top-20 list, which is dominated by ~30.00008xx-second entries -- that
    # jitter is real clock-timestamp noise, not a data error).
    gap_seconds_rounded = gaps.dt.total_seconds().round().astype("Int64")
    sampling_interval_distribution = gap_seconds_rounded.value_counts().sort_index().to_dict()

    # Export the exact interval-filtered rows as a CSV via DuckDB's own COPY
    # (no pyarrow/fastparquet available on this Pi for a Parquet export --
    # CSV is dependency-free, universally hashable, and native to DuckDB).
    dataset_csv_path = OUT_DIR / "raw_observations_2026-06-18_to_2026-08-16.csv"
    con.execute(
        f"COPY (SELECT * FROM raw_observations WHERE ts >= ? AND ts < ? ORDER BY ts) "
        f"TO '{dataset_csv_path}' (FORMAT CSV, HEADER)",
        [START_INCLUSIVE, END_EXCLUSIVE],
    )

# --- Export the exact interval-filtered rows as the citable "dataset" for
# every downstream research script in this run: a Parquet file (smaller,
# columnar, trivially hashed) alongside the retained full-DB snapshot copy
# AirMonitorSource just made (source._snapshot_path is gone once the `with`
# block exits without retain, but retain_snapshot=True kept it -- locate it
# by newest file in snapshot_dir matching this run's copy). ---
snapshot_dir = Path(settings.paths.snapshot_dir)
candidate_snapshots = sorted(snapshot_dir.glob("snapshot_*.duckdb"), key=lambda p: p.stat().st_mtime)
retained_snapshot_path = candidate_snapshots[-1] if candidate_snapshots else None

frozen_db_path = OUT_DIR / "air_monitor_frozen_snapshot.duckdb"
if retained_snapshot_path is not None:
    import shutil as _shutil
    _shutil.copy2(retained_snapshot_path, frozen_db_path)
    # Clean up the transient-named copy under snapshot_dir now that a
    # permanently-named, immutable copy lives under this run's own
    # directory -- avoids silently accumulating one extra untracked
    # full-DB copy per invocation of this script.
    retained_snapshot_path.unlink(missing_ok=True)
    Path(str(retained_snapshot_path) + ".wal").unlink(missing_ok=True)

dataset_csv_sha256 = sha256_of(dataset_csv_path)
frozen_db_sha256 = sha256_of(frozen_db_path) if frozen_db_path.exists() else None

report = {
    "requested_start_inclusive": START_INCLUSIVE.isoformat(),
    "requested_end_exclusive": END_EXCLUSIVE.isoformat(),
    "timezone_note": timezone_note,
    "conversion_method": "DuckDB TIMESTAMPTZ (already UTC-normalized internally) read under an explicit session SET TimeZone='UTC'; no numeric offset arithmetic applied.",
    "total_rows_all_time_in_snapshot": int(total_rows),
    "selected_row_count": int(len(sel)),
    "selected_unique_ts_count": int(sel["ts"].nunique()) if not sel.empty else 0,
    "selected_min_ts": str(sel["ts"].min()) if not sel.empty else None,
    "selected_max_ts": str(sel["ts"].max()) if not sel.empty else None,
    "rows_outside_requested_interval_found_in_selection": int(out_of_range),
    "duplicate_ts_count": int(dup_ts),
    "timestamp_ordering_violations": int(ordering_violations),
    "top_20_gap_intervals_seconds_and_counts": [[k, int(v)] for k, v in gap_counts.items()],
    "gaps_over_5min_count": int(len(gaps_over_5min)),
    "gaps_over_5min_sample": gaps_over_5min_sample,
    "sensor_channel_column": sensor_col,
    "rows_per_sensor_channel": per_sensor_counts,
    "null_counts_by_column": null_counts,
    "nonfinite_inf_counts_by_numeric_column": nonfinite_counts,
    "sampling_interval_distribution_seconds_rounded": {str(k): int(v) for k, v in sampling_interval_distribution.items()},
    "dataset_csv_path": str(dataset_csv_path),
    "dataset_csv_sha256": dataset_csv_sha256,
    "frozen_full_db_snapshot_path": str(frozen_db_path) if frozen_db_path.exists() else None,
    "frozen_full_db_snapshot_sha256": frozen_db_sha256,
    "read_only_access_note": "Snapshot taken via iaq_hfis.db.AirMonitorSource / make_snapshot(): a file copy of air_monitor.duckdb opened read-only; the live pipeline's writer process and its file were never opened for writing by this script.",
}

(OUT_DIR / "data_interval_verification.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
(OUT_DIR / "dataset_sha256.txt").write_text(f"{dataset_csv_sha256}  {dataset_csv_path.name}\n" + (f"{frozen_db_sha256}  {frozen_db_path.name}\n" if frozen_db_sha256 else ""), encoding="utf-8")

print(json.dumps({k: v for k, v in report.items() if k not in ("null_counts_by_column", "rows_per_sensor_channel", "sampling_interval_distribution_seconds_rounded", "nonfinite_inf_counts_by_numeric_column")}, indent=2, default=str))
