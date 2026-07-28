-- src/iaq_hfis/sql/create_tables.sql
-- Derived schema for the iaq_hfis fuzzy IAQ index, deployed to a NEW,
-- dedicated DuckDB file (config: paths.derived_db_path). This file is
-- entirely additive and never shares a database with air-monitor's
-- raw_observations / microbatches / runtime_metrics / weather_observations
-- tables (those are read-only sources, opened from a separate file/snapshot).
-- All statements are idempotent (CREATE TABLE IF NOT EXISTS).
--
-- Schema version 2: every run-dependent row is tagged with the exact
-- pipeline_run_id (and, for evaluation tables, evaluation_run_id) that
-- produced it. This is a run-isolation schema: two pipeline runs over the
-- same timestamps, or two evaluation runs over the same pipeline run, never
-- overwrite or mix each other's rows. See iaq_hfis.db for legacy-schema
-- detection and the rebuild-db command (schema version 1 had no run
-- isolation and cannot be safely reinterpreted as version 2 data).

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER     NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id         VARCHAR PRIMARY KEY,
    started_at              TIMESTAMPTZ NOT NULL,
    finished_at             TIMESTAMPTZ,
    status                  VARCHAR     NOT NULL,   -- success | failed
    computed_ts_min         TIMESTAMPTZ,
    computed_ts_max         TIMESTAMPTZ,
    window_minutes          INTEGER,
    n_timestamps_processed  INTEGER,
    n_snapshot_retries      INTEGER,
    config_hash             VARCHAR     NOT NULL,
    engine_version          VARCHAR     NOT NULL,
    source_git_commit       VARCHAR
);

CREATE TABLE IF NOT EXISTS observation_quality (
    pipeline_run_id VARCHAR     NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,   -- expected slot timestamp
    channel         VARCHAR     NOT NULL,   -- pm2_5 | pm10 | co2 | temperature | humidity
    raw_value       DOUBLE,                  -- copied for audit only; raw_observations is never modified
    stage1_state    VARCHAR     NOT NULL,   -- VALID | MISSING | INVALID
    stage2_state    VARCHAR     NOT NULL,   -- VALID | SUSPECT | INVALID | MISSING
    usable          BOOLEAN     NOT NULL,   -- u_i(t): counts toward coverage/aggregation
    confirmed       BOOLEAN,                 -- NULL unless stage2_state = SUSPECT
    reason_codes    VARCHAR[],               -- single_spike | stuck_value | data_loss | gradual_drift | out_of_range
    hampel_median   DOUBLE,
    hampel_mad      DOUBLE,
    computed_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (pipeline_run_id, ts, channel)
);

CREATE TABLE IF NOT EXISTS window_aggregates (
    pipeline_run_id VARCHAR     NOT NULL,
    computed_ts     TIMESTAMPTZ NOT NULL,
    window_minutes  INTEGER     NOT NULL,   -- 5 | 15 | 30 | 60
    channel         VARCHAR     NOT NULL,
    n_expected      INTEGER     NOT NULL,
    n_usable        INTEGER     NOT NULL,
    coverage_ratio  DOUBLE      NOT NULL,
    coverage_ok     BOOLEAN     NOT NULL,
    weighted_mean   DOUBLE,                  -- NULL if coverage_ok = FALSE
    PRIMARY KEY (pipeline_run_id, computed_ts, window_minutes, channel)
);

CREATE TABLE IF NOT EXISTS outdoor_context (
    pipeline_run_id         VARCHAR     NOT NULL,
    computed_ts             TIMESTAMPTZ NOT NULL,
    outdoor_forecast_time   TIMESTAMPTZ,
    age_minutes             DOUBLE,
    is_stale                BOOLEAN     NOT NULL,
    pm2_5                   DOUBLE,
    pm10                    DOUBLE,
    temperature_2m          DOUBLE,
    relative_humidity_2m    DOUBLE,
    PRIMARY KEY (pipeline_run_id, computed_ts)
);

CREATE TABLE IF NOT EXISTS component_scores (
    pipeline_run_id         VARCHAR     NOT NULL,
    computed_ts             TIMESTAMPTZ NOT NULL,
    window_minutes          INTEGER     NOT NULL,
    component               VARCHAR     NOT NULL,   -- A | V | M
    available               BOOLEAN     NOT NULL,
    missing_inputs          VARCHAR[],
    membership_favorable    DOUBLE,
    membership_acceptable   DOUBLE,
    membership_degraded     DOUBLE,
    membership_critical     DOUBLE,
    crisp_score             DOUBLE,
    room                    VARCHAR,
    season                  VARCHAR,
    PRIMARY KEY (pipeline_run_id, computed_ts, window_minutes, component)
);

