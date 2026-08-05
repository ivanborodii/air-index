# Article Results Summary

> Factual, validated-metrics-only summary for manual adaptation into the
> manuscript's Results/Discussion. Every number here is copied directly from
> `run_summary_5cadd5e4f1cb4a84ab62be376f5e9728.json` -- no claim beyond what the
> numbers themselves support. This is not manuscript prose.

## 1. Dataset and experiment period

- Period: 2026-06-18T00:00:00+00:00 to 2026-08-04T07:31:26+00:00
- Window: 15 minutes; recompute grid per config
- pipeline_run_id: `5cadd5e4f1cb4a84ab62be376f5e9728`; evaluation_run_id: `05f1c0bbf3d34bad99c5fdcd6157f4cc`
- config_hash: `d0a9f31ada5ffe122a5ecc472c54bd46de25992fc7298e84a624cd3378c2339c`; git commit: `9cce835a62065353640ccf3d9ca09973cfda6754`

## 2. Expected and processed calculation timestamps

- Processed: 13626

## 3. OK / PARTIAL / FAILED counts and percentages

- OK: 0 (0.0%)
- PARTIAL: 12564 (92.2%)
- FAILED: 1062 (7.8%)

## 4. Air-quality class distribution (successfully formed indices)

See `index_timeseries.csv` (completeness_status=OK rows, group by index_class) for the exact distribution.

Dominant-component frequency (which of A/V/M won the priority-hierarchy tie-break, OK/PARTIAL computed_ts only):
- A: 11508 (91.6%)
- V: 1056 (8.4%)

## 5. Inter-method agreement (unlabeled real data)

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 99.9% agreement, Cohen's kappa=0.998 (n=12944). This is agreement, not accuracy.
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 99.9% agreement, Cohen's kappa=0.998 (n=12564). This is agreement, not accuracy.
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 85.7% agreement, Cohen's kappa=0.409 (n=12944). This is agreement, not accuracy.
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 100.0% agreement, Cohen's kappa=1.000 (n=12564). This is agreement, not accuracy.
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 85.6% agreement, Cohen's kappa=0.407 (n=12944). This is agreement, not accuracy.
- PROPOSED_HFIS vs WEIGHTED_MEAN: 85.2% agreement, Cohen's kappa=0.384 (n=12564). This is agreement, not accuracy.

## 6. Adverse-component masking comparison

- FUZZY_COMPONENT_MAX (>= Critical): masking_rate=0.0% (0/281 events).
- CRISP_CLASS_MAX (>= Critical): masking_rate=0.0% (0/281 events).
- WEIGHTED_MEAN (>= Critical): masking_rate=60.5% (170/281 events).

## 7. HFIS vs FUZZY_COMPONENT_MAX numerical continuity

- PROPOSED_HFIS: mean largest adjacent-point jump 1.41 index points across 81 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- FUZZY_COMPONENT_MAX: mean largest adjacent-point jump 1.41 index points across 81 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- WEIGHTED_MEAN: mean largest adjacent-point jump 0.63 index points across 81 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- Smoothness comparison (local Lipschitz ratio, 81 boundary/context pairs): PROPOSED_HFIS and FUZZY_COMPONENT_MAX had numerically identical local Lipschitz ratios on all 81 boundary/context pairs tested -- no smoothness advantage observed under this experimental design. This is expected, not a defect in either method: each sweep perturbs only ONE channel within a narrow +/-sensor-uncertainty window while the other channels are held at a FIXED representative value for the context; the worst-of rule base makes whichever channel has the higher severity dominate the aggregated result, and in this design one channel dominates the ENTIRE sweep (the swept channel's narrow local range essentially never crosses the fixed other channels' value), so both methods reduce to reporting that one dominant channel's own score throughout -- see docs/hfis_vs_crispmax_audit.md section 3 for the proof, and its independent multi-component synthetic check (section 2) for evidence the two methods DO diverge substantially once more than one channel is simultaneously close to the maximum severity.

## 8. Multi-point stability results

- 30 sampled points, 30 trials each, seed=42.
  - CRISP_CLASS_MAX: class_change_rate=13.1% (moved better=6.6%, moved worse=6.6%), mean|Δindex|=3.28
  - FUZZY_COMPONENT_MAX: class_change_rate=12.4% (moved better=7.9%, moved worse=4.6%), mean|Δindex|=2.95
  - PROPOSED_HFIS: class_change_rate=12.4% (moved better=7.9%, moved worse=4.6%), mean|Δindex|=2.96
  - WEIGHTED_MEAN: class_change_rate=5.7% (moved better=4.0%, moved worse=1.7%), mean|Δindex|=1.89
