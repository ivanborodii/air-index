# iaq_hfis Run Summary

Pipeline run ID: `2bb2374fbdcc4fbda817178b3b07eb4c`

## Run Metadata

- Status: **success**
- Started: 2026-08-04T16:24:33.699854+00:00
- Finished: 2026-08-04T23:47:36.733391+00:00
- Computed range: 2026-06-18T00:00:00+00:00 to 2026-08-04T16:24:02+00:00
- Window: 15 minutes
- Timestamps processed: 13732
- Snapshot retries: 0
- Config hash: `ebb05ee097084ab880c7c6671bb92bf891d467d1321d08429c6d6133b63101dc`
- Engine version: 0.1.0
- Selected evaluation run ID: 410c40df13524947a383b8aaecacf887

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: 79daa4fff9626b11c56d5b4a4c32160fcbdc2645
- git_tree_dirty: False
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 12232
- PARTIAL: 769
- FAILED: 731

Dominant-component frequency (OK/PARTIAL computed_ts only):
- A: 4268
- M: 7888
- V: 845

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

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 0.9983 agreement, Cohen's kappa=0.9975 (n=13143, excluded=589)
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 0.9982 agreement, Cohen's kappa=0.9975 (n=13001, excluded=731)
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 0.3154 agreement, Cohen's kappa=0.1411 (n=13143, excluded=589)
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 1 agreement, Cohen's kappa=1 (n=13001, excluded=731)
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 0.3142 agreement, Cohen's kappa=0.1395 (n=13143, excluded=589)
- PROPOSED_HFIS vs WEIGHTED_MEAN: 0.3067 agreement, Cohen's kappa=0.1335 (n=13001, excluded=731)

## Masking

- FUZZY_COMPONENT_MAX (>= Critical): rate=0 (0/5074 events)
- CRISP_CLASS_MAX (>= Critical): rate=0 (0/5074 events)
- WEIGHTED_MEAN (>= Critical): rate=0.984 (4993/5074 events)

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
- CRISP_CLASS_MAX: class_change_rate=0.35 (95% CI [0.3195, 0.3817]), mean|Δindex|=8.75, p95|Δindex|=25, max|Δindex|=25
- FUZZY_COMPONENT_MAX: class_change_rate=0.3378 (95% CI [0.3076, 0.3693]), mean|Δindex|=7.035, p95|Δindex|=16.53, max|Δindex|=24.8
- PROPOSED_HFIS: class_change_rate=0.3378 (95% CI [0.3076, 0.3693]), mean|Δindex|=7.026, p95|Δindex|=16.53, max|Δindex|=24.8
- WEIGHTED_MEAN: class_change_rate=0.05333 (95% CI [0.04046, 0.07]), mean|Δindex|=2.996, p95|Δindex|=7.206, max|Δindex|=13.78

## Sensitivity

- Sample points: 50
- Strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favourable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale
  - coverage_threshold=0.7: class_agreement=0.96, mean|Δindex|=2.342, n=50
  - coverage_threshold=0.8: class_agreement=1, mean|Δindex|=0, n=50
  - coverage_threshold=0.9: class_agreement=0.98, mean|Δindex|=1.216, n=50
  - window_minutes=5.0: class_agreement=0.9, mean|Δindex|=6.876, n=50
  - window_minutes=15.0: class_agreement=1, mean|Δindex|=0, n=50
  - window_minutes=30.0: class_agreement=0.88, mean|Δindex|=4.492, n=50
  - window_minutes=60.0: class_agreement=0.84, mean|Δindex|=6.47, n=50

## Fault / Reason-Code Frequency

- Status proportions (n=13732): OK=0.8908, PARTIAL=0.056, FAILED=0.05323
  - single_spike: 69325
  - out_of_range: 32637
  - stuck_value: 15916
  - data_loss: 2988
  - gradual_drift: 1779
