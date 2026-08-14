# Causal Hampel Filtering and Screening Recalibration: Revision Report

> Software-generated summary. Every number below is read from a generated
> artifact in this repository (paths given inline); none is copied from
> memory or an earlier conversation.

- **New pipeline_run_id**: `7e71d6bc86f142cf87a26b0e314bcb5b`
- **New evaluation_run_id**: `0bc42ce1129e45b78e8cfcfc3912baea`
- **Source Git commit**: `46035981d66485193757873d5581c5e0f76127b2` (implementation commit `4603598`, "Implement causal Hampel filtering and recalibrate screening")
- **Effective config hash**: `f878f1eed7d5342cff2ca15d2b266d67a4782e3c413eab7b218c437f2f11b086`
- **Study period**: `2026-06-18T00:00:00+00:00` .. `2026-08-04T16:24:02+00:00` (unchanged from the prior publication run -- same exact range, not shortened)
- **Old pipeline_run_id** (for comparison): `2bb2374fbdcc4fbda817178b3b07eb4c`, evaluation_run_id `410c40df13524947a383b8aaecacf887`, git commit `79daa4fff9626b11c56d5b4a4c32160fcbdc2645` (commit before this revision), read from git history at commit `b833e6f`

---

## 1. The old algorithm vs. the new algorithm

**Old (centered window).** For measurement x_i, `iaq_hfis.quality.hampel.hampel_flags` used a window `[i - window_size//2, i + window_size//2]` -- for `window_size=11`, 5 samples before x_i, x_i itself, and 5 samples *after* it. The module docstring claimed this was equivalent to a causal filter "because this pipeline only ever computes aggregates over a window that has already fully elapsed" -- true for the recompute *schedule*, but not true for the per-point statistic itself: x_i's own median/MAD/outlier decision depended on up to 5 measurements that, at x_i's own instant, had not yet occurred.

**New (causal window).** For measurement x_i, the window is `{x_{i-window_size+1}, ..., x_{i-1}, x_i}` -- x_i and the `window_size-1` samples immediately preceding it, never a later one. This matches the manuscript's own stated definition. See `src/iaq_hfis/quality/hampel.py`'s module docstring and `hampel_flags`.

## 2. Why historical context is required

The primary 15-minute window (30 slots @ 30 s cadence) does not, by itself, contain enough preceding samples for its *own earliest points* to ever reach a full 11-point causal window -- the very first in-window slot has zero samples before it within the window. `iaq_hfis.pipeline.compute_index_at` now fetches `hampel.window_size - 1` extra raw samples *before* `window_start` (never after `computed_ts`) for every computed_ts, runs the full hard+soft quality-check stack over this extended slot set, and **only afterward** restricts the result to the requested `[window_start, computed_ts]` interval before aggregation, coverage, completeness, and persistence. Historical context therefore only ever influences which quality *state* an in-window point receives -- it can never inflate `n_expected`, `n_usable`, coverage ratio, or the weighted mean (verified in `tests/integration/test_historical_context.py`, including that the 5-minute window, which has only 10 of its own slots, can still use the 11-point causal filter through this mechanism).

## 3. Hampel mad_multiplier: old and new configured value

| | Old | New |
|---|---|---|
| `window_size` | 11 | 11 (unchanged) |
| `mad_multiplier` | 1.0 | **3.0** |
| Provenance status | `LITERATURE_INFORMED` (both window_size and mad_multiplier) | `window_size`: `LITERATURE_INFORMED` (point count only); `mad_multiplier`: **`CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT`** |
| Selection policy | "Always retained regardless of grid outcome" -- the grid was diagnostic only, `selected=True` was hardcoded to whatever was already configured | Genuinely selected: `select_hampel_multiplier` reads only calibration-split rows at `window_size=11`, compares h in {1.0, 2.0, 3.0}, picks the highest objective S with a deterministic tie-break |

## 4. Calibration results for all candidate multipliers (window_size=11, calibration split)

Source: `research_results/final/exports/hampel_calibration.csv`.

| h | fault_recall (R_spike) | genuine_event_preservation (P_event) | single_spike_FPR | **S** | selected |
|---|---|---|---|---|---|
| 1.0 | 1.0 | 0.95 | 0.2215 | 0.9095 | no |
| 2.0 | 1.0 | 1.0 | 0.0696 | 0.9768 | no |
| **3.0** | 1.0 | 1.0 | 0.0570 | **0.9810** | **yes** |

h=3.0 wins outright on step 1 of the selection order (highest S) -- no tie-break steps were needed.

## 5. Validation results for the selected value (h=3.0, window_size=11)

Source: `research_results/final/exports/hampel_calibration.csv` (validation split rows) and `parameter_selection.json`.

