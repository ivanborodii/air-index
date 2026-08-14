# iaq_hfis Run Summary

Pipeline run ID: `7e71d6bc86f142cf87a26b0e314bcb5b`

## Run Metadata

- Status: **success**
- Started: 2026-08-13T20:21:32.090532+00:00
- Finished: 2026-08-14T02:58:45.300660+00:00
- Computed range: 2026-06-18T00:00:00+00:00 to 2026-08-04T16:24:02+00:00
- Window: 15 minutes
- Timestamps processed: 13732
- Snapshot retries: 0
- Config hash: `f878f1eed7d5342cff2ca15d2b266d67a4782e3c413eab7b218c437f2f11b086`
- Engine version: 0.1.0
- Selected evaluation run ID: 0bc42ce1129e45b78e8cfcfc3912baea

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: 46035981d66485193757873d5581c5e0f76127b2
- git_tree_dirty: False
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 12212
- PARTIAL: 775
- FAILED: 745

Dominant-component frequency (OK/PARTIAL computed_ts only):
- A: 4282
- M: 7859
- V: 846

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

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 0.9984 agreement, Cohen's kappa=0.9978 (n=13157, excluded=575)
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 0.9984 agreement, Cohen's kappa=0.9977 (n=12987, excluded=745)
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 0.3185 agreement, Cohen's kappa=0.1436 (n=13157, excluded=575)
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 1 agreement, Cohen's kappa=1 (n=12987, excluded=745)
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 0.3174 agreement, Cohen's kappa=0.1421 (n=13157, excluded=575)
- PROPOSED_HFIS vs WEIGHTED_MEAN: 0.3085 agreement, Cohen's kappa=0.135 (n=12987, excluded=745)

## Masking

- FUZZY_COMPONENT_MAX (>= Critical): rate=0 (0/5059 events)
- CRISP_CLASS_MAX (>= Critical): rate=0 (0/5059 events)
- WEIGHTED_MEAN (>= Critical): rate=0.984 (4978/5059 events)

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
- CRISP_CLASS_MAX: class_change_rate=0.3456 (95% CI [0.3152, 0.3772]), mean|Δindex|=8.639, p95|Δindex|=25, max|Δindex|=25
- FUZZY_COMPONENT_MAX: class_change_rate=0.34 (95% CI [0.3098, 0.3716]), mean|Δindex|=7.155, p95|Δindex|=17.03, max|Δindex|=24.8
- PROPOSED_HFIS: class_change_rate=0.34 (95% CI [0.3098, 0.3716]), mean|Δindex|=7.146, p95|Δindex|=17.03, max|Δindex|=24.8
- WEIGHTED_MEAN: class_change_rate=0.06 (95% CI [0.04627, 0.07747]), mean|Δindex|=3.066, p95|Δindex|=7.116, max|Δindex|=13.95

## Sensitivity

- Sample points: 50
- Strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favourable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale
  - coverage_threshold=0.7: class_agreement=0.9, mean|Δindex|=5.834, n=50
  - coverage_threshold=0.8: class_agreement=1, mean|Δindex|=0, n=50
  - coverage_threshold=0.9: class_agreement=0.96, mean|Δindex|=1.097, n=50
  - window_minutes=5.0: class_agreement=0.9, mean|Δindex|=4.922, n=50
  - window_minutes=15.0: class_agreement=1, mean|Δindex|=0, n=50
  - window_minutes=30.0: class_agreement=0.88, mean|Δindex|=3.899, n=50
  - window_minutes=60.0: class_agreement=0.7, mean|Δindex|=13.35, n=50

## Fault / Reason-Code Frequency

- Status proportions (n=13732): OK=0.8893, PARTIAL=0.05644, FAILED=0.05425
  - single_spike: 47718
  - out_of_range: 32637
  - stuck_value: 19034
  - data_loss: 2988
  - gradual_drift: 982
