"""Stage 1 (hard) validation: record presence, numeric format, device status
flags, datasheet technical range, and PM cross-channel ordering.

Every function here only ever *reads* raw values — raw_observations is
never modified, and every raw value is copied into the derived
``observation_quality`` table purely for audit.
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from iaq_hfis.config import ChannelMapEntry, ChannelTechnicalRange, SensorSpecs
from iaq_hfis.constants import QualityState, ReasonCode
from iaq_hfis.schema import RAW_COLUMN_TO_SENSOR_SPEC

# Auxiliary SPS30 columns used only for the PM cross-order sanity check
# (Table 1 of the manuscript: PM1/PM4 are auxiliary features, not direct inputs).
_PM1_COLUMN = "mass_pm1_0"
_PM4_COLUMN = "mass_pm4_0"


def check_record_presence(matched_slots: dict[datetime, datetime | None]) -> dict[datetime, bool]:
    """True for every expected slot that matched an actual raw timestamp."""
    return {slot: (actual is not None) for slot, actual in matched_slots.items()}


def check_numeric_format(value: object) -> bool:
    """True if ``value`` is a finite real number (not None, NaN, or +/-inf)."""
    if value is None:
        return False
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if isinstance(v, float) and pd.isna(v):
        return False
    return math.isfinite(v)


def check_technical_range(value: float, spec: ChannelTechnicalRange) -> bool:
    """True if ``value`` falls within the sensor's datasheet technical range."""
    return spec.min <= value <= spec.max


def check_device_status(status_value: object, status_state_map: dict[str, str]) -> QualityState | None:
    """Map a raw device-status flag (e.g. ``sensor_status``) to a quality
    state override. Returns None when the status is unknown or maps to
    VALID, meaning "no override — continue with the value-level checks".
    """
    if status_value is None or (isinstance(status_value, float) and pd.isna(status_value)):
        return None
    mapped = status_state_map.get(str(status_value).lower())
    if mapped is None:
        return None
    state = QualityState(mapped)
    return None if state == QualityState.VALID else state


def check_pm_ordering(pm1: float | None, pm2_5: float | None, pm4: float | None, pm10: float | None, tolerance_pct: float) -> bool:
    """PM1 <= PM2.5 <= PM4 <= PM10 is physically expected (cumulative mass
    concentrations); allow ``tolerance_pct`` slack for sensor noise near
    equal readings. Returns True (no violation) if any value is missing —
    this check only judges internal consistency, not completeness.
    """
    vals = [pm1, pm2_5, pm4, pm10]
    if any(v is None or not check_numeric_format(v) for v in vals):
        return True

    def _tol(reference: float) -> float:
        return abs(reference) * (tolerance_pct / 100.0)

    if pm1 > pm2_5 + _tol(pm2_5):
        return False
    if pm2_5 > pm4 + _tol(pm4):
        return False
    if pm4 > pm10 + _tol(pm10):
        return False
    return True


def run_hard_checks(
    raw_df: pd.DataFrame,
    matched_slots: dict[datetime, datetime | None],
    channel: str,
    channel_map: ChannelMapEntry,
    sensor_specs: SensorSpecs,
    status_state_map: dict[str, str],
    pm_ordering_tolerance_pct: float = 20.0,
) -> pd.DataFrame:
    """Stage 1 validation for one channel over one set of expected slots.

    Returns a DataFrame with one row per expected slot:
    ``ts, raw_value, stage1_state, reason_codes``.
    """
    indexed = raw_df.set_index("ts") if "ts" in raw_df.columns else raw_df
    spec_key = RAW_COLUMN_TO_SENSOR_SPEC.get(channel_map.source_column)
    spec = sensor_specs.channels.get(spec_key) if spec_key else None

    rows = []
    for slot, actual_ts in matched_slots.items():
        reasons: list[str] = []
        if actual_ts is None:
            rows.append(
                {"ts": slot, "raw_value": None, "stage1_state": QualityState.MISSING.value, "reason_codes": [ReasonCode.DATA_LOSS.value]}
            )
            continue

        record = indexed.loc[actual_ts]
        if isinstance(record, pd.DataFrame):  # duplicate actual_ts guard
            record = record.iloc[0]

        raw_value = record.get(channel_map.source_column)
        status_value = record.get(channel_map.device_status_column)

        status_override = check_device_status(status_value, status_state_map)
        if status_override is not None:
            reason = ReasonCode.DATA_LOSS.value if status_override == QualityState.MISSING else ReasonCode.OUT_OF_RANGE.value
            rows.append({"ts": slot, "raw_value": raw_value, "stage1_state": status_override.value, "reason_codes": [reason]})
            continue

        if not check_numeric_format(raw_value):
            rows.append(
                {"ts": slot, "raw_value": raw_value, "stage1_state": QualityState.INVALID.value, "reason_codes": [ReasonCode.OUT_OF_RANGE.value]}
            )
            continue

        value = float(raw_value)
        if spec is not None and not check_technical_range(value, spec):
            rows.append(
                {"ts": slot, "raw_value": value, "stage1_state": QualityState.INVALID.value, "reason_codes": [ReasonCode.OUT_OF_RANGE.value]}
            )
            continue

        if channel in ("pm2_5", "pm10") and _PM1_COLUMN in record.index and _PM4_COLUMN in record.index:
            pm1, pm4 = record.get(_PM1_COLUMN), record.get(_PM4_COLUMN)
            pm2_5_val = record.get("mass_pm2_5")
            pm10_val = record.get("mass_pm10")
            if not check_pm_ordering(pm1, pm2_5_val, pm4, pm10_val, pm_ordering_tolerance_pct):
                rows.append(
                    {"ts": slot, "raw_value": value, "stage1_state": QualityState.INVALID.value, "reason_codes": [ReasonCode.OUT_OF_RANGE.value]}
                )
                continue

        rows.append({"ts": slot, "raw_value": value, "stage1_state": QualityState.VALID.value, "reason_codes": []})

    return pd.DataFrame(rows)
