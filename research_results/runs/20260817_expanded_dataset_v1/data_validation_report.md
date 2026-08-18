# Data validation report

Full machine-readable detail: `snapshot/data_interval_verification.json`.
SHA256 hashes: `snapshot/dataset_sha256.txt`.

| Check | Result |
|---|---|
| Requested interval | 2026-06-18T00:00:00Z (incl.) -- 2026-08-16T00:00:00Z (excl.) |
| Timezone | `raw_observations.ts` is `TIMESTAMPTZ`, UTC-normalized internally by DuckDB; session `SET TimeZone='UTC'` used explicitly, no numeric offset arithmetic |
| Selected row count | 169,331 |
| Selected unique timestamp count | 169,331 (equal to row count -- no duplicate timestamps) |
| Min / max selected timestamp | 2026-06-18 00:00:06.79Z / 2026-08-15 23:59:52.74Z |
| Duplicate timestamps | 0 |
| Timestamp ordering violations | 0 |
| Rows found outside the requested interval | 0 |
| Gaps > 5 minutes | 6 (largest: 3h05m, 2026-06-24 23:56 -- see `snapshot/data_interval_verification.json` for the full list with timestamps) |
| Sampling interval | dominant cadence ~30.00008s (float jitter is real clock noise, not a data defect) |
| Frozen snapshot SHA256 (interval-filtered CSV export) | see `snapshot/dataset_sha256.txt` |
| Frozen snapshot SHA256 (full raw_observations DB copy) | see `snapshot/dataset_sha256.txt` |
| Read-only access confirmed | Snapshot taken via `iaq_hfis.db.AirMonitorSource`/`make_snapshot()` -- a file copy of `air_monitor.duckdb` opened read-only; the live pipeline's writer process was never opened for writing by any script in this research run |

No null-count or non-finite-value anomalies were found in the interval-
filtered selection beyond what `snapshot/data_interval_verification.json`'s
`null_counts_by_column` / `nonfinite_inf_counts_by_numeric_column` fields
already record explicitly (see that file for exact per-column counts).
