from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from iaq_hfis.aggregation import aggregate_channel, compute_coverage, time_weighted_mean

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


def test_24_of_30_usable_gives_coverage_0_80():
    result = compute_coverage(n_expected=30, n_usable=24, min_ratio=0.80)
    assert result.ratio == pytest.approx(0.80)
    assert result.ok is True


def test_23_of_30_usable_fails_0_80_threshold():
    result = compute_coverage(n_expected=30, n_usable=23, min_ratio=0.80)
    assert result.ok is False


def test_zero_expected_is_not_ok():
    result = compute_coverage(n_expected=0, n_usable=0, min_ratio=0.80)
    assert result.ok is False


def test_time_weighted_mean_uniform_cadence_reduces_to_simple_mean():
    start = NOW
    end = NOW + timedelta(seconds=90)
    points = [(NOW, 10.0, True), (NOW + timedelta(seconds=30), 20.0, True), (NOW + timedelta(seconds=60), 30.0, True), (NOW + timedelta(seconds=90), 40.0, True)]
    mean = time_weighted_mean(points, start, end)
    assert mean == pytest.approx(25.0, abs=0.5)


def test_time_weighted_mean_only_over_usable_points():
    start = NOW
    end = NOW + timedelta(seconds=60)
    points = [(NOW, 1000.0, False), (NOW + timedelta(seconds=30), 20.0, True), (NOW + timedelta(seconds=60), 20.0, True)]
    mean = time_weighted_mean(points, start, end)
    assert mean == pytest.approx(20.0)


def test_time_weighted_mean_no_usable_points_is_none():
    points = [(NOW, 10.0, False)]
    assert time_weighted_mean(points, NOW, NOW + timedelta(seconds=30)) is None


def test_time_weighted_mean_single_point():
    points = [(NOW, 42.0, True)]
    assert time_weighted_mean(points, NOW, NOW + timedelta(seconds=30)) == 42.0


def test_aggregate_channel_weighted_mean_none_when_coverage_not_ok():
    slots = [NOW + timedelta(seconds=30 * i) for i in range(30)]
    usable = [i < 20 for i in range(30)]  # 20/30 = 0.667 < 0.80
    df = pd.DataFrame({"ts": slots, "raw_value": [700.0] * 30, "usable": usable})
    result = aggregate_channel(df, "co2", slots[0], slots[-1], min_ratio=0.80)
    assert result.coverage.ok is False
    assert result.weighted_mean is None


def test_aggregate_channel_weighted_mean_present_when_coverage_ok():
    slots = [NOW + timedelta(seconds=30 * i) for i in range(30)]
    df = pd.DataFrame({"ts": slots, "raw_value": [700.0] * 30, "usable": [True] * 30})
    result = aggregate_channel(df, "co2", slots[0], slots[-1], min_ratio=0.80)
    assert result.coverage.ok is True
    assert result.weighted_mean == pytest.approx(700.0)
