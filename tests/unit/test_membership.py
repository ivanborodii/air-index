import math

import pytest

from iaq_hfis.constants import CLASS_ORDER
from iaq_hfis.membership import build_monotonic_classes, build_two_sided_classes, evaluate_memberships, trapezoid


def test_trapezoid_basic_shape():
    assert trapezoid(0, 0, 10, 20, 30) == 0.0
    assert trapezoid(10, 0, 10, 20, 30) == 1.0
    assert trapezoid(15, 0, 10, 20, 30) == 1.0
    assert trapezoid(25, 0, 10, 20, 30) == 0.5
    assert trapezoid(30, 0, 10, 20, 30) == 0.0
    assert trapezoid(5, 0, 10, 20, 30) == 0.5


def test_trapezoid_shoulder_down_with_infinite_left():
    inf = math.inf
    assert trapezoid(-1000, -inf, -inf, 10, 20) == 1.0
    assert trapezoid(15, -inf, -inf, 10, 20) == 0.5
    assert trapezoid(30, -inf, -inf, 10, 20) == 0.0


def test_trapezoid_shoulder_up_with_infinite_right():
    inf = math.inf
    assert trapezoid(1000, 10, 20, inf, inf) == 1.0
    assert trapezoid(15, 10, 20, inf, inf) == 0.5
    assert trapezoid(5, 10, 20, inf, inf) == 0.0


@pytest.mark.parametrize("x", [-100, 0, 15, 25, 37.5, 50, 60, 1000])
def test_all_monotonic_memberships_in_unit_interval(x):
    shapes = build_monotonic_classes([15, 25, 50], [2.0, 2.0, 2.0])
    degrees = evaluate_memberships(x, shapes)
    for cls in CLASS_ORDER:
        assert 0.0 <= degrees[cls] <= 1.0


def test_adjacent_monotonic_classes_cross_at_boundary():
    shapes = build_monotonic_classes([15, 25, 50], [2.0, 2.0, 2.0])
    degrees = evaluate_memberships(15.0, shapes)
    assert degrees["Favourable"] == pytest.approx(0.5)
    assert degrees["Acceptable"] == pytest.approx(0.5)


def test_monotonic_channel_is_right_shoulder_only():
    shapes = build_monotonic_classes([15, 25, 50], [2.0, 2.0, 2.0])
    # increasing x never increases Favourable's degree, never decreases Critical's
    xs = [0, 5, 14, 15, 16, 30, 60, 100]
    favourable = [evaluate_memberships(x, shapes)["Favourable"] for x in xs]
    critical = [evaluate_memberships(x, shapes)["Critical"] for x in xs]
    assert all(a >= b for a, b in zip(favourable, favourable[1:]))
    assert all(a <= b for a, b in zip(critical, critical[1:]))


def test_two_sided_penalizes_both_low_and_high(room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    shapes = build_two_sided_classes(profile.ranges, profile.ranges.transition_width)
    favorable_mid = evaluate_memberships(19.5, shapes)["Favourable"]
    too_cold = evaluate_memberships(10.0, shapes)["Favourable"]
    too_hot = evaluate_memberships(30.0, shapes)["Favourable"]
    assert favorable_mid == 1.0
    assert too_cold == 0.0
    assert too_hot == 0.0
    assert evaluate_memberships(10.0, shapes)["Critical"] == 1.0
    assert evaluate_memberships(30.0, shapes)["Critical"] == 1.0


@pytest.mark.parametrize("x", [-50, 0, 15.5, 18, 19.5, 21, 23.5, 100])
def test_all_two_sided_memberships_in_unit_interval(x, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    shapes = build_two_sided_classes(profile.ranges, profile.ranges.transition_width)
    degrees = evaluate_memberships(x, shapes)
    for cls in CLASS_ORDER:
        assert 0.0 <= degrees[cls] <= 1.0


def test_two_sided_adjacent_classes_cross_at_shared_boundary(room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    shapes = build_two_sided_classes(profile.ranges, profile.ranges.transition_width)
    boundary = profile.ranges.favourable[0]  # 18.0, shared edge between Acceptable-low and Favourable
    degrees = evaluate_memberships(boundary, shapes)
    assert degrees["Favourable"] == pytest.approx(0.5)
    assert degrees["Acceptable"] == pytest.approx(0.5)
