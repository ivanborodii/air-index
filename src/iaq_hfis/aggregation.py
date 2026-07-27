"""Coverage ρ = n_usable / n_expected and the time-weighted window mean.

C̄ᵢ,w(t) = Σ Cᵢ(tₖ)·Δtₖ·uᵢ(tₖ) / Σ Δtₖ·uᵢ(tₖ), computed only over usable
(VALID or confirmed-SUSPECT) points, per the manuscript's aggregation
formula.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from iaq_hfis.models import AggregateResult, CoverageResult


def compute_coverage(n_expected: int, n_usable: int, min_ratio: float) -> CoverageResult:
    """ρ = n_usable/n_expected; ok = ρ >= min_ratio (>= so exactly-at-threshold
    coverage passes, e.g. 24/30 = 0.80 passes, 23/30 = 0.7667 fails)."""
    ratio = (n_usable / n_expected) if n_expected > 0 else 0.0
    ok = n_expected > 0 and ratio >= min_ratio
    return CoverageResult(n_expected=n_expected, n_usable=n_usable, ratio=ratio, ok=ok)


def time_weighted_mean(
    points: list[tuple[datetime, float | None, bool]], window_start: datetime, window_end: datetime
) -> float | None:
    """Time-weighted mean over only the usable points.

    PROVISIONAL Δt_k rule: each usable point's weight is the midpoint-rule
    interval to its usable neighbors, clipped to the window bounds at the
    edges — the manuscript specifies the aggregation formula's shape but not
    the practical Δt_k assignment between irregular samples.
    """
    usable = sorted(((t, v) for t, v, u in points if u and v is not None), key=lambda p: p[0])
    if not usable:
        return None
    if len(usable) == 1:
        return usable[0][1]

    times = [p[0] for p in usable]
    values = [p[1] for p in usable]
    n = len(usable)

    weighted_sum = 0.0
    total_weight = 0.0
    for i in range(n):
        left = window_start if i == 0 else times[i - 1] + (times[i] - times[i - 1]) / 2
        right = window_end if i == n - 1 else times[i] + (times[i + 1] - times[i]) / 2
        dt = max((right - left).total_seconds(), 0.0)
        weighted_sum += dt * values[i]
        total_weight += dt

    return (weighted_sum / total_weight) if total_weight > 0 else None


def aggregate_channel(
    quality_df: pd.DataFrame, channel: str, window_start: datetime, window_end: datetime, min_ratio: float
) -> AggregateResult:
    """Bundles coverage + weighted mean for one channel over one window.

    ``quality_df`` is the per-slot output of
    :func:`iaq_hfis.quality.soft_checks.run_soft_checks` (columns ``ts``,
    ``raw_value``, ``usable``). ``weighted_mean`` is only computed when
    coverage is sufficient — below-threshold coverage makes the aggregate
    unavailable, per the manuscript, not merely low-confidence.
    """
    n_expected = len(quality_df)
    n_usable = int(quality_df["usable"].sum())
    coverage = compute_coverage(n_expected, n_usable, min_ratio)

    weighted_mean = None
    if coverage.ok:
        points = list(zip(quality_df["ts"], quality_df["raw_value"], quality_df["usable"]))
        weighted_mean = time_weighted_mean(points, window_start, window_end)

    return AggregateResult(channel=channel, window_start=window_start, window_end=window_end, coverage=coverage, weighted_mean=weighted_mean)
