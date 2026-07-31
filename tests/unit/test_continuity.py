from iaq_hfis.evaluation.continuity import (
    ContinuityBoundary,
    GridPoint,
    enumerate_boundaries,
    summarize_boundary,
    summarize_continuity_smoothness,
)


def _points(boundary: ContinuityBoundary, method: str, values: list[float | None], classes: list[str | None], context: str = "favorable") -> list[GridPoint]:
    return [
        GridPoint(
            boundary_id=boundary.boundary_id, channel=boundary.channel, context=context, boundary_value=boundary.boundary_value,
            grid_index=i, input_value=float(v) if v is not None else float(i), method=method, index_value=v, index_class=c,
        )
        for i, (v, c) in enumerate(zip(values, classes))
    ]


def _by_method(summary_rows) -> dict:
    return {r.method: r for r in summary_rows}


def test_summarize_boundary_detects_a_planted_hard_discontinuity():
    """Mandatory regression test: the continuity metrics themselves (not
    the real engine, which may legitimately show similar smoothness for
    HFIS and FUZZY_COMPONENT_MAX) must correctly detect a known, deliberately
    planted discontinuity in a synthetic crisp test function."""
    boundary = ContinuityBoundary(boundary_id="test_boundary", channel="pm2_5", boundary_value=15.0)

    # SMOOTH (PROPOSED_HFIS role): a gentle ramp, no jump larger than 1.0.
    smooth_values = [10.0 + i * 1.0 for i in range(21)]
    smooth_classes = ["Favorable"] * 10 + ["Acceptable"] * 11
    smooth_points = _points(boundary, "PROPOSED_HFIS", smooth_values, smooth_classes)

    # HARD (FUZZY_COMPONENT_MAX role): identical except for one deliberately planted 40-point jump at the midpoint.
    hard_values = list(smooth_values)
    hard_values[10] = hard_values[9] + 40.0
    for i in range(11, len(hard_values)):
        hard_values[i] += 40.0
    hard_classes = smooth_classes
    hard_points = _points(boundary, "FUZZY_COMPONENT_MAX", hard_values, hard_classes)

    smooth_summary = _by_method(summarize_boundary(boundary, "favorable", smooth_points))["PROPOSED_HFIS"]
    hard_summary = _by_method(summarize_boundary(boundary, "favorable", hard_points))["FUZZY_COMPONENT_MAX"]

    assert hard_summary.max_adjacent_jump == 40.0
    assert smooth_summary.max_adjacent_jump == 1.0
    assert hard_summary.max_adjacent_jump > smooth_summary.max_adjacent_jump
    assert hard_summary.total_variation > smooth_summary.total_variation


def test_summarize_boundary_detects_monotonicity_violation_for_pollutant_channel():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    # A decrease as PM2.5 increases is a monotonicity violation for a pollutant channel.
    values = [10.0, 11.0, 12.0, 9.0, 13.0, 14.0]
    classes = ["Favorable"] * 6
    points = _points(boundary, "PROPOSED_HFIS", values, classes)
    summary = _by_method(summarize_boundary(boundary, "favorable", points))["PROPOSED_HFIS"]
    assert summary.monotonicity_violations == 1


def test_summarize_boundary_no_violation_for_strictly_increasing_pollutant():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    values = [10.0, 11.0, 12.0, 13.0, 14.0]
    classes = ["Favorable"] * 5
    points = _points(boundary, "PROPOSED_HFIS", values, classes)
    summary = _by_method(summarize_boundary(boundary, "favorable", points))["PROPOSED_HFIS"]
    assert summary.monotonicity_violations == 0


def test_summarize_boundary_counts_class_transitions_and_positions():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    values = [10.0, 12.0, 14.0, 16.0, 18.0]
    classes = ["Favorable", "Favorable", "Favorable", "Acceptable", "Acceptable"]
    points = _points(boundary, "PROPOSED_HFIS", values, classes)
    summary = _by_method(summarize_boundary(boundary, "favorable", points))["PROPOSED_HFIS"]
    assert summary.n_class_transitions == 1
    assert summary.class_transition_positions == [16.0]


def test_summarize_boundary_undefined_when_fewer_than_two_defined_values():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    points = _points(boundary, "PROPOSED_HFIS", [None], [None])
    summary = _by_method(summarize_boundary(boundary, "favorable", points))["PROPOSED_HFIS"]
    assert summary.max_adjacent_jump is None
    assert summary.total_variation is None


def test_enumerate_boundaries_covers_all_required_channels(base_settings, room_profiles):
    boundaries = enumerate_boundaries(base_settings.control_regions, room_profiles)
    channels = {b.channel for b in boundaries}
    assert channels == {"pm2_5", "pm10", "co2", "humidity", "temperature"}
    # 3 breakpoints each for the 3 monotonic pollutant channels
    assert sum(1 for b in boundaries if b.channel == "pm2_5") == 3
    assert sum(1 for b in boundaries if b.channel == "pm10") == 3
    assert sum(1 for b in boundaries if b.channel == "co2") == 3
    # 6 edges for the humidity channel (not room/season dependent)
    assert sum(1 for b in boundaries if b.channel == "humidity") == 6
    # 6 edges PER room/season profile for temperature -- "every seasonal
    # temperature boundary", not just one representative profile.
    n_profiles = len(room_profiles.profiles)
    assert n_profiles > 1  # sanity: the real config has more than one profile, so this actually exercises the expansion
    assert sum(1 for b in boundaries if b.channel == "temperature") == 6 * n_profiles


