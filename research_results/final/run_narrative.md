> **This is a reproducible, software-generated draft. Review before inclusion in a publication.**

# iaq_hfis Run Narrative

Run `2bb2374fbdcc4fbda817178b3b07eb4c` computed the hierarchical fuzzy indoor air quality index over 2026-06-18T00:00:00+00:00 to 2026-08-04T16:24:02+00:00, using a 15-minute rolling window, recomputed at each aligned timestamp (13732 timestamps processed).

Provisional parameters engaged this run (16): cadence.slot_match_tolerance_seconds; confirmation.gradual_drift_magnitude_multiplier; confirmation.gradual_drift_min_consecutive_steps; confirmation.persistence_min_consecutive_samples; confirmation.pm_cross_channel_tolerance_pct; confirmation.stuck_value_min_repeats; control_regions.output.transition_widths; control_regions.relative_humidity.transition_width; evaluation.masking_severity_threshold; evaluation.stability_n_trials; evaluation.stability_seed; fuzzy_engine.partial_mode_inference_rule; hampel.mad_multiplier; hampel.window_size; membership.output_transition_width; profile_selection.season_month_ranges. Results depending on these should be treated as preliminary until the author confirms the underlying values.

## Completeness
Of 13732 computed timestamps, 12232 were OK (all three components available with sufficient coverage), 769 were PARTIAL (one component unavailable), and 731 were FAILED (index and class not formed).
Dominant-component frequency across OK/PARTIAL computed timestamps: A: 4268 (32.8%), M: 7888 (60.7%), V: 845 (6.5%).

