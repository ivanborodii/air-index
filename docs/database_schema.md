# Database schema

The derived database (`data/iaq_hfis/iaq_hfis.duckdb`, config:
`paths.derived_db_path`) is `iaq_hfis`'s own, entirely additive DuckDB file
-- it never shares a database with air-monitor's `raw_observations` /
`microbatches` / `runtime_metrics` / `weather_observations` tables (those
are read-only sources, opened from a separate file/snapshot; see
`docs/reproducibility.md`). Source of truth for the exact DDL:
`src/iaq_hfis/sql/create_tables.sql`; this document is a reading guide, not
a substitute for it.

**Schema version**: `iaq_hfis.db.SCHEMA_VERSION` (currently 5) is stamped
into `schema_version` on creation. Every run-dependent table carries the
exact `pipeline_run_id` (and, for evaluation tables, `evaluation_run_id`)
that produced it -- run isolation, not overwrite-in-place. A version
mismatch raises `LegacySchemaError` rather than silently reinterpreting old
rows; fix via `iaq_hfis rebuild-db --confirm` (deletes and recreates only
this file, never the raw/weather sources).

## Pipeline core (one row set per `iaq_hfis run` invocation)

| Table | Grain | Notes |
|---|---|---|
| `pipeline_runs` | one row per `pipeline_run_id` | Run metadata: status, timestamp range, `config_hash`, `engine_version`, `source_git_commit`. |
| `observation_quality` | `(pipeline_run_id, ts, channel)` | Stage 1/2 validation verdict per raw expected slot: `stage1_state`/`stage2_state` (VALID/SUSPECT/INVALID/MISSING), `usable`, `confirmed`, `reason_codes[]` (single_spike/stuck_value/data_loss/gradual_drift/out_of_range), Hampel median/MAD. `raw_value` is copied for audit only -- `raw_observations` itself is never modified. |
| `window_aggregates` | `(pipeline_run_id, computed_ts, window_minutes, channel)` | Per-channel time-weighted mean over the rolling window, coverage ratio, `coverage_ok`. `weighted_mean` is NULL when coverage fails. |
| `outdoor_context` | `(pipeline_run_id, computed_ts)` | Outdoor weather snapshot used for context only (staleness, season selection) -- never a direct index input. |
| `component_scores` | `(pipeline_run_id, computed_ts, window_minutes, component)` | Level-1 Mamdani output per component (A/V/M): class membership degrees, `crisp_score`, room/season. |
| `iaq_index_results` | `(pipeline_run_id, computed_ts, window_minutes)` | The final index: `completeness_status`, `index_value`/`index_class` (NULL if FAILED), and the dominance result -- `dominant_component` (single VARCHAR, the deterministic priority-hierarchy winner), `co_dominant_components` (VARCHAR[], the full tied set), `worst_component_class`, `largest_component_score`, `dominance_reason` (see `fuzzy_engine.determine_dominance`), plus the older `rule_level_contributors[]` diagnostic (NOT the same thing -- see that column's own comment in the DDL). |

## Evaluation core (one row set per `iaq_hfis evaluate` invocation)

| Table | Grain | Notes |
|---|---|---|
| `evaluation_runs` | one row per `evaluation_run_id` | Run metadata, including its own `config_hash`/`evaluation_config_hash` (should match the pipeline run's `config_hash` -- checked by `validate-artifacts`). |
| `baseline_results` | `(..., computed_ts, window_minutes, method)` | CRISP-MAX / WEIGHTED-MEAN index value+class, computed from the *same* component crisp scores PROPOSED-HFIS uses. |
| `evaluation_agreement` | `(evaluation_run_id, method_a, method_b)` | Pairwise % agreement + Cohen's kappa on real, unlabeled data -- agreement, never accuracy. |
| `evaluation_masking` | `(evaluation_run_id, method, severity_threshold)` | Whether a baseline's aggregated class hid an available component's own severe class. |
| `evaluation_reference_cases` | `(evaluation_run_id, method)` | Consistency (macro-F1, kappa) against synthetic pre-labeled boundary vectors -- NOT empirical accuracy. |

## Multi-point stability

| Table | Grain | Notes |
|---|---|---|
| `evaluation_stability_samples` | `(evaluation_run_id, sample_id)` | One deterministically-selected computed_ts (boundary_adjacent or random_comparison) and each method's unperturbed baseline class/value. |
| `evaluation_stability_trials` | `(evaluation_run_id, sample_id, method, trial_index)` | One perturbation trial's outcome. Every stability summary grain (overall/by_variable/by_original_class, in both `run_summary.json` and every `stability_*.csv`) is computed from exactly these persisted rows by one shared function -- never independently recomputed. |

## Multi-point sensitivity

| Table | Grain | Notes |
|---|---|---|
| `evaluation_sensitivity` | `(evaluation_run_id, sample_id, varied_parameter, value)` | One swept value (window_minutes or coverage_threshold) at one stratified-sampled computed_ts, against that point's own reference. `compute_sensitivity_summary()` is the one function that aggregates this into both `run_summary.json` and `sensitivity_*_summary.csv`. |

## Boundary continuity (HFIS vs CRISP-MAX vs WEIGHTED-MEAN)

| Table | Grain | Notes |
|---|---|---|
| `evaluation_continuity_grid` | `(evaluation_run_id, boundary_id, context, method, grid_index)` | One point of a dense input-grid sweep. `context` is favorable/acceptable/degraded -- the severity of the OTHER, non-swept channels (see `docs/hfis_vs_crispmax_audit.md` for why this matters). |
| `evaluation_continuity_summary` | `(evaluation_run_id, boundary_id, context, method)` | Recomputable directly from the grid table: max/mean/median/p95 adjacent jump, total variation, local Lipschitz ratio, class transitions, monotonicity violations, and (PROPOSED-HFIS rows only) area between its curve and CRISP-MAX's. |

## Fault-injection benchmark (labeled synthetic, separate from real data)

| Table | Grain | Notes |
|---|---|---|
| `fault_injection_events` | `(evaluation_run_id, scenario_id, channel, injected_at_index)` | One injected fault's ground truth: type, position, duration. `dataset_split` (calibration/validation) is a stored column, always derivable from `scenario_id`'s suffix too (`fault_injection.dataset_split_of`). |
| `fault_detection_predictions` | `(evaluation_run_id, scenario_id, channel, sample_index)` | Row-level prediction: true label, predicted reason codes, stage2 state, usable. |
| `fault_detection_metrics` | `(evaluation_run_id, dataset_split, reason_code)` | Row-level TP/FP/FN/TN, precision/recall/F1/specificity/FPR, mean detection delay. |
| `fault_detection_event_metrics` | `(evaluation_run_id, dataset_split, reason_code)` | Event-level: one-to-one matched TP/FP/FN (never double-counts a multi-sample fault), `temporal_tolerance_samples`, true/predicted event counts. |
| `fault_detection_confusion_matrix` | `(evaluation_run_id, dataset_split, true_label, predicted_label)` | Row-level confusion matrix, including "none" for genuinely clean/unflagged samples. |
| `hampel_calibration` | `(evaluation_run_id, dataset_split, window_size, mad_multiplier)` | Grid-search diagnostic; `dataset_split` is calibration/validation (renamed from an earlier development/holdout terminology). `selected=TRUE` always marks the currently *configured* value, never a value chosen by this grid alone. |

## Miscellaneous

- `parameter_provenance` is declared in the DDL but **not currently
  written to** -- the actual `parameter_provenance.csv` artifact is
  generated directly from `iaq_hfis.provenance.collect_parameter_provenance()`
  Python objects at report time, bypassing the database entirely. Documented
  here so this isn't mistaken for a coverage gap in the derived database.

## Cross-table identity

Every table above carries `pipeline_run_id` (and, where applicable,
`evaluation_run_id`) in its primary key -- see `docs/reproducibility.md`
for the full identity chain and how to reproduce a specific result.
