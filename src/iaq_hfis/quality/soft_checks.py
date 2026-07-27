"""Stage 2 (soft) validation: orchestrates the Hampel filter, stuck-value and
gradual-drift detectors, and the confirmation rules into a final per-slot
``stage2_state``, ``usable`` and ``confirmed`` verdict for one channel.

Stage 1 (:mod:`iaq_hfis.quality.hard_checks`) must run first — only points
that are stage1 VALID are eligible to be examined here; MISSING/INVALID
points pass through unchanged (they were already unusable for a reason
unrelated to outlier detection).
"""

from __future__ import annotations

import pandas as pd

from iaq_hfis.config import ChannelMapEntry, ConfirmationConfig, HampelConfig
from iaq_hfis.constants import QualityState, ReasonCode
from iaq_hfis.quality import confirmation
from iaq_hfis.quality.hampel import hampel_flags
from iaq_hfis.quality.reasons import detect_gradual_drift, detect_stuck_value

# Auxiliary SPS30 columns used only for PM confirmation (Table 1: auxiliary features).
_PM_AUX_COLUMNS = {
    "pm2_5": ["mass_pm1_0", "mass_pm4_0", "number_pm2_5", "typical_size_um"],
    "pm10": ["mass_pm1_0", "mass_pm4_0", "number_pm10", "typical_size_um"],
}


def run_soft_checks(
    stage1_df: pd.DataFrame,
    channel: str,
    channel_map: ChannelMapEntry,
    aligned_raw: pd.DataFrame,
    outdoor_trend_sign: int | None,
    hampel_cfg: HampelConfig,
    confirmation_cfg: ConfirmationConfig,
    drift_min_magnitude: float = 0.0,
    dual_channel_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Returns ``stage1_df`` augmented with ``stage2_state``, ``usable``,
    ``confirmed``, merged ``reason_codes``, ``hampel_median``, ``hampel_mad``
    — one row per expected slot, same order as the input.

    ``drift_min_magnitude`` and ``dual_channel_tolerance`` are caller-resolved
    (from :mod:`iaq_hfis.schema`'s ``channel_uncertainty``/``dual_channel_tolerance``)
    -- kept out of this module's own responsibilities so it doesn't need
    SensorSpecs/schema mapping directly, only already-resolved config values
    (like ``hampel_cfg``/``confirmation_cfg``).
    """
    df = stage1_df.reset_index(drop=True).copy()
    slots = df["ts"].tolist()

    raw_numeric = pd.to_numeric(df["raw_value"], errors="coerce")
    series = raw_numeric.where(df["stage1_state"] == QualityState.VALID.value)
    series.index = slots

    hampel_result = hampel_flags(series, hampel_cfg.window_size, hampel_cfg.mad_multiplier)
    stuck = detect_stuck_value(series, confirmation_cfg.stuck_value_min_repeats)
    drift = detect_gradual_drift(series, confirmation_cfg.gradual_drift_min_consecutive_steps, drift_min_magnitude)
    is_outlier = hampel_result["is_outlier"]

    is_suspect_candidate = is_outlier | stuck | drift

    aligned = aligned_raw.copy()
    aligned.index = slots
    for col in aligned.columns:
        aligned[col] = pd.to_numeric(aligned[col], errors="coerce")

    if channel in _PM_AUX_COLUMNS:
        aux_channels = {c: aligned[c] for c in _PM_AUX_COLUMNS[channel] if c in aligned.columns}
        confirmed = confirmation.confirm_pm_event(
            is_suspect_candidate, series, aux_channels, outdoor_trend_sign, confirmation_cfg.persistence_min_consecutive_samples
        )
    elif channel in ("temperature", "humidity"):
        secondary = aligned[channel_map.secondary_column] if channel_map.secondary_column in aligned.columns else None
        confirmed = confirmation.confirm_dual_channel_event(
            is_suspect_candidate, series, secondary, outdoor_trend_sign, dual_channel_tolerance, confirmation_cfg.persistence_min_consecutive_samples
        )
    else:  # co2 — no cross-channel corroboration available (see confirmation.confirm_by_persistence_only)
        confirmed = confirmation.confirm_by_persistence_only(
            is_suspect_candidate, confirmation_cfg.persistence_min_consecutive_samples
        )

    stage2_state = []
    usable = []
    confirmed_col = []
    reason_codes = []
    for i, slot in enumerate(slots):
        s1 = df.at[i, "stage1_state"]
        reasons = list(df.at[i, "reason_codes"])
        if s1 != QualityState.VALID.value:
            stage2_state.append(s1)
            usable.append(False)
            confirmed_col.append(None)
            reason_codes.append(reasons)
            continue

        if not bool(is_suspect_candidate.loc[slot]):
            stage2_state.append(QualityState.VALID.value)
            usable.append(True)
            confirmed_col.append(None)
            reason_codes.append(reasons)
            continue

        if bool(stuck.loc[slot]):
            reasons.append(ReasonCode.STUCK_VALUE.value)
        if bool(drift.loc[slot]):
            reasons.append(ReasonCode.GRADUAL_DRIFT.value)
        if bool(is_outlier.loc[slot]) and not bool(stuck.loc[slot]):
            reasons.append(ReasonCode.SINGLE_SPIKE.value)

        is_confirmed = bool(confirmed.loc[slot])
        stage2_state.append(QualityState.SUSPECT.value)
        usable.append(is_confirmed)
        confirmed_col.append(is_confirmed)
        reason_codes.append(reasons)

    df["stage2_state"] = stage2_state
    df["usable"] = usable
    df["confirmed"] = confirmed_col
    df["reason_codes"] = reason_codes
    df["hampel_median"] = [hampel_result["median"].loc[s] for s in slots]
    df["hampel_mad"] = [hampel_result["mad"].loc[s] for s in slots]
    return df
