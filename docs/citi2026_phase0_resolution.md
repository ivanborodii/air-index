# CITI-2026 Phase 0 — Resolution of Open Decisions

Resolved 2026-09-20T12:07:57.894711+00:00, author-delegated ("resolve everything").

## Decision 1 — Analysis window

Primary analysis window: **2026-06-18 00:00:00 → 2026-09-20 00:00:00 (Kyiv, exclusive)** = **94 calendar days**, **263,873 rows**.
The pre-gap era (2026-04-16 → 2026-04-28, 34,060 rows) is excluded from analysis but **not deleted** — it remains in `raw_observations_full_history` in the same output file, for any later sensitivity check.

- Fully complete days (≥99% of 2880 expected samples): **87 / 94**
- Incomplete days: **7** — see `research_results/citi2026/phase0/day_completeness.csv` for the full day-by-day table (needed for Phase 5's whole-day split).

### Incomplete days (lowest coverage first)

| day | samples | % of expected |
|---|---:|---:|
| 2026-09-14 | 36 | 1.2 |
| 2026-09-13 | 535 | 18.6 |
| 2026-08-18 | 1812 | 62.9 |
| 2026-06-25 | 2484 | 86.2 |
| 2026-07-01 | 2815 | 97.7 |
| 2026-06-18 | 2831 | 98.3 |
| 2026-06-26 | 2844 | 98.8 |

The two lowest-coverage days are the known 2026-09-13/09-14 venv-corruption outage (see project memory `project_air_monitor`) — genuine device-down time. Phase 5 should exclude any day below the completeness threshold it adopts from both train and test splits rather than impute across a real multi-hour outage.

## Decision 2 — `gas_resistance_ohm` dropped from independent channels

Confirmed dropped from the Phase 3 weak-label/concordance independent-channel set (CO2, PM2.5, PM10, pressure remain). The column is untouched in the data — this is a usage decision, not a data change.

## Decision 3 — Hard datasheet-technical-range check

Reused verbatim from `config/sensor_specs.yaml` (already verified against manufacturer datasheets in the sibling iaq_hfis project — not re-derived or guessed here). A row failing a channel's technical range gets `hardcheck_fail_<channel> = TRUE` in both output tables; **no value is modified, nulled, or removed** — later phases decide how to use the flag (Phase 1 excludes flagged rows from bias/MAD/correlation stats; Phase 4 excludes flagged rows from the base signal used for synthetic fault injection, so pre-existing real faults never contaminate the injected ground-truth mask).

| channel | technical range | rows flagged | source |
|---|---|---:|---|
| co2_ppm | [400, 40000] | 181 | Sensirion SCD4x Datasheet v1.7 (April 2025), Table 1 p.3: CO2 output r… |
| scd_temp_c | [-10, 60] | 7 | Sensirion SCD4x Datasheet v1.7 (April 2025), Table 3 p.3: temperature … |
| scd_humidity_pct | [0, 100] | 0 | Sensirion SCD4x Datasheet v1.7 (April 2025), Table 2 p.3: humidity ran… |
| bme_temp_c | [-40, 85] | 2 | Bosch BME688 Datasheet Rev.1.3 BST-BME688-DS000-03 (Feb 2024), Table 1… |
| bme_humidity_pct | [0, 100] | 0 | Bosch BME688 Datasheet Rev.1.3 BST-BME688-DS000-03 (Feb 2024), Table 8… |
| pressure_hpa | [300, 1100] | 3 | Bosch BME688 Datasheet Rev.1.3 BST-BME688-DS000-03 (Feb 2024), Table 9… |
| mass_pm1_0 | [0, 1000] | 7600 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: mass conce… |
| mass_pm2_5 | [0, 1000] | 7663 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: mass conce… |
| mass_pm4_0 | [0, 1000] | 7695 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: mass conce… |
| mass_pm10 | [0, 1000] | 7701 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: mass conce… |
| number_pm0_5 | [0, 3000] | 8339 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: number con… |
| number_pm1_0 | [0, 3000] | 8670 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: number con… |
| number_pm2_5 | [0, 3000] | 8688 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: number con… |
| number_pm4_0 | [0, 3000] | 8690 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: number con… |
| number_pm10 | [0, 3000] | 8690 | Sensirion SPS30 Datasheet v2.0 D1 (June 2023), Table 1 p.2: number con… |

**Total rows with ≥1 hard-range violation: 8,810 out of 304,110 (2.897%)**

Note: PM channels account for the large majority of hard-range violations (~7,600-8,700 rows per PM sub-channel, vs. single/low-hundreds for CO2/temperature/pressure) — the SPS30's technical range (0-1000 ug/m3 mass, 0-3000 #/cm3 number) is genuinely exceeded on a meaningful fraction of rows, not just occasionally. Whether these are sensor-fault bursts or extreme real cooking-smoke events (both are physically plausible triggers for exceeding the sensor's rated range) is NOT decided here -- that judgement call belongs to Phase 1 (pair/channel characterisation) and Phase 3 (weak labels), which have the surrounding context (duration, co-occurrence with other channels) this hard check does not look at.

Output dataset: `data/citi2026/analysis_dataset_20260920T120752Z.duckdb` (`raw_observations_full_history` + `raw_observations_analysis` tables, both carrying the same `hardcheck_fail_*` columns).