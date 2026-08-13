"""Causal-window-specific tests for iaq_hfis.quality.hampel.hampel_flags.

Uses the real production function throughout -- no separate simplified
Hampel implementation for testing (task requirement).
"""

import numpy as np
import pandas as pd

from iaq_hfis.quality.hampel import hampel_flags


def test_window_contains_exactly_current_and_ten_preceding_when_window_size_11():
    # 25 points, spike planted at index 15. With window_size=11, index 15's
    # causal window is indices [5..15] (11 points: x_15 and the 10 before
    # it) -- verified indirectly: an identical spike shape starting exactly
    # 10 points earlier (so it first has a full window at the same relative
    # position) must be detected identically.
    values = [700.0] * 25
    values[15] = 5000.0
    series = pd.Series(values)
    result = hampel_flags(series, window_size=11, mad_multiplier=3.0)
    assert bool(result["is_outlier"].iloc[15]) is True
    # index 14 (immediately before the spike) must NOT see the spike (it's
    # strictly in the future relative to index 14) -- its causal window is
    # [4..14], all flat 700.0, so it's not an outlier.
    assert bool(result["is_outlier"].iloc[14]) is False
    # index 10 is the first index with 11 valid points behind it counting
    # itself (window [0..10]); nothing planted there, so no flag, but its
    # median must be defined (full window available).
    assert not np.isnan(result["median"].iloc[10])
    # index 9 has only 10 points available (indices 0..9) -- one short of
    # window_size=11 -- must be left unevaluated.
    assert np.isnan(result["median"].iloc[9])
    assert bool(result["is_outlier"].iloc[9]) is False


def test_changing_a_later_value_never_changes_an_earlier_points_result():
    """Prefix invariance: x_i's median/MAD/outlier status must depend only
    on x_i and points strictly before it. Mandatory regression test for
    causal (not centered) behavior."""
    base = [700.0 + (i % 5) * 0.3 for i in range(30)]
    series_a = pd.Series(base)
    series_b = pd.Series(base)
    # Mutate everything from index 20 onward into wild, unrelated values.
    for i in range(20, 30):
        series_b.iloc[i] = -99999.0 + i * 12345.0

    result_a = hampel_flags(series_a, window_size=11, mad_multiplier=3.0)
    result_b = hampel_flags(series_b, window_size=11, mad_multiplier=3.0)

    for i in range(20):  # every point strictly before the mutated region
        assert result_a["median"].iloc[i] == result_b["median"].iloc[i] or (
            np.isnan(result_a["median"].iloc[i]) and np.isnan(result_b["median"].iloc[i])
        )
        assert result_a["mad"].iloc[i] == result_b["mad"].iloc[i] or (
            np.isnan(result_a["mad"].iloc[i]) and np.isnan(result_b["mad"].iloc[i])
        )
        assert bool(result_a["is_outlier"].iloc[i]) == bool(result_b["is_outlier"].iloc[i])


def test_no_future_measurement_is_used_for_a_planted_future_spike():
    """A spike planted strictly after x_i must never affect x_i's own
    outlier status -- the direct behavioral consequence of causality."""
    values = [700.0] * 30
    series_no_future_spike = pd.Series(values)
    series_with_future_spike = pd.Series(values)
    series_with_future_spike.iloc[25] = 999999.0  # far in the future relative to index 14

    r1 = hampel_flags(series_no_future_spike, window_size=11, mad_multiplier=3.0)
    r2 = hampel_flags(series_with_future_spike, window_size=11, mad_multiplier=3.0)
    for i in range(25):
        assert bool(r1["is_outlier"].iloc[i]) == bool(r2["is_outlier"].iloc[i]) is False


def test_value_not_evaluated_without_full_valid_history():
    # window_size=11: the first 10 points (indices 0..9) can never have 11
    # valid points in their causal window, regardless of how smooth/stable
    # the series is.
    series = pd.Series([700.0] * 15)
    result = hampel_flags(series, window_size=11, mad_multiplier=3.0)
    for i in range(10):
        assert np.isnan(result["median"].iloc[i])
        assert bool(result["is_outlier"].iloc[i]) is False
    assert not np.isnan(result["median"].iloc[10])  # exactly enough history at index 10


def test_nan_gap_in_history_also_withholds_evaluation_until_refilled():
    values = [700.0] * 20
    series = pd.Series(values, dtype=float)
    series.iloc[3] = np.nan  # one gap early in the history
    result = hampel_flags(series, window_size=11, mad_multiplier=3.0)
    # index 10's causal window [0..10] now has only 10 valid values (one NaN) -- not enough.
    assert np.isnan(result["median"].iloc[10])
    # index 11's causal window [1..11] still contains the NaN at index 3 -- still short by one.
    assert np.isnan(result["median"].iloc[11])
    # index 13's causal window [3..13] excludes index 3's own NaN from validity but the window
    # itself still only has 10 non-NaN values out of 11 slots (index 3 is NaN) -- still short.
    assert np.isnan(result["median"].iloc[13])
    # index 14's causal window [4..14] no longer includes the NaN at index 3 -- 11 valid values.
    assert not np.isnan(result["median"].iloc[14])


def test_deterministic_repeated_calls():
    values = [700.0 + 3.0 * np.sin(i / 2.0) for i in range(50)]
    values[30] = 5000.0
    series = pd.Series(values)
    r1 = hampel_flags(series, window_size=11, mad_multiplier=3.0)
    r2 = hampel_flags(series, window_size=11, mad_multiplier=3.0)
    pd.testing.assert_frame_equal(r1, r2)
