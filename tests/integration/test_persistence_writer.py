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
}


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
        row = [NOW, 15, "OK", [], [], 42.5, "Acceptable", ["A"], 30, "0.1.0", "abc123", NOW]
        sql = """INSERT OR REPLACE INTO iaq_index_results
                 (computed_ts, window_minutes, completeness_status, missing_components, missing_inputs,
                  index_value, index_class, dominant_component, n_rules_fired, engine_version, config_hash, computed_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"""
        writer.connection.execute(sql, row)
        row[5] = 43.0  # re-insert with a different value at the same primary key
        writer.connection.execute(sql, row)
        result = writer.connection.execute("SELECT index_value FROM iaq_index_results WHERE computed_ts=? AND window_minutes=?", [NOW, 15]).fetchall()
        assert len(result) == 1
        assert result[0][0] == 43.0
    finally:
        writer.close()


def test_schema_creation_is_idempotent_across_writers(base_settings):
    w1 = DerivedResultsWriter(base_settings.paths.derived_db_path)
    w1.close()
    w2 = DerivedResultsWriter(base_settings.paths.derived_db_path)  # re-running CREATE TABLE IF NOT EXISTS must not error
    w2.close()