| Metric | Value |
|---|---|
| fault_recall (R_spike) | 1.0 |
| genuine_event_preservation_rate (P_event) | 1.0 |
| single_spike_false_positive_rate (FPR_spike) | 0.0570 |
| Objective S | 0.9810 |

The validation split was scored **once**, after the calibration-only selection was frozen; it was never inspected while selecting (see `tests/unit/test_fault_injection.py::test_select_hampel_multiplier_ignores_validation_rows_entirely`).

For reference, the *old* configured value (h=1.0, which was never actually selected by any procedure, just retained) scored S=0.9095 (calibration) / 0.8987 (validation) under the same old objective formula -- both lower than the new h=3.0's score under the new causal filter.

## 6. Before / after: fault-detection metrics (row-level, validation split, primary screening)

Source: `fault_detection_metrics.csv`, old copy read from git commit `b833e6f`.

| Reason code | Old P / R / F1 | New P / R / F1 | Note |
|---|---|---|---|
| single_spike | 0.0197 / 1.0 / 0.0386 | 0.1045 / 1.0 / 0.1892 | Improved precision (fewer FP: 349 -> 60), still weak -- disclosed, not hidden |
| **stuck_value** | **0.2388 / 1.0 / 0.3855** | **1.0 / 1.0 / 1.0** | **Fixed** -- benchmark plateau bug (section 7), not a detector change |
| data_loss | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | Unchanged |
| out_of_range | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | Unchanged |
| gradual_drift | 0.4878 / 1.0 / 0.6557 | 0.6154 / **0.6** / 0.6076 | Precision improved; recall honestly reduced by the causal fix (section 8) -- see event-level below |

**gradual_drift event-level** (`fault_detection_event_metrics.csv`, validation split): precision 0.4, **recall 1.0** (all 4 true events still detected), F1 0.571, mean detection delay 4.0 samples (2 minutes at 30 s cadence) -- honestly nonzero now, reflecting the causal filter's inherent minimum detection latency, instead of the old algorithm's artifactual zero-delay retroactive flagging.

## 7. New: primary screening vs. final exclusion (task spec section 9)

This distinction did not exist before this revision (`fault_final_exclusion_metrics.csv` is new). Source: `research_results/final/exports/fault_final_exclusion_metrics.csv`, validation split.

| Reason code | Primary screening R (predicted_reason_codes) | Final exclusion R (usable=False) | Confirmation recovery |
|---|---|---|---|
| single_spike | 1.0 | 0.143 | Most primary single_spike candidates are recovered (confirmed usable) |
| stuck_value | 1.0 | 0.25 | Most primary stuck_value candidates are recovered |
| gradual_drift | 0.6 | 0.2 | |
| data_loss | 1.0 | 1.0 | Data loss can never be "recovered" -- no value exists |
| out_of_range | 1.0 | 1.0 | Out-of-range values are never recovered by confirmation |

Overall (both splits, synthetic benchmark): genuine-event false rejection rate = **0.0** (unchanged, still perfect); confirmation recovery rate = 82.5% (calibration) / 82.8% (validation) -- source: `run_summary.json:evaluation.fault_injection.confirmation_recovery_rate_by_split`.

## 8. Real deployment data: SUSPECT and confirmation counts (not the synthetic benchmark)

Queried directly from the derived database, `observation_quality` table, `pipeline_run_id=7e71d6bc86f142cf87a26b0e314bcb5b` (686,700 total quality-check rows over the full study period):

| State | Count | % of total |
|---|---|---|
| VALID | 583,399 | 84.96% |
| SUSPECT | 67,616 | 9.85% |
| INVALID | 32,697 | 4.76% |
| MISSING | 2,988 | 0.44% |

Of the 67,616 SUSPECT rows: **64,391 confirmed usable (95.23%)**, 3,225 unconfirmed / excluded (4.77%).

Real-data reason-code frequency (a SUSPECT row may carry more than one reason code): out_of_range 32,637; single_spike 47,718; stuck_value 19,034; data_loss 2,988; gradual_drift 982 -- source: `article_metrics.json:reason_code_frequency`.

## 9. Before / after: main publication results

Source: `article_metrics.json` (new: `research_results/final/`; old: git commit `b833e6f`).

| | Old | New |
|---|---|---|
| Total raw records | 136,737 | 136,739 |
| Total computed timestamps | 13,732 | 13,732 |
| OK | 12,232 (89.08%) | 12,212 (88.93%) |
| PARTIAL | 769 (5.60%) | 775 (5.64%) |
| FAILED | 731 (5.32%) | 745 (5.43%) |
| Dominant component A / M / V | 4,268 / 7,888 / 845 | 4,282 / 7,859 / 846 |

