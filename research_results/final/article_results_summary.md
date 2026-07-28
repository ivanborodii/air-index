# Article Results Summary

> Factual, validated-metrics-only summary for manual adaptation into the
> manuscript's Results/Discussion. Every number here is copied directly from
> `run_summary_47195a37fb52424cae0411555732c23f.json` -- no claim beyond what the
> numbers themselves support. This is not manuscript prose.

## 1. Dataset and experiment period

- Period: 2026-07-14T21:01:29+00:00 to 2026-07-28T21:01:29+00:00
- Window: 15 minutes; recompute grid per config
- pipeline_run_id: `47195a37fb52424cae0411555732c23f`; evaluation_run_id: `fad333e03b9a4ed9ad07646ad653334e`
- config_hash: `49fa03b6c0d202b58e8a533c3bd3e5febb1934234f5fbd081e99ff7a2fea31e1`; git commit: `a15562a887dec8f334b4addb9652e82be522a152`

## 2. Expected and processed calculation timestamps

- Processed: 4032

## 3. OK / PARTIAL / FAILED counts and percentages

- OK: 3836 (95.1%)
- PARTIAL: 181 (4.5%)
- FAILED: 15 (0.4%)

## 4. Air-quality class distribution (successfully formed indices)

See `index_timeseries.csv` (completeness_status=OK rows, group by index_class) for the exact distribution.

## 5. Inter-method agreement (unlabeled real data)

- CRISP-MAX vs PROPOSED-HFIS: 100.0% agreement, Cohen's kappa=1.000 (n=4017). This is agreement, not accuracy.
- CRISP-MAX vs WEIGHTED-MEAN: 30.8% agreement, Cohen's kappa=0.076 (n=4032). This is agreement, not accuracy.
- PROPOSED-HFIS vs WEIGHTED-MEAN: 30.5% agreement, Cohen's kappa=0.074 (n=4017). This is agreement, not accuracy.

## 6. Adverse-component masking comparison

- CRISP-MAX (>= Critical): masking_rate=0.0% (0/904 events).
- WEIGHTED-MEAN (>= Critical): masking_rate=99.2% (897/904 events).

## 7. HFIS vs CRISP-MAX numerical continuity

- PROPOSED-HFIS: mean largest adjacent-point jump 2.61 index points across 21 boundaries (see `continuity_summary.csv` for per-boundary detail).
- CRISP-MAX: mean largest adjacent-point jump 2.61 index points across 21 boundaries (see `continuity_summary.csv` for per-boundary detail).
- WEIGHTED-MEAN: mean largest adjacent-point jump 0.87 index points across 21 boundaries (see `continuity_summary.csv` for per-boundary detail).

## 8. Multi-point stability results

- 30 sampled points, 30 trials each, seed=42.
  - PROPOSED-HFIS: class_change_rate=37.2%, mean|Δindex|=8.20
  - CRISP-MAX: class_change_rate=37.2%, mean|Δindex|=8.22
  - WEIGHTED-MEAN: class_change_rate=8.4%, mean|Δindex|=3.23

## 9. Multi-point sensitivity results

- 50 sampled points across strata: boundary_adjacent, class_Acceptable, class_Critical, class_Degraded, class_Favorable, completeness_PARTIAL, data_quality_event, ordinary, outdoor_context_fresh, outdoor_context_stale.
- See `sensitivity_window_summary.csv` / `sensitivity_coverage_summary.csv` for per-value statistics.

## 10. Synthetic reference-case consistency results

- PROPOSED-HFIS: macro-F1=0.869, Cohen's kappa=0.807 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- CRISP-MAX: macro-F1=0.869, Cohen's kappa=0.807 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.
- WEIGHTED-MEAN: macro-F1=0.153, Cohen's kappa=-0.041 (n=42). Consistency with predefined synthetic labels, NOT empirical accuracy.

## 11. Fault-injection performance

- single_spike: precision=0.012, recall=1.000, F1=0.024.
- stuck_value: precision=0.205, recall=1.000, F1=0.340.
- data_loss: precision=1.000, recall=1.000, F1=1.000.
- gradual_drift: precision=1.000, recall=1.000, F1=1.000.
- out_of_range: precision=0.500, recall=1.000, F1=0.667.
- False rejection rate for genuine events: 0.0%.

## 12. Execution-time and resource results

- Platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41 (aarch64, 4 CPUs)
- Total pipeline runtime: 7194.4 s for 4032 timestamps
- Per-timestamp latency: mean=1779.0 ms, median=1574.7 ms, p95=3016.1 ms, max=4935.4 ms
- Peak memory: 408.4 MB
- Source raw row count: 40313

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

## 14. Recommended article tables and figures

| Table/figure | Source CSV |
|---|---|
| Study overview & completeness | `index_timeseries.csv`, this document §1-3 |
| Method agreement | `method_comparison.csv`, `reference_case_consistency.csv` |
| Masking comparison | `masking_summary.csv` |
| Boundary continuity curves | `continuity_grid.csv`, `continuity_summary.csv` |
| Stability under perturbation | `stability_summary.csv`, `stability_trials.csv` |
| Sensitivity to window/coverage | `sensitivity_window_summary.csv`, `sensitivity_coverage_summary.csv` |
| Fault-detection performance | `fault_detection_metrics.csv` |
| Parameter provenance (supplementary) | `parameter_provenance.csv` |

> **This document is generated. Review and rewrite before including any text in the manuscript.**