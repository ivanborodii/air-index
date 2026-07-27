-- src/iaq_hfis/sql/create_tables.sql
-- Derived schema for the iaq_hfis fuzzy IAQ index, deployed to a NEW,
-- dedicated DuckDB file (config: paths.derived_db_path). This file is
-- entirely additive and never shares a database with air-monitor's
-- raw_observations / microbatches / runtime_metrics / weather_observations
-- tables (those are read-only sources, opened from a separate file/snapshot).
-- All statements are idempotent (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS observation_quality (
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
    PRIMARY KEY (ts, channel)
);

CREATE TABLE IF NOT EXISTS window_aggregates (
    computed_ts     TIMESTAMPTZ NOT NULL,
    window_minutes  INTEGER     NOT NULL,   -- 5 | 15 | 30 | 60
    channel         VARCHAR     NOT NULL,
    n_expected      INTEGER     NOT NULL,
    n_usable        INTEGER     NOT NULL,
    coverage_ratio  DOUBLE      NOT NULL,
    coverage_ok     BOOLEAN     NOT NULL,
    weighted_mean   DOUBLE,                  -- NULL if coverage_ok = FALSE
    PRIMARY KEY (computed_ts, window_minutes, channel)
);

CREATE TABLE IF NOT EXISTS outdoor_context (
    computed_ts             TIMESTAMPTZ NOT NULL,
    outdoor_forecast_time   TIMESTAMPTZ,
    age_minutes             DOUBLE,
    is_stale                BOOLEAN     NOT NULL,
    pm2_5                   DOUBLE,
    pm10                    DOUBLE,
    temperature_2m          DOUBLE,
    relative_humidity_2m    DOUBLE,
    PRIMARY KEY (computed_ts)
);

CREATE TABLE IF NOT EXISTS component_scores (
    computed_ts             TIMESTAMPTZ NOT NULL,
    window_minutes          INTEGER     NOT NULL,
    component                VARCHAR     NOT NULL,   -- A | V | M
    available                 BOOLEAN     NOT NULL,
    missing_inputs             VARCHAR[],
    membership_favorable        DOUBLE,
    membership_acceptable       DOUBLE,
    membership_degraded         DOUBLE,
    membership_critical         DOUBLE,
    crisp_score                  DOUBLE,     -- reserved for Phase 2 CRISP-MAX / WEIGHTED-MEAN baselines
    room                          VARCHAR,
    season                        VARCHAR,
    PRIMARY KEY (computed_ts, window_minutes, component)
);

CREATE TABLE IF NOT EXISTS iaq_index_results (
    computed_ts               TIMESTAMPTZ NOT NULL,
    window_minutes             INTEGER     NOT NULL,
    completeness_status         VARCHAR     NOT NULL,   -- OK | PARTIAL | FAILED
    missing_components           VARCHAR[],
    missing_inputs                 VARCHAR[],
    index_value                     DOUBLE,               -- NULL if FAILED
    index_class                     VARCHAR,              -- NULL if FAILED
    dominant_component               VARCHAR[],            -- >=1 entries; ties preserved
    n_rules_fired                     INTEGER,
    engine_version                     VARCHAR NOT NULL,
    config_hash                         VARCHAR NOT NULL,
    computed_at                          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (computed_ts, window_minutes)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id                  VARCHAR PRIMARY KEY,
    started_at               TIMESTAMPTZ NOT NULL,
    finished_at               TIMESTAMPTZ,
    status                     VARCHAR NOT NULL,   -- success | partial | failed
    computed_ts_min             TIMESTAMPTZ,
    computed_ts_max             TIMESTAMPTZ,
    n_timestamps_processed        INTEGER,
    n_snapshot_retries              INTEGER,
    config_hash                       VARCHAR NOT NULL,
    run_summary_path                    VARCHAR
);

-- Phase 2A: baselines + quantitative evaluation. All additive, all new
-- tables, still never touching raw_observations/weather_observations.

CREATE TABLE IF NOT EXISTS baseline_results (
    computed_ts       TIMESTAMPTZ NOT NULL,
    window_minutes    INTEGER     NOT NULL,
    method            VARCHAR     NOT NULL,   -- CRISP-MAX | WEIGHTED-MEAN
    index_value       DOUBLE,                  -- NULL if no components available
    index_class       VARCHAR,
    n_components      INTEGER     NOT NULL,
    PRIMARY KEY (computed_ts, window_minutes, method)
);

CREATE TABLE IF NOT EXISTS evaluation_agreement (
    run_id             VARCHAR     NOT NULL,
    method_a           VARCHAR     NOT NULL,
    method_b           VARCHAR     NOT NULL,
    n                  INTEGER     NOT NULL,
    n_excluded         INTEGER     NOT NULL,
    percent_agreement  DOUBLE,
    cohens_kappa       DOUBLE,
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, method_a, method_b)
);

CREATE TABLE IF NOT EXISTS evaluation_stability (
    run_id             VARCHAR     NOT NULL,
    computed_ts        TIMESTAMPTZ NOT NULL,
    seed               INTEGER     NOT NULL,
    n_trials           INTEGER     NOT NULL,
    baseline_class     VARCHAR,
    n_class_changes    INTEGER     NOT NULL,
    class_change_rate  DOUBLE      NOT NULL,
    trial_classes      VARCHAR[]   NOT NULL,   -- per-trial outcome, in trial order (Phase 2B plots/exports)
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, computed_ts)
);

CREATE TABLE IF NOT EXISTS evaluation_sensitivity (
    run_id               VARCHAR     NOT NULL,
    computed_ts          TIMESTAMPTZ NOT NULL,
    varied_parameter     VARCHAR     NOT NULL,   -- window_minutes | coverage_threshold
    value                DOUBLE      NOT NULL,
    completeness_status  VARCHAR     NOT NULL,
    index_value          DOUBLE,
    index_class          VARCHAR,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, computed_ts, varied_parameter, value)
);

CREATE TABLE IF NOT EXISTS evaluation_masking (
    run_id               VARCHAR     NOT NULL,
    method               VARCHAR     NOT NULL,
    severity_threshold   VARCHAR     NOT NULL,
    n_critical_events    INTEGER     NOT NULL,
    n_masked             INTEGER     NOT NULL,
    masking_rate         DOUBLE,                  -- NULL when n_critical_events = 0
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, method, severity_threshold)
);

CREATE TABLE IF NOT EXISTS evaluation_ground_truth (
    run_id             VARCHAR     NOT NULL,
    method             VARCHAR     NOT NULL,
    n                  INTEGER     NOT NULL,
    n_excluded         INTEGER     NOT NULL,
    macro_f1           DOUBLE,
    cohens_kappa       DOUBLE,
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, method)
);