## Method comparison
Evaluation run `410c40df13524947a383b8aaecacf887` (the selected evaluation for this pipeline run):
- CRISP_CLASS_MAX and FUZZY_COMPONENT_MAX agreed on 99.8% of 13143 compared timestamps (unlabeled agreement, Cohen's kappa=0.998).
- CRISP_CLASS_MAX and PROPOSED_HFIS agreed on 99.8% of 13001 compared timestamps (unlabeled agreement, Cohen's kappa=0.998).
- CRISP_CLASS_MAX and WEIGHTED_MEAN agreed on 31.5% of 13143 compared timestamps (unlabeled agreement, Cohen's kappa=0.141).
- FUZZY_COMPONENT_MAX and PROPOSED_HFIS agreed on 100.0% of 13001 compared timestamps (unlabeled agreement, Cohen's kappa=1.000).
- FUZZY_COMPONENT_MAX and WEIGHTED_MEAN agreed on 31.4% of 13143 compared timestamps (unlabeled agreement, Cohen's kappa=0.140).
- PROPOSED_HFIS and WEIGHTED_MEAN agreed on 30.7% of 13001 compared timestamps (unlabeled agreement, Cohen's kappa=0.133).
- FUZZY_COMPONENT_MAX hid a component that individually reached Critical in 0.0% of 5074 such events.
- CRISP_CLASS_MAX hid a component that individually reached Critical in 0.0% of 5074 such events.
- WEIGHTED_MEAN hid a component that individually reached Critical in 98.4% of 5074 such events.
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), PROPOSED_HFIS scored macro-F1=0.908, Cohen's kappa=0.871 (consistency, not empirical accuracy).
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), FUZZY_COMPONENT_MAX scored macro-F1=0.908, Cohen's kappa=0.871 (consistency, not empirical accuracy).
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), CRISP_CLASS_MAX scored macro-F1=1.000, Cohen's kappa=1.000 (consistency, not empirical accuracy).
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), WEIGHTED_MEAN scored macro-F1=0.153, Cohen's kappa=-0.041 (consistency, not empirical accuracy).

## Stability and sensitivity
Multi-point stability: 30 deterministically-sampled computed_ts (boundary-adjacent + random-comparison, seed=42), 30 perturbation trials each (every available channel perturbed within its declared sensor uncertainty).
- CRISP_CLASS_MAX: class changed in 35.0% of 900 trials, 95% CI [32.0%, 38.2%] (moved to a strictly better class in 18.9% of trials, a strictly worse class in 16.1% -- these two sum to the class-change rate); mean absolute index change 8.75, p95 25.00.
- FUZZY_COMPONENT_MAX: class changed in 33.8% of 900 trials, 95% CI [30.8%, 36.9%] (moved to a strictly better class in 16.6% of trials, a strictly worse class in 17.2% -- these two sum to the class-change rate); mean absolute index change 7.03, p95 16.53.
- PROPOSED_HFIS: class changed in 33.8% of 900 trials, 95% CI [30.8%, 36.9%] (moved to a strictly better class in 16.6% of trials, a strictly worse class in 17.2% -- these two sum to the class-change rate); mean absolute index change 7.03, p95 16.53.
- WEIGHTED_MEAN: class changed in 5.3% of 900 trials, 95% CI [4.0%, 7.0%] (moved to a strictly better class in 3.0% of trials, a strictly worse class in 2.3% -- these two sum to the class-change rate); mean absolute index change 3.00, p95 7.21.
Multi-point sensitivity: 50 stratified sample points (strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favourable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale), swept across window durations and coverage thresholds (see sensitivity_window_summary.csv / sensitivity_coverage_summary.csv for per-value statistics).

## Boundary continuity
Deterministic input grids (21 points each) around 33 control-region boundaries, each swept under 3 'other components' contexts (acceptable, degraded, favourable), comparing PROPOSED_HFIS, FUZZY_COMPONENT_MAX, and WEIGHTED_MEAN numerically (see continuity_grid.csv / continuity_summary.csv).
- PROPOSED_HFIS: mean largest adjacent-point jump 1.74 index points across 99 boundary/context sweeps, 70 class transitions total.
- FUZZY_COMPONENT_MAX: mean largest adjacent-point jump 1.74 index points across 99 boundary/context sweeps, 70 class transitions total.
- WEIGHTED_MEAN: mean largest adjacent-point jump 0.60 index points across 99 boundary/context sweeps, 16 class transitions total.
- Smoothness (local Lipschitz ratio, 99 boundary/context pairs compared): PROPOSED_HFIS and FUZZY_COMPONENT_MAX had numerically identical local Lipschitz ratios on all 99 boundary/context pairs tested -- no smoothness advantage observed under this experimental design. This is expected, not a defect in either method: each sweep perturbs only ONE channel within a narrow +/-sensor-uncertainty window while the other channels are held at a FIXED representative value for the context; the worst-of rule base makes whichever channel has the higher severity dominate the aggregated result, and in this design one channel dominates the ENTIRE sweep (the swept channel's narrow local range essentially never crosses the fixed other channels' value), so both methods reduce to reporting that one dominant channel's own score throughout -- see docs/hfis_vs_crispmax_audit.md section 3 for the proof, and its independent multi-component synthetic check (section 2) for evidence the two methods DO diverge substantially once more than one channel is simultaneously close to the maximum severity.

## Fault-injection benchmark
Deterministic, pre-labeled synthetic scenarios (60 across co2, humidity, pm10, pm2_5, temperature), fully separate from the unlabeled real-data reason-code frequency below. Numbers here are the validation split ONLY -- a disjoint scenario set from calibration (which the Hampel grid below is tuned against), so no parameter was tuned against the numbers being reported (see fault_detection_metrics.csv, fault_detection_event_metrics.csv, fault_detection_confusion_matrix.csv for row-level, event-level, and confusion-matrix detail).
- single_spike (row-level): precision=0.020, recall=1.000, F1=0.039 (tp=7, fp=349, fn=0).
- stuck_value (row-level): precision=0.239, recall=1.000, F1=0.386 (tp=32, fp=102, fn=0).
- data_loss (row-level): precision=1.000, recall=1.000, F1=1.000 (tp=20, fp=0, fn=0).
- gradual_drift (row-level): precision=0.488, recall=1.000, F1=0.656 (tp=40, fp=42, fn=0).
- out_of_range (row-level): precision=1.000, recall=1.000, F1=1.000 (tp=5, fp=0, fn=0).
- single_spike (event-level, tolerance=1 samples): precision=0.061, recall=1.000, F1=0.116 (7 true event(s), 114 predicted event(s)).
- stuck_value (event-level, tolerance=1 samples): precision=0.400, recall=1.000, F1=0.571 (4 true event(s), 10 predicted event(s)).
- data_loss (event-level, tolerance=1 samples): precision=1.000, recall=1.000, F1=1.000 (4 true event(s), 4 predicted event(s)).
- gradual_drift (event-level, tolerance=1 samples): precision=0.571, recall=1.000, F1=0.727 (4 true event(s), 7 predicted event(s)).
- out_of_range (event-level, tolerance=1 samples): precision=1.000, recall=1.000, F1=1.000 (5 true event(s), 5 predicted event(s)).
- **Disclosed limitation**: single_spike, stuck_value scored row-level F1 below 0.5 on this benchmark -- reported here as-is, not hidden or excluded from the summary.
- Genuine sustained events falsely rejected: 0.0%.
- Hampel calibration grid (window_size x mad_multiplier) evaluated on calibration and validation scenario splits; current configuration (window_size=11, mad_multiplier=1.0) is retained regardless of this synthetic grid's outcome -- see hampel_calibration.csv and 'Provisional parameters engaged' above.

## Limitations

PROPOSED_HFIS and FUZZY_COMPONENT_MAX agreed on 100.0% of compared timestamps this run (Cohen's kappa=1.000, real unlabeled data -- agreement, not accuracy).
The boundary continuity experiment additionally found the two methods numerically tied on every one of 99 boundary/context pairs tested this run (see 'Boundary continuity' above and docs/hfis_vs_crispmax_audit.md) -- an intrinsic property of the single-channel-perturbation experimental design (see that section's own note), not independent evidence of general equivalence.
**PROPOSED_HFIS and FUZZY_COMPONENT_MAX are effectively equivalent at the classification level on this run's measurements.** Stated explicitly, not minimized: where the two methods coincide numerically, PROPOSED_HFIS's remaining value is structural, not demonstrated as an empirical advantage by this run's results alone -- (a) continuous within-class severity via centroid defuzzification and the explicit per-component membership degrees (component_scores_timeseries.csv's membership_* columns), which FUZZY_COMPONENT_MAX's raw max() never computes; (b) graded uncertainty representation -- simultaneous partial membership in more than one class per component, with no equivalent in a hard maximum; (c) extensibility -- a two-level rule base can express component-interaction logic (e.g. rules conditioned on two components being simultaneously non-favourable) that a scalar max() cannot express by construction, though the worst-of rule base actually configured here has not been extended to exercise that capability. An independent synthetic check (docs/hfis_vs_crispmax_audit.md section 2) shows the two methods DO diverge substantially (mean |difference| ~5.7 index points on a 0-100 scale) once more than one component is simultaneously close to its most severe class -- a condition this dataset rarely presents (see 'Dominant-component frequency' above: one component typically dominates).

- 16 provisional parameter(s) were engaged this run -- see 'Provisional parameters engaged' above and the generated provisional_parameter_assessment.md for what each one's status actually implies (whether calibrated, against what dataset, whether conclusions depend strongly on it).
- The boundary continuity experiment and the fault-injection benchmark are both deterministic, synthetic constructions -- they show the inference method and the data-quality detection layer behave as designed on known, controlled inputs; they do not measure performance across the full range of conditions the actual live sensor deployment may encounter.
- Fault-injection precision is weak for single_spike, stuck_value on this run's validation split (F1 below 0.5) -- disclosed here, not excluded from the summary above.
- Multi-point stability and sensitivity are deterministic, bounded SAMPLES of the evaluated range (boundary-adjacent + random-comparison for stability; stratified for sensitivity), not exhaustive coverage of every computed_ts.
- No empirical, ground-truth-labeled accuracy claim exists or is possible for this deployment -- every consistency/agreement/precision figure above is against either unlabeled real data or a synthetic, pre-labeled construction (see 'Forbidden overclaims' below).

## Forbidden overclaims

This narrative, and any prose built from it, must never do the following:

- Do not report agreement (real, unlabeled data) or stability (self-consistency under perturbation) as accuracy.
- Do not report reference-case or fault-injection consistency/precision/recall against synthetic, pre-labeled data as real-world empirical accuracy.
- Do not claim a PROVISIONAL parameter is validated because a synthetic benchmark's calibration grid favored its configured value -- that result is scoped to the benchmark, never universal.
- Do not claim PROPOSED_HFIS is smoother than FUZZY_COMPONENT_MAX, or vice versa, without checking this run's own continuity smoothness_comparison -- the single-channel-perturbation design can force the two methods to coincide regardless of context (see docs/hfis_vs_crispmax_audit.md).
- Do not describe a FAILED or PARTIAL-completeness computed_ts's absent index value as low or zero -- it is undefined, not low.
- Do not use outdoor CO as a proxy for indoor CO2, or WHO 24-hour PM reference points as a compliance assessment for a 15-minute index.
- Do not present sampled multi-point stability/sensitivity results as exhaustive coverage of every computed_ts.

## Scientific cautions

- Outdoor carbon monoxide (CO) is a distinct pollutant from indoor CO2 and is never used as a CO2 substitute.
- Outdoor atmospheric data are used only as context (confirming data-quality decisions and selecting the seasonal temperature profile) and are never a direct input to the index.
- The WHO PM2.5/PM10 reference points are 24-hour averaging guidelines; using them as control points for a 15-minute index is an operational adaptation, not a WHO compliance assessment.
- This 15-minute index is an operational, short-term indicator; it is not a regulatory or WHO compliance measurement.
- The CO2 thresholds represent an operational ventilation scale, not a universal toxicity limit -- CO2 interpretation depends on occupancy, ventilation rate, and room type.
- Temperature and humidity control regions are room- and season-specific; the profile actually used for this run is recorded above, including whether it is a provisional stand-in.
- Several membership transition widths and confirmation/detection thresholds are provisional research configuration, not manuscript-derived values -- see 'Provisional parameters engaged' above.
- Method agreement computed against unlabeled real observations is agreement only, never accuracy. Macro-F1/Cohen's kappa are reported only against the synthetic, pre-labeled reference cases under 'Method comparison', and describe consistency with those predefined labels, not real-world classification accuracy.

> **This is a reproducible, software-generated draft. Review before inclusion in a publication.**