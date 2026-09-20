# CITI-2026 Phase 4 — Day Split & Controlled Fault Injection

Seed: **42** (all randomness in this phase — day-split shuffling and fault placement — comes from one `np.random.default_rng(42)`).

## Day split

- train: 65 days
- test: 27 days
- excluded: 2 days

Stratified by calendar month, 70%/30% train/test within each month. 2026-09-13/09-14 (the venv-outage days, <20% coverage each) are excluded from both splits entirely — full table: `research_results/citi2026/phase4/day_split.csv`.

## Channel MAD (of first-difference, TRAIN days only)

| channel | MAD of diff (used as the amplitude-grid unit) |
|---|---:|
| scd_temp_c | 0.01335 |
| bme_temp_c | 0.01000 |
| scd_humidity_pct | 0.03357 |
| bme_humidity_pct | 0.02700 |

Computed on TRAIN days only, so no information from held-out test days leaks into the amplitude scale used to build the injected benchmark.

## Injected faults

Total instances: **1,528** across 4 channels x 4 fault types.

| fault type | channel | grid dimension | instances placed |
|---|---|---|---:|
| gradual_shift | bme_humidity_pct | amplitude (x MAD) | 99 |
| gradual_shift | bme_temp_c | amplitude (x MAD) | 94 |
| gradual_shift | scd_humidity_pct | amplitude (x MAD) | 93 |
| gradual_shift | scd_temp_c | amplitude (x MAD) | 94 |
| noise_burst | bme_humidity_pct | amplitude (x MAD) | 95 |
| noise_burst | bme_temp_c | amplitude (x MAD) | 93 |
| noise_burst | scd_humidity_pct | amplitude (x MAD) | 94 |
| noise_burst | scd_temp_c | amplitude (x MAD) | 96 |
| spike | bme_humidity_pct | amplitude (x MAD) | 98 |
| spike | bme_temp_c | amplitude (x MAD) | 94 |
| spike | scd_humidity_pct | amplitude (x MAD) | 98 |
| spike | scd_temp_c | amplitude (x MAD) | 98 |
| stuck_value | bme_humidity_pct | duration (samples) | 95 |
| stuck_value | bme_temp_c | duration (samples) | 94 |
| stuck_value | scd_humidity_pct | duration (samples) | 97 |
| stuck_value | scd_temp_c | duration (samples) | 96 |

By split: train=1074, test=454

**18.1%** of injected faults temporally overlap a Phase 3 weak-labelled real event — placement was uniformly random (not deliberately avoiding or seeking overlap), so this fraction reflects the real event base rate (~6.5% of samples) rather than a designed stress test; it is still enough overlapping instances (277) for Phase 7's false-event-rate metric to be computed meaningfully, not just theoretically defined.

Any placement attempt that could not find a valid, non-overlapping, hard-range-clean window within 200 tries was skipped rather than forced — see the per-combination counts above for any shortfall below the requested 20 replicates.

## Fault shape parameters (fixed, only amplitude/duration varies per the grid)

- gradual_shift: 10 min linear ramp to target, then holds 20 min (30 min total)
- spike: single-sample impulse, random sign
- noise_burst: 30 min of added zero-mean Gaussian noise, std = k x channel MAD
- stuck_value: freezes at the onset value; NO amplitude parameter (disclosed, not forced into the amplitude grid) — its grid dimension is duration instead ([5, 10, 20, 40, 80] samples = [2.5, 5.0, 10.0, 20.0, 40.0] min)

Output: `data/citi2026/injected_dataset.duckdb` (`observations_injected` + `fault_injection_log` tables). Full per-instance log: `research_results/citi2026/phase4/fault_injection_log.csv`.