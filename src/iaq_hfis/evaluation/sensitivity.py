"""Sensitivity sweeps: window duration and completeness coverage threshold.

Both sweep ranges are given explicitly by the manuscript (window minutes
{5, 15, 30, 60}; coverage threshold {0.70, 0.80, 0.90}) — not provisional —
via ``EvaluationConfig.sensitivity_window_minutes`` /
``sensitivity_coverage_thresholds``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings
from iaq_hfis.db import AirMonitorSource


@dataclass(frozen=True)
class SensitivityResult:
    varied_parameter: str  # "window_minutes" | "coverage_threshold"
    value: float
    completeness_status: str
    index_value: float | None
    index_class: str | None


def sweep_window_minutes(
    ctx, source: AirMonitorSource, computed_ts: datetime, window_minutes_list: list[int], mode: str = "publication"
) -> list[SensitivityResult]:
    """Re-runs inference at the same computed_ts over each window size,
    reusing a single already-built :class:`iaq_hfis.pipeline.RuntimeContext`
    (window size is already a parameter of ``compute_index_at``, no context
    rebuild needed). ``mode`` must match the pipeline run being evaluated --
    an exploratory-mode evaluation must not raise TEMPERATURE_PROFILE_NOT_DEFINED
    on a room/season with no DBN profile."""
    from iaq_hfis.pipeline import compute_index_at

    results = []
    for window_minutes in window_minutes_list:
        outcome = compute_index_at(ctx, source, computed_ts, window_minutes, writer=None, mode=mode)
        results.append(
            SensitivityResult(
                varied_parameter="window_minutes",
                value=window_minutes,
                completeness_status=outcome["completeness_status"],
                index_value=outcome["index_value"],
                index_class=outcome["index_class"],
            )
        )
    return results


def sweep_coverage_thresholds(
    settings: Settings,
    sensor_specs: SensorSpecs,
    room_profiles: RoomProfilesConfig,
    source: AirMonitorSource,
    computed_ts: datetime,
    window_minutes: int,
    thresholds: list[float],
    mode: str = "publication",
) -> list[SensitivityResult]:
    """Coverage threshold lives in ``Settings.coverage.min_ratio``, read
    fresh from ``ctx.settings`` on every ``compute_index_at`` call — so
    each threshold needs its own :class:`RuntimeContext` (a deep-copied
    settings variant), unlike the window sweep above. ``mode`` must match
    the pipeline run being evaluated (see :func:`sweep_window_minutes`)."""
    from iaq_hfis.pipeline import build_runtime_context, compute_index_at

    actual_columns = source.raw_schema_columns()
    results = []
    for threshold in thresholds:
        settings_variant = settings.model_copy(deep=True)
        settings_variant.coverage.min_ratio = threshold
        ctx_variant = build_runtime_context(settings_variant, sensor_specs, room_profiles, actual_columns)
        outcome = compute_index_at(ctx_variant, source, computed_ts, window_minutes, writer=None, mode=mode)
        results.append(
            SensitivityResult(
                varied_parameter="coverage_threshold",
                value=threshold,
                completeness_status=outcome["completeness_status"],
                index_value=outcome["index_value"],
                index_class=outcome["index_class"],
            )
        )
    return results
