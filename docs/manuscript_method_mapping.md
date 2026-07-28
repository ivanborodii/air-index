# Manuscript-to-code mapping

Maps concepts and formulas from the Borodii & Osukhivska manuscript to the
`iaq_hfis` modules, config paths, derived-DB tables, and CSV exports that
implement them. See `src/iaq_hfis/provenance.py` for the machine-readable,
per-parameter version of this mapping (one row per scientific/operational
parameter, with its status: `manuscript_defined`, `standard_based`,
`sensor_specification`, `author_defined`, or `provisional`).

## Data-quality states (VALID / SUSPECT / INVALID / MISSING)

- **Stage 1 (hard checks)**: record presence, numeric format, device status
  flag, datasheet technical range, PM cross-channel ordering.
  `src/iaq_hfis/quality/hard_checks.py:run_hard_checks`.
- **Stage 2 (soft checks)**: Hampel filter (median + MAD outlier candidacy),
  stuck-value/gradual-drift detectors, then confirmation (cross-channel for
  PM, dual-channel for T/RH, persistence-only for CO2).
  `src/iaq_hfis/quality/soft_checks.py:run_soft_checks`,
  `src/iaq_hfis/quality/hampel.py`, `src/iaq_hfis/quality/reasons.py`,
  `src/iaq_hfis/quality/confirmation.py`.
- Persisted per (pipeline_run_id, ts, channel) in `observation_quality`.

## Coverage and time-weighted aggregation

- Coverage ratio rho_i(t) = n_usable / n_expected, threshold
  `coverage.min_ratio` (manuscript: >= 0.80).
  `src/iaq_hfis/completeness.py`, `src/iaq_hfis/aggregation.py:aggregate_channel`.
- Time-weighted mean: each usable sample weighted by its time interval to
  the next sample within the window (`aggregation.time_weighted_mean_rule`
  in provenance -- `manuscript_defined`).
- Persisted in `window_aggregates`; exported as `data_quality_summary.csv`.

## Membership functions and control regions

- PM2.5/PM10/CO2: monotonic (right-shoulder) classes built from 3
  breakpoints each. `src/iaq_hfis/membership.py:build_monotonic_classes`.
- Temperature/RH: two-sided classes (favorable band, both-direction
  degradation). `build_two_sided_classes`. Temperature is room/season
  dependent (`config/room_profiles.yaml`); RH is not.
- Config: `config/iaq_hfis.yaml:control_regions`, `config/room_profiles.yaml`.
- Validated against declared sensor uncertainty at startup:
  `src/iaq_hfis/schema.py:validate_membership_config`,
  `validate_room_profile_widths`.

## Components A (aerosol), V (ventilation), M (microclimate)

- `A` = PM2.5 + PM10 (2-input first-level Mamdani rules, worst-of consequent).
- `V` = CO2 (single-input pass-through, no rule firing).
- `M` = temperature + humidity (2-input first-level Mamdani rules).
- Rule generation: `src/iaq_hfis/rules.py:generate_component_rules`
  (Cartesian product over classes; consequent = highest-severity input).
- Inference: `src/iaq_hfis/fuzzy_engine.py:MamdaniEngine.infer_component`.
- Persisted in `component_scores`; exported as `component_scores_timeseries.csv`.

## Integral index I (second-level Mamdani inference)

- Combines A/V/M class-degree vectors via the same worst-of rule structure
  (`rule_base.index_rules` for OK; `generate_component_rules(available, level=2)`
  for PARTIAL -- see `fuzzy_engine.infer_index` docstring for why PARTIAL
  cannot reuse the full 3-input rule base with the missing input filtered out).
- Defuzzification: centroid over a 401-point discretized output universe
  [0, 100]. `MamdaniEngine._centroid`.
- Output classes: Favorable [0,25) / Acceptable [25,50) / Degraded [50,75) /
  Critical [75,100], boundary values map to the less-favorable class.
  `fuzzy_engine.classify_output`.
- **Dominant adverse component**: the available component with the highest
  adverse crisp score, tie-tolerant (`membership.dominant_component_tie_tolerance`,
  `author_defined`). `fuzzy_engine.dominant_adverse_component`. A separate
  `rule_level_contributors` diagnostic (which component "bound" the min() in
  fired rules) is NOT this and must not be confused with it.
- Persisted in `iaq_index_results`; exported as `index_timeseries.csv`.

## Completeness status (OK / PARTIAL / FAILED)

- OK: all 3 components available with sufficient coverage.
- PARTIAL: exactly one component unavailable (its inputs failed coverage).
- FAILED: index/class not formed (multiple components unavailable, or the
  one available component's own inputs are insufficient). FAILED rows
  always have `index_value = NULL`, `index_class = NULL`,
  `dominant_component = []` -- enforced and tested
  (`tests/integration/test_mandatory_regressions.py`).
  `src/iaq_hfis/completeness.py:completeness_status`.

## Baselines: CRISP-MAX and WEIGHTED-MEAN

- Both reuse the same per-component crisp scores the Mamdani engine already
  produces -- no separate scoring logic, only a different aggregation.
- CRISP-MAX: hard max of available component scores (structurally cannot
  mask a critical component -- see `evaluation/masking.py` docstring).
- WEIGHTED-MEAN: equal-weight arithmetic mean.
- `src/iaq_hfis/baselines.py`.

## Evaluation protocol

See `docs/evaluation_protocol.md` for sampling, perturbation, continuity,
sensitivity, masking, reference-case, and fault-injection methodology.

## Manuscript-specified (not provisional) parameters

- `cadence.sample_cadence_seconds` = 30
- `cadence.aggregation_window_minutes` = 15
- `cadence.recompute_interval_minutes` = 5
- `coverage.min_ratio` = 0.80
- `evaluation.sensitivity_window_minutes` = [5, 15, 30, 60]
- `evaluation.sensitivity_coverage_thresholds` = [0.70, 0.80, 0.90]
- `control_regions.output.breakpoints` = [25, 50, 75] (method-defined output scale)
- Two-level Mamdani inference with min antecedent activation, max
  aggregation, centroid defuzzification (fixed structurally, not a config value)
- No compensation of an adverse component by favorable ones (structural:
  worst-of rule consequents throughout)
