"""Historical-context tests (task spec section 4/5): the causal Hampel
filter needs window_size-1 valid samples strictly before a point, so the
aggregation interval's own first slots need data from before window_start.
Uses the real production pipeline (run_pipeline/compute_index_at) throughout.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest
from fixtures.build_synthetic_db import create_air_monitor_db, create_weather_db, default_weather_row, make_rows

from iaq_hfis.pipeline import run_pipeline

COMPUTED_TS = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _run(base_settings, sensor_specs, room_profiles, rows, computed_ts=COMPUTED_TS, window_minutes=15):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), rows)
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(computed_ts - timedelta(hours=1))])
    summary = run_pipeline(
        base_settings, sensor_specs, room_profiles, computed_ts - timedelta(minutes=1), computed_ts + timedelta(minutes=1),
        window_minutes=window_minutes,
    )
    con = duckdb.connect(base_settings.paths.derived_db_path, read_only=True)
    quality = con.execute(
        "SELECT ts, stage1_state, stage2_state, usable, hampel_median FROM observation_quality "
        "WHERE pipeline_run_id = ? AND channel = 'co2' ORDER BY ts",
        [summary["pipeline_run_id"]],
    ).df()
    aggregate = con.execute(
        "SELECT n_expected, n_usable FROM window_aggregates WHERE pipeline_run_id = ? AND channel = 'co2'",
        [summary["pipeline_run_id"]],
    ).fetchone()
    con.close()
    return summary, quality, aggregate


def test_historical_context_lets_the_first_in_window_slot_use_a_full_causal_hampel_window(base_settings, sensor_specs, room_profiles):
    # window_minutes=15 @ 30s cadence -> window_start = COMPUTED_TS - 15min.
    # hampel.window_size=11 (real config) needs 10 valid samples strictly
    # before a point. Provide 10 historical rows before window_start PLUS
    # the 30 in-window rows.
    window_start = COMPUTED_TS - timedelta(minutes=15)
    history_rows = make_rows(window_start - timedelta(seconds=30 * 9), 10)
    window_rows = make_rows(window_start + timedelta(seconds=30), 30)
    _, quality, aggregate = _run(base_settings, sensor_specs, room_profiles, history_rows + window_rows)

    first_slot = quality.iloc[0]
    assert first_slot["ts"] == window_start + timedelta(seconds=30)
    assert first_slot["hampel_median"] is not None and not (first_slot["hampel_median"] != first_slot["hampel_median"])  # not NaN

    # Item 6: historical context must never inflate n_expected/n_usable --
    # exactly the 30 in-window slots, never 40.
    n_expected, n_usable = aggregate
    assert n_expected == 30
    assert n_usable == 30
    assert len(quality) == 30  # only in-window rows persisted, never the 10 historical ones


def test_without_historical_context_the_first_slots_hampel_median_is_undefined(base_settings, sensor_specs, room_profiles):
    # Same window, but with NO data at all before window_start -- the first
    # in-window slot can have at most 1 valid sample in its causal window,
    # nowhere near window_size=11, so it must be left unevaluated (median NaN).
    window_start = COMPUTED_TS - timedelta(minutes=15)
    window_rows = make_rows(window_start + timedelta(seconds=30), 30)
    _, quality, aggregate = _run(base_settings, sensor_specs, room_profiles, window_rows)

    first_slot = quality.iloc[0]
    assert first_slot["hampel_median"] != first_slot["hampel_median"]  # NaN
    # Coverage/usability of the slot itself is unaffected (VALID clean data, just no Hampel opinion yet).
    assert first_slot["stage1_state"] == "VALID"
    assert bool(first_slot["usable"]) is True
    n_expected, n_usable = aggregate
    assert n_expected == 30
    assert n_usable == 30


def test_five_minute_window_can_use_the_eleven_point_causal_hampel_filter_via_history(base_settings, sensor_specs, room_profiles):
    # window_minutes=5 @ 30s cadence -> only 10 expected slots -- one short
    # of the 11 a causal window_size=11 filter needs even for the LAST slot
    # without history. With 10 historical rows before window_start, the
    # very FIRST in-window slot already has a full 11-point causal window.
    window_start = COMPUTED_TS - timedelta(minutes=5)
    history_rows = make_rows(window_start - timedelta(seconds=30 * 9), 10)
    window_rows = make_rows(window_start + timedelta(seconds=30), 10)
    _, quality, aggregate = _run(base_settings, sensor_specs, room_profiles, history_rows + window_rows, window_minutes=5)

    assert len(quality) == 10  # exactly the 5-minute window's own slots
    first_slot = quality.iloc[0]
    assert not (first_slot["hampel_median"] != first_slot["hampel_median"])  # defined, not NaN
    n_expected, n_usable = aggregate
    assert n_expected == 10
    assert n_usable == 10


def test_five_minute_window_without_history_never_gets_a_defined_hampel_median(base_settings, sensor_specs, room_profiles):
    # The Hampel filter must NOT be silently disabled for the 5-minute
    # config -- but without history, 10 in-window slots alone can never
    # reach window_size=11, so every slot correctly stays unevaluated.
    window_start = COMPUTED_TS - timedelta(minutes=5)
    window_rows = make_rows(window_start + timedelta(seconds=30), 10)
    _, quality, _ = _run(base_settings, sensor_specs, room_profiles, window_rows, window_minutes=5)
    assert quality["hampel_median"].isna().all()


@pytest.mark.parametrize("window_minutes", [15, 30, 60])
def test_larger_window_configurations_continue_to_work_with_history(base_settings, sensor_specs, room_profiles, window_minutes):
    window_start = COMPUTED_TS - timedelta(minutes=window_minutes)
    n_window_slots = (window_minutes * 60) // 30
    history_rows = make_rows(window_start - timedelta(seconds=30 * 9), 10)
    window_rows = make_rows(window_start + timedelta(seconds=30), n_window_slots)
    _, quality, aggregate = _run(base_settings, sensor_specs, room_profiles, history_rows + window_rows, window_minutes=window_minutes)
    assert len(quality) == n_window_slots
    n_expected, n_usable = aggregate
    assert n_expected == n_window_slots
    assert n_usable == n_window_slots


def test_missing_value_inside_window_stays_missing_despite_surrounding_history(base_settings, sensor_specs, room_profiles):
    window_start = COMPUTED_TS - timedelta(minutes=15)
    history_rows = make_rows(window_start - timedelta(seconds=30 * 9), 10)
    # Drop row index 5 entirely (simulate a genuinely missing raw sample).
    window_rows = [r for i, r in enumerate(make_rows(window_start + timedelta(seconds=30), 30)) if i != 5]
    _, quality, _ = _run(base_settings, sensor_specs, room_profiles, history_rows + window_rows)
    missing_row = quality.iloc[5]
    assert missing_row["stage1_state"] == "MISSING"
    assert missing_row["stage2_state"] == "MISSING"
    assert bool(missing_row["usable"]) is False


def test_pipeline_results_are_deterministic_with_historical_context(base_settings, sensor_specs, room_profiles):
    window_start = COMPUTED_TS - timedelta(minutes=15)
    history_rows = make_rows(window_start - timedelta(seconds=30 * 9), 10)
    window_rows = make_rows(window_start + timedelta(seconds=30), 30)
    rows = history_rows + window_rows

    _, quality_1, aggregate_1 = _run(base_settings, sensor_specs, room_profiles, rows)
    _, quality_2, aggregate_2 = _run(base_settings, sensor_specs, room_profiles, rows)

    assert quality_1["hampel_median"].tolist() == quality_2["hampel_median"].tolist()
    assert quality_1["usable"].tolist() == quality_2["usable"].tolist()
    assert aggregate_1 == aggregate_2