def test_summarize_boundary_computes_local_lipschitz_ratio():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    # input spaced 1.0 apart throughout; index_value jumps by 1,1,1,10 -> max ratio = 10/1 = 10.0
    inputs = [0.0, 1.0, 2.0, 3.0, 4.0]
    values = [10.0, 11.0, 12.0, 13.0, 23.0]
    classes = ["Favorable"] * 5
    points = [
        GridPoint(boundary_id=boundary.boundary_id, channel=boundary.channel, context="favorable", boundary_value=boundary.boundary_value,
                  grid_index=i, input_value=inputs[i], method="PROPOSED_HFIS", index_value=v, index_class=c)
        for i, (v, c) in enumerate(zip(values, classes))
    ]
    summary = _by_method(summarize_boundary(boundary, "favorable", points))["PROPOSED_HFIS"]
    assert summary.local_lipschitz_ratio == 10.0


def test_summarize_boundary_area_between_curves_only_populated_for_hfis():
    boundary = ContinuityBoundary(boundary_id="pm2_5_test", channel="pm2_5", boundary_value=15.0)
    inputs = [10.0, 11.0, 12.0]
    hfis_values = [10.0, 10.0, 10.0]
    crisp_max_values = [12.0, 12.0, 12.0]  # constant offset of 2.0 -> area = 2.0 * (12.0 - 10.0) = 4.0
    classes = ["Favorable"] * 3
    points = (
        _points(boundary, "PROPOSED_HFIS", hfis_values, classes)
        + _points(boundary, "FUZZY_COMPONENT_MAX", crisp_max_values, classes)
        + _points(boundary, "WEIGHTED_MEAN", hfis_values, classes)
    )
    # override input_value to the shared grid (the _points helper defaults input_value to the index)
    points = [GridPoint(p.boundary_id, p.channel, p.context, p.boundary_value, p.grid_index, inputs[p.grid_index], p.method, p.index_value, p.index_class) for p in points]
    by_method = _by_method(summarize_boundary(boundary, "favorable", points))
    assert by_method["PROPOSED_HFIS"].area_between_curves_vs_crisp_max == 4.0
    assert by_method["FUZZY_COMPONENT_MAX"].area_between_curves_vs_crisp_max is None
    assert by_method["WEIGHTED_MEAN"].area_between_curves_vs_crisp_max is None


def _points_with_grid(boundary: ContinuityBoundary, method: str, inputs: list[float], values: list[float], context: str = "favorable") -> list[GridPoint]:
    """Like ``_points`` but with an input grid independent of the index
    values -- needed for Lipschitz-ratio tests, since ``_points`` defaults
    input_value to the index value itself, which would make every ratio 1.0."""
    return [
        GridPoint(boundary_id=boundary.boundary_id, channel=boundary.channel, context=context, boundary_value=boundary.boundary_value,
                  grid_index=i, input_value=x, method=method, index_value=v, index_class="Favorable")
        for i, (x, v) in enumerate(zip(inputs, values))
    ]


def test_summarize_continuity_smoothness_reports_hfis_smoother():
    boundary = ContinuityBoundary(boundary_id="b1", channel="pm2_5", boundary_value=15.0)
    inputs = [0.0, 1.0, 2.0]
    smooth = _by_method(summarize_boundary(boundary, "favorable", _points_with_grid(boundary, "PROPOSED_HFIS", inputs, [10.0, 10.5, 11.0])))["PROPOSED_HFIS"]
    rough = _by_method(summarize_boundary(boundary, "favorable", _points_with_grid(boundary, "FUZZY_COMPONENT_MAX", inputs, [10.0, 20.0, 11.0])))["FUZZY_COMPONENT_MAX"]
    result = summarize_continuity_smoothness([smooth, rough])
    assert result["n_boundary_context_pairs_compared"] == 1
    assert result["hfis_smoother_count"] == 1
    assert result["crisp_max_smoother_count"] == 0
    assert "PROPOSED_HFIS is smoother" in result["conclusion"] or "smoother than FUZZY_COMPONENT_MAX" in result["conclusion"]


def test_summarize_continuity_smoothness_does_not_overclaim_when_crisp_max_is_smoother():
    boundary = ContinuityBoundary(boundary_id="b1", channel="pm2_5", boundary_value=15.0)
    inputs = [0.0, 1.0, 2.0]
    rough = _by_method(summarize_boundary(boundary, "favorable", _points_with_grid(boundary, "PROPOSED_HFIS", inputs, [10.0, 20.0, 11.0])))["PROPOSED_HFIS"]
    smooth = _by_method(summarize_boundary(boundary, "favorable", _points_with_grid(boundary, "FUZZY_COMPONENT_MAX", inputs, [10.0, 10.5, 11.0])))["FUZZY_COMPONENT_MAX"]
    result = summarize_continuity_smoothness([rough, smooth])
    assert result["crisp_max_smoother_count"] == 1
    assert result["hfis_smoother_count"] == 0
    assert "NOT smoother" in result["conclusion"]


def test_summarize_continuity_smoothness_empty_input():
    result = summarize_continuity_smoothness([])
    assert result["n_boundary_context_pairs_compared"] == 0
    assert result["conclusion"]
