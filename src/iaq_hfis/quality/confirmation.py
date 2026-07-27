"""SUSPECT-confirmation rules: cross-channel corroboration, dual-channel
agreement, and persistence in subsequent readings.

Per the manuscript: a PM change is confirmed if corroborated by consistent
dynamics in the auxiliary PM channels (PM1/PM4/number concentrations/typical
particle size) or by outdoor PM2.5/PM10; a temperature or humidity change is
confirmed via the duplicate SCD41/BME688 channel and/or outdoor context.
Either way, confirmation also requires the change to persist in following
measurements, not just appear at a single sample.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from iaq_hfis.quality.reasons import run_lengths


def cross_channel_agreement(primary: pd.Series, other: pd.Series) -> pd.Series:
    """True where the sample-to-sample change in ``primary`` has the same
    (nonzero) sign as the change in ``other`` — evidence the primary
    channel's movement reflects a real environmental change rather than a
    single-channel artifact."""
    p_sign = np.sign(primary.diff())
    o_sign = np.sign(other.diff())
    return (p_sign == o_sign) & (p_sign != 0)


def dual_channel_close(primary: pd.Series, secondary: pd.Series, tolerance: float) -> pd.Series:
    """True where two duplicate-measurement channels (e.g. BME688 vs SCD41
    temperature) agree within ``tolerance``."""
    return (primary - secondary).abs() <= tolerance


def outdoor_trend_agrees(indoor_series: pd.Series, outdoor_trend_sign: int | None) -> pd.Series:
    """True where the indoor channel's cumulative change from the window's
    first valid value up to each point has the same sign as
    ``outdoor_trend_sign``.

    Outdoor data is hourly while indoor channels are sampled every 30 s, so
    a point-wise diff-sign comparison against a single repeated as-of value
    would be meaningless (the outdoor diff would be ~0 at every indoor
    sample). Instead the caller precomputes ``outdoor_trend_sign`` from two
    as-of outdoor fetches spanning the recent past (e.g. now vs ~1h ago),
    and this only asks whether the indoor channel is moving the same
    direction over the window as that slower outdoor trend.
    """
    if outdoor_trend_sign is None or outdoor_trend_sign == 0 or indoor_series.notna().sum() == 0:
        return pd.Series(False, index=indoor_series.index)
    first_valid = indoor_series.dropna().iloc[0]
    cumulative_sign = np.sign(indoor_series - first_valid)
    return cumulative_sign == outdoor_trend_sign


def persists(is_suspect: pd.Series, min_consecutive: int) -> pd.Series:
    """True at every position that is part of a run of >= ``min_consecutive``
    consecutive SUSPECT flags — an isolated single-sample flag never
    persists and stays unconfirmed."""
    is_suspect = is_suspect.fillna(False)
    same_as_prev_suspect = (is_suspect & is_suspect.shift().fillna(False)) | (~is_suspect)
    run_length = run_lengths(same_as_prev_suspect)
    return is_suspect & (run_length >= min_consecutive)


def confirm_pm_event(
    is_suspect: pd.Series,
    primary: pd.Series,
    auxiliary_channels: dict[str, pd.Series],
    outdoor_trend_sign: int | None,
    min_consecutive: int,
) -> pd.Series:
    """Confirm SUSPECT PM readings: corroborated by at least one auxiliary
    channel (PM1/PM4/number concentrations/typical particle size) or by the
    outdoor PM trend, and persisting for ``min_consecutive`` samples."""
    corroborated = pd.Series(False, index=primary.index)
    for aux in auxiliary_channels.values():
        corroborated = corroborated | cross_channel_agreement(primary, aux)
    corroborated = corroborated | outdoor_trend_agrees(primary, outdoor_trend_sign)

    persistent = persists(is_suspect, min_consecutive)
    return is_suspect & corroborated & persistent


def confirm_dual_channel_event(
    is_suspect: pd.Series,
    primary: pd.Series,
    secondary: pd.Series | None,
    outdoor_trend_sign: int | None,
    dual_channel_tolerance: float,
    min_consecutive: int,
) -> pd.Series:
    """Confirm SUSPECT temperature/humidity readings: agreement with the
    duplicate sensor channel and/or a corroborating outdoor trend, plus
    persistence."""
    corroborated = pd.Series(False, index=primary.index)
    if secondary is not None:
        corroborated = corroborated | dual_channel_close(primary, secondary, dual_channel_tolerance)
    corroborated = corroborated | outdoor_trend_agrees(primary, outdoor_trend_sign)

    persistent = persists(is_suspect, min_consecutive)
    return is_suspect & corroborated & persistent


def confirm_by_persistence_only(is_suspect: pd.Series, min_consecutive: int) -> pd.Series:
    """CO2 has no duplicate sensor channel and no usable outdoor CO2 proxy
    (``weather_observations.carbon_monoxide`` is CO, never a CO2 substitute)
    — the manuscript gives CO2 no cross-channel corroboration mechanism, so
    confirmation for this channel relies on persistence alone."""
    return persists(is_suspect, min_consecutive)