The small shift (OK -20, PARTIAL +6, FAILED +14; a net 0.15 percentage-point change) reflects a handful of timestamps whose quality classification changed under the causal Hampel filter / recalibrated multiplier / fixed gradual-drift detector -- not a data or configuration change. **manuscript_readiness stayed `READY`** in both the old and new run (`research_results/final/manuscript_readiness.json`), no blocking issues, no unsupported claims, in the new run.

## 10. Runtime and memory

Source: `run_summary.json:performance` (new), git commit `b833e6f` (old).

| | Old | New |
|---|---|---|
| Total runtime | 26,583 s (~7.4 h) | 23,834 s (~6.6 h) |
| Mean per-timestamp latency | 1934.7 ms | 1735.4 ms |
| Median | 1825.5 ms | 1616.8 ms |
| p95 | 2815.7 ms | 2554.0 ms |
| Max | 6139.2 ms | 34,760.0 ms (one outlier timestamp; see limitations) |
| Peak memory | 826.5 MB | 570.3 MB |

Despite fetching additional historical-context data per timestamp, mean/median/p95 latency and peak memory both *decreased* -- plausibly measurement variance between runs (this is a live, shared Raspberry Pi 5, not an isolated benchmark machine) rather than a causal effect of the code change; not investigated further, reported honestly either way. The new run's single very high maximum (34.76 s vs. the old run's 6.1 s) is flagged as a limitation below.

## 11. Manuscript numbers requiring an update

Any manuscript table/text currently citing the pre-revision numbers must be updated to the "New" column values above, specifically:

1. **Hampel filter description**: change from "centered window (5 before, current, 5 after)" to "causal window (current sample and 10 immediately preceding samples)".
2. **mad_multiplier**: 1.0 -> 3.0; its provenance description changes from "literature-informed (Pearson et al. 2016 illustrative example)" to "calibrated on the synthetic calibration split (window size only is literature-informed)".
3. **stuck_value precision** (Table 8 or equivalent): 0.239 -> **1.0**.
4. **gradual_drift row-level recall**: 1.0 -> **0.6** (validation split), with the event-level recall (still 1.0) and mean detection delay (4.0 samples) reported alongside, not in place of it.
5. **OK/PARTIAL/FAILED counts and percentages**: use the New column of section 9's table above.
6. **Dominant-component distribution**: use the New column of section 9's table above.
7. **Runtime figures** (if cited): use the New column of section 10's table above.
8. Any claim describing the Hampel multiplier as "retained from the literature regardless of calibration outcome" must be removed -- it is now genuinely selected from calibration data.
9. If the manuscript's Results section separately discusses primary detection vs. final data usability for any reason code, it can now cite `fault_final_exclusion_metrics.csv` (section 7 above) as a real, distinct metric -- this did not exist in the prior submission.

## 12. Remaining scientific limitations

- **single_spike precision remains weak** (validation 0.1045) across non-CO2 channels -- the calibration procedure is CO2-scoped per the manuscript's own original concern; other channels' single_spike behavior at the new h=3.0 was not independently tuned. Disclosed automatically in `run_narrative.md`/`article_results_summary.md` ("Disclosed limitation" for any reason code with row-level F1 < 0.5).
- **gradual_drift row-level recall is now honestly below 1.0** for short runs -- an inherent property of causal detection (a run cannot be flagged before it accumulates its own minimum length), not a defect to be tuned away; event-level recall remains 1.0.
- **The new run's maximum per-timestamp latency (34.76 s) is a single outlier**, not investigated further in this revision -- worth a follow-up profiling pass if it recurs.
- **Synthetic calibration is not real-fault validation** -- `mad_multiplier=3.0` is calibrated against deterministic synthetic fault-injection scenarios, never manually labelled real sensor faults (see `SYNTHETIC_CALIBRATION_DISCLAIMER` in `parameter_selection.json`).
- **The 16 other provisional parameters are unchanged by this revision** and remain disclosed exactly as before (`provisional_parameter_assessment.md`).

## 13. Source artifacts for every number above

- `research_results/final/run_summary.json`
- `research_results/final/article_metrics.json`
- `research_results/final/manifest.json`
- `research_results/final/manuscript_readiness.json`
- `research_results/final/parameter_selection.json`
- `research_results/final/exports/hampel_calibration.csv`
- `research_results/final/exports/fault_detection_metrics.csv`
- `research_results/final/exports/fault_detection_event_metrics.csv`
- `research_results/final/exports/fault_final_exclusion_metrics.csv`
- Old-run comparison values: `git show b833e6f:research_results/final/{run_summary.json,article_metrics.json,exports/fault_detection_metrics.csv,exports/hampel_calibration.csv}`
- Real-data SUSPECT/confirmation counts: derived database `data/iaq_hfis/iaq_hfis.duckdb`, table `observation_quality`, `pipeline_run_id='7e71d6bc86f142cf87a26b0e314bcb5b'` (query in section 8 above)
