from datetime import datetime, timedelta, timezone

from iaq_hfis.db import DerivedResultsWriter
from iaq_hfis.evaluation.faults import compute_reason_code_frequency, compute_status_proportions

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
RANGE_FROM = NOW - timedelta(hours=1)
RANGE_TO = NOW + timedelta(hours=1)


def _writer(base_settings) -> DerivedResultsWriter:
    return DerivedResultsWriter(base_settings.paths.derived_db_path)


def test_status_proportions_sum_to_one(base_settings):
    writer = _writer(base_settings)
    con = writer.connection
    rows = [("OK",), ("OK",), ("OK",), ("PARTIAL",), ("FAILED",)]
    for i, (status,) in enumerate(rows):
        con.execute(
            "INSERT INTO iaq_index_results (computed_ts, window_minutes, completeness_status, missing_components, missing_inputs, index_value, index_class, dominant_component, n_rules_fired, engine_version, config_hash, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [NOW.replace(minute=i), 15, status, [], [], None, None, [], None, "0.1.0", "hash", NOW],
        )
    result = compute_status_proportions(con, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    writer.close()

    assert result.n_total == 5
    assert result.ok == 3 / 5
    assert result.partial == 1 / 5
    assert result.failed == 1 / 5
    assert result.ok + result.partial + result.failed == 1.0


def test_status_proportions_none_when_no_data(base_settings):
    writer = _writer(base_settings)
    result = compute_status_proportions(writer.connection, window_minutes=15, from_ts=RANGE_FROM, to_ts=RANGE_TO)
    writer.close()
    assert result.n_total == 0
    assert result.ok is None  # explained, not fabricated as 0.0


def test_reason_code_frequency_counts_correctly(base_settings):
    writer = _writer(base_settings)
    con = writer.connection
    rows = [["stuck_value"], ["stuck_value", "out_of_range"], [], ["data_loss"]]
    for i, codes in enumerate(rows):
        con.execute(
            "INSERT INTO observation_quality (ts, channel, raw_value, stage1_state, stage2_state, usable, confirmed, reason_codes, hampel_median, hampel_mad, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [NOW.replace(minute=i), "co2", 700.0, "VALID", "VALID", True, None, codes, None, None, NOW],
        )
    result = compute_reason_code_frequency(con, RANGE_FROM, RANGE_TO)
    writer.close()

    assert result.n_total_quality_rows == 4
    assert result.counts["stuck_value"] == 2
    assert result.counts["out_of_range"] == 1
    assert result.counts["data_loss"] == 1


def test_reason_code_frequency_none_data_gives_empty_counts(base_settings):
    writer = _writer(base_settings)
    result = compute_reason_code_frequency(writer.connection, RANGE_FROM, RANGE_TO)
    writer.close()
    assert result.n_total_quality_rows == 0
    assert result.counts == {}
