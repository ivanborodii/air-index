# CITI-2026 Phase 0 — Data Audit & Dataset Extension

Paper: *Distinguishing Sensor Faults from Indoor Climate Changes Using Redundant Measurements* (I. Borodii, supervisor H. Osukhivska, TNTU).

Audit run at **2026-09-20T11:59:59.953898+00:00** on **Raspberry Pi 5 Model B Rev 1.0**. The live `air_monitor.duckdb` was opened read-only via a snapshot copy only (same technique as the production MotherDuck replication job) — it was never opened for writing and no existing row was altered.

## 1. Immutability / provenance

- Live table row count at audit start: **304,110**
- Live table row count in the frozen working copy: **304,110**
- Difference (**0** rows) is new data appended by the still-running live collector between the two snapshots taken a few seconds apart — not a modification of any existing row (`raw_observations` has no UPDATE path anywhere in the pipeline, only INSERT).
- Frozen dataset (this project's **primary dataset**, read-only from here on): `data/citi2026/primary_dataset_20260920T115959Z.duckdb`
- Coverage: **2026-04-16 00:46:25.616503+03:00 → 2026-09-20 14:56:38.661131+03:00**

## 2. Cadence

- Configured cadence: 30 s
- Median observed inter-sample interval (excluding flagged gaps): 30.00 s
- Gap threshold used: > 60 s (2× expected cadence)
- Gaps found: **68**, total **1248.44 h** of missing collection time

### Largest gaps

| start | end | duration (h) |
|---|---|---:|
| 2026-04-28 07:23:35.952624+00:00 | 2026-06-16 08:11:44.763552+00:00 | 1176.80 |
| 2026-09-13 11:06:47.090243+00:00 | 2026-09-14 20:42:07.252645+00:00 | 33.59 |
| 2026-09-13 01:22:49.988896+00:00 | 2026-09-13 11:02:15.517632+00:00 | 9.66 |
| 2026-08-18 07:06:25.192866+00:00 | 2026-08-18 15:53:59.838221+00:00 | 8.79 |
| 2026-04-26 22:32:15.453605+00:00 | 2026-04-27 04:54:44.308896+00:00 | 6.37 |
| 2026-04-27 19:28:42.346497+00:00 | 2026-04-28 00:01:24.312008+00:00 | 4.54 |
| 2026-06-24 23:56:25.577114+00:00 | 2026-06-25 03:01:48.586265+00:00 | 3.09 |
| 2026-04-27 17:57:44.437054+00:00 | 2026-04-27 19:28:42.346497+00:00 | 1.52 |
| 2026-06-18 01:38:30.371466+00:00 | 2026-06-18 02:03:04.040453+00:00 | 0.41 |
| 2026-06-26 02:03:18.813220+00:00 | 2026-06-26 02:21:46.420901+00:00 | 0.31 |
| 2026-06-17 01:41:14.940322+00:00 | 2026-06-17 01:58:36.514605+00:00 | 0.29 |
| 2026-04-26 15:01:38.161827+00:00 | 2026-04-26 15:14:08.683457+00:00 | 0.21 |
| 2026-06-24 23:40:51.942783+00:00 | 2026-06-24 23:53:07.474318+00:00 | 0.20 |
| 2026-04-21 17:10:48.625871+00:00 | 2026-04-21 17:21:22.607906+00:00 | 0.18 |
| 2026-04-19 21:57:47.879700+00:00 | 2026-04-19 22:07:38.363058+00:00 | 0.16 |

The largest gap is the documented Sep 13 04:22 → Sep 14 23:41 venv-corruption outage (see project memory `project_air_monitor`) — a real device-down period, not a data artefact. It must be excluded from any day used for training/testing (whole-day split, see §5) rather than imputed.

## 3. Duplicates

- Duplicate `ts` values: **0**
- Duplicate `(batch_id, row_in_batch)` pairs: **0**

## 4. Per-channel audit

Full table: `research_results/citi2026/phase0/per_channel_audit.csv`. Headline channels (the ones this paper reasons about):

| channel | coverage % | missing % | min | max | mean | std | flatline runs (≥5) | longest run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Temperature (SCD41) | 95.985 | 4.015 | 18.3 | 130 | 24.4 | 2.61 | 5 | 6 |
| Temperature (BME688) | 96.347 | 3.653 | 19 | 193 | 25.4 | 2.76 | 11045 | 132 |
| Relative humidity (SCD41) | 95.985 | 4.015 | 23.6 | 100 | 49.2 | 7.58 | 0 | 4 |
| Relative humidity (BME688) | 96.347 | 3.653 | 17.4 | 100 | 42.7 | 7.3 | 23 | 8 |
| CO2 (SCD41) | 95.985 | 4.015 | 204 | 6.55e+04 | 677 | 330 | 107 | 7 |
| PM2.5 (SPS30) | 98.518 | 1.482 | 0.506 | 2.87e+04 | 291 | 1.77e+03 | 0 | 1 |
| PM10 (SPS30) | 98.518 | 1.482 | 0.531 | 4.81e+04 | 292 | 1.77e+03 | 0 | 1 |
| Gas-sensor resistance (BME688) | 11.200 | 88.800 | 3.23e+07 | 1.02e+08 | 8.44e+07 | 2.32e+07 | 3 | 15171 |
| Barometric pressure (BME688) | 96.347 | 3.653 | -237 | 1.24e+03 | 979 | 18.8 | 2273 | 22 |

## 5. Status-field breakdown

See `research_results/citi2026/phase0/status_breakdown.json` for exact counts of `sensor_status` / `scd41_status` / `bme688_status` / `sps30_status`.

## 6. Reproducibility

Full environment/provenance record: `research_results/citi2026/phase0/environment.json` (device, OS, Python/DuckDB/pandas/numpy versions, git commit of both repos, exact row counts, cutoff timestamp).
