# iaq_hfis Run Summary

Pipeline run ID: `47195a37fb52424cae0411555732c23f`

## Run Metadata

- Status: **success**
- Started: 2026-07-28T21:02:18.395392+00:00
- Finished: 2026-07-28T23:02:12.772875+00:00
- Computed range: 2026-07-14T21:01:29+00:00 to 2026-07-28T21:01:29+00:00
- Window: 15 minutes
- Timestamps processed: 4032
- Snapshot retries: 0
- Config hash: `49fa03b6c0d202b58e8a533c3bd3e5febb1934234f5fbd081e99ff7a2fea31e1`
- Engine version: 0.1.0
- Selected evaluation run ID: fad333e03b9a4ed9ad07646ad653334e

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: a15562a887dec8f334b4addb9652e82be522a152
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 3836
- PARTIAL: 181
- FAILED: 15

## Provisional Parameters Used

None engaged this run.

## Publication Readiness

- Ready: **True**
- Warning: 16 provisional parameter(s) engaged this run -- disclosed in provisional_parameters_used, not resolved
- Warning: 16 engaged provisional parameter(s) have no sensitivity-analysis coverage: cadence.slot_match_tolerance_seconds, confirmation.gradual_drift_magnitude_multiplier, confirmation.gradual_drift_min_consecutive_steps, confirmation.persistence_min_consecutive_samples, confirmation.pm_cross_channel_tolerance_pct, confirmation.stuck_value_min_repeats, control_regions.output.transition_widths, control_regions.relative_humidity.transition_width, evaluation.masking_severity_threshold, evaluation.stability_n_trials, evaluation.stability_seed, fuzzy_engine.partial_mode_inference_rule, hampel.mad_multiplier, hampel.window_size, membership.output_transition_width, profile_selection.season_month_ranges

## Baseline Comparison (agreement, unlabeled real data)

- CRISP-MAX vs PROPOSED-HFIS: 1 agreement, Cohen's kappa=1 (n=4017, excluded=15)
- CRISP-MAX vs WEIGHTED-MEAN: 0.308 agreement, Cohen's kappa=0.07608 (n=4032, excluded=0)
- PROPOSED-HFIS vs WEIGHTED-MEAN: 0.3055 agreement, Cohen's kappa=0.07357 (n=4017, excluded=15)

## Masking

- CRISP-MAX (>= Critical): rate=0 (0/904 events)
- WEIGHTED-MEAN (>= Critical): rate=0.9923 (897/904 events)

## Reference-Case Consistency

Consistency with predefined synthetic boundary-adjacent labels -- NOT an empirical accuracy estimate.
- PROPOSED-HFIS: macro-F1=0.8689, Cohen's kappa=0.8073 (n=42, excluded=0)
- CRISP-MAX: macro-F1=0.8689, Cohen's kappa=0.8073 (n=42, excluded=0)
- WEIGHTED-MEAN: macro-F1=0.1528, Cohen's kappa=-0.04077 (n=42, excluded=0)

## Stability

- Sample points: 30 (boundary-adjacent + random-comparison)
- Seed: 42 (fixed, reproducible)
- Trials per sample: 30
- PROPOSED-HFIS: class_change_rate=0.3722 (95% CI [0.3412, 0.4043]), mean|Δindex|=8.196, p95|Δindex|=19.43, max|Δindex|=26.45
- CRISP-MAX: class_change_rate=0.3722 (95% CI [0.3412, 0.4043]), mean|Δindex|=8.222, p95|Δindex|=19.43, max|Δindex|=26.45
- WEIGHTED-MEAN: class_change_rate=0.08444 (95% CI [0.068, 0.1044]), mean|Δindex|=3.234, p95|Δindex|=7.821, max|Δindex|=13.24

## Sensitivity

- Sample points: 50
- Strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favorable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale
  - coverage_threshold=0.7: class_agreement=0.96, mean|Δindex|=1.565, n=50
  - coverage_threshold=0.8: class_agreement=1, mean|Δindex|=0, n=50
  - coverage_threshold=0.9: class_agreement=0.96, mean|Δindex|=0, n=50
  - window_minutes=5: class_agreement=0.86, mean|Δindex|=5.868, n=50
  - window_minutes=15: class_agreement=1, mean|Δindex|=0, n=50
  - window_minutes=30: class_agreement=0.94, mean|Δindex|=1.612, n=50
  - window_minutes=60: class_agreement=0.84, mean|Δindex|=5.2, n=50

## Fault / Reason-Code Frequency

- Status proportions (n=4032): OK=0.9514, PARTIAL=0.04489, FAILED=0.00372
  - single_spike: 20983
  - stuck_value: 4872
  - out_of_range: 1943
  - gradual_drift: 635
  - data_loss: 25
