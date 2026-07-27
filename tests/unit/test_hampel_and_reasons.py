import pandas as pd

from iaq_hfis.quality.hampel import hampel_flags
from iaq_hfis.quality.reasons import detect_gradual_drift, detect_stuck_value


def test_hampel_flags_a_single_spike_as_outlier_candidate():
    values = [700.0] * 10 + [2000.0] + [700.0] * 9  # one sharp spike in a flat series
    series = pd.Series(values)
    result = hampel_flags(series, window_size=5, mad_multiplier=3.0)
    assert bool(result["is_outlier"].iloc[10]) is True
    assert bool(result["is_outlier"].iloc[0]) is False


def test_hampel_no_flags_on_smooth_series():
    values = [700.0 + 0.1 * i for i in range(20)]
    series = pd.Series(values)
    result = hampel_flags(series, window_size=5, mad_multiplier=3.0)
    assert not result["is_outlier"].any()


def test_hampel_insufficient_window_not_flagged():
    series = pd.Series([1.0, 2.0])  # shorter than window_size
    result = hampel_flags(series, window_size=5, mad_multiplier=3.0)
    assert not result["is_outlier"].any()
    assert result["median"].isna().all()


def test_detect_stuck_value():
    series = pd.Series([1.0, 2.0, 5.0, 5.0, 5.0, 5.0, 6.0])
    flagged = detect_stuck_value(series, min_repeats=4)
    assert list(flagged) == [False, False, True, True, True, True, False]


def test_detect_stuck_value_ignores_nan_gaps():
    series = pd.Series([5.0, None, 5.0, 5.0])
    flagged = detect_stuck_value(series, min_repeats=3)
    assert not flagged.iloc[0]
    assert not flagged.iloc[2] and not flagged.iloc[3]  # run broken by the NaN, only length 2


def test_detect_gradual_drift_flags_monotonic_run():
    series = pd.Series([700.0, 701.0, 702.0, 703.0, 704.0, 705.0, 690.0])
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5)
    assert flagged.iloc[4] or flagged.iloc[5]
    assert not flagged.iloc[0]


def test_detect_gradual_drift_magnitude_gate_suppresses_ordinary_small_trend():
    # Real, physically ordinary CO2 dynamics (e.g. a room de-gassing after
    # ventilation): 6 consecutive same-direction 30s steps, but the total
    # change (~15 ppm) is small relative to CO2's declared uncertainty
    # (50 ppm) -- must NOT be flagged once magnitude-gated. This is a
    # regression test for a real false-positive found against live data.
    series = pd.Series([698.0, 695.0, 692.0, 689.0, 686.0, 683.0])
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5, min_magnitude=150.0)
    assert not flagged.any()


def test_detect_gradual_drift_magnitude_gate_still_catches_large_drift():
    # Same run shape, but a cumulative change well beyond the magnitude
    # threshold -- a genuine sustained shift must still be flagged.
    series = pd.Series([700.0, 650.0, 600.0, 550.0, 500.0, 450.0])
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5, min_magnitude=150.0)
    assert flagged.any()


def test_detect_gradual_drift_default_magnitude_zero_matches_prior_behavior():
    series = pd.Series([700.0, 701.0, 702.0, 703.0, 704.0, 705.0])
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5)
    assert flagged.any()


def test_detect_gradual_drift_not_flagged_on_flat_series():
    series = pd.Series([700.0] * 10)
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5)
    assert not flagged.any()
