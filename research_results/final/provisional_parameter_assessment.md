# Provisional Parameter Assessment

> Software-generated from `iaq_hfis.provenance` and this run's `run_summary.json` -- not hand-maintained. Regenerate rather than hand-edit if anything here looks stale.

**Two hard rules enforced throughout:** a synthetic benchmark's calibration result is scoped to that benchmark and is never claimed to make a parameter universally valid, and a parameter grounded in a literature example is never described as "calibrated" merely because of that citation; no parameter is promoted to STANDARD_BASED in this report -- that only happens in `iaq_hfis.provenance`'s own catalog, with a cited source, never here.

16 parameter(s) with a provisional-like status (PROVISIONAL, AUTHOR_DEFINED_PROVISIONAL, LITERATURE_INFORMED, or CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT) in the current configuration; 16 engaged (actually applied) this run.

## `cadence.slot_match_tolerance_seconds`

- **Status**: `AUTHOR_DEFINED_PROVISIONAL`
- **Current value**: `15.0` seconds
- **Engaged this run**: yes
- **Why provisional**: Half the sensor sample cadence: computed_ts has an arbitrary phase offset from the sensor's own ~30s cadence, so a tighter tolerance would systematically miss real readings that were never dropped.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`cadence.slot_match_tolerance_seconds`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Indirect: affects which raw samples are matched to the sample-cadence grid before aggregation; too tight a tolerance would silently manufacture MISSING samples, too loose would blend adjacent cadence slots. Does not affect fuzzy inference logic itself.
- **Recommended future validation**: Confirm the deployed sensors' actual sample-time jitter against this value over a longer live deployment window; tighten only if jitter is measurably smaller than half the cadence.

## `confirmation.gradual_drift_magnitude_multiplier`

- **Status**: `PROVISIONAL`
- **Current value**: `3.0` x declared sensor uncertainty
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript; empirically verified against live data to avoid flagging ordinary environmental trends (e.g. CO2 falling after ventilation) as faults.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`confirmation.gradual_drift_magnitude_multiplier`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Indirect: sets the magnitude gate (x declared sensor uncertainty) a drift must clear to be flagged; affects completeness, not fuzzy inference. Directly benchmarked by the fault-injection gradual_drift scenarios (see fault_detection_metrics.csv) -- but that is a synthetic-scenario result, not a real-data validation of this exact multiplier value.
- **Recommended future validation**: Track real-data gradual_drift flagging frequency over time; a multiplier producing implausibly many or zero real flags would indicate this needs revisiting.

## `confirmation.gradual_drift_min_consecutive_steps`

- **Status**: `PROVISIONAL`
- **Current value**: `5` samples
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`confirmation.gradual_drift_min_consecutive_steps`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Indirect: determines how many consecutive monotonic steps are required before a slow trend is even considered for the gradual_drift check; affects completeness, not fuzzy inference.
- **Recommended future validation**: Cross-check against real ventilation-driven CO2 decay curves to confirm this window is short enough to catch genuine sensor drift without false-flagging normal decay.

## `confirmation.persistence_min_consecutive_samples`

- **Status**: `PROVISIONAL`
- **Current value**: `2` samples
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`confirmation.persistence_min_consecutive_samples`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Indirect: affects the SUSPECT-to-usable confirmation delay for every soft-check-flagged sample, which can shift window completeness. Does not affect fuzzy inference logic.
- **Recommended future validation**: Compare against real-data confirmation delay statistics once enough live SUSPECT events have accumulated to characterize a typical genuine-event confirmation time.

## `confirmation.pm_cross_channel_tolerance_pct`

- **Status**: `PROVISIONAL`
- **Current value**: `20.0` %
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`confirmation.pm_cross_channel_tolerance_pct`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Indirect: affects only the PM1/PM2.5/PM4/PM10 cumulative-ordering hard-check, i.e. completeness for PM channels, not fuzzy inference.
- **Recommended future validation**: Verify against the SPS30's actual observed cross-channel noise on live data over a representative pollution-level range (this benchmark's synthetic scenario only tests one magnitude).

## `confirmation.stuck_value_min_repeats`

- **Status**: `PROVISIONAL`
- **Current value**: `5` samples
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript. Exact-equality repeat count; there is no separate stuck-value tolerance parameter.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`confirmation.stuck_value_min_repeats`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Indirect: determines the exact-equality repeat count that triggers a stuck_value flag; affects completeness, not fuzzy inference.
- **Recommended future validation**: Review against the sensors' actual quantization step -- too small a repeat count risks flagging genuinely stable real readings (e.g. a steady room) as stuck.

## `control_regions.output.transition_widths`

