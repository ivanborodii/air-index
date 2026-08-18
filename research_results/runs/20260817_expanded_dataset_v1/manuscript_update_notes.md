# Manuscript update notes (2026-08-17 expanded-dataset research run)

Every value below is traceable to a specific artifact under
`research_results/runs/20260817_expanded_dataset_v1/`. None of these edits
have been applied to the manuscript DOCX -- this document is input for the
author to apply by hand.

## 1. Dataset window (affects any table/figure citing the analysis period)

- **Old**: earlier published results (`research_results/final/`) covered a
  narrower window (2026-07-15..2026-07-29, per commit 76d2a87's
  `manuscript_readiness.md`).
- **New**: this run covers **2026-06-18T00:00:00Z (inclusive) to
  2026-08-16T00:00:00Z (exclusive)** -- 169,331 raw rows, 169,331 unique
  timestamps, 0 duplicate timestamps, 0 ordering violations, 0 rows outside
  the requested interval (`snapshot/data_interval_verification.json`).
- Baseline pipeline run (unchanged config/rules) over this window: 16,992
  computed timestamps at the 15-minute window, completeness OK=15,242
  (89.7%) / PARTIAL=1,004 (5.9%) / FAILED=746 (4.4%)
  (`baseline/baseline_run_manifest.json`).

## 2. Hampel MAD-multiplier selection (Section on the Hampel filter)

- The current shipped production value is `mad_multiplier=3.0` (unchanged
  by this sweep -- task explicitly forbids changing the production model
  merely to get better numbers).
- **Sweep finding**: over h in {1.0, 1.5, ..., 5.0}, both S_old and S_new
  select **h=5.0** on the calibration set, under every split method tested.
  Recall and genuine-event-preservation are already saturated (1.0) from
  h=1.5 upward; precision and F1 keep climbing to the edge of the tested
  range. **This means h=5.0 is only the best of the 9 values tested, not a
  proven optimum** -- the true optimum may lie beyond 5.0. Do not cite this
  sweep as establishing h=5.0 as optimal; cite it only as showing the
  currently-shipped h=3.0 is not the calibration-optimal choice among the
  values tested.
- Full numbers: `hampel_sweep/hampel_calibration_results.csv`,
  `hampel_validation_results.csv`, `hampel_selected_parameter.json`.
- **The "near 0.024" value referenced in review**: this is the
  **precision** (not recall/F1/FPR) of Hampel `single_spike` detection on
  the calibration split of the **exploratory-mode** evaluation run
  (`research_results/exploratory/run_summary.json`,
  `evaluation.fault_injection.row_level_metrics_by_split.calibration[0]`):
  precision=0.0215 (TP=7, FP=319, FN=0, TN=874; recall=1.0, F1=0.042,
  FPR=0.267). It never appeared in the published `final/` package (fault
  injection is exploratory-only). See `hampel_sweep/near_0024_value_explained.md`
  for the full derivation. **Suggested manuscript text**: state plainly that
  recall was perfect but precision was poor (98% of single_spike flags were
  false positives) in the exploratory diagnostic run, and that this
  motivated re-examining the multiplier (this sweep).

## 3. Missing-data strategy comparison (NEW section/table -- did not exist before)

- Evaluated on the chronological final-30% (validation) portion of
  complete-record-reference timestamps, 5 strategies x 8 masking cases.
- Headline finding (validation split, `component:M` masking): the
  **production "proposed" strategy (exclude the missing component) hides
  ~89-95% of complete-record-reference CRITICAL results** when temperature
  or the whole M component is masked -- worse than `locf` (~0-2%) at
  preserving CRITICAL detection, though `locf` has its own coverage
  limitations (10-minute lookback budget; falls back to "proposed" beyond
  that). See `missing_data_strategy/missing_data_strategy_summary.csv`
  columns `rate_hiding_critical_complete_record_reference`,
  `underestimation_rate`. **This is a genuine, unflattering finding about
  the manuscript's own proposed missing-data handling and should be
  reported as such, not smoothed over.**
- Bootstrap CIs (10,000 reps, block-by-day, seed 20260815, no degradation):
  `missing_data_strategy/missing_data_bootstrap_intervals.csv`.

## 4. Pollution vs. microclimate decomposition (NEW)

- Over 15,242 OK-completeness timestamps: current integrated index is
  Critical 44.9% of the time; a pollution-oriented index (A,V only, via the
  real engine with M excluded) is Critical only 3.4% of the time; the
  microclimate component (M) alone is Critical 44.1% of the time.
- Of the 6,841 timestamps where the current index is Critical, only 521
  (7.6%) remain Critical when only pollution (A,V) is considered --
  **microclimate (temperature/humidity), not aerosol/ventilation pollution,
  is the dominant driver of Critical classifications in this deployment**.
  Reported as an association for this dataset, not a causal claim.
- `co_dominant_components` was non-empty for 100% of OK timestamps in this
  run (`tie_rate=1.0`) -- flagged as worth the author's attention; verify
  against the manuscript's dominance-tie definition before citing, since a
  100% tie rate is unusual enough to warrant a second look at whether "tie"
  here means what the manuscript intends.
- `pollution_microclimate/pollution_microclimate_summary.json`,
  `critical_driver_summary.csv`, `critical_driver_by_day.csv`,
  `critical_driver_by_hour.csv`.

## 5. Second fuzzy level (rule audit + equivalence)

- Rule-level: all 64 index-level rules verified EXHAUSTIVELY (not sampled)
  to assign the worst-of-antecedents class, by construction
  (`second_level_equivalence/second_level_rule_audit.md`). This is a
  complete proof for the rule-level property -- but it does NOT by itself
  prove the aggregate numerical/class output of the two methods is
  identical (see below).
