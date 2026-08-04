# iaq_hfis Run Summary

Pipeline run ID: `5cadd5e4f1cb4a84ab62be376f5e9728`

## Run Metadata

- Status: **success**
- Started: 2026-08-04T07:32:00.172287+00:00
- Finished: 2026-08-04T14:25:42.870892+00:00
- Computed range: 2026-06-18T00:00:00+00:00 to 2026-08-04T07:31:26+00:00
- Window: 15 minutes
- Timestamps processed: 13626
- Snapshot retries: 0
- Config hash: `d0a9f31ada5ffe122a5ecc472c54bd46de25992fc7298e84a624cd3378c2339c`
- Engine version: 0.1.0
- Selected evaluation run ID: 05f1c0bbf3d34bad99c5fdcd6157f4cc

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: 9cce835a62065353640ccf3d9ca09973cfda6754
- git_tree_dirty: False
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 0
- PARTIAL: 12564
- FAILED: 1062

Dominant-component frequency (OK/PARTIAL computed_ts only):
- A: 11508
- V: 1056

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
- Manuscript ready: **False**
  - Blocking: pipeline run mode='exploratory' -- only mode='publication' runs are manuscript-eligible (exploratory runs never fabricate the microclimate component)
  - Blocking: no OK-completeness computed_ts exist in this run -- a full A/V/M/I result was never produced
  - Unsupported claim: Full three-component (A/V/M/I) proposed-method result
- See `manuscript_readiness.md` for the standalone readiness report.

## Baseline Comparison (agreement, unlabeled real data)

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 0.9993 agreement, Cohen's kappa=0.9978 (n=12944, excluded=682)
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 0.9993 agreement, Cohen's kappa=0.9977 (n=12564, excluded=1062)
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 0.8569 agreement, Cohen's kappa=0.4086 (n=12944, excluded=682)
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 1 agreement, Cohen's kappa=1 (n=12564, excluded=1062)
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 0.8562 agreement, Cohen's kappa=0.4073 (n=12944, excluded=682)
- PROPOSED_HFIS vs WEIGHTED_MEAN: 0.8519 agreement, Cohen's kappa=0.3838 (n=12564, excluded=1062)

## Masking

- FUZZY_COMPONENT_MAX (>= Critical): rate=0 (0/281 events)
- CRISP_CLASS_MAX (>= Critical): rate=0 (0/281 events)
- WEIGHTED_MEAN (>= Critical): rate=0.605 (170/281 events)

## Reference-Case Consistency

Consistency with predefined synthetic boundary-adjacent labels -- NOT an empirical accuracy estimate.
- PROPOSED_HFIS: macro-F1=0.6622, Cohen's kappa=0.5495 (n=30, excluded=0)
- FUZZY_COMPONENT_MAX: macro-F1=0.6622, Cohen's kappa=0.5495 (n=30, excluded=0)
- CRISP_CLASS_MAX: macro-F1=0.7484, Cohen's kappa=0.6429 (n=30, excluded=0)
- WEIGHTED_MEAN: macro-F1=0.2082, Cohen's kappa=0.08257 (n=30, excluded=0)

## Stability

- Sample points: 30 (boundary-adjacent + random-comparison)
- Seed: 42 (fixed, reproducible)
- Trials per sample: 30
- CRISP_CLASS_MAX: class_change_rate=0.1311 (95% CI [0.1106, 0.1547]), mean|Δindex|=3.278, p95|Δindex|=25, max|Δindex|=25
- FUZZY_COMPONENT_MAX: class_change_rate=0.1244 (95% CI [0.1045, 0.1476]), mean|Δindex|=2.947, p95|Δindex|=12.81, max|Δindex|=20.08
- PROPOSED_HFIS: class_change_rate=0.1244 (95% CI [0.1045, 0.1476]), mean|Δindex|=2.958, p95|Δindex|=12.81, max|Δindex|=20.08
- WEIGHTED_MEAN: class_change_rate=0.05667 (95% CI [0.04336, 0.07374]), mean|Δindex|=1.885, p95|Δindex|=7.649, max|Δindex|=15.35

## Sensitivity

- Sample points: 20
- Strata: completeness_PARTIAL, data_quality_event, outdoor_context_fresh, outdoor_context_stale
  - coverage_threshold=0.7: class_agreement=0.95, mean|Δindex|=0, n=20
  - coverage_threshold=0.8: class_agreement=1, mean|Δindex|=0, n=20
  - coverage_threshold=0.9: class_agreement=1, mean|Δindex|=0, n=20
  - window_minutes=5.0: class_agreement=0.95, mean|Δindex|=1.603, n=20
  - window_minutes=15.0: class_agreement=1, mean|Δindex|=0, n=20
  - window_minutes=30.0: class_agreement=0.95, mean|Δindex|=0.379, n=20
  - window_minutes=60.0: class_agreement=0.9, mean|Δindex|=1.719, n=20

## Fault / Reason-Code Frequency

- Status proportions (n=13626): OK=0, PARTIAL=0.9221, FAILED=0.07794
  - single_spike: 68795
  - out_of_range: 32637
  - stuck_value: 15779
  - data_loss: 3008
  - gradual_drift: 1733
