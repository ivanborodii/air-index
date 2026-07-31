from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from iaq_hfis.db import DerivedResultsWriter
from iaq_hfis.reporting import exports

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
RANGE_FROM = NOW - timedelta(hours=1)
RANGE_TO = NOW + timedelta(hours=1)
PIPELINE_RUN_ID = "test-pipeline-1"
EVALUATION_RUN_ID = "test-eval-1"


@pytest.fixture
def writer(base_settings):
    w = DerivedResultsWriter(base_settings.paths.derived_db_path)
    yield w
    w.close()


def _insert_index_result(con, computed_ts, window_minutes=15, status="OK", index_value=42.5, index_class="Acceptable", pipeline_run_id=PIPELINE_RUN_ID):
    con.execute(
        "INSERT INTO iaq_index_results (pipeline_run_id, computed_ts, window_minutes, completeness_status, missing_components, missing_inputs, index_value, index_class, dominant_component, co_dominant_components, rule_level_contributors, n_rules_fired, engine_version, config_hash, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [pipeline_run_id, computed_ts, window_minutes, status, [], [], index_value, index_class, "A", ["A"], ["A"], 5, "0.1.0", "hash", NOW],
    )


def test_export_index_timeseries_has_correct_columns_and_data(writer, tmp_path):
    con = writer.connection
    _insert_index_result(con, NOW)
    path = exports.export_index_timeseries(con, tmp_path, PIPELINE_RUN_ID, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    df = pd.read_csv(path)
    assert list(df.columns) == [c.name for c in exports.COLUMNS[exports.INDEX_TIMESERIES]]
    assert len(df) == 1
    assert df.iloc[0]["index_value"] == 42.5
    assert df.iloc[0]["dominant_component"] == "A"
    assert df.iloc[0]["co_dominant_components"] == "A"  # list joined with ';' (single element here)


def test_export_index_timeseries_joins_multi_element_co_dominant_list(writer, tmp_path):
    con = writer.connection
    con.execute(
        "INSERT INTO iaq_index_results (pipeline_run_id, computed_ts, window_minutes, completeness_status, missing_components, missing_inputs, index_value, index_class, dominant_component, co_dominant_components, rule_level_contributors, n_rules_fired, engine_version, config_hash, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [PIPELINE_RUN_ID, NOW, 15, "OK", [], [], 50.0, "Degraded", "A", ["A", "V"], ["A", "V"], 3, "0.1.0", "hash", NOW],
    )
    path = exports.export_index_timeseries(con, tmp_path, PIPELINE_RUN_ID, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    df = pd.read_csv(path)
    assert df.iloc[0]["co_dominant_components"] == "A;V"


def test_export_index_timeseries_scoped_to_pipeline_run_id(writer, tmp_path):
    con = writer.connection
    _insert_index_result(con, NOW, pipeline_run_id="other-run")
    path = exports.export_index_timeseries(con, tmp_path, PIPELINE_RUN_ID, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    df = pd.read_csv(path)
    assert len(df) == 0  # the row belongs to a different pipeline_run_id


def test_export_reason_code_frequency_none_when_no_data(writer, tmp_path):
    assert exports.export_reason_code_frequency(writer.connection, tmp_path, PIPELINE_RUN_ID, RANGE_FROM, RANGE_TO) is None


def test_export_masking_summary_none_when_no_data(writer, tmp_path):
    assert exports.export_masking_summary(writer.connection, tmp_path, EVALUATION_RUN_ID) is None


def test_export_stability_trials_none_when_no_data(writer, tmp_path):
    assert exports.export_stability_trials(writer.connection, tmp_path, EVALUATION_RUN_ID) is None


def test_export_stability_trials_has_expected_rows(writer, tmp_path):
    con = writer.connection
    con.execute(
        "INSERT INTO evaluation_stability_samples (evaluation_run_id, pipeline_run_id, sample_id, computed_ts, selection_reason, boundary_channel, "
        "baseline_class_hfis, baseline_index_hfis, baseline_class_crisp_max, baseline_index_crisp_max, baseline_class_weighted_mean, baseline_index_weighted_mean) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [EVALUATION_RUN_ID, PIPELINE_RUN_ID, "sample-1", NOW, "boundary_adjacent", "pm2_5", "Favorable", 10.0, "Favorable", 10.0, "Favorable", 10.0],
    )
    trial_classes = ["Favorable", "Favorable", "Acceptable"]
    for i, tc in enumerate(trial_classes):
        con.execute(
            "INSERT INTO evaluation_stability_trials (evaluation_run_id, pipeline_run_id, sample_id, method, trial_index, trial_class, trial_index_value, changed_from_baseline, abs_index_change) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [EVALUATION_RUN_ID, PIPELINE_RUN_ID, "sample-1", "PROPOSED_HFIS", i, tc, 10.0 if tc == "Favorable" else 26.0, tc != "Favorable", 0.0 if tc == "Favorable" else 16.0],
        )
    path = exports.export_stability_trials(con, tmp_path, EVALUATION_RUN_ID)
    df = pd.read_csv(path)
    assert len(df) == 3
    assert list(df["changed_from_baseline"]) == [False, False, True]


def test_export_all_returns_a_path_or_none_for_every_file(writer, tmp_path):
    con = writer.connection
    _insert_index_result(con, NOW)
    result = exports.export_all(con, tmp_path, window_minutes=15, pipeline_run_id=PIPELINE_RUN_ID, evaluation_run_id=EVALUATION_RUN_ID, from_ts=NOW.replace(hour=0), to_ts=NOW)
    assert set(result.keys()) == set(exports.COLUMNS.keys())
    assert result[exports.INDEX_TIMESERIES] is not None
    assert result[exports.MASKING_SUMMARY] is None  # nothing inserted for this evaluation_run_id


def test_export_all_with_no_evaluation_run_id_skips_evaluation_exports(writer, tmp_path):
    con = writer.connection
    _insert_index_result(con, NOW)
    result = exports.export_all(con, tmp_path, window_minutes=15, pipeline_run_id=PIPELINE_RUN_ID, evaluation_run_id=None, from_ts=NOW.replace(hour=0), to_ts=NOW)
    assert result[exports.INDEX_TIMESERIES] is not None
    assert result[exports.METHOD_COMPARISON] is None
    assert result[exports.STABILITY_SUMMARY] is None
