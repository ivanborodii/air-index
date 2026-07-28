from datetime import datetime, timezone

from iaq_hfis.db import DerivedResultsWriter

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)

EXPECTED_TABLES = {
    "observation_quality",
    "window_aggregates",
    "outdoor_context",
    "component_scores",
    "iaq_index_results",
    "pipeline_runs",
    "evaluation_runs",
    "schema_version",
}

_INSERT_SQL = """INSERT OR REPLACE INTO iaq_index_results
         (pipeline_run_id, computed_ts, window_minutes, completeness_status, missing_components, missing_inputs,
          index_value, index_class, dominant_component, rule_level_contributors, n_rules_fired, engine_version, config_hash, computed_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _row(pipeline_run_id: str, index_value: float) -> list:
    return [pipeline_run_id, NOW, 15, "OK", [], [], index_value, "Acceptable", ["A"], ["A"], 30, "0.1.0", "abc123", NOW]


def test_schema_creates_all_derived_tables(base_settings):
    writer = DerivedResultsWriter(base_settings.paths.derived_db_path)
    try:
        tables = {r[0] for r in writer.connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
        assert EXPECTED_TABLES <= tables
    finally:
        writer.close()


def test_writer_never_touches_air_monitor_tables(base_settings):
    writer = DerivedResultsWriter(base_settings.paths.derived_db_path)
    try:
        tables = {r[0] for r in writer.connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
        assert "raw_observations" not in tables
        assert "weather_observations" not in tables
        assert "microbatches" not in tables
        assert "runtime_metrics" not in tables
    finally:
        writer.close()


def test_upsert_is_idempotent(base_settings):
    writer = DerivedResultsWriter(base_settings.paths.derived_db_path)
    try:
        writer.connection.execute(_INSERT_SQL, _row("run-a", 42.5))
        writer.connection.execute(_INSERT_SQL, _row("run-a", 43.0))  # re-insert, same key, different value
        result = writer.connection.execute(
            "SELECT index_value FROM iaq_index_results WHERE pipeline_run_id=? AND computed_ts=? AND window_minutes=?", ["run-a", NOW, 15]
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == 43.0
    finally:
        writer.close()


def test_two_pipeline_runs_over_same_timestamp_do_not_overwrite_each_other(base_settings):
    """Mandatory regression test: two pipeline runs over the same
    computed_ts/window_minutes must be isolated by pipeline_run_id, never
    overwrite or read each other's rows -- the core guarantee of the
    run-isolated schema."""
    writer = DerivedResultsWriter(base_settings.paths.derived_db_path)
    try:
        writer.connection.execute(_INSERT_SQL, _row("run-a", 10.0))
        writer.connection.execute(_INSERT_SQL, _row("run-b", 90.0))

        a = writer.connection.execute(
            "SELECT index_value FROM iaq_index_results WHERE pipeline_run_id=? AND computed_ts=? AND window_minutes=?", ["run-a", NOW, 15]
        ).fetchone()
        b = writer.connection.execute(
            "SELECT index_value FROM iaq_index_results WHERE pipeline_run_id=? AND computed_ts=? AND window_minutes=?", ["run-b", NOW, 15]
        ).fetchone()
        both = writer.connection.execute(
            "SELECT COUNT(*) FROM iaq_index_results WHERE computed_ts=? AND window_minutes=?", [NOW, 15]
        ).fetchone()

        assert a[0] == 10.0
        assert b[0] == 90.0
        assert both[0] == 2  # both rows coexist, neither overwrote the other
    finally:
        writer.close()


def test_schema_creation_is_idempotent_across_writers(base_settings):
    w1 = DerivedResultsWriter(base_settings.paths.derived_db_path)
    w1.close()
    w2 = DerivedResultsWriter(base_settings.paths.derived_db_path)  # re-running CREATE TABLE IF NOT EXISTS must not error
    w2.close()
