"""Outdoor atmospheric context: as-of fetch, staleness flagging, and trend
signs used only for SUSPECT confirmation and seasonal profile selection —
never as a direct index input (manuscript: outdoor data explains internal
changes, it does not enter the integral index numerically).

``weather_observations.carbon_monoxide`` is CO, never CO2 — this module
never reads that field into anything CO2-related; the schema-level guard
against that specific mistake lives in
:class:`iaq_hfis.config.SchemaMappingConfig`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from iaq_hfis.db import AirMonitorSource

#: Outdoor fields (weather_observations columns) actually used by iaq_hfis.
#: Deliberately excludes carbon_monoxide (CO) and every other unused column.
_USED_OUTDOOR_FIELDS = ("forecast_time", "pm2_5", "pm10", "temperature_2m", "relative_humidity_2m")

_TREND_FIELD_MAP = {"pm2_5": "pm2_5", "pm10": "pm10", "temperature": "temperature_2m", "humidity": "relative_humidity_2m"}


def compute_outdoor_trend_signs(current: dict | None, previous: dict | None) -> dict[str, int | None]:
    """Sign of the outdoor change between two as-of fetches, per canonical
    channel. None means "no trend signal available" (missing/stale data on
    either side); 0 means no change; +-1 means rising/falling.

    Weather data is hourly, so a meaningful "dynamics" signal for outdoor
    corroboration (per the manuscript) can only be a slower before/after
    comparison, not a per-30s series like the indoor channels.
    """
    out: dict[str, int | None] = {}
    for canonical, col in _TREND_FIELD_MAP.items():
        if current is None or previous is None:
            out[canonical] = None
            continue
        cv, pv = current.get(col), previous.get(col)
        if cv is None or pv is None or pd.isna(cv) or pd.isna(pv):
            out[canonical] = None
            continue
        diff = float(cv) - float(pv)
        out[canonical] = int(np.sign(diff))
    return out


def fetch_outdoor_context(
    source: AirMonitorSource, computed_ts: datetime, max_age_minutes: float, trend_lookback_hours: float = 1.0
) -> dict:
    """As-of outdoor snapshot for ``computed_ts`` plus staleness flag and
    trend signs (computed against an as-of fetch ``trend_lookback_hours`` earlier).
    """
    current = source.fetch_outdoor_asof(computed_ts)
    previous = source.fetch_outdoor_asof(computed_ts - timedelta(hours=trend_lookback_hours))
    trend_signs = compute_outdoor_trend_signs(current, previous)

    if current is None:
        return {
            "forecast_time": None,
            "age_minutes": None,
            "is_stale": True,
            "pm2_5": None,
            "pm10": None,
            "temperature_2m": None,
            "relative_humidity_2m": None,
            "trend_signs": trend_signs,
        }

    forecast_time = current.get("forecast_time")
    age_minutes = (computed_ts - forecast_time).total_seconds() / 60.0 if forecast_time is not None else None
    is_stale = age_minutes is None or age_minutes > max_age_minutes

    return {
        "forecast_time": forecast_time,
        "age_minutes": age_minutes,
        "is_stale": is_stale,
        "pm2_5": current.get("pm2_5"),
        "pm10": current.get("pm10"),
        "temperature_2m": current.get("temperature_2m"),
        "relative_humidity_2m": current.get("relative_humidity_2m"),
        "trend_signs": trend_signs,
    }