CREATE TABLE IF NOT EXISTS iaq_index_results (
    pipeline_run_id         VARCHAR     NOT NULL,
    computed_ts             TIMESTAMPTZ NOT NULL,
    window_minutes          INTEGER     NOT NULL,
    completeness_status     VARCHAR     NOT NULL,   -- OK | PARTIAL | FAILED
    missing_components      VARCHAR[],
    missing_inputs          VARCHAR[],
    index_value             DOUBLE,                  -- NULL if FAILED
    index_class             VARCHAR,                 -- NULL if FAILED
    -- Dominant adverse component(s): the available component(s) with the
    -- highest adverse crisp score, ties preserved only within
    -- membership.dominant_component_tie_tolerance. Empty for FAILED.
    dominant_component      VARCHAR[],
    -- Separate diagnostic: which component(s) "bound" the min() in the
    -- fired Mamdani rules (rule-level attribution). NOT the manuscript's
    -- dominant adverse component -- kept only as an optional diagnostic.
    rule_level_contributors VARCHAR[],
    n_rules_fired           INTEGER,
    engine_version          VARCHAR     NOT NULL,
    config_hash             VARCHAR     NOT NULL,
    computed_at             TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (pipeline_run_id, computed_ts, window_minutes)
);

-- Evaluation identity: distinct from pipeline_run_id. One pipeline run may
-- be evaluated multiple times (e.g. after a config change); each evaluation
-- execution gets its own evaluation_run_id and never mixes rows with any
-- other evaluation_run_id, even for the same pipeline_run_id.
CREATE TABLE IF NOT EXISTS evaluation_runs (
    evaluation_run_id        VARCHAR PRIMARY KEY,
    pipeline_run_id          VARCHAR     NOT NULL,
    started_at               TIMESTAMPTZ NOT NULL,
    finished_at              TIMESTAMPTZ,
    status                   VARCHAR     NOT NULL,   -- success | failed
    evaluated_range_from     TIMESTAMPTZ,
    evaluated_range_to       TIMESTAMPTZ,
    window_minutes           INTEGER,
    config_hash              VARCHAR     NOT NULL,
    evaluation_config_hash   VARCHAR     NOT NULL,
    stability_seed           INTEGER,
    stability_n_trials       INTEGER,
    sample_strategy          VARCHAR,
    n_computed_ts_evaluated  INTEGER,
    errors                   VARCHAR[],
    warnings                 VARCHAR[]
);

CREATE TABLE IF NOT EXISTS baseline_results (
    pipeline_run_id    VARCHAR     NOT NULL,
    evaluation_run_id  VARCHAR     NOT NULL,
    computed_ts        TIMESTAMPTZ NOT NULL,
    window_minutes     INTEGER     NOT NULL,
    method             VARCHAR     NOT NULL,   -- CRISP-MAX | WEIGHTED-MEAN
    index_value        DOUBLE,                  -- NULL if no components available
    index_class        VARCHAR,
    n_components       INTEGER     NOT NULL,
    PRIMARY KEY (pipeline_run_id, evaluation_run_id, computed_ts, window_minutes, method)
);

CREATE TABLE IF NOT EXISTS evaluation_agreement (
    evaluation_run_id  VARCHAR     NOT NULL,
    pipeline_run_id    VARCHAR     NOT NULL,
    method_a           VARCHAR     NOT NULL,
    method_b           VARCHAR     NOT NULL,
    n                  INTEGER     NOT NULL,
    n_excluded         INTEGER     NOT NULL,
    percent_agreement  DOUBLE,
    cohens_kappa       DOUBLE,
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (evaluation_run_id, method_a, method_b)
);

