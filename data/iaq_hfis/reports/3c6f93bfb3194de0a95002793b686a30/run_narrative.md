> **This is a reproducible, software-generated draft. Review before inclusion in a publication.**

# iaq_hfis Run Narrative

Run `3c6f93bfb3194de0a95002793b686a30` computed the hierarchical fuzzy indoor air quality index over 2026-06-18T21:00:00+00:00 to 2026-07-27T20:29:16+00:00, using a 15-minute rolling window, recomputed at each aligned timestamp (11231 timestamps processed).

No provisional parameters were engaged for this run's actual computed timestamps.

## Completeness
Of 11231 computed timestamps, 10242 were OK (all three components available with sufficient coverage), 442 were PARTIAL (one component unavailable), and 547 were FAILED (index and class not formed).

## Method comparison
- CRISP-MAX and PROPOSED-HFIS agreed on 100.0% of 10678 compared timestamps (Cohen's kappa=1.000).
- CRISP-MAX and WEIGHTED-MEAN agreed on 24.3% of 10696 compared timestamps (Cohen's kappa=0.078).
- PROPOSED-HFIS and WEIGHTED-MEAN agreed on 24.2% of 10678 compared timestamps (Cohen's kappa=0.077).
- CRISP-MAX hid a component that individually reached Critical in 0.0% of 4231 such events.
- WEIGHTED-MEAN hid a component that individually reached Critical in 99.4% of 4231 such events.
- Against the synthetic boundary-adjacent ground truth (n=42), PROPOSED-HFIS scored macro-F1=0.869, Cohen's kappa=0.807.
- Against the synthetic boundary-adjacent ground truth (n=42), CRISP-MAX scored macro-F1=0.869, Cohen's kappa=0.807.
- Against the synthetic boundary-adjacent ground truth (n=42), WEIGHTED-MEAN scored macro-F1=0.153, Cohen's kappa=-0.041.

## Stability and sensitivity
Under 30 perturbation trials (fixed seed=42, each channel perturbed within its declared sensor uncertainty) sampled at 2026-07-27T23:25:00+03:00, the index class changed from the baseline (Acceptable) in 16.7% of trials.
Sensitivity to window duration and coverage threshold was swept at the manuscript-specified values (see the Sensitivity section of run_summary.md and sensitivity_window.csv / sensitivity_coverage.csv).

## Scientific cautions

- Outdoor carbon monoxide (CO) is a distinct pollutant from indoor CO2 and is never used as a CO2 substitute.
- Outdoor atmospheric data are used only as context (confirming data-quality decisions and selecting the seasonal temperature profile) and are never a direct input to the index.
- The WHO PM2.5/PM10 reference points are 24-hour averaging guidelines; using them as control points for a 15-minute index is an operational adaptation, not a WHO compliance assessment.
- This 15-minute index is an operational, short-term indicator; it is not a regulatory or WHO compliance measurement.
- The CO2 thresholds represent an operational ventilation scale, not a universal toxicity limit -- CO2 interpretation depends on occupancy, ventilation rate, and room type.
- Temperature and humidity control regions are room- and season-specific; the profile actually used for this run is recorded above, including whether it is a provisional stand-in.
- Several membership transition widths and confirmation/detection thresholds are provisional research configuration, not manuscript-derived values -- see 'Provisional parameters engaged' above.
- No accuracy or macro-F1/kappa claim is made against unlabeled real observations; those metrics are computed only against the synthetic, pre-labeled ground-truth vectors reported under 'Method comparison'.

> **This is a reproducible, software-generated draft. Review before inclusion in a publication.**