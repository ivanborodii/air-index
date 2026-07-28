> **This is a reproducible, software-generated draft. Review before inclusion in a publication.**

# iaq_hfis Run Narrative

Run `47195a37fb52424cae0411555732c23f` computed the hierarchical fuzzy indoor air quality index over 2026-07-14T21:01:29+00:00 to 2026-07-28T21:01:29+00:00, using a 15-minute rolling window, recomputed at each aligned timestamp (4032 timestamps processed).

No provisional parameters were engaged for this run's actual computed timestamps.

## Completeness
Of 4032 computed timestamps, 3836 were OK (all three components available with sufficient coverage), 181 were PARTIAL (one component unavailable), and 15 were FAILED (index and class not formed).

## Method comparison
Evaluation run `fad333e03b9a4ed9ad07646ad653334e` (the selected evaluation for this pipeline run):
- CRISP-MAX and PROPOSED-HFIS agreed on 100.0% of 4017 compared timestamps (unlabeled agreement, Cohen's kappa=1.000).
- CRISP-MAX and WEIGHTED-MEAN agreed on 30.8% of 4032 compared timestamps (unlabeled agreement, Cohen's kappa=0.076).
- PROPOSED-HFIS and WEIGHTED-MEAN agreed on 30.5% of 4017 compared timestamps (unlabeled agreement, Cohen's kappa=0.074).
- CRISP-MAX hid a component that individually reached Critical in 0.0% of 904 such events.
- WEIGHTED-MEAN hid a component that individually reached Critical in 99.2% of 904 such events.
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), PROPOSED-HFIS scored macro-F1=0.869, Cohen's kappa=0.807 (consistency, not empirical accuracy).
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), CRISP-MAX scored macro-F1=0.869, Cohen's kappa=0.807 (consistency, not empirical accuracy).
- Against the synthetic, pre-labeled boundary-adjacent reference cases (n=42), WEIGHTED-MEAN scored macro-F1=0.153, Cohen's kappa=-0.041 (consistency, not empirical accuracy).

## Stability and sensitivity
Multi-point stability: 30 deterministically-sampled computed_ts (boundary-adjacent + random-comparison, seed=42), 30 perturbation trials each (every available channel perturbed within its declared sensor uncertainty).
- PROPOSED-HFIS: class changed in 37.2% of 900 trials, 95% CI [34.1%, 40.4%]; mean absolute index change 8.20, p95 19.43.
- CRISP-MAX: class changed in 37.2% of 900 trials, 95% CI [34.1%, 40.4%]; mean absolute index change 8.22, p95 19.43.
- WEIGHTED-MEAN: class changed in 8.4% of 900 trials, 95% CI [6.8%, 10.4%]; mean absolute index change 3.23, p95 7.82.
Multi-point sensitivity: 50 stratified sample points (strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favorable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale), swept across window durations and coverage thresholds (see sensitivity_window_summary.csv / sensitivity_coverage_summary.csv for per-value statistics).

## Boundary continuity
Deterministic input grids (21 points each) around 21 control-region boundaries, comparing PROPOSED-HFIS, CRISP-MAX, and WEIGHTED-MEAN numerically (see continuity_grid.csv / continuity_summary.csv).
- PROPOSED-HFIS: mean largest adjacent-point jump 2.61 index points across 21 boundaries, 25 class transitions total.
- CRISP-MAX: mean largest adjacent-point jump 2.61 index points across 21 boundaries, 25 class transitions total.
- WEIGHTED-MEAN: mean largest adjacent-point jump 0.87 index points across 21 boundaries, 4 class transitions total.

## Fault-injection benchmark
Deterministic, pre-labeled synthetic scenarios (8), fully separate from the unlabeled real-data reason-code frequency below (see fault_detection_metrics.csv).
- single_spike: precision=0.012, recall=1.000, F1=0.024 (tp=1, fp=82, fn=0).
- stuck_value: precision=0.205, recall=1.000, F1=0.340 (tp=8, fp=31, fn=0).
- data_loss: precision=1.000, recall=1.000, F1=1.000 (tp=5, fp=0, fn=0).
- gradual_drift: precision=1.000, recall=1.000, F1=1.000 (tp=10, fp=0, fn=0).
- out_of_range: precision=0.500, recall=1.000, F1=0.667 (tp=1, fp=1, fn=0).
- Genuine sustained events falsely rejected: 0.0%.
- Hampel calibration grid (window_size x mad_multiplier) evaluated on development and holdout scenario splits; current configuration (window_size=11, mad_multiplier=1.0) is retained regardless of this synthetic grid's outcome -- see hampel_calibration.csv and 'Provisional parameters engaged' above.

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