from datetime import datetime, timedelta, timezone

import pandas as pd

from iaq_hfis.timegrid import align_columns_to_slots, align_computed_timestamps, expected_slots, match_actual_to_slots

NOW = datetime(2026, 7, 23, 15, 37, 12, 345678, tzinfo=timezone.utc)


def test_15min_30s_window_has_30_expected_slots():
    slots = expected_slots(NOW, window_minutes=15, cadence_seconds=30)
    assert len(slots) == 30
    assert slots[-1] == NOW
    assert slots[0] == NOW - timedelta(seconds=29 * 30)


def test_5min_window_has_10_slots():
    assert len(expected_slots(NOW, window_minutes=5, cadence_seconds=30)) == 10


def test_5min_alignment_is_deterministic():
    start = datetime(2026, 7, 23, 15, 3, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 23, 15, 20, 0, tzinfo=timezone.utc)
    a = align_computed_timestamps(start, end, 5)
    b = align_computed_timestamps(start, end, 5)
    assert a == b
    assert a == [
        datetime(2026, 7, 23, 15, 5, tzinfo=timezone.utc),
        datetime(2026, 7, 23, 15, 10, tzinfo=timezone.utc),
        datetime(2026, 7, 23, 15, 15, tzinfo=timezone.utc),
        datetime(2026, 7, 23, 15, 20, tzinfo=timezone.utc),
    ]


def test_duplicate_expected_slots_not_double_counted():
    expected = [NOW - timedelta(seconds=30), NOW]
    # a single actual timestamp close to both slots (30s apart, slot spacing 30s):
    actual = pd.Series([NOW - timedelta(seconds=15)])
    matched = match_actual_to_slots(expected, actual, tolerance_seconds=20)
    matched_count = sum(1 for v in matched.values() if v is not None)
    assert matched_count == 1  # never claimed by both slots


def test_match_actual_to_slots_nearest_wins():
    expected = [NOW - timedelta(seconds=30), NOW]
    actual = pd.Series([NOW - timedelta(seconds=29), NOW - timedelta(seconds=1)])
    matched = match_actual_to_slots(expected, actual, tolerance_seconds=5)
    assert matched[expected[0]] == NOW - timedelta(seconds=29)
    assert matched[expected[1]] == NOW - timedelta(seconds=1)


def test_no_match_when_outside_tolerance():
    expected = [NOW]
    actual = pd.Series([NOW - timedelta(seconds=100)])
    matched = match_actual_to_slots(expected, actual, tolerance_seconds=5)
    assert matched[NOW] is None


def test_align_columns_to_slots_unmatched_slot_is_nan():
    raw_df = pd.DataFrame({"ts": [NOW], "mass_pm2_5": [4.2]})
    matched = {NOW - timedelta(seconds=30): None, NOW: NOW}
    aligned = align_columns_to_slots(raw_df, matched, ["mass_pm2_5"])
    assert pd.isna(aligned.loc[NOW - timedelta(seconds=30), "mass_pm2_5"])
    assert aligned.loc[NOW, "mass_pm2_5"] == 4.2