- **Status**: `PROVISIONAL`
- **Current value**: `[2.0, 2.0, 2.0]` index points
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript.
- **Where used**: pipeline stage `membership_construction`; source `config/iaq_hfis.yaml` (`control_regions.output.transition_widths`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Direct: a membership-construction parameter for the OUTPUT scale itself -- changes here directly change the index value and class near every 25/50/75 output boundary.
- **Recommended future validation**: No manuscript-specified value exists; if a future manuscript revision specifies these widths explicitly, this becomes STANDARD_BASED and this entry should be removed.

## `control_regions.relative_humidity.transition_width`

- **Status**: `PROVISIONAL`
- **Current value**: `3.0` %
- **Engaged this run**: yes
- **Why provisional**: Matches sensor_specs.yaml bme_humidity.declared_uncertainty; the RH breakpoints themselves are standard-based (DBN B.2.5-67:2013) but this transition width is not separately specified there.
- **Where used**: pipeline stage `membership_construction`; source `config/iaq_hfis.yaml` (`control_regions.relative_humidity.transition_width`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Direct: a membership-construction parameter -- changes here directly change every computed index value and class whenever humidity is near a control-region boundary.
- **Recommended future validation**: This transition width is already floored at the RH sensor's declared uncertainty (auto-expanded if narrower); no further action beyond re-verifying that floor if the sensor is ever replaced.

## `evaluation.masking_severity_threshold`

- **Status**: `PROVISIONAL`
- **Current value**: `Critical`
- **Engaged this run**: yes
- **Why provisional**: Which severity counts as 'hidden' by an aggregation baseline; not specified in the manuscript.
- **Where used**: pipeline stage `evaluation_masking`; source `config/iaq_hfis.yaml` (`evaluation.masking_severity_threshold`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: None on the primary index computation: only defines which severity counts as 'hidden' for the masking-comparison diagnostic (masking_summary.csv), not the index/class computation itself.
- **Recommended future validation**: Consider reporting masking at multiple severity thresholds (not just Critical) if the manuscript ultimately wants a threshold-sensitivity view of the masking claim.

## `evaluation.stability_n_trials`

- **Status**: `PROVISIONAL`
- **Current value**: `30` trials
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript.
- **Where used**: pipeline stage `evaluation_stability`; source `config/iaq_hfis.yaml` (`evaluation.stability_n_trials`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: None on the primary index computation: only affects the statistical precision (confidence interval width) of the stability experiment's own summary statistics, not the index/class computation itself.
- **Recommended future validation**: Increase if a future run's Wilson confidence intervals in stability_summary.csv are judged too wide to support a specific claim; bounded mainly by Raspberry Pi 5 runtime.

## `evaluation.stability_seed`

- **Status**: `PROVISIONAL`
- **Current value**: `42`
- **Engaged this run**: yes
- **Why provisional**: The manuscript requires a fixed seed for reproducibility but gives no value.
- **Where used**: pipeline stage `evaluation_stability`; source `config/iaq_hfis.yaml` (`evaluation.stability_seed`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: None on the primary index computation: only affects which perturbation trials the multi-point stability experiment happens to draw, not the index/class computation itself. A different seed would change stability_summary.csv's exact numbers but not the pipeline's primary output.
- **Recommended future validation**: None needed -- the manuscript requires a fixed seed for reproducibility, not a specific value; any fixed value satisfies that requirement equally.

## `fuzzy_engine.partial_mode_inference_rule`

- **Status**: `AUTHOR_DEFINED_PROVISIONAL`
- **Current value**: `PARTIAL-mode index rules are regenerated directly from the available components (same worst-of consequent), not the full 3-input rule base with the missing component filtered out`
- **Engaged this run**: yes
- **Why provisional**: The manuscript does not specify PARTIAL-mode inference mechanics; see fuzzy_engine.infer_index docstring for why naive filtering of the full rule base would be unsound (a real design rationale, not an arbitrary guess) -- still needs sensitivity coverage since it is not manuscript-confirmed.
- **Where used**: pipeline stage `fuzzy_inference`; source `src/iaq_hfis/fuzzy_engine.py` (`infer_index()`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Direct, but PARTIAL-only: this design choice governs every PARTIAL-completeness computed_ts's index value and dominance -- a materially different fraction of the dataset than OK timestamps, but real and non-negligible whenever any component is unavailable.
- **Recommended future validation**: If the manuscript is later revised to specify PARTIAL-mode mechanics explicitly, replace this AUTHOR-level design choice with the specified mechanism.

## `hampel.mad_multiplier`

- **Status**: `CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT`
- **Current value**: `3.0`
- **Engaged this run**: yes
- **Why provisional**: Selected by comparing h in {1.0, 2.0, 3.0} at window_size=11 on the deterministic synthetic fault-injection calibration split only (never validation), maximizing S = (single_spike recall + genuine-event preservation + (1 - single_spike FPR)) / 3 -- see iaq_hfis.evaluation.fault_injection.select_hampel_multiplier, parameter_selection.json, and research_results/hampel_causal_revision_report.md.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`hampel.mad_multiplier`)
- **Diagnostic calibration grid exists**: yes -- see parameter_selection.json; mad_multiplier is selected from this grid (calibration split only), window_size is literature-informed and held fixed
- **Calibration/validation dataset**: Fault-injection benchmark's calibration split (single_spike + genuine-event scenarios, CO2 channel) for the grid search; validation split (disjoint scenario_ids and a numerically distinct scale/phase) for the reported objective score -- see docs/fault_injection_audit.md.
- **Sensitivity result**: Fault-injection calibration grid objective score for the selected value (mad_multiplier=3.0, selected purely from the calibration split), on the VALIDATION split (disjoint from the split used to search the grid): 0.981 (1.0 = perfect single_spike recall + perfect genuine-event preservation + zero single_spike FPR). See hampel_calibration.csv for the full grid on both splits.
- **Do conclusions depend strongly on it?**: Direct but scoped: same as hampel.window_size (paired parameter of the same filter).
- **Recommended future validation**: Same as hampel.window_size -- verify jointly, not independently, since they interact.

## `hampel.window_size`

- **Status**: `LITERATURE_INFORMED`
- **Current value**: `11` samples
- **Engaged this run**: yes
- **Why provisional**: Point count (11) sourced from Pearson, Neuvo, Astola, Gabbouj, "Generalized Hampel Filters" (2016) -- the manuscript's own cited source's illustrative example (K=5 -> 11-point window) -- but the WINDOW SHAPE is causal (x_i and the 10 samples strictly before it), per the manuscript's own definition, not the cited paper's centered shape; see iaq_hfis.quality.hampel's module docstring.
- **Where used**: pipeline stage `validation`; source `config/iaq_hfis.yaml` (`hampel.window_size`)
- **Diagnostic calibration grid exists**: yes -- see parameter_selection.json; mad_multiplier is selected from this grid (calibration split only), window_size is literature-informed and held fixed
- **Calibration/validation dataset**: Fault-injection benchmark's calibration split (single_spike + genuine-event scenarios, CO2 channel) for the grid search; validation split (disjoint scenario_ids and a numerically distinct scale/phase) for the reported objective score -- see docs/fault_injection_audit.md.
- **Sensitivity result**: Fault-injection calibration grid objective score for the selected value (mad_multiplier=3.0, selected purely from the calibration split), on the VALIDATION split (disjoint from the split used to search the grid): 0.981 (1.0 = perfect single_spike recall + perfect genuine-event preservation + zero single_spike FPR). See hampel_calibration.csv for the full grid on both splits.
- **Do conclusions depend strongly on it?**: Direct but scoped: affects which raw samples are flagged single_spike and therefore excluded before aggregation -- changes here can shift window completeness and, rarely, which OK/PARTIAL/FAILED status a timestamp receives. Does not affect the fuzzy inference/HFIS-vs-baseline comparison logic itself.
- **Recommended future validation**: The synthetic fault-injection calibration grid (see below) is diagnostic only; any change to the configured value must be separately verified against a real live-data deployment period showing fewer false single_spike flags without missing genuine spikes, per the existing calibration policy.

## `membership.output_transition_width`

- **Status**: `PROVISIONAL`
- **Current value**: `2.0` index points
- **Engaged this run**: yes
- **Why provisional**: Not given numerically in the manuscript; same rationale as control_regions.output.transition_widths.
- **Where used**: pipeline stage `membership_construction`; source `config/iaq_hfis.yaml` (`membership.output_transition_width`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Direct: same role as control_regions.output.transition_widths (used identically in membership construction for the output scale).
- **Recommended future validation**: Same as control_regions.output.transition_widths.

## `profile_selection.season_month_ranges`

- **Status**: `PROVISIONAL`
- **Current value**: `{'cold_period': [10, 11, 12, 1, 2, 3], 'warm_period': [4, 5, 6, 7, 8, 9]}` months
- **Engaged this run**: yes
- **Why provisional**: Season cutover months not given in the manuscript.
- **Where used**: pipeline stage `profile_selection`; source `config/iaq_hfis.yaml` (`profile_selection.season_month_ranges`)
- **Diagnostic calibration grid exists**: no
- **Calibration/validation dataset**: Not applicable -- no calibration procedure exists for this parameter.
- **Sensitivity result**: Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run.
- **Do conclusions depend strongly on it?**: Direct: determines WHICH room/season temperature profile (and therefore which membership functions) applies to a given computed_ts -- a wrong season boundary would apply the wrong control region to real data near a seasonal transition.
- **Recommended future validation**: Confirm season cutover months against the actual regional climate the deployment site experiences, not a generic calendar split.
