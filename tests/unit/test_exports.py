from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from iaq_hfis.db import DerivedResultsWriter
from iaq_hfis.reporting import exports

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
RANGE_FROM = NOW - timedelta(hours=1)
RANGE_TO = NOW + timedelta(hours=1)
RUN_ID = "test-run-1"


@pytest.fixture
def writer(base_settings):
    w = DerivedResultsWriter(base_settings.paths.derived_db_path)
    yield w
    w.close()


def _insert_index_result(con, computed_ts, window_minutes=15, status="OK", index_value=42.5, index_class="Acceptable"):
    con.execute(
        "INSERT INTO iaq_index_results (computed_ts, window_minutes, completeness_status, missing_components, missing_inputs, index_value, index_class, dominant_component, n_rules_fired, engine_version, config_hash, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [computed_ts, window_minutes, status, [], [], index_value, index_class, ["A"], 5, "0.1.0", "hash", NOW],
    )


def test_export_index_timeseries_has_correct_columns_and_data(writer, tmp_path):
    con = writer.connection
    _insert_index_result(con, NOW)
    path = exports.export_index_timeseries(con, tmp_path, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    df = pd.read_csv(path)
    assert list(df.columns) == [c.name for c in exports.COLUMNS[exports.INDEX_TIMESERIES]]
    assert len(df) == 1
    assert df.iloc[0]["index_value"] == 42.5
    assert df.iloc[0]["dominant_component"] == "A"  # list joined with ';' (single element here)


def test_export_index_timeseries_joins_multi_element_lists(writer, tmp_path):
    con = writer.connection
    con.execute(
        "INSERT INTO iaq_index_results (computed_ts, window_minutes, completeness_status, missing_components, missing_inputs, index_value, index_class, dominant_component, n_rules_fired, engine_version, config_hash, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [NOW, 15, "OK", [], [], 50.0, "Degraded", ["A", "V"], 3, "0.1.0", "hash", NOW],
    )
    path = exports.export_index_timeseries(con, tmp_path, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    df = pd.read_csv(path)
    assert df.iloc[0]["dominant_component"] == "A;V"


def test_export_reason_code_frequency_none_when_no_data(writer, tmp_path):
    assert exports.export_reason_code_frequency(writer.connection, tmp_path, RANGE_FROM, RANGE_TO) is None


def test_export_masking_summary_none_when_no_data(writer, tmp_path):
    assert exports.export_masking_summary(writer.connection, tmp_path, RUN_ID) is None


def test_export_stability_trials_none_when_no_data(writer, tmp_path):
    assert exports.export_stability_trials(writer.connection, tmp_path, RUN_ID) is None


def test_export_stability_trials_has_expected_rows(writer, tmp_path):
    con = writer.connection
    con.execute(
        "INSERT INTO evaluation_stability (run_id, computed_ts, seed, n_trials, baseline_class, n_class_changes, class_change_rate, trial_classes, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        [RUN_ID, NOW, 42, 3, "Favorable", 1, 1 / 3, ["Favorable", "Favorable", "Acceptable"], NOW],
    )
    path = exports.export_stability_trials(con, tmp_path, RUN_ID)
    df = pd.read_csv(path)
    assert len(df) == 3
    assert list(df["changed_from_baseline"]) == [False, False, True]


def test_export_all_returns_a_path_or_none_for_every_file(writer, tmp_path):
    con = writer.connection
    _insert_index_result(con, NOW)
    result = exports.export_all(con, tmp_path, window_minutes=15, run_id=RUN_ID, from_ts=NOW.replace(hour=0), to_ts=NOW)
    assert set(result.keys()) == set(exports.COLUMNS.keys())
    assert result[exports.INDEX_TIMESERIES] is not None
    assert result[exports.MASKING_SUMMARY] is None  # nothing inserted for this run_id
