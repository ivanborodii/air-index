# Manuscript Readiness

> Software-generated from `iaq_hfis.provenance.assess_readiness` -- not hand-maintained.

**`artifact_readiness`** means only that the computational artifacts (pipeline run, evaluation, `iaq_hfis validate-artifacts`, the test suite) are internally complete and consistent. It says nothing about whether this run's result is eligible to be described as the manuscript's complete proposed method -- that is `manuscript_readiness`, below, which may be `true` only when the temperature profile is directly DBN-supported, the run was executed in `mode=publication`, and a full A/V/M/I (`completeness_status=OK`) result actually exists.

## Artifact readiness: READY

- Warning: 16 provisional parameter(s) engaged this run -- disclosed in provisional_parameters_used, not resolved
- Warning: 16 engaged provisional parameter(s) have no sensitivity-analysis coverage: cadence.slot_match_tolerance_seconds, confirmation.gradual_drift_magnitude_multiplier, confirmation.gradual_drift_min_consecutive_steps, confirmation.persistence_min_consecutive_samples, confirmation.pm_cross_channel_tolerance_pct, confirmation.stuck_value_min_repeats, control_regions.output.transition_widths, control_regions.relative_humidity.transition_width, evaluation.masking_severity_threshold, evaluation.stability_n_trials, evaluation.stability_seed, fuzzy_engine.partial_mode_inference_rule, hampel.mad_multiplier, hampel.window_size, membership.output_transition_width, profile_selection.season_month_ranges

## Manuscript readiness: NOT READY

- Blocking: pipeline run mode='exploratory' -- only mode='publication' runs are manuscript-eligible (exploratory runs never fabricate the microclimate component)
- Blocking: no OK-completeness computed_ts exist in this run -- a full A/V/M/I result was never produced
- Warning: 16 provisional parameter(s) engaged this run -- disclosed in provisional_parameters_used, not resolved
- Warning: 16 engaged provisional parameter(s) have no sensitivity-analysis coverage: cadence.slot_match_tolerance_seconds, confirmation.gradual_drift_magnitude_multiplier, confirmation.gradual_drift_min_consecutive_steps, confirmation.persistence_min_consecutive_samples, confirmation.pm_cross_channel_tolerance_pct, confirmation.stuck_value_min_repeats, control_regions.output.transition_widths, control_regions.relative_humidity.transition_width, evaluation.masking_severity_threshold, evaluation.stability_n_trials, evaluation.stability_seed, fuzzy_engine.partial_mode_inference_rule, hampel.mad_multiplier, hampel.window_size, membership.output_transition_width, profile_selection.season_month_ranges

## Unsupported claims

- Full three-component (A/V/M/I) proposed-method result

## Scientific blockers

- pipeline run mode='exploratory' -- only mode='publication' runs are manuscript-eligible (exploratory runs never fabricate the microclimate component)
- no OK-completeness computed_ts exist in this run -- a full A/V/M/I result was never produced
