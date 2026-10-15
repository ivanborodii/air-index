"""Deviation score d_i (formula (1)) and classes (Tables 1 and 2).

d_i = 25 * (k + |x - b_k| / |b_{k+1} - b_k|) is piecewise-linear between
breakpoints, 0 inside the normative range and 100 beyond b4 -- exactly a
linear interpolation of the knots (b0..b4) -> (0, 25, 50, 75, 100) clamped
at both ends, which is how it is evaluated here (vectorized, NaN-preserving).
"""

from __future__ import annotations

import numpy as np

from iaq_index.config import IndexConfig, IndicatorBreakpoints


def _knot_scores(cfg: IndexConfig) -> np.ndarray:
    return cfg.points_per_class * np.arange(5, dtype=float)


def deviation_score(x, bp: IndicatorBreakpoints, cfg: IndexConfig) -> np.ndarray:
    """Formula (1), vectorized. NaN in -> NaN out. For two-sided indicators
    the breakpoints on the side of the deviation are used."""
    x = np.asarray(x, dtype=float)
    knots = _knot_scores(cfg)
    d = np.interp(x, np.asarray(bp.high), knots)
    if bp.kind == "two_sided":
        # low breakpoints decrease (b0 > b1 > ...): mirror to an increasing axis
        d_low = np.interp(-x, -np.asarray(bp.low), knots)
        d = np.maximum(d, d_low)
    return np.where(np.isnan(x), np.nan, d)


def class_from_score(d) -> np.ndarray:
    """Table 2: EXCELLENT = 0; GOOD (0;25]; MODERATE (25;50]; LOW (50;75];
    CRITICAL (75;100]. Returns the rank 0..4 as float (NaN for NaN)."""
    d = np.asarray(d, dtype=float)
    # ceil(d/25) maps 0 -> 0, (0,25] -> 1, (25,50] -> 2, ...; the knots
    # 25/50/75 are produced exactly by np.interp, so no epsilon is needed.
    r = np.clip(np.ceil(d / 25.0), 0, 4)
    return np.where(np.isnan(d), np.nan, r)


def class_from_value(x: float, bp: IndicatorBreakpoints) -> int:
    """Table 1 classification straight from the value (scalar, used to
    cross-check the score-based class in tests). Square bracket = limit
    included, round = excluded; limits are included on the side closer to
    the normative range."""
    hi = bp.high
    if bp.kind == "monotonic":
        if x <= hi[0]:
            return 0
        for k in range(1, 4):
            if x <= hi[k]:
                return k
        return 4
    lo = bp.low
    if lo[0] <= x <= hi[0]:
        return 0
    if x < lo[0]:
        for k in range(1, 4):
            if x >= lo[k]:
                return k
        return 4
    for k in range(1, 4):
        if x <= hi[k]:
            return k
    return 4
