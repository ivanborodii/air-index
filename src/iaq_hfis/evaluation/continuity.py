"""Boundary continuity experiment: compares PROPOSED-HFIS's smooth Mamdani
inference against the CRISP-MAX and WEIGHTED-MEAN baselines directly, by
sweeping a dense input grid across each control-region boundary while
holding every other channel at a deeply-favorable baseline (so the swept
channel's own class dominates the worst-of aggregation, exactly like
:mod:`iaq_hfis.evaluation.reference_cases`'s single-channel-perturbed
construction).

For each boundary and method, reports the largest and mean adjacent-point
index jump, total variation, class-transition count/positions, index
range, monotonicity violations (for monotonic pollutant channels, a
decrease as the input worsens), and whether a favorable component masked
the adverse channel's own severity in the aggregated result.

This is a deterministic numerical experiment, not a statistical one: same
grid every time, no randomness, so results are exactly reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from iaq_hfis.baselines import crisp_max, weighted_mean
from iaq_hfis.fuzzy_engine import classify_output
from iaq_hfis.pipeline import RuntimeContext, infer_from_values
from iaq_hfis.schema import channel_uncertainty

#: Deeply-favorable baseline values for channels NOT under test.
_FAVORABLE_BASELINE = {"pm2_5": 5.0, "pm10": 10.0, "co2": 600.0}

METHODS = ["PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"]
MONOTONIC_CHANNELS = {"pm2_5", "pm10", "co2"}


@dataclass(frozen=True)
class ContinuityBoundary:
    boundary_id: str
    channel: str
    boundary_value: float


@dataclass(frozen=True)
class GridPoint:
    boundary_id: str
    channel: str
    boundary_value: float
    grid_index: int
    input_value: float
    method: str
    index_value: float | None
    index_class: str | None


@dataclass(frozen=True)
class ContinuitySummaryRow:
    boundary_id: str
    channel: str
    method: str
    max_adjacent_jump: float | None
    mean_adjacent_jump: float | None
    total_variation: float | None
    n_class_transitions: int
    class_transition_positions: list[float]
    index_range: float | None
    monotonicity_violations: int
    masked_by_favorable: bool


def _baseline_values(control_regions, room_profile) -> dict[str, float]:
    values = dict(_FAVORABLE_BASELINE)
    values["temperature"] = sum(room_profile.ranges.favorable) / 2
    values["humidity"] = sum(control_regions.relative_humidity.favorable) / 2
    return values


def _monotonic_boundaries(control_regions) -> list[ContinuityBoundary]:
    boundaries = []
    for channel, region in (("pm2_5", control_regions.pm2_5), ("pm10", control_regions.pm10), ("co2", control_regions.co2)):
        for i, bp in enumerate(region.breakpoints):
            boundaries.append(ContinuityBoundary(boundary_id=f"{channel}_breakpoint{i}", channel=channel, boundary_value=bp))
    return boundaries


def _two_sided_boundaries(channel: str, ranges, season_label: str) -> list[ContinuityBoundary]:
    edges = {
        "critical_low": ranges.critical_low_max,
        "acceptable_low_edge": ranges.acceptable_low[1],
        "favorable_low_edge": ranges.favorable[0],
        "favorable_high_edge": ranges.favorable[1],
        "acceptable_high_edge": ranges.acceptable_high[0],
        "critical_high": ranges.critical_high_min,
    }
    return [ContinuityBoundary(boundary_id=f"{channel}_{name}_{season_label}", channel=channel, boundary_value=value) for name, value in edges.items()]


def enumerate_boundaries(control_regions, room_profile) -> list[ContinuityBoundary]:
    boundaries = list(_monotonic_boundaries(control_regions))
    boundaries += _two_sided_boundaries("humidity", control_regions.relative_humidity, room_profile.season)
    boundaries += _two_sided_boundaries("temperature", room_profile.ranges, room_profile.season)
    return boundaries


def _grid_values(boundary_value: float, uncertainty: float, n_points: int) -> np.ndarray:
    half_span = max(uncertainty, 1e-9)
    return np.linspace(boundary_value - half_span, boundary_value + half_span, n_points)


def sweep_boundary(
    ctx: RuntimeContext,
    control_regions,
    room_profile,
    boundary: ContinuityBoundary,
    n_points: int,
) -> list[GridPoint]:
    uncertainty = channel_uncertainty(boundary.channel, ctx.settings.schema_mapping, ctx.sensor_specs)
    grid = _grid_values(boundary.boundary_value, uncertainty, n_points)

    points: list[GridPoint] = []
    for i, x in enumerate(grid):
        values = _baseline_values(control_regions, room_profile)
        values[boundary.channel] = float(x)
        component_results, index_result = infer_from_values(ctx, values, {"A", "V", "M"}, room_profile)
        scores = {c: r.crisp_score for c, r in component_results.items()}

        hfis_value = index_result.index_value if index_result else None
        hfis_class = index_result.index_class if index_result else None
        cm = crisp_max(scores)
        wm = weighted_mean(scores)

        for method, value, cls in (
            ("PROPOSED-HFIS", hfis_value, hfis_class),
            ("CRISP-MAX", cm.index_value, cm.index_class),
            ("WEIGHTED-MEAN", wm.index_value, wm.index_class),
        ):
            points.append(
                GridPoint(
                    boundary_id=boundary.boundary_id, channel=boundary.channel, boundary_value=boundary.boundary_value,
                    grid_index=i, input_value=float(x), method=method, index_value=value, index_class=cls,
                )
            )
    return points


def summarize_boundary(boundary: ContinuityBoundary, points: list[GridPoint]) -> list[ContinuitySummaryRow]:
    rows = []
    for method in METHODS:
        method_points = sorted((p for p in points if p.method == method), key=lambda p: p.grid_index)
        values = [p.index_value for p in method_points]
        classes = [p.index_class for p in method_points]
        inputs = [p.input_value for p in method_points]

        defined = [v for v in values if v is not None]
        if len(defined) < 2:
            rows.append(
                ContinuitySummaryRow(
                    boundary_id=boundary.boundary_id, channel=boundary.channel, method=method,
                    max_adjacent_jump=None, mean_adjacent_jump=None, total_variation=None,
                    n_class_transitions=0, class_transition_positions=[], index_range=None,
                    monotonicity_violations=0, masked_by_favorable=False,
                )
            )
            continue

        jumps = [abs(b - a) for a, b in zip(values, values[1:]) if a is not None and b is not None]
        transitions = [(inputs[i + 1]) for i in range(len(classes) - 1) if classes[i] is not None and classes[i + 1] is not None and classes[i] != classes[i + 1]]
        monotonicity_violations = 0
        if boundary.channel in MONOTONIC_CHANNELS:
            monotonicity_violations = sum(1 for a, b in zip(values, values[1:]) if a is not None and b is not None and b < a - 1e-9)

        # "masked by favorable": at the boundary's own crossing point, the adverse channel is
        # the only non-favorable input by construction, so masking would show as the aggregated
        # class staying more favorable than the swept channel's own crisp classification would be.
        crossing_idx = min(range(len(inputs)), key=lambda i: abs(inputs[i] - boundary.boundary_value))
        masked = classes[crossing_idx] is not None and classes[crossing_idx] == "Favorable" and boundary.boundary_value > 0

        rows.append(
            ContinuitySummaryRow(
                boundary_id=boundary.boundary_id, channel=boundary.channel, method=method,
                max_adjacent_jump=max(jumps) if jumps else None,
                mean_adjacent_jump=(sum(jumps) / len(jumps)) if jumps else None,
                total_variation=sum(jumps) if jumps else None,
                n_class_transitions=len(transitions),
                class_transition_positions=transitions,
                index_range=(max(defined) - min(defined)) if defined else None,
                monotonicity_violations=monotonicity_violations,
                masked_by_favorable=masked,
            )
        )
    return rows


def run_continuity_experiment(ctx: RuntimeContext, control_regions, room_profile, n_points: int) -> tuple[list[GridPoint], list[ContinuitySummaryRow]]:
    all_points: list[GridPoint] = []
    all_summaries: list[ContinuitySummaryRow] = []
    for boundary in enumerate_boundaries(control_regions, room_profile):
        points = sweep_boundary(ctx, control_regions, room_profile, boundary, n_points)
        all_points.extend(points)
        all_summaries.extend(summarize_boundary(boundary, points))
    return all_points, all_summaries