-- Multi-point stability: one row per (evaluation_run_id, sample_id) -- a
-- deterministically-selected computed_ts, not just the latest one.
CREATE TABLE IF NOT EXISTS evaluation_stability_samples (
    evaluation_run_id      VARCHAR     NOT NULL,
    pipeline_run_id        VARCHAR     NOT NULL,
    sample_id              VARCHAR     NOT NULL,
    computed_ts            TIMESTAMPTZ NOT NULL,
    selection_reason       VARCHAR     NOT NULL,   -- boundary_adjacent | random_comparison
    boundary_channel       VARCHAR,
    baseline_class_hfis            VARCHAR,
    baseline_index_hfis            DOUBLE,
    baseline_class_crisp_max       VARCHAR,
    baseline_index_crisp_max       DOUBLE,
    baseline_class_weighted_mean   VARCHAR,
    baseline_index_weighted_mean   DOUBLE,
    PRIMARY KEY (evaluation_run_id, sample_id)
);

-- Tidy per-trial outcomes: one row per (sample, method, trial).
CREATE TABLE IF NOT EXISTS evaluation_stability_trials (
    evaluation_run_id      VARCHAR     NOT NULL,
    pipeline_run_id        VARCHAR     NOT NULL,
    sample_id              VARCHAR     NOT NULL,
    method                 VARCHAR     NOT NULL,   -- PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN
    trial_index            INTEGER     NOT NULL,
    trial_class            VARCHAR,
    trial_index_value      DOUBLE,
    changed_from_baseline  BOOLEAN     NOT NULL,
    abs_index_change       DOUBLE,
    PRIMARY KEY (evaluation_run_id, sample_id, method, trial_index)
);

-- Multi-point sensitivity: one row per (evaluation_run_id, sample_id,
-- varied_parameter, value) -- a deterministic stratified sample of
-- computed_ts, not just the latest one.
CREATE TABLE IF NOT EXISTS evaluation_sensitivity (
    evaluation_run_id    VARCHAR     NOT NULL,
    pipeline_run_id      VARCHAR     NOT NULL,
    sample_id            VARCHAR     NOT NULL,
    computed_ts          TIMESTAMPTZ NOT NULL,
    stratum              VARCHAR     NOT NULL,   -- e.g. class=Favorable | boundary_adjacent | ordinary
    reference_completeness_status VARCHAR,
    reference_index_class VARCHAR,
    reference_index_value DOUBLE,
    varied_parameter     VARCHAR     NOT NULL,   -- window_minutes | coverage_threshold
    value                DOUBLE      NOT NULL,
    completeness_status  VARCHAR     NOT NULL,
    index_value          DOUBLE,
    index_class          VARCHAR,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (evaluation_run_id, sample_id, varied_parameter, value)
);

CREATE TABLE IF NOT EXISTS evaluation_masking (
    evaluation_run_id    VARCHAR     NOT NULL,
    pipeline_run_id      VARCHAR     NOT NULL,
    method               VARCHAR     NOT NULL,
    severity_threshold   VARCHAR     NOT NULL,
    n_critical_events    INTEGER     NOT NULL,
    n_masked             INTEGER     NOT NULL,
    masking_rate         DOUBLE,                  -- NULL when n_critical_events = 0
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (evaluation_run_id, method, severity_threshold)
);

-- Synthetic, deterministic, pre-labeled reference vectors constructed from
-- the manuscript's own control-region boundaries -- rule-consistency checks
-- against a known label, NOT an empirical ground truth. See
-- iaq_hfis.evaluation.reference_cases.
CREATE TABLE IF NOT EXISTS evaluation_reference_cases (
    evaluation_run_id  VARCHAR     NOT NULL,
    pipeline_run_id    VARCHAR     NOT NULL,
    method             VARCHAR     NOT NULL,
    n                  INTEGER     NOT NULL,
    n_excluded         INTEGER     NOT NULL,
    macro_f1           DOUBLE,
    cohens_kappa       DOUBLE,
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (evaluation_run_id, method)
);

-- HFIS vs CRISP-MAX (vs WEIGHTED-MEAN where meaningful) boundary continuity
-- experiment: dense input grids around each control-region boundary.
CREATE TABLE IF NOT EXISTS evaluation_continuity_grid (
    evaluation_run_id  VARCHAR     NOT NULL,
    pipeline_run_id    VARCHAR     NOT NULL,
    boundary_id        VARCHAR     NOT NULL,
    channel            VARCHAR     NOT NULL,
    boundary_value     DOUBLE      NOT NULL,
    grid_index         INTEGER     NOT NULL,
    input_value        DOUBLE      NOT NULL,
    method             VARCHAR     NOT NULL,   -- PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN
    index_value        DOUBLE,
    index_class        VARCHAR,
    PRIMARY KEY (evaluation_run_id, boundary_id, method, grid_index)
);