- Breakdowns by boundary/channel (`stability_summary_by_variable.csv`) and by originating class (`stability_summary_by_original_class.csv`) are exported separately; not repeated here.

## 9. Multi-point sensitivity results

- 20 sampled points across strata: completeness_PARTIAL, data_quality_event, outdoor_context_fresh, outdoor_context_stale.
- See `sensitivity_window_summary.csv` / `sensitivity_coverage_summary.csv` for per-value statistics.

## 10. Synthetic reference-case consistency results

- PROPOSED_HFIS: macro-F1=0.662, Cohen's kappa=0.550 (n=30). Consistency with predefined synthetic labels, NOT empirical accuracy.
- FUZZY_COMPONENT_MAX: macro-F1=0.662, Cohen's kappa=0.550 (n=30). Consistency with predefined synthetic labels, NOT empirical accuracy.
- CRISP_CLASS_MAX: macro-F1=0.748, Cohen's kappa=0.643 (n=30). Consistency with predefined synthetic labels, NOT empirical accuracy.
- WEIGHTED_MEAN: macro-F1=0.208, Cohen's kappa=0.083 (n=30). Consistency with predefined synthetic labels, NOT empirical accuracy.

## 11. Fault-injection performance

60 scenarios across co2, humidity, pm10, pm2_5, temperature; numbers below are the validation split (disjoint from calibration -- no parameter was tuned against these numbers).

Row-level (every affected sample counted individually):
- single_spike: precision=0.020, recall=1.000, F1=0.039, specificity=not available (tp=7, fp=349, fn=0, tn=None).
- stuck_value: precision=0.239, recall=1.000, F1=0.386, specificity=not available (tp=32, fp=102, fn=0, tn=None).
- data_loss: precision=1.000, recall=1.000, F1=1.000, specificity=not available (tp=20, fp=0, fn=0, tn=None).
- gradual_drift: precision=0.488, recall=1.000, F1=0.656, specificity=not available (tp=40, fp=42, fn=0, tn=None).
- out_of_range: precision=1.000, recall=1.000, F1=1.000, specificity=not available (tp=5, fp=0, fn=0, tn=None).

Event-level (each injected fault matched at most once, one-to-one):
- single_spike: precision=0.061, recall=1.000, F1=0.116 (7 true / 114 predicted event(s)).
- stuck_value: precision=0.400, recall=1.000, F1=0.571 (4 true / 10 predicted event(s)).
- data_loss: precision=1.000, recall=1.000, F1=1.000 (4 true / 4 predicted event(s)).
- gradual_drift: precision=0.571, recall=1.000, F1=0.727 (4 true / 7 predicted event(s)).
- out_of_range: precision=1.000, recall=1.000, F1=1.000 (5 true / 5 predicted event(s)).

- False rejection rate for genuine events: 0.0%.
- Full confusion matrix: `fault_detection_confusion_matrix.csv`.

## 12. Execution-time and resource results

- Platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41 (aarch64, 4 CPUs)
- Total pipeline runtime: 24822.7 s for 13626 timestamps
- Per-timestamp latency: mean=1820.5 ms, median=1716.0 ms, p95=2676.1 ms, max=8052.4 ms
- Peak memory: 724.3 MB
- Source raw row count: 135667

## 13. Provisional parameters and limitations

16 provisional parameter(s) engaged this run (see `parameter_provenance.csv` for status/source of each):
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

See `run_narrative.md`'s dedicated **Limitations** and **Forbidden overclaims** sections for the full discussion, including the PROPOSED_HFIS vs FUZZY_COMPONENT_MAX equivalence finding (if applicable to this run) and what claims this run's data does and does not support.

## 14. Recommended article tables and figures

| Table/figure | Source CSV |
|---|---|
| Study overview & completeness | `index_timeseries.csv`, this document §1-3 |
| Method agreement | `method_comparison.csv`, `reference_case_consistency.csv` |
| Masking comparison | `masking_summary.csv` |
| Boundary continuity curves | `continuity_grid.csv`, `continuity_summary.csv` |
| Stability under perturbation | `stability_summary.csv`, `stability_summary_by_variable.csv`, `stability_summary_by_original_class.csv`, `stability_by_point.csv`, `stability_trials.csv` |
| Sensitivity to window/coverage | `sensitivity_window_summary.csv`, `sensitivity_coverage_summary.csv` |
| Fault-detection performance | `fault_detection_metrics.csv`, `fault_detection_event_metrics.csv`, `fault_detection_confusion_matrix.csv` |
| Parameter provenance (supplementary) | `parameter_provenance.csv` |

> **This document is generated. Review and rewrite before including any text in the manuscript.**