"""Synthetic ground-truth vectors near each control-region boundary, and
scoring against them.

Per the manuscript: macro-F1 and Cohen's kappa are only ever computed
against manually-labeled or synthetic observations with a pre-defined
reference class — never against unlabeled real data (see
:mod:`iaq_hfis.evaluation.agreement` for the unlabeled-data comparison,
which reports agreement only, not these metrics).

Each synthetic vector perturbs exactly one direct-input channel to a point
just below/above one of its configured breakpoints, holding every other
channel at a deeply-favorable baseline. Because the fuzzy rule base is
worst-of (Phase 1, ``rules.py``), the expected final index class in this
single-channel-perturbed construction is exactly the perturbed channel's
own crisp class — no combinatorial multi-channel ground truth is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from iaq_hfis.config import ClassBoundaries, RoomTemperatureProfile, TwoSidedRanges
from iaq_hfis.constants import CLASS_ORDER

#: Deeply-favorable baseline values for channels NOT under test, chosen well
#: inside their Favorable band regardless of room/season profile.
_FAVORABLE_BASELINE = {"pm2_5": 5.0, "pm10": 10.0, "co2": 600.0}


@dataclass(frozen=True)
class GroundTruthVector:
    name: str
    perturbed_channel: str
    values: dict[str, float]
    expected_class: str


def crisp_class_monotonic(value: float, boundaries: ClassBoundaries) -> str:
    """Table 2's own literal <=/> convention for a monotonic channel
    (higher is never better) -- e.g. PM2.5 "<=15" Favorable, ">15-25"
    Acceptable. Used only for ground-truth labeling; the pipeline itself
    never hard-classifies a direct input (only the continuous membership
    functions built from the same breakpoints)."""
    b0, b1, b2 = boundaries.breakpoints
    if value <= b0:
        return "Favorable"
    if value <= b1:
        return "Acceptable"
    if value <= b2:
        return "Degraded"
    return "Critical"


def crisp_class_two_sided(value: float, ranges: TwoSidedRanges) -> str:
    """Table 2's own convention for a two-sided channel (T/RH): half-open
    bands where the shared boundary value belongs to the more favorable
    side, matching how the manuscript's ranges are written (e.g. RH
    "25-<30" Acceptable, so 30 itself is Favorable)."""
    if ranges.favorable[0] <= value <= ranges.favorable[1]:
        return "Favorable"
    if (ranges.acceptable_low[0] <= value < ranges.favorable[0]) or (ranges.favorable[1] < value <= ranges.acceptable_high[1]):
        return "Acceptable"
    if (ranges.degraded_low[0] <= value < ranges.acceptable_low[0]) or (ranges.acceptable_high[1] < value <= ranges.degraded_high[1]):
        return "Degraded"
    return "Critical"


def _monotonic_test_points(boundaries: ClassBoundaries, offset: float) -> list[tuple[str, float]]:
    points = []
    for i, bp in enumerate(boundaries.breakpoints):
        points.append((f"breakpoint{i}_below", bp - offset))
        points.append((f"breakpoint{i}_above", bp + offset))
    return points


def _two_sided_test_points(ranges: TwoSidedRanges, offset: float) -> list[tuple[str, float]]:
    edges = {
        "critical_low": ranges.critical_low_max,
        "acceptable_low_edge": ranges.acceptable_low[1],
        "favorable_low_edge": ranges.favorable[0],
        "favorable_high_edge": ranges.favorable[1],
        "acceptable_high_edge": ranges.acceptable_high[0],
        "critical_high": ranges.critical_high_min,
    }
    points = []
    for name, edge in edges.items():
        points.append((f"{name}_below", edge - offset))
        points.append((f"{name}_above", edge + offset))
    return points


def _baseline_values(control_regions, room_profile: RoomTemperatureProfile) -> dict[str, float]:
    values = dict(_FAVORABLE_BASELINE)
    values["temperature"] = sum(room_profile.ranges.favorable) / 2
    values["humidity"] = sum(control_regions.relative_humidity.favorable) / 2
    return values


def generate_boundary_vectors(control_regions, room_profile: RoomTemperatureProfile, offset: float = 0.5) -> list[GroundTruthVector]:
    """One vector per boundary-adjacent test point for every direct-input
    channel. ``offset`` is a small crisp-classification margin (distinct
    from the membership transition width) chosen to land unambiguously on
    one side of the boundary for labeling purposes.
    """
    vectors: list[GroundTruthVector] = []

    monotonic = {"pm2_5": control_regions.pm2_5, "pm10": control_regions.pm10, "co2": control_regions.co2}
    for channel, boundaries in monotonic.items():
        for label, value in _monotonic_test_points(boundaries, offset):
            values = _baseline_values(control_regions, room_profile)
            values[channel] = value
            vectors.append(
                GroundTruthVector(
                    name=f"{channel}_{label}", perturbed_channel=channel, values=values, expected_class=crisp_class_monotonic(value, boundaries)
                )
            )

    two_sided = {"temperature": room_profile.ranges, "humidity": control_regions.relative_humidity}
    for channel, ranges in two_sided.items():
        for label, value in _two_sided_test_points(ranges, offset):
            values = _baseline_values(control_regions, room_profile)
            values[channel] = value
            vectors.append(
                GroundTruthVector(name=f"{channel}_{label}", perturbed_channel=channel, values=values, expected_class=crisp_class_two_sided(value, ranges))
            )

    return vectors


def score_against_ground_truth(vectors: list[GroundTruthVector], predicted_classes: list[str | None]) -> dict:
    """macro-F1 and Cohen's kappa of ``predicted_classes`` against each
    vector's ``expected_class``. Entries with a None prediction (e.g. a
    FAILED completeness status) are excluded, and their count is reported
    separately rather than silently dropped."""
    from iaq_hfis.evaluation._metrics import cohens_kappa, macro_f1

    if len(vectors) != len(predicted_classes):
        raise ValueError("vectors and predicted_classes must be the same length")

    paired = [(v.expected_class, p) for v, p in zip(vectors, predicted_classes) if p is not None]
    n_excluded = len(vectors) - len(paired)
    if not paired:
        return {"n": 0, "n_excluded": n_excluded, "macro_f1": None, "cohens_kappa": None}

    y_true = [p[0] for p in paired]
    y_pred = [p[1] for p in paired]
    return {
        "n": len(paired),
        "n_excluded": n_excluded,
        "macro_f1": macro_f1(y_true, y_pred, CLASS_ORDER),
        "cohens_kappa": cohens_kappa(y_true, y_pred, CLASS_ORDER),
    }