- **Real timestamps (n=15,242, actual deployment data)**: PROPOSED_HFIS and
  FUZZY_COMPONENT_MAX have **100% class agreement** (0 disagreements), even
  though their numerical index values differ at 2,209/15,242 timestamps
  (mean |diff|=0.021, p99=0.266, max=2.00 index points).
- **Synthetic grid, 41 points/axis (68,921 combinations of A,V,M)**: class
  agreement is **95.95%** (66,130/68,921 agree; 2,791 disagree) --
  **NOT 1.0**. This corrects an earlier finding from a first-pass coarse
  11-point grid (1,331 combinations) that showed 100% grid agreement too
  sparsely to catch the disagreement region -- kept here as a documented
  lesson: **grid density materially changes this conclusion**; do not cite
  the 11-point-grid number.
- **Correct manuscript framing**: the two methods are demonstrably NOT
  class-equivalent in general (proven by the denser synthetic grid), but
  they agree on every real timestamp that actually occurred in this
  deployment's ~2-month dataset. State both facts -- do not claim general
  class-equivalence from the real-data agreement alone, and do not claim
  the two methods are meaningfully different in this deployment's practice
  from the grid disagreement alone.
- `second_level_equivalence/second_level_equivalence_summary.json`,
  `second_level_equivalence_real.csv`, `second_level_equivalence_grid.csv`
  (deterministic 50,000-row sample of the full 68,921-row grid, seed
  20260815).

## 6. Data-quality reason accounting

- Status over the full 16,992-timestamp baseline run: OK=15,242 (89.7%),
  PARTIAL=1,004 (5.9%), FAILED=746 (4.4%).
- Reason-code rates are uneven by channel: `temperature` has the highest
  `stuck_value` rate (13.8% of temperature rows) and the highest overall
  SUSPECT rate (27.0%) of any channel; `co2`/`humidity` have the highest
  `single_spike` rates (7.1%/7.7%). Reported as reason-code frequencies
  only -- no hardware cause is claimed (no I2C/sensor-fault diagnosis;
  none of the recorded reason codes carry that information).
- 223 distinct continuous PARTIAL/FAILED intervals over the window; the
  longest is 77,100 seconds (~21.4 hours) -- worth the author checking
  against `air-monitor`'s own operational logs for that period (outside
  this research task's scope to diagnose further).
- `data_quality_reasons/data_quality_reason_summary.csv`,
  `data_quality_reason_by_sensor.csv`, `_by_day.csv`, `_by_hour.csv`,
  `data_quality_failure_intervals.csv`.

## 7. Runtime

- Full-pass inference only (stage1 shared membership/component inference +
  stage2), 2,000 real timestamps, 1 warmup + 5 timed reps, this Raspberry
  Pi 5: **PROPOSED_HFIS mean 1.37ms/timestamp**; **FUZZY_COMPONENT_MAX mean
  0.58ms/timestamp** (HFIS ~2.4x slower per timestamp than the crisp-max
  baseline, but both sub-2ms -- negligible for the 5-minute recompute
  cadence).
- Stage breakdown: stage1 (shared membership + component inference)
  ~0.19ms/ts; stage2 HFIS (2nd-level Mamdani + centroid) ~0.26ms/ts; stage2
  FUZZY_COMPONENT_MAX (plain max) ~0.0036ms/ts.
- **This is a narrower, inference-only measurement** -- it excludes DB
  snapshot/I-O, validation, and aggregation, which is why it is much faster
  than the README's previously-cited ~5s/timestamp full-pipeline figure.
  Do not conflate the two numbers in the manuscript; cite each for what it
  actually measures.
- `runtime_profiling/runtime_profiling_report.json`.

## 9. Boundary/stability (paired analysis, existing stability trials)

- PROPOSED_HFIS vs FUZZY_COMPONENT_MAX: **zero discordant pairs** across
  900 paired stability trials (exact McNemar p=1.0, bootstrap point_diff=0,
  CI=[0,0]) -- perfect agreement under input perturbation too, consistent
  with (but not proof of) the real-timestamp class-agreement finding above.
- PROPOSED_HFIS vs WEIGHTED_MEAN: highly significant difference (McNemar
  p=3.4e-40); WEIGHTED_MEAN changes class far more often under the same
  perturbations (class_change_rate difference +0.211, CI [0.127, 0.299]).
- `boundary_stability_paired/stability_paired_sign_test.csv`,
  `stability_paired_bootstrap_ci.csv`, `stability_class_flapping_summary.csv`.

## Limitations / deviations from the requested protocol (task section 15)

- The multi-component grid for section 8 was run at 41 points/axis (68,921
  combinations) rather than the requested 101 (1,030,301 combinations),
  after a first 101-point attempt exceeded a practical time budget on this
  Raspberry Pi partway through this session; documented here rather than
  silently substituted. The 41-point grid is still dense enough to have
  materially changed the class-agreement conclusion versus an initial
  coarser 11-point (module-default) attempt (see section 5 above), so it is
  not treated as a token substitute -- but a future 101-point run, given
  more time, could still refine the exact 95.95% figure further.
- `missing_data_strategy_predictions.csv` is the task-specified filename;
  the script (written in an earlier, interrupted session) originally used
  `missing_data_strategy_instances.csv` for identical content. Both were
  written during generation; the redundant `_instances.csv` copy (6.75MB,
  byte-identical to `_predictions.csv`) was removed before committing to
  avoid doubling repo size for no informational gain.
