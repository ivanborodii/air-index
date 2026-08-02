# iaq_hfis Run Summary

Pipeline run ID: `ea2cb02424ef4be99374f0f40a41d497`

## Run Metadata

- Status: **success**
- Started: 2026-08-02T11:23:09.310953+00:00
- Finished: 2026-08-02T13:17:27.091307+00:00
- Computed range: 2026-07-15T00:00:00+00:00 to 2026-07-29T00:00:00+00:00
- Window: 15 minutes
- Timestamps processed: 4032
- Snapshot retries: 0
- Config hash: `133162d56aa30bc8022c2be07a32d7436fb03c2010e92432070bbe8b34d3dc31`
- Engine version: 0.1.0
- Selected evaluation run ID: 0348eeaf3b5543818f2b3bf45bc89672

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: 3593efb0504d282396ab4d6b9404326e5f658e34
- git_tree_dirty: False
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 3836
- PARTIAL: 181
- FAILED: 15

Dominant-component frequency (OK/PARTIAL computed_ts only):
- A: 1536
- M: 2306
- V: 175

## Provisional Parameters Used

- cadence.slot_match_tolerance_seconds
- confirmation.gradual_drift_magnitude_multiplier
- confirmation.gradual_drift_min_consecutive_steps
- confirmation.persistence_min_consecutive_samples
- confirmation.pm_cross_channel_tolerance_pct
- confirmation.stuck_value_min_repeats
- control_regions.output.transition_widths
- control_regions.relative_humidity.transition_width
- evaluation.masking_severity_threshold
- evaluation.stability_n_trials
- evaluation.stability_seed
- fuzzy_engine.partial_mode_inference_rule
- hampel.mad_multiplier
- hampel.window_size
- membership.output_transition_width
- profile_selection.season_month_ranges

## Artifact and Manuscript Readiness

- Artifact ready: **True**
  - Warning: 16 provisional parameter(s) engaged this run -- disclosed in provisional_parameters_used, not resolved
  - Warning: 16 engaged provisional parameter(s) have no sensitivity-analysis coverage: cadence.slot_match_tolerance_seconds, confirmation.gradual_drift_magnitude_multiplier, confirmation.gradual_drift_min_consecutive_steps, confirmation.persistence_min_consecutive_samples, confirmation.pm_cross_channel_tolerance_pct, confirmation.stuck_value_min_repeats, control_regions.output.transition_widths, control_regions.relative_humidity.transition_width, evaluation.masking_severity_threshold, evaluation.stability_n_trials, evaluation.stability_seed, fuzzy_engine.partial_mode_inference_rule, hampel.mad_multiplier, hampel.window_size, membership.output_transition_width, profile_selection.season_month_ranges
- Manuscript ready: **True**
- See `manuscript_readiness.md` for the standalone readiness report.

## Baseline Comparison (agreement, unlabeled real data)

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 0.998 agreement, Cohen's kappa=0.9973 (n=4032, excluded=0)
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 0.998 agreement, Cohen's kappa=0.9973 (n=4017, excluded=15)
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 0.4266 agreement, Cohen's kappa=0.1714 (n=4032, excluded=0)
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 1 agreement, Cohen's kappa=1 (n=4017, excluded=15)
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 0.4251 agreement, Cohen's kappa=0.1695 (n=4032, excluded=0)
- PROPOSED_HFIS vs WEIGHTED_MEAN: 0.423 agreement, Cohen's kappa=0.1678 (n=4017, excluded=15)

## Masking

- FUZZY_COMPONENT_MAX (>= Critical): rate=0 (0/755 events)
- CRISP_CLASS_MAX (>= Critical): rate=0 (0/755 events)
- WEIGHTED_MEAN (>= Critical): rate=0.9907 (748/755 events)

## Reference-Case Consistency

Consistency with predefined synthetic boundary-adjacent labels -- NOT an empirical accuracy estimate.
- PROPOSED_HFIS: macro-F1=0.9085, Cohen's kappa=0.8708 (n=42, excluded=0)
- FUZZY_COMPONENT_MAX: macro-F1=0.9085, Cohen's kappa=0.8708 (n=42, excluded=0)
- CRISP_CLASS_MAX: macro-F1=1, Cohen's kappa=1 (n=42, excluded=0)
- WEIGHTED_MEAN: macro-F1=0.1528, Cohen's kappa=-0.04077 (n=42, excluded=0)

## Stability

- Sample points: 30 (boundary-adjacent + random-comparison)
- Seed: 42 (fixed, reproducible)
- Trials per sample: 30
- CRISP_CLASS_MAX: class_change_rate=0.3811 (95% CI [0.35, 0.4133]), mean|Δindex|=9.528, p95|Δindex|=25, max|Δindex|=25
- FUZZY_COMPONENT_MAX: class_change_rate=0.3678 (95% CI [0.3369, 0.3998]), mean|Δindex|=7.615, p95|Δindex|=17.79, max|Δindex|=26.45
- PROPOSED_HFIS: class_change_rate=0.3678 (95% CI [0.3369, 0.3998]), mean|Δindex|=7.578, p95|Δindex|=17.59, max|Δindex|=26.45
- WEIGHTED_MEAN: class_change_rate=0.07222 (95% CI [0.05707, 0.09101]), mean|Δindex|=3.111, p95|Δindex|=7.231, max|Δindex|=11.57

## Sensitivity

- Sample points: 50
- Strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favorable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale
  - coverage_threshold=0.7: class_agreement=0.96, mean|Δindex|=1.565, n=50
  - coverage_threshold=0.8: class_agreement=1, mean|Δindex|=0, n=50
  - coverage_threshold=0.9: class_agreement=0.96, mean|Δindex|=0, n=50
  - window_minutes=5.0: class_agreement=0.9, mean|Δindex|=4.45, n=50
  - window_minutes=15.0: class_agreement=1, mean|Δindex|=0, n=50
  - window_minutes=30.0: class_agreement=0.92, mean|Δindex|=1.236, n=50
  - window_minutes=60.0: class_agreement=0.82, mean|Δindex|=4.677, n=50

## Fault / Reason-Code Frequency

- Status proportions (n=4032): OK=0.9514, PARTIAL=0.04489, FAILED=0.00372
  - single_spike: 20990
  - stuck_value: 4867
  - out_of_range: 1943
  - gradual_drift: 642
  - data_loss: 10
