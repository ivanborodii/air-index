# iaq_hfis Run Summary

Pipeline run ID: `49f2df39757245408465d4f274393e86`

## Run Metadata

- Status: **success**
- Started: 2026-07-31T09:58:47.440716+00:00
- Finished: 2026-07-31T11:51:23.643268+00:00
- Computed range: 2026-07-15T00:00:00+00:00 to 2026-07-29T00:00:00+00:00
- Window: 15 minutes
- Timestamps processed: 4032
- Snapshot retries: 0
- Config hash: `f5cde8425c2d994845d2d10d9545c8b79fa9f0ac4b92ba2cf78801aeee3e3909`
- Engine version: 0.1.0
- Selected evaluation run ID: 1ff631777e9c4f3a90351ebdc4b3a6cc

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: 64e5448d3e42b5074d1275b8723ae40ee0a09fc5
- git_tree_dirty: False
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 0
- PARTIAL: 3873
- FAILED: 159

Dominant-component frequency (OK/PARTIAL computed_ts only):
- A: 3625
- V: 248

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

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 0.9998 agreement, Cohen's kappa=0.9988 (n=4032, excluded=0)
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 0.9997 agreement, Cohen's kappa=0.9987 (n=3873, excluded=159)
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 0.9261 agreement, Cohen's kappa=0.5517 (n=4032, excluded=0)
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 1 agreement, Cohen's kappa=1 (n=3873, excluded=159)
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 0.9258 agreement, Cohen's kappa=0.5508 (n=4032, excluded=0)
- PROPOSED_HFIS vs WEIGHTED_MEAN: 0.9228 agreement, Cohen's kappa=0.515 (n=3873, excluded=159)

## Masking

- FUZZY_COMPONENT_MAX (>= Critical): rate=0 (0/74 events)
- CRISP_CLASS_MAX (>= Critical): rate=0 (0/74 events)
- WEIGHTED_MEAN (>= Critical): rate=0.6351 (47/74 events)

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
- CRISP_CLASS_MAX: class_change_rate=0.1578 (95% CI [0.1354, 0.183]), mean|Δindex|=3.944, p95|Δindex|=25, max|Δindex|=25
- FUZZY_COMPONENT_MAX: class_change_rate=0.15 (95% CI [0.1282, 0.1748]), mean|Δindex|=3.525, p95|Δindex|=16.22, max|Δindex|=25.02
- PROPOSED_HFIS: class_change_rate=0.15 (95% CI [0.1282, 0.1748]), mean|Δindex|=3.523, p95|Δindex|=16.22, max|Δindex|=25.02
- WEIGHTED_MEAN: class_change_rate=0.02556 (95% CI [0.01709, 0.03806]), mean|Δindex|=2.074, p95|Δindex|=8.914, max|Δindex|=21.68

## Sensitivity

- Sample points: 20
- Strata: completeness_PARTIAL, data_quality_event, outdoor_context_fresh, outdoor_context_stale
  - coverage_threshold=0.7: class_agreement=1, mean|Δindex|=0, n=20
  - coverage_threshold=0.8: class_agreement=1, mean|Δindex|=0, n=20
  - coverage_threshold=0.9: class_agreement=1, mean|Δindex|=0, n=20
  - window_minutes=5.0: class_agreement=1, mean|Δindex|=0.1059, n=20
  - window_minutes=15.0: class_agreement=1, mean|Δindex|=0, n=20
  - window_minutes=30.0: class_agreement=1, mean|Δindex|=0.4674, n=20
  - window_minutes=60.0: class_agreement=0.95, mean|Δindex|=1.217, n=20

## Fault / Reason-Code Frequency

- Status proportions (n=4032): OK=0, PARTIAL=0.9606, FAILED=0.03943
  - single_spike: 20990
  - stuck_value: 4867
  - out_of_range: 1943
  - gradual_drift: 642
  - data_loss: 10
