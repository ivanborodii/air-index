# Publication Claims Matrix

> Software-generated from this run's `run_summary.json` -- a claim is never marked SUPPORTED merely because the implementing code exists; every row cites the exact artifact/metric inspected.

## `claim_01`: The data-quality layer prevents index calculation from insufficient data.

- **Status**: **SUPPORTED**
- **Required evidence**: FAILED-completeness computed_ts have a null index_value/index_class.
- **Artifact**: `exports/index_timeseries.csv`
- **Metric**: `FAILED count` = `745`
- **Limitation**: FAILED-status rows are structurally guaranteed to carry a null index_value/index_class (see tests/integration/test_mandatory_regressions.py::test_failed_results_have_null_index_class_and_no_dominant_component), not merely usually null.
- **Recommended wording**: The pipeline never reports an index value or class when fewer than two components have sufficient data (FAILED status); it is left null rather than approximated.

## `claim_02`: The system separates sensor faults from plausible environmental changes.

- **Status**: **PARTIALLY_SUPPORTED**
- **Required evidence**: Low false-rejection rate for genuine events on the validation split; per-reason-code precision/recall.
- **Artifact**: `exports/fault_detection_metrics.csv`
- **Metric**: `false_rejection_rate_for_genuine_events (validation)` = `0.000`
- **Limitation**: False rejection of genuine events is low (0.000), but validation-split precision is weak for: single_spike (see fault_detection_metrics.csv) -- separation is real but not equally reliable across every fault type.
- **Recommended wording**: The validation split showed a low false-rejection rate for genuine events, though precision for isolated-spike detection specifically remains limited (see Limitations).

## `claim_03`: Weighted averaging can mask an adverse component.

- **Status**: **SUPPORTED**
- **Required evidence**: WEIGHTED_MEAN masking_rate > 0 for at least one critical-severity event.
- **Artifact**: `exports/masking_summary.csv`
- **Metric**: `masking_rate` = `0.984`
- **Limitation**: 4978/5059 critical-component events were masked by WEIGHTED_MEAN this run.
- **Recommended wording**: WEIGHTED_MEAN can classify a result as less severe than its most adverse component when other components are favourable, diluting the signal.

## `claim_04`: The proposed HFIS preserves adverse-component priority.

- **Status**: **SUPPORTED**
- **Required evidence**: A deterministic dominant-component attribution exists and is non-trivial across real computed_ts.
- **Artifact**: `exports/index_timeseries.csv`
- **Metric**: `dominant_component_frequency` = `{'A': 4282, 'M': 7859, 'V': 846}`
- **Limitation**: Structural guarantee (the 2nd-level Mamdani rule base's worst-of consequent, see fuzzy_engine.determine_dominance and tests/unit/test_dominance.py) verified per-timestamp by a non-trivial, real dominant-component distribution this run.
- **Recommended wording**: PROPOSED_HFIS's worst-of rule base structurally prevents a favourable component from suppressing a critical component's severity in the aggregated class.

## `claim_05`: HFIS provides smoother numeric behavior near thresholds than CRISP_CLASS_MAX.

- **Status**: **SUPPORTED**
- **Required evidence**: Lower local Lipschitz ratio (max |delta index| / |delta input|) than CRISP_CLASS_MAX on most boundary/context pairs.
- **Artifact**: `exports/continuity_summary.csv`
- **Metric**: `hfis_smoother_count / n_boundary_context_pairs_compared` = `59/99`
- **Limitation**: PROPOSED_HFIS had a strictly lower local Lipschitz ratio than CRISP_CLASS_MAX on 59/99 boundary/context pairs (7 the reverse, 33 tied) -- PROPOSED_HFIS is smoother than CRISP_CLASS_MAX on most of the boundaries and contexts tested, not uniformly.
- **Recommended wording**: PROPOSED_HFIS's continuous membership functions avoid the step discontinuities CRISP_CLASS_MAX exhibits at every control-region boundary.

## `claim_06`: HFIS provides more stable classifications under sensor uncertainty than the crisp baseline.

- **Status**: **SUPPORTED**
- **Required evidence**: Lower class-change rate than CRISP_CLASS_MAX under identical perturbation trials.
- **Artifact**: `exports/stability_summary.csv`
- **Metric**: `class_change_rate (PROPOSED_HFIS vs CRISP_CLASS_MAX)` = `0.34 vs 0.34555555555555556`
- **Limitation**: PROPOSED_HFIS class-change rate 0.340 < CRISP_CLASS_MAX's 0.346 under the same perturbation trials.
- **Recommended wording**: Under bounded sensor-uncertainty perturbation, PROPOSED_HFIS's smooth membership functions change output class less often than the hard-threshold CRISP_CLASS_MAX baseline.

## `claim_07`: The system is computationally feasible on Raspberry Pi 5.

- **Status**: **SUPPORTED**
- **Required evidence**: Per-timestamp latency and peak memory measured on the actual RPi5 deployment hardware.
- **Artifact**: `run_summary.json:performance`
- **Metric**: `per_timestamp_latency_ms.mean, peak_memory_mb` = `1735.441430464428 ms`
- **Limitation**: Measured on Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41: mean per-timestamp latency 1735.4 ms, peak memory 570.25 MB.
- **Recommended wording**: Measured runtime and peak memory on the deployment Raspberry Pi 5 stay well within the 5-minute recompute interval.

## `claim_08`: Outdoor data improve confirmation/explanation without directly entering the index.

- **Status**: **SUPPORTED**
- **Required evidence**: Outdoor fields are never mapped to a direct index input (structural); outdoor context is recorded per computed_ts for confirmation/explanation only.
- **Artifact**: `exports/outdoor_context_timeseries.csv`
- **Metric**: `structural guarantee` = `schema.SchemaMappingConfig._no_carbon_monoxide_as_co2 + COMPONENT_INPUTS excludes outdoor.*`
- **Limitation**: Enforced at config-load time (iaq_hfis.config.SchemaMappingConfig) and by construction: COMPONENT_INPUTS never references an outdoor.* channel; verified by tests/unit/test_config.py::test_schema_mapping_rejects_carbon_monoxide_as_co2 and the confirmation logic in quality/soft_checks.py.
- **Recommended wording**: Outdoor PM2.5/PM10/temperature/CO2 context is used only for dual-source confirmation and trend annotation, never as a direct fuzzy-inference input to the integrated index.

## `claim_09`: The full microclimate component is standards-based for the selected room and season.

- **Status**: **SUPPORTED**
- **Required evidence**: The room/season temperature profile actually used is DBN-supported (not provisional) and the run was executed in mode='publication'.
- **Artifact**: `manuscript_readiness.json`
- **Metric**: `manuscript_readiness.ready` = `True`
- **Limitation**: This run's temperature profile is DBN-supported (provisional_parameters_used contains no room_profiles.* entry) and mode='publication'.
- **Recommended wording**: The microclimate component's temperature control region is taken directly from DBN V.2.5-67:2013 for the deployed room and the data period's season.
