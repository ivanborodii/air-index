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


def test_detect_gradual_drift_is_causal_not_retrospective():
    """Mandatory regression test: a real drift run must not retroactively
    flag earlier points once a later point confirms the run reached
    min_consecutive_same_direction -- each flagged point's status must
    depend only on itself and points strictly before it."""
    base = list(range(700, 720))  # 20-point monotonic ramp
    series = pd.Series([float(v) for v in base])
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5, min_magnitude=0.0)
    first_flagged = flagged[flagged].index.min()
    # The run starts at index 0; it cannot reach a 5-step run before index
    # 4 (0->1->2->3->4 is 4 steps from the start, run_length=5 first holds
    # at index 4). The first flag must be AT or AFTER that point, never
    # earlier -- if it were retrospective, index 0/1 would also be flagged.
    assert first_flagged >= 4
    assert not flagged.iloc[0]
    assert not flagged.iloc[1]
    assert not flagged.iloc[2]


def test_detect_gradual_drift_changing_a_later_value_never_changes_an_earlier_flag():
    """Prefix invariance for gradual drift, same principle as the causal
    Hampel filter: mutating everything from some index onward must not
    change any earlier point's flag."""
    base = [700.0 + i for i in range(20)]
    series_a = pd.Series(base)
    series_b = pd.Series(base)
    for i in range(12, 20):
        series_b.iloc[i] = 50.0 - i  # completely different continuation from index 12 onward

    flagged_a = detect_gradual_drift(series_a, min_consecutive_same_direction=5, min_magnitude=0.0)
    flagged_b = detect_gradual_drift(series_b, min_consecutive_same_direction=5, min_magnitude=0.0)
    for i in range(12):
        assert bool(flagged_a.iloc[i]) == bool(flagged_b.iloc[i])


def test_detect_gradual_drift_detection_delay_is_honest_for_a_short_injected_run():
    """An injected drift run exactly min_consecutive_same_direction samples
    long is only flagged from the point the run condition is first met
    onward -- never for its full duration, and the detector must not claim
    otherwise (detection delay = min_consecutive_same_direction - 1 samples,
    not zero)."""
    # Flat baseline, then a monotonic run of exactly 5 steps (6 points incl. the pivot).
    values = [700.0] * 5 + [701.0, 702.0, 703.0, 704.0, 705.0]
    series = pd.Series(values)
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5, min_magnitude=0.0)
    # Run starts at index 4 (the last flat point, value just before the rise).
    # 5-step run_length is first reached at index 9 (4 -> 9 is 5 steps).
    assert not flagged.iloc[:9].any()
    assert bool(flagged.iloc[9]) is True


def test_detect_gradual_drift_still_detects_a_real_persistent_change_event_level():
    """Event-level detection (was the run flagged at all) must survive the
    causal fix even though row-level recall for the run's own first samples
    necessarily does not (see the docstring's tradeoff)."""
    values = [700.0 + i * 2.0 for i in range(15)]  # long, unambiguous drift
    series = pd.Series(values)
    flagged = detect_gradual_drift(series, min_consecutive_same_direction=5, min_magnitude=0.0)
    assert flagged.any()  # the event is still detected somewhere in the run
