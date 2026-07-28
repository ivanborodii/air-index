from iaq_hfis.evaluation.continuity import (
    ContinuityBoundary,
    GridPoint,
    enumerate_boundaries,
    summarize_boundary,
)


def _points(boundary: ContinuityBoundary, method: str, values: list[float | None], classes: list[str | None]) -> list[GridPoint]:
    return [
        GridPoint(
            boundary_id=boundary.boundary_id, channel=boundary.channel, boundary_value=boundary.boundary_value,
            grid_index=i, input_value=float(v) if v is not None else float(i), method=method, index_value=v, index_class=c,
        )
        for i, (v, c) in enumerate(zip(values, classes))
    ]


def _by_method(summary_rows) -> dict:
    return {r.method: r for r in summary_rows}


def test_summarize_boundary_detects_a_planted_hard_discontinuity():
    """Mandatory regression test: the continuity metrics themselves (not
    the real engine, which may legitimately show similar smoothness for
    HFIS and CRISP-MAX) must correctly detect a known, deliberately
    planted discontinuity in a synthetic crisp test function."""
    boundary = ContinuityBoundary(boundary_id="test_boundary", channel="pm2_5", boundary_value=15.0)

    # SMOOTH (PROPOSED-HFIS role): a gentle ramp, no jump larger than 1.0.
    smooth_values = [10.0 + i * 1.0 for i in range(21)]
    smooth_classes = ["Favorable"] * 10 + ["Acceptable"] * 11
    smooth_points = _points(boundary, "PROPOSED-HFIS", smooth_values, smooth_classes)

    # HARD (CRISP-MAX role): identical except for one deliberately planted 40-point jump at the midpoint.
    hard_values = list(smooth_values)
    hard_values[10] = hard_values[9] + 40.0
    for i in range(11, len(hard_values)):
        hard_values[i] += 40.0
    hard_classes = smooth_classes
    hard_points = _points(boundary, "CRISP-MAX", hard_values, hard_classes)

    smooth_summary = _by_method(summarize_boundary(boundary, smooth_points))["PROPOSED-HFIS"]
    hard_summary = _by_method(summarize_boundary(boundary, hard_points))["CRISP-MAX"]

    assert hard_summary.max_adjacent_jump == 40.0
    assert smooth_summary.max_adjacent_jump == 1.0
    assert hard_summary.max_adjacent_jump > smooth_summary.max_adjacent_jump
    assert hard_summary.total_variation > smooth_summary.total_variation


def test_summarize_boundary_detects_monotonicity_violation_for_pollutant_channel():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    # A decrease as PM2.5 increases is a monotonicity violation for a pollutant channel.
    values = [10.0, 11.0, 12.0, 9.0, 13.0, 14.0]
    classes = ["Favorable"] * 6
    points = _points(boundary, "PROPOSED-HFIS", values, classes)
    summary = _by_method(summarize_boundary(boundary, points))["PROPOSED-HFIS"]
    assert summary.monotonicity_violations == 1


def test_summarize_boundary_no_violation_for_strictly_increasing_pollutant():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    values = [10.0, 11.0, 12.0, 13.0, 14.0]
    classes = ["Favorable"] * 5
    points = _points(boundary, "PROPOSED-HFIS", values, classes)
    summary = _by_method(summarize_boundary(boundary, points))["PROPOSED-HFIS"]
    assert summary.monotonicity_violations == 0


def test_summarize_boundary_counts_class_transitions_and_positions():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    values = [10.0, 12.0, 14.0, 16.0, 18.0]
    classes = ["Favorable", "Favorable", "Favorable", "Acceptable", "Acceptable"]
    points = _points(boundary, "PROPOSED-HFIS", values, classes)
    summary = _by_method(summarize_boundary(boundary, points))["PROPOSED-HFIS"]
    assert summary.n_class_transitions == 1
    assert summary.class_transition_positions == [16.0]


def test_summarize_boundary_undefined_when_fewer_than_two_defined_values():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    points = _points(boundary, "PROPOSED-HFIS", [None], [None])
    summary = _by_method(summarize_boundary(boundary, points))["PROPOSED-HFIS"]
    assert summary.max_adjacent_jump is None
    assert summary.total_variation is None


def test_enumerate_boundaries_covers_all_required_channels(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    boundaries = enumerate_boundaries(base_settings.control_regions, profile)
    channels = {b.channel for b in boundaries}
    assert channels == {"pm2_5", "pm10", "co2", "humidity", "temperature"}
    # 3 breakpoints each for the 3 monotonic pollutant channels
    assert sum(1 for b in boundaries if b.channel == "pm2_5") == 3
    assert sum(1 for b in boundaries if b.channel == "pm10") == 3
    assert sum(1 for b in boundaries if b.channel == "co2") == 3
    # 6 edges each for the 2 two-sided channels
    assert sum(1 for b in boundaries if b.channel == "humidity") == 6
    assert sum(1 for b in boundaries if b.channel == "temperature") == 6
