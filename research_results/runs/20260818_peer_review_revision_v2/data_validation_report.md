# Data validation report

Independent re-verification of the raw dataset and computed index results
for this run, per task section 3. All numbers below were recomputed fresh
(not copied from the prior run) by
`scripts/research/data_snapshot_and_interval_verification.py`; full detail
in `snapshot/data_interval_verification.json`.

## Interval

- Start (inclusive): `2026-06-18T00:00:00+00:00`
- End (exclusive): `2026-08-16T00:00:00+00:00` (last calendar day included: 2026-08-15)

## Raw data checks

| Check | Value |
|---|---:|
| Total raw rows (all time in snapshot) | 215,380 |
| Selected raw rows in interval | 169,331 |
| Unique timestamps in interval | 169,331 |
| Duplicate timestamps | 0 |
| Timestamp ordering violations | 0 |
| Rows outside requested interval (leak check) | 0 |
| Min timestamp | 2026-06-18 00:00:06.791927+00:00 |
| Max timestamp | 2026-08-15 23:59:52.737594+00:00 |
| Dominant sampling cadence | ~30.000 s (see `sampling_interval_distribution_seconds_rounded`) |
| Gaps > 5 minutes | 6 (largest: 3h 05m 23s, on 2026-06-24) |

**Comparison with the previous run's reported approximate numbers**: the
previous run reported ~169,331 raw rows / 169,331 unique timestamps. This
run's independent recomputation matches **exactly** (not approximately) --
`dataset_csv_sha256` is byte-identical to the prior run's
(`6286fc8bc2d459533d7e552e67db477c82ebd925295f7cae5551df1e84a90061`),
confirming the underlying raw data for this fixed historical interval has
not changed between the two runs (expected: new sensor data only appends
after the interval's end boundary).

## Computed index checks

| Check | Value |
|---|---:|
| Total computed_ts | 16,992 |
| OK | 15,242 (89.70%) |
| PARTIAL | 1,004 (5.91%) |
| FAILED | 746 (4.39%) |

**Comparison with the previous run's reported approximate numbers**: the
task-stated approximate figures (16,992 total; OK 15,242; PARTIAL 1,004;
FAILED 746) match this run's independently reverified figures exactly. This
is expected and correct, not a red flag: the underlying pipeline computation
(`iaq_hfis.pipeline`) was not modified in this revision (see
`baseline/baseline_run_manifest.json`'s `note_on_rerun_policy`), and the raw
input data for this fixed historical interval is unchanged (same SHA-256),
so recomputing derived statistics over the same already-persisted pipeline
run necessarily reproduces the same counts.

## Missing values and non-finite values by channel

See `snapshot/data_interval_verification.json`'s `null_counts_by_column`
and `nonfinite_inf_counts_by_numeric_column` for the full per-raw-column
breakdown, and `data_quality_reasons/data_quality_reason_summary.csv` for
the per-derived-channel VALID/SUSPECT/INVALID/MISSING breakdown used by the
pipeline (pm2_5, pm10, co2, temperature, humidity).

## Test suite baseline

Full existing test suite run before any code change in this revision:
**457 passed**, 0 failed (`test_report_before.txt`; wall time 44m 47s).
