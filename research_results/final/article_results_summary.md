# Article Results Summary

> Factual, validated-metrics-only summary for manual adaptation into the
> manuscript's Results/Discussion. Every number here is copied directly from
> `run_summary_ea2cb02424ef4be99374f0f40a41d497.json` -- no claim beyond what the
> numbers themselves support. This is not manuscript prose.

## 1. Dataset and experiment period

- Period: 2026-07-15T00:00:00+00:00 to 2026-07-29T00:00:00+00:00
- Window: 15 minutes; recompute grid per config
- pipeline_run_id: `ea2cb02424ef4be99374f0f40a41d497`; evaluation_run_id: `0348eeaf3b5543818f2b3bf45bc89672`
- config_hash: `133162d56aa30bc8022c2be07a32d7436fb03c2010e92432070bbe8b34d3dc31`; git commit: `3593efb0504d282396ab4d6b9404326e5f658e34`

## 2. Expected and processed calculation timestamps

- Processed: 4032

## 3. OK / PARTIAL / FAILED counts and percentages

- OK: 3836 (95.1%)
- PARTIAL: 181 (4.5%)
- FAILED: 15 (0.4%)

## 4. Air-quality class distribution (successfully formed indices)

See `index_timeseries.csv` (completeness_status=OK rows, group by index_class) for the exact distribution.

Dominant-component frequency (which of A/V/M won the priority-hierarchy tie-break, OK/PARTIAL computed_ts only):
- A: 1536 (38.2%)
- M: 2306 (57.4%)
- V: 175 (4.4%)

## 5. Inter-method agreement (unlabeled real data)

- CRISP_CLASS_MAX vs FUZZY_COMPONENT_MAX: 99.8% agreement, Cohen's kappa=0.997 (n=4032). This is agreement, not accuracy.
- CRISP_CLASS_MAX vs PROPOSED_HFIS: 99.8% agreement, Cohen's kappa=0.997 (n=4017). This is agreement, not accuracy.
- CRISP_CLASS_MAX vs WEIGHTED_MEAN: 42.7% agreement, Cohen's kappa=0.171 (n=4032). This is agreement, not accuracy.
- FUZZY_COMPONENT_MAX vs PROPOSED_HFIS: 100.0% agreement, Cohen's kappa=1.000 (n=4017). This is agreement, not accuracy.
- FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN: 42.5% agreement, Cohen's kappa=0.170 (n=4032). This is agreement, not accuracy.
- PROPOSED_HFIS vs WEIGHTED_MEAN: 42.3% agreement, Cohen's kappa=0.168 (n=4017). This is agreement, not accuracy.

## 6. Adverse-component masking comparison

- FUZZY_COMPONENT_MAX (>= Critical): masking_rate=0.0% (0/755 events).
- CRISP_CLASS_MAX (>= Critical): masking_rate=0.0% (0/755 events).
- WEIGHTED_MEAN (>= Critical): masking_rate=99.1% (748/755 events).

## 7. HFIS vs FUZZY_COMPONENT_MAX numerical continuity

- PROPOSED_HFIS: mean largest adjacent-point jump 1.74 index points across 99 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- FUZZY_COMPONENT_MAX: mean largest adjacent-point jump 1.74 index points across 99 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- WEIGHTED_MEAN: mean largest adjacent-point jump 0.60 index points across 99 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- Smoothness comparison (local Lipschitz ratio, 99 boundary/context pairs): PROPOSED_HFIS and FUZZY_COMPONENT_MAX had numerically identical local Lipschitz ratios on all 99 boundary/context pairs tested -- no smoothness advantage observed under this experimental design. This is expected, not a defect in either method: each sweep perturbs only ONE channel within a narrow +/-sensor-uncertainty window while the other channels are held at a FIXED representative value for the context; the worst-of rule base makes whichever channel has the higher severity dominate the aggregated result, and in this design one channel dominates the ENTIRE sweep (the swept channel's narrow local range essentially never crosses the fixed other channels' value), so both methods reduce to reporting that one dominant channel's own score throughout -- see docs/hfis_vs_crispmax_audit.md section 3 for the proof, and its independent multi-component synthetic check (section 2) for evidence the two methods DO diverge substantially once more than one channel is simultaneously close to the maximum severity.

## 8. Multi-point stability results

- 30 sampled points, 30 trials each, seed=42.
  - CRISP_CLASS_MAX: class_change_rate=38.1% (moved better=12.6%, moved worse=25.6%), mean|Δindex|=9.53
  - FUZZY_COMPONENT_MAX: class_change_rate=36.8% (moved better=15.3%, moved worse=21.4%), mean|Δindex|=7.61
  - PROPOSED_HFIS: class_change_rate=36.8% (moved better=15.3%, moved worse=21.4%), mean|Δindex|=7.58
  - WEIGHTED_MEAN: class_change_rate=7.2% (moved better=3.1%, moved worse=4.1%), mean|Δindex|=3.11
- Breakdowns by boundary/channel (`stability_summary_by_variable.csv`) and by originating class (`stability_summary_by_original_class.csv`) are exported separately; not repeated here.

## 9. Multi-point sensitivity results

- 50 sampled points across strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favorable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale.
- See `sensitivity_window_summary.csv` / `sensitivity_coverage_summary.csv` for per-value statistics.

## 10. Synthetic reference-case consistency results

- PROPOSED_HFIS: macro-F1=0.908, Cohen's kappa=0.871 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- FUZZY_COMPONENT_MAX: macro-F1=0.908, Cohen's kappa=0.871 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- CRISP_CLASS_MAX: macro-F1=1.000, Cohen's kappa=1.000 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- WEIGHTED_MEAN: macro-F1=0.153, Cohen's kappa=-0.041 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.

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
- Total pipeline runtime: 6857.8 s for 4032 timestamps
- Per-timestamp latency: mean=1699.6 ms, median=1596.7 ms, p95=2600.6 ms, max=4873.8 ms
- Peak memory: 451.1 MB
- Source raw row count: 40319

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