# Artifact Validation Report

pipeline_run_id: `49f2df39757245408465d4f274393e86`

**Result: FAILED** -- 54 passed, 1 violation(s)

## Violations

- working tree has uncommitted changes -- a final publication snapshot must be built from a clean, committed tree

## Checks passed

- run_summary.json validates against config/run_summary.schema.json
- run_summary.json pipeline_run_id matches the requested pipeline_run_id
- evaluation section's pipeline_run_id/evaluation_run_id match the summary's own identifiers
- n_timestamps_processed (4032) == persisted iaq_index_results count (4032)
- completeness_summary sums to n_timestamps_processed (4032)
- every FAILED row has a null index_value, null index_class, and no dominant_component
- index_timeseries.csv row count (4032) == persisted iaq_index_results count (4032)
- status counts agree between run_summary.json and index_timeseries.csv
- run_summary.md contains the OK/PARTIAL/FAILED counts from run_summary.json
- run_narrative.md contains the OK/PARTIAL/FAILED counts from run_summary.json
- agreement n+n_excluded reconciles with method_comparison.csv row count for every method pair
- masking n_masked <= n_critical_events for every method
- stability_trials.csv row count for CRISP_CLASS_MAX (900) == n_trials_total (900)
- stability class_change_rate for CRISP_CLASS_MAX reconciles with stability_trials.csv
- stability_trials.csv row count for FUZZY_COMPONENT_MAX (900) == n_trials_total (900)
- stability class_change_rate for FUZZY_COMPONENT_MAX reconciles with stability_trials.csv
- stability_trials.csv row count for PROPOSED_HFIS (900) == n_trials_total (900)
- stability class_change_rate for PROPOSED_HFIS reconciles with stability_trials.csv
- stability_trials.csv row count for WEIGHTED_MEAN (900) == n_trials_total (900)
- stability class_change_rate for WEIGHTED_MEAN reconciles with stability_trials.csv
- stability by_variable rows for CRISP_CLASS_MAX sum to overall n_trials_total (900)
- stability by_original_class rows for CRISP_CLASS_MAX sum to overall n_trials_total (900)
- stability by_variable rows for FUZZY_COMPONENT_MAX sum to overall n_trials_total (900)
- stability by_original_class rows for FUZZY_COMPONENT_MAX sum to overall n_trials_total (900)
- stability by_variable rows for PROPOSED_HFIS sum to overall n_trials_total (900)
- stability by_original_class rows for PROPOSED_HFIS sum to overall n_trials_total (900)
- stability by_variable rows for WEIGHTED_MEAN sum to overall n_trials_total (900)
- stability by_original_class rows for WEIGHTED_MEAN sum to overall n_trials_total (900)
- every plot_manifest.json entry references columns that exist in its source CSV
- every PNG in plots/ corresponds to a current plot_manifest.json entry
- every rendered plot's declared source_csv still exists in exports/
- readiness.provisional_parameters_used matches run_summary.json's top-level provisional_parameters_used
- parameter_provenance.csv engaged provisional-like rows match run_summary.json's provisional_parameters_used
- run_summary.md names all 16 authoritative provisional parameters
- run_narrative.md names all 16 authoritative provisional parameters
- article_results_summary.md names all 16 authoritative provisional parameters
- sensitivity_window_summary.csv has no duplicate parameter settings
- sensitivity_window_summary.csv recomputes exactly from sensitivity_window_by_point.csv (tolerance 1e-06)
- run_summary.json sensitivity (window_minutes) agrees with sensitivity_window_summary.csv
- sensitivity_coverage_summary.csv has no duplicate parameter settings
- sensitivity_coverage_summary.csv recomputes exactly from sensitivity_coverage_by_point.csv (tolerance 1e-06)
- run_summary.json sensitivity (coverage_threshold) agrees with sensitivity_coverage_summary.csv
- continuity_grid.csv covers every manuscript-configured breakpoint for channel=pm2_5
- continuity_grid.csv covers every manuscript-configured breakpoint for channel=pm10
- continuity_grid.csv covers every manuscript-configured breakpoint for channel=co2
- continuity_grid.csv covers both two-sided channels (temperature, humidity)
- continuity_grid.csv is dense (contiguous grid_index) and monotonic (input_value) for every boundary/context/method
- continuity_summary.csv's max_adjacent_jump recomputes exactly from continuity_grid.csv
- fault_injection_events.csv's calibration and validation splits share no scenario_id (no data leakage)
- fault_detection_event_metrics.csv's n_true_events matches fault_injection_events.csv, and tp/fp/fn are internally consistent (one-to-one matching)
- fault_detection_confusion_matrix.csv's diagonal matches fault_detection_metrics.csv's row-level tp for every reason code
- evaluation_runs.config_hash matches run_summary.json's pipeline config_hash (evaluate was run against the same config as run)
- publication_claims_matrix.csv covers 9 claims, all with a valid status
- current git commit matches the commit recorded when this run was computed (same-commit invariant holds)