CREATE TABLE IF NOT EXISTS evaluation_continuity_summary (
    evaluation_run_id          VARCHAR NOT NULL,
    pipeline_run_id            VARCHAR NOT NULL,
    boundary_id                VARCHAR NOT NULL,
    channel                    VARCHAR NOT NULL,
    method                     VARCHAR NOT NULL,
    max_adjacent_jump          DOUBLE,
    mean_adjacent_jump         DOUBLE,
    total_variation            DOUBLE,
    n_class_transitions        INTEGER,
    class_transition_positions VARCHAR,   -- semicolon-joined input_values
    index_range                DOUBLE,
    monotonicity_violations    INTEGER,
    masked_by_favorable        BOOLEAN,
    PRIMARY KEY (evaluation_run_id, boundary_id, method)
);

-- Fault-injection benchmark: deterministic synthetic scenarios with known
-- injected faults, scored against the real quality-detection layer. Kept
-- fully separate from observation_quality (real, unlabeled data).
CREATE TABLE IF NOT EXISTS fault_injection_events (
    evaluation_run_id  VARCHAR     NOT NULL,
    pipeline_run_id    VARCHAR     NOT NULL,
    scenario_id        VARCHAR     NOT NULL,
    channel            VARCHAR     NOT NULL,
    fault_type         VARCHAR     NOT NULL,
    injected_at_index  INTEGER     NOT NULL,
    duration_samples   INTEGER     NOT NULL,
    description        VARCHAR,
    PRIMARY KEY (evaluation_run_id, scenario_id, channel, injected_at_index)
);

CREATE TABLE IF NOT EXISTS fault_detection_predictions (
    evaluation_run_id  VARCHAR     NOT NULL,
    pipeline_run_id    VARCHAR     NOT NULL,
    scenario_id        VARCHAR     NOT NULL,
    channel            VARCHAR     NOT NULL,
    sample_index       INTEGER     NOT NULL,
    true_fault_type    VARCHAR,    -- NULL when the sample is genuinely clean/no fault
    predicted_reason_codes VARCHAR[],
    stage2_state        VARCHAR,
    usable               BOOLEAN,
    PRIMARY KEY (evaluation_run_id, scenario_id, channel, sample_index)
);

CREATE TABLE IF NOT EXISTS fault_detection_metrics (
    evaluation_run_id      VARCHAR NOT NULL,
    pipeline_run_id        VARCHAR NOT NULL,
    reason_code            VARCHAR NOT NULL,
    tp                     INTEGER NOT NULL,
    fp                     INTEGER NOT NULL,
    fn                     INTEGER NOT NULL,
    precision               DOUBLE,
    recall                  DOUBLE,
    f1                      DOUBLE,
    false_positive_rate     DOUBLE,
    mean_detection_delay    DOUBLE,
    PRIMARY KEY (evaluation_run_id, reason_code)
);

CREATE TABLE IF NOT EXISTS hampel_calibration (
    evaluation_run_id  VARCHAR NOT NULL,
    pipeline_run_id    VARCHAR NOT NULL,
    dataset_split       VARCHAR NOT NULL,  -- development | holdout
    window_size          INTEGER NOT NULL,
    mad_multiplier         DOUBLE  NOT NULL,
    fault_recall             DOUBLE,
    genuine_event_preservation_rate DOUBLE,
    objective_score            DOUBLE,
    selected                    BOOLEAN NOT NULL,
    PRIMARY KEY (evaluation_run_id, dataset_split, window_size, mad_multiplier)
);

-- Machine-readable parameter provenance: one row per scientific/operational
-- parameter, per pipeline_run_id (values are read from the effective
-- config at run time, so provenance travels with the run that used them).
CREATE TABLE IF NOT EXISTS parameter_provenance (
    pipeline_run_id  VARCHAR NOT NULL,
    parameter_path   VARCHAR NOT NULL,
    effective_value  VARCHAR NOT NULL,
    unit             VARCHAR,
    status           VARCHAR NOT NULL,  -- manuscript_defined | standard_based | sensor_specification | author_defined | provisional
    source           VARCHAR NOT NULL,
    engaged          BOOLEAN NOT NULL,
    sensitivity_coverage VARCHAR,
    PRIMARY KEY (pipeline_run_id, parameter_path)
);
