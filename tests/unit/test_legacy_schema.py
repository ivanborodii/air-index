import duckdb
import pytest

from iaq_hfis.db import DerivedResultsWriter, LegacySchemaError, rebuild_derived_database


def test_legacy_schema_without_pipeline_run_id_is_detected(tmp_path):
    """Mandatory regression test: a pre-run-isolation derived database
    (iaq_index_results without a pipeline_run_id column) must be detected
    and rejected, never silently reinterpreted."""
    db_path = tmp_path / "legacy.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """CREATE TABLE iaq_index_results (
               computed_ts TIMESTAMPTZ, window_minutes INTEGER, completeness_status VARCHAR,
               index_value DOUBLE, index_class VARCHAR, dominant_component VARCHAR[],
               n_rules_fired INTEGER, engine_version VARCHAR, config_hash VARCHAR, computed_at TIMESTAMPTZ
           )"""
    )
    con.close()

    with pytest.raises(LegacySchemaError, match="pipeline_run_id"):
        DerivedResultsWriter(str(db_path))


def test_rebuild_db_recovers_from_legacy_schema(tmp_path):
    db_path = tmp_path / "legacy.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE iaq_index_results (computed_ts TIMESTAMPTZ, window_minutes INTEGER)")
    con.close()

    with pytest.raises(LegacySchemaError):
        DerivedResultsWriter(str(db_path))

    rebuild_derived_database(str(db_path))
    writer = DerivedResultsWriter(str(db_path))  # must not raise now
    writer.close()


def test_schema_version_mismatch_is_detected(tmp_path):
    db_path = tmp_path / "future.duckdb"
    writer = DerivedResultsWriter(str(db_path))
    writer.connection.execute("UPDATE schema_version SET version = 999")
    writer.close()

    with pytest.raises(LegacySchemaError, match="schema_version=999"):
        DerivedResultsWriter(str(db_path))
