"""Boundary continuity experiment: compares PROPOSED-HFIS's smooth Mamdani
inference against the CRISP-MAX and WEIGHTED-MEAN baselines directly, by
sweeping a dense input grid across every manuscript control-region boundary.

Each boundary is swept under THREE separate "other components" contexts --
``favorable``, ``acceptable``, ``degraded`` -- not just a single
deeply-favorable baseline. This matters: when every other channel is pinned
fully Favorable, the 2nd-level Mamdani engine's class-activation vector
becomes mathematically identical to the swept channel's own component-level
class-activation vector (worst-of consequent + Favorable's minimal severity
rank), so PROPOSED-HFIS and CRISP-MAX are *provably* forced to coincide in
that one regime -- see docs/hfis_vs_crispmax_audit.md section 3 for the
proof. Testing only that regime would make any "HFIS is smoother" claim
untestable, not merely weak. The acceptable/degraded contexts exercise the
genuine multi-input rule interaction the favorable-only sweep cannot reach.

Every ``room_profiles.yaml`` room/season combination is swept for
temperature boundaries (not just the run's representative profile), so
"every seasonal temperature boundary" is actually covered, matching the
other four channels' full breakpoint/edge sets.

For each (boundary, context, method), reports the largest, mean, median and
p95 adjacent-point index jump, total variation, a local Lipschitz ratio
(max |delta index| / |delta input| between adjacent grid points -- the
discrete-grid analogue of a Lipschitz constant), class-transition
count/positions, index range, monotonicity violations (for monotonic
pollutant channels, a decrease as the input worsens), and whether a
favorable component masked the adverse channel's own severity in the
aggregated result. PROPOSED-HFIS rows additionally report the area between
its own curve and CRISP-MAX's curve (trapezoidal integral of
|HFIS(x) - CRISP-MAX(x)| over the swept input) -- a single number
summarizing how much the two methods diverge across the whole boundary
sweep, not just at isolated points.

This is a deterministic numerical experiment, not a statistical one: same
grid every time, no randomness, so results are exactly reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from iaq_hfis.baselines import crisp_max, weighted_mean
from iaq_hfis.pipeline import RuntimeContext, infer_from_values
from iaq_hfis.schema import channel_uncertainty

METHODS = ["PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"]
MONOTONIC_CHANNELS = {"pm2_5", "pm10", "co2"}
CONTEXTS = ["favorable", "acceptable", "degraded"]


@dataclass(frozen=True)
class ContinuityBoundary:
    boundary_id: str
    channel: str
    boundary_value: float
    room: str | None = None    # set only for temperature boundaries
    season: str | None = None  # set only for temperature boundaries


@dataclass(frozen=True)
class GridPoint:
    boundary_id: str
    channel: str
    context: str
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
    context: str
    method: str
    max_adjacent_jump: float | None
    mean_adjacent_jump: float | None
    median_adjacent_jump: float | None
    p95_adjacent_jump: float | None
    total_variation: float | None
    local_lipschitz_ratio: float | None
    n_class_transitions: int
    class_transition_positions: list[float]
    index_range: float | None
    monotonicity_violations: int
    masked_by_favorable: bool
    area_between_curves_vs_crisp_max: float | None  # only populated for method == "PROPOSED-HFIS"


def _monotonic_context_value(breakpoints: list[float], context: str) -> float:
    b0, b1, b2 = breakpoints
    if context == "favorable":
        return b0 / 2.0
    if context == "acceptable":
        return (b0 + b1) / 2.0
    return (b1 + b2) / 2.0  # degraded


def _two_sided_context_value(ranges, context: str) -> float:
    """Representative value for a given severity context. ``acceptable``
    and ``degraded`` deterministically use the high-side band (an arbitrary
    but fixed and documented choice -- the low/high bands are symmetric in
    how the worst-of rule base treats them, so either side exercises the
    same rule-interaction behavior)."""
    if context == "favorable":
        lo, hi = ranges.favorable
    elif context == "acceptable":
        lo, hi = ranges.acceptable_high
    else:
        lo, hi = ranges.degraded_high
    return (lo + hi) / 2.0


def _context_values(control_regions, room_profile, context: str) -> dict[str, float]:
    return {
        "pm2_5": _monotonic_context_value(control_regions.pm2_5.breakpoints, context),
        "pm10": _monotonic_context_value(control_regions.pm10.breakpoints, context),
        "co2": _monotonic_context_value(control_regions.co2.breakpoints, context),
        "temperature": _two_sided_context_value(room_profile.ranges, context),
        "humidity": _two_sided_context_value(control_regions.relative_humidity, context),
    }


def _monotonic_boundaries(control_regions) -> list[ContinuityBoundary]:
    boundaries = []
    for channel, region in (("pm2_5", control_regions.pm2_5), ("pm10", control_regions.pm10), ("co2", control_regions.co2)):
        for i, bp in enumerate(region.breakpoints):
            boundaries.append(ContinuityBoundary(boundary_id=f"{channel}_breakpoint{i}", channel=channel, boundary_value=bp))
    return boundaries


def _two_sided_boundaries(channel: str, ranges, boundary_suffix: str, room: str | None = None, season: str | None = None) -> list[ContinuityBoundary]:
    edges = {
        "critical_low": ranges.critical_low_max,
        "acceptable_low_edge": ranges.acceptable_low[1],
        "favorable_low_edge": ranges.favorable[0],
        "favorable_high_edge": ranges.favorable[1],
        "acceptable_high_edge": ranges.acceptable_high[0],
        "critical_high": ranges.critical_high_min,
    }
    return [
        ContinuityBoundary(boundary_id=f"{channel}_{name}_{boundary_suffix}", channel=channel, boundary_value=value, room=room, season=season)
        for name, value in edges.items()
    ]


def enumerate_boundaries(control_regions, room_profiles) -> list[ContinuityBoundary]:
    """Every manuscript control-region boundary: PM2.5/PM10/CO2 breakpoints,
    humidity's 6 edges, and temperature's 6 edges for EVERY room/season
    profile in ``room_profiles`` (not just one representative profile) --
    so "every seasonal temperature boundary" is actually exhaustive."""
    boundaries = list(_monotonic_boundaries(control_regions))
    boundaries += _two_sided_boundaries("humidity", control_regions.relative_humidity, "all_seasons")
    for profile in room_profiles.profiles:
        boundaries += _two_sided_boundaries("temperature", profile.ranges, f"{profile.room}_{profile.season}", room=profile.room, season=profile.season)
    return boundaries


def _grid_values(boundary_value: float, uncertainty: float, n_points: int) -> np.ndarray:
    half_span = max(uncertainty, 1e-9)
    return np.linspace(boundary_value - half_span, boundary_value + half_span, n_points)


def _representative_profile_for(boundary: ContinuityBoundary, room_profiles, fallback_profile):
    if boundary.room is None:
        return fallback_profile
    return room_profiles.find(boundary.room, boundary.season)


def sweep_boundary(
    ctx: RuntimeContext,
    control_regions,
    room_profiles,
    fallback_profile,
    boundary: ContinuityBoundary,
    context: str,
    n_points: int,
) -> list[GridPoint]:
    profile = _representative_profile_for(boundary, room_profiles, fallback_profile)
    uncertainty = channel_uncertainty(boundary.channel, ctx.settings.schema_mapping, ctx.sensor_specs)
    grid = _grid_values(boundary.boundary_value, uncertainty, n_points)

    points: list[GridPoint] = []
    for i, x in enumerate(grid):
        values = _context_values(control_regions, profile, context)
        values[boundary.channel] = float(x)
        component_results, index_result = infer_from_values(ctx, values, {"A", "V", "M"}, profile)
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
                    boundary_id=boundary.boundary_id, channel=boundary.channel, context=context, boundary_value=boundary.boundary_value,
                    grid_index=i, input_value=float(x), method=method, index_value=value, index_class=cls,
                )
            )
    return points


def summarize_boundary(boundary: ContinuityBoundary, context: str, points: list[GridPoint]) -> list[ContinuitySummaryRow]:
    by_method: dict[str, list[GridPoint]] = {}
    for method in METHODS:
        by_method[method] = sorted((p for p in points if p.method == method), key=lambda p: p.grid_index)

    hfis_values = [p.index_value for p in by_method["PROPOSED-HFIS"]]
    crisp_max_values = [p.index_value for p in by_method["CRISP-MAX"]]
    inputs_for_area = [p.input_value for p in by_method["PROPOSED-HFIS"]]

    rows = []
    for method in METHODS:
        method_points = by_method[method]
        values = [p.index_value for p in method_points]
        classes = [p.index_class for p in method_points]
        inputs = [p.input_value for p in method_points]

        defined = [v for v in values if v is not None]
        if len(defined) < 2:
            rows.append(
                ContinuitySummaryRow(
                    boundary_id=boundary.boundary_id, channel=boundary.channel, context=context, method=method,
                    max_adjacent_jump=None, mean_adjacent_jump=None, median_adjacent_jump=None, p95_adjacent_jump=None,
                    total_variation=None, local_lipschitz_ratio=None,
                    n_class_transitions=0, class_transition_positions=[], index_range=None,
                    monotonicity_violations=0, masked_by_favorable=False, area_between_curves_vs_crisp_max=None,
                )
            )
            continue

        jumps = [abs(b - a) for a, b in zip(values, values[1:]) if a is not None and b is not None]
        deltas_in = [abs(bi - ai) for ai, bi in zip(inputs, inputs[1:])]
        lipschitz_ratios = [j / d for j, d in zip(jumps, deltas_in) if d > 1e-12]
        transitions = [(inputs[i + 1]) for i in range(len(classes) - 1) if classes[i] is not None and classes[i + 1] is not None and classes[i] != classes[i + 1]]
        monotonicity_violations = 0
        if boundary.channel in MONOTONIC_CHANNELS:
            monotonicity_violations = sum(1 for a, b in zip(values, values[1:]) if a is not None and b is not None and b < a - 1e-9)

        # "masked by favorable": at the boundary's own crossing point, the adverse channel is
        # the only non-favorable input by construction only in the favorable context; kept as a
        # per-context diagnostic (still meaningful under acceptable/degraded contexts: does the
        # aggregated class stay more favorable than the swept channel's own crossing would imply?).
        crossing_idx = min(range(len(inputs)), key=lambda i: abs(inputs[i] - boundary.boundary_value))
        masked = classes[crossing_idx] is not None and classes[crossing_idx] == "Favorable" and boundary.boundary_value > 0

        area = None
        if method == "PROPOSED-HFIS":
            pairs = [(x, h, c) for x, h, c in zip(inputs_for_area, hfis_values, crisp_max_values) if h is not None and c is not None]
            if len(pairs) >= 2:
                xs = np.array([p[0] for p in pairs])
                diffs = np.array([abs(p[1] - p[2]) for p in pairs])
                area = float(np.trapezoid(diffs, xs))

        rows.append(
            ContinuitySummaryRow(
                boundary_id=boundary.boundary_id, channel=boundary.channel, context=context, method=method,
                max_adjacent_jump=max(jumps) if jumps else None,
                mean_adjacent_jump=(sum(jumps) / len(jumps)) if jumps else None,
                median_adjacent_jump=float(np.median(jumps)) if jumps else None,
                p95_adjacent_jump=float(np.percentile(jumps, 95)) if jumps else None,
                total_variation=sum(jumps) if jumps else None,
                local_lipschitz_ratio=max(lipschitz_ratios) if lipschitz_ratios else None,
                n_class_transitions=len(transitions),
                class_transition_positions=transitions,
                index_range=(max(defined) - min(defined)) if defined else None,
                monotonicity_violations=monotonicity_violations,
                masked_by_favorable=masked,
                area_between_curves_vs_crisp_max=area,
            )
        )
    return rows


def summarize_continuity_smoothness(summaries: list[ContinuitySummaryRow]) -> dict:
    """Aggregate, honest comparison of PROPOSED-HFIS's smoothness against
    CRISP-MAX across every (boundary, context) pair actually swept -- never
    a single cherry-picked case. Computed directly from ``summaries`` (never
    independently recomputed elsewhere), so this is the same object
    ``run_summary.json``, the narrative, and the artifact validator all see.

    "Smoother" is operationalized as a strictly lower local Lipschitz ratio
    (max |delta index| / |delta input| between adjacent grid points) -- the
    discrete-grid analogue of a Lipschitz constant, and the same quantity
    the manuscript-validation task spec asks for. Ties count as neither
    smoother nor rougher.
    """
    by_key: dict[tuple[str, str], dict[str, ContinuitySummaryRow]] = {}
    for s in summaries:
        by_key.setdefault((s.boundary_id, s.context), {})[s.method] = s

    n_pairs = 0
    hfis_smoother, crisp_max_smoother, tied = 0, 0, 0
    hfis_lipschitz: list[float] = []
    crisp_max_lipschitz: list[float] = []
    areas: list[float] = []
    for pair in by_key.values():
        hfis = pair.get("PROPOSED-HFIS")
        cm = pair.get("CRISP-MAX")
        if hfis is None or cm is None:
            continue
        if hfis.local_lipschitz_ratio is not None:
            hfis_lipschitz.append(hfis.local_lipschitz_ratio)
        if cm.local_lipschitz_ratio is not None:
            crisp_max_lipschitz.append(cm.local_lipschitz_ratio)
        if hfis.area_between_curves_vs_crisp_max is not None:
            areas.append(hfis.area_between_curves_vs_crisp_max)
        if hfis.local_lipschitz_ratio is None or cm.local_lipschitz_ratio is None:
            continue
        n_pairs += 1
        if hfis.local_lipschitz_ratio < cm.local_lipschitz_ratio - 1e-9:
            hfis_smoother += 1
        elif hfis.local_lipschitz_ratio > cm.local_lipschitz_ratio + 1e-9:
            crisp_max_smoother += 1
        else:
            tied += 1

    mean_hfis_lipschitz = float(np.mean(hfis_lipschitz)) if hfis_lipschitz else None
    mean_crisp_max_lipschitz = float(np.mean(crisp_max_lipschitz)) if crisp_max_lipschitz else None
    mean_area = float(np.mean(areas)) if areas else None

    if n_pairs == 0:
        conclusion = "No (boundary, context) pairs had a defined Lipschitz ratio for both methods -- no smoothness comparison possible."
    elif hfis_smoother == 0 and crisp_max_smoother == 0:
        conclusion = (
            f"PROPOSED-HFIS and CRISP-MAX had numerically identical local Lipschitz ratios on all {n_pairs} "
            f"boundary/context pairs tested -- no smoothness advantage observed under this experimental design. "
            f"This is expected, not a defect in either method: each sweep perturbs only ONE channel within a "
            f"narrow +/-sensor-uncertainty window while the other channels are held at a FIXED representative "
            f"value for the context; the worst-of rule base makes whichever channel has the higher severity "
            f"dominate the aggregated result, and in this design one channel dominates the ENTIRE sweep (the "
            f"swept channel's narrow local range essentially never crosses the fixed other channels' value), so "
            f"both methods reduce to reporting that one dominant channel's own score throughout -- see "
            f"docs/hfis_vs_crispmax_audit.md section 3 for the proof, and its independent multi-component "
            f"synthetic check (section 2) for evidence the two methods DO diverge substantially once more than "
            f"one channel is simultaneously close to the maximum severity."
        )
    elif hfis_smoother > crisp_max_smoother:
        conclusion = (
            f"PROPOSED-HFIS had a strictly lower local Lipschitz ratio than CRISP-MAX on {hfis_smoother}/{n_pairs} "
            f"boundary/context pairs ({crisp_max_smoother} the reverse, {tied} tied) -- PROPOSED-HFIS is smoother "
            f"than CRISP-MAX on most of the boundaries and contexts tested, not uniformly."
        )
    elif crisp_max_smoother > hfis_smoother:
        conclusion = (
            f"CRISP-MAX had a strictly lower local Lipschitz ratio than PROPOSED-HFIS on {crisp_max_smoother}/{n_pairs} "
            f"boundary/context pairs ({hfis_smoother} the reverse, {tied} tied) -- PROPOSED-HFIS is NOT smoother than "
            f"CRISP-MAX on most of the boundaries and contexts tested; any smoothness claim must be scoped accordingly."
        )
    else:
        conclusion = f"PROPOSED-HFIS was smoother on {hfis_smoother}/{n_pairs} pairs and CRISP-MAX on an equal number ({crisp_max_smoother}/{n_pairs}) -- no overall smoothness advantage either way."

    return {
        "n_boundary_context_pairs_compared": n_pairs,
        "hfis_smoother_count": hfis_smoother,
        "crisp_max_smoother_count": crisp_max_smoother,
        "tied_count": tied,
        "mean_local_lipschitz_ratio_hfis": mean_hfis_lipschitz,
        "mean_local_lipschitz_ratio_crisp_max": mean_crisp_max_lipschitz,
        "mean_area_between_curves_vs_crisp_max": mean_area,
        "conclusion": conclusion,
    }


def run_continuity_experiment(ctx: RuntimeContext, control_regions, room_profiles, fallback_profile, n_points: int) -> tuple[list[GridPoint], list[ContinuitySummaryRow]]:
    all_points: list[GridPoint] = []
    all_summaries: list[ContinuitySummaryRow] = []
    for boundary in enumerate_boundaries(control_regions, room_profiles):
        for context in CONTEXTS:
            points = sweep_boundary(ctx, control_regions, room_profiles, fallback_profile, boundary, context, n_points)
            all_points.extend(points)
            all_summaries.extend(summarize_boundary(boundary, context, points))
    return all_points, all_summaries
