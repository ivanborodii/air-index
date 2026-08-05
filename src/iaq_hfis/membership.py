"""Trapezoidal membership functions built from the manuscript's control
regions (:class:`iaq_hfis.config.ControlRegions` / room temperature
profiles) and validated transition widths
(:func:`iaq_hfis.schema.validate_membership_config`).

Boundary monotonicity is already enforced when the config models load
(:mod:`iaq_hfis.config`'s pydantic validators reject non-increasing
breakpoints at load time) — this module can assume every breakpoint list it
receives is already valid and only needs to build and evaluate shapes.

Every class is represented uniformly as a list of one or two ``(a, b, c, d)``
trapezoids (two for the two-sided low/high bands of a Critical/Degraded/
Acceptable class on temperature or humidity); a class's membership degree is
the max over its shapes. Pure shoulders use ``+/-math.inf`` sentinels for
the missing edge so the same :func:`trapezoid` handles every case.
"""

from __future__ import annotations

import math

from iaq_hfis.config import TwoSidedRanges
from iaq_hfis.constants import CLASS_ORDER

Shape = tuple[float, float, float, float]


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """μ(x; a, b, c, d) = max(0, min((x-a)/(b-a), 1, (d-x)/(d-c))).

    ``a == b`` degenerates the rising edge to a step (used for shoulders
    with ``a = b = -inf``); ``c == d`` degenerates the falling edge the same
    way (``c = d = +inf``).
    """
    left = 1.0 if b == a else (x - a) / (b - a)
    right = 1.0 if d == c else (d - x) / (d - c)
    return max(0.0, min(left, 1.0, right))


def build_monotonic_classes(breakpoints: list[float], widths: list[float]) -> dict[str, list[Shape]]:
    """Right-shoulder-only classes for a monotonic channel (PM2.5, PM10,
    CO2, or the output index): higher is never better."""
    bp0, bp1, bp2 = breakpoints
    w0, w1, w2 = widths
    inf = math.inf
    return {
        "Favourable": [(-inf, -inf, bp0 - w0 / 2, bp0 + w0 / 2)],
        "Acceptable": [(bp0 - w0 / 2, bp0 + w0 / 2, bp1 - w1 / 2, bp1 + w1 / 2)],
        "Degraded": [(bp1 - w1 / 2, bp1 + w1 / 2, bp2 - w2 / 2, bp2 + w2 / 2)],
        "Critical": [(bp2 - w2 / 2, bp2 + w2 / 2, inf, inf)],
    }


def _band_shape(lo: float, hi: float, width: float) -> Shape:
    return (lo - width / 2, lo + width / 2, hi - width / 2, hi + width / 2)


def build_two_sided_classes(ranges: TwoSidedRanges, width: float) -> dict[str, list[Shape]]:
    """Two-sided classes for temperature or relative humidity: both low and
    high deviations from the favourable band are unfavorable. Critical,
    Degraded and Acceptable each cover a low-side and a high-side band;
    Favourable is the single central band.

    Each class's shape is built from its own band edges, so two adjacent
    classes that share a numeric boundary (as every manuscript profile
    does) automatically cross at membership 0.5 exactly at that boundary.
    """
    inf = math.inf
    low_tail = (-inf, -inf, ranges.critical_low_max - width / 2, ranges.critical_low_max + width / 2)
    high_tail = (ranges.critical_high_min - width / 2, ranges.critical_high_min + width / 2, inf, inf)
    return {
        "Favourable": [_band_shape(ranges.favourable[0], ranges.favourable[1], width)],
        "Acceptable": [
            _band_shape(ranges.acceptable_low[0], ranges.acceptable_low[1], width),
            _band_shape(ranges.acceptable_high[0], ranges.acceptable_high[1], width),
        ],
        "Degraded": [
            _band_shape(ranges.degraded_low[0], ranges.degraded_low[1], width),
            _band_shape(ranges.degraded_high[0], ranges.degraded_high[1], width),
        ],
        "Critical": [low_tail, high_tail],
    }


def evaluate_memberships(value: float, class_shapes: dict[str, list[Shape]]) -> dict[str, float]:
    """Degree of membership in every class in :data:`iaq_hfis.constants.CLASS_ORDER`."""
    return {cls: max(trapezoid(value, *shape) for shape in class_shapes[cls]) for cls in CLASS_ORDER}
