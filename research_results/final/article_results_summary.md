# Article Results Summary

> Factual, validated-metrics-only summary for manual adaptation into the
> manuscript's Results/Discussion. Every number here is copied directly from
> `run_summary_a09f711d3c0c44508cd499e12028ae17.json` -- no claim beyond what the
> numbers themselves support. This is not manuscript prose.

## 1. Dataset and experiment period

- Period: 2026-07-15T19:11:17+00:00 to 2026-07-29T19:11:17+00:00
- Window: 15 minutes; recompute grid per config
- pipeline_run_id: `a09f711d3c0c44508cd499e12028ae17`; evaluation_run_id: `81fadef3088d4f658fb1cb03ab44d47e`
- config_hash: `49fa03b6c0d202b58e8a533c3bd3e5febb1934234f5fbd081e99ff7a2fea31e1`; git commit: `5f284166076b56f1d9b561626544cab87c3e5d4a`

## 2. Expected and processed calculation timestamps

- Processed: 4032

## 3. OK / PARTIAL / FAILED counts and percentages

- OK: 3835 (95.1%)
- PARTIAL: 182 (4.5%)
- FAILED: 15 (0.4%)

## 4. Air-quality class distribution (successfully formed indices)

See `index_timeseries.csv` (completeness_status=OK rows, group by index_class) for the exact distribution.

Dominant-component frequency (which of A/V/M won the priority-hierarchy tie-break, OK/PARTIAL computed_ts only):
- A: 1050 (26.1%)
- M: 2799 (69.7%)
- V: 168 (4.2%)

## 5. Inter-method agreement (unlabeled real data)

- CRISP-MAX vs PROPOSED-HFIS: 100.0% agreement, Cohen's kappa=1.000 (n=4017). This is agreement, not accuracy.
- CRISP-MAX vs WEIGHTED-MEAN: 32.6% agreement, Cohen's kappa=0.099 (n=4032). This is agreement, not accuracy.
- PROPOSED-HFIS vs WEIGHTED-MEAN: 32.4% agreement, Cohen's kappa=0.096 (n=4017). This is agreement, not accuracy.

## 6. Adverse-component masking comparison

- CRISP-MAX (>= Critical): masking_rate=0.0% (0/896 events).
- WEIGHTED-MEAN (>= Critical): masking_rate=99.2% (889/896 events).

## 7. HFIS vs CRISP-MAX numerical continuity

- PROPOSED-HFIS: mean largest adjacent-point jump 1.79 index points across 99 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- CRISP-MAX: mean largest adjacent-point jump 1.79 index points across 99 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- WEIGHTED-MEAN: mean largest adjacent-point jump 0.62 index points across 99 boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).
- Smoothness comparison (local Lipschitz ratio, 99 boundary/context pairs): PROPOSED-HFIS and CRISP-MAX had numerically identical local Lipschitz ratios on all 99 boundary/context pairs tested -- no smoothness advantage observed under this experimental design. This is expected, not a defect in either method: each sweep perturbs only ONE channel within a narrow +/-sensor-uncertainty window while the other channels are held at a FIXED representative value for the context; the worst-of rule base makes whichever channel has the higher severity dominate the aggregated result, and in this design one channel dominates the ENTIRE sweep (the swept channel's narrow local range essentially never crosses the fixed other channels' value), so both methods reduce to reporting that one dominant channel's own score throughout -- see docs/hfis_vs_crispmax_audit.md section 3 for the proof, and its independent multi-component synthetic check (section 2) for evidence the two methods DO diverge substantially once more than one channel is simultaneously close to the maximum severity.

## 8. Multi-point stability results

- 30 sampled points, 30 trials each, seed=42.
  - CRISP-MAX: class_change_rate=36.6% (moved better=12.3%, moved worse=24.2%), mean|Δindex|=8.07
  - PROPOSED-HFIS: class_change_rate=36.6% (moved better=12.3%, moved worse=24.2%), mean|Δindex|=8.04
  - WEIGHTED-MEAN: class_change_rate=6.9% (moved better=2.7%, moved worse=4.2%), mean|Δindex|=3.27
- Breakdowns by boundary/channel (`stability_summary_by_variable.csv`) and by originating class (`stability_summary_by_original_class.csv`) are exported separately; not repeated here.

## 9. Multi-point sensitivity results

- 50 sampled points across strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favorable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale.
- See `sensitivity_window_summary.csv` / `sensitivity_coverage_summary.csv` for per-value statistics.

## 10. Synthetic reference-case consistency results

- PROPOSED-HFIS: macro-F1=0.869, Cohen's kappa=0.807 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- CRISP-MAX: macro-F1=0.869, Cohen's kappa=0.807 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- WEIGHTED-MEAN: macro-F1=0.153, Cohen's kappa=-0.041 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.

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
- Total pipeline runtime: 6767.3 s for 4032 timestamps
- Per-timestamp latency: mean=1673.5 ms, median=1560.0 ms, p95=2576.9 ms, max=6109.3 ms
- Peak memory: 413.9 MB
- Source raw row count: 40318

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

See `run_narrative.md`'s dedicated **Limitations** and **Forbidden overclaims** sections for the full discussion, including the PROPOSED-HFIS vs CRISP-MAX equivalence finding (if applicable to this run) and what claims this run's data does and does not support.

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