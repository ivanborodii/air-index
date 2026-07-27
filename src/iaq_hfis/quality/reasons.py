"""Explanatory fault-category detectors: stuck value and gradual drift.

Single-spike and out-of-range are already produced directly by
:mod:`iaq_hfis.quality.hampel` and :mod:`iaq_hfis.quality.hard_checks`
respectively; this module covers the two remaining categories named in the
manuscript ("фіксація показника на незмінному рівні" / stuck value,
"поступове зміщення показників" / gradual drift) but not algorithmically
specified there — both are PROVISIONAL heuristics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def run_lengths(group_key: pd.Series) -> pd.Series:
    """Length of the consecutive-True run each position belongs to, given a
    boolean "same as previous" series. Shared by stuck-value, gradual-drift,
    and (via :mod:`iaq_hfis.quality.confirmation`) persistence checks."""
    group_id = (~group_key.fillna(False)).cumsum()
    return group_id.map(group_id.value_counts())


def detect_stuck_value(series: pd.Series, min_repeats: int) -> pd.Series:
    """True at every point that is part of a run of >= ``min_repeats``
    consecutive exactly-equal values (a sensor "stuck" reading a fixed
    value regardless of true conditions). NaN values are never flagged.
    """
    same_as_prev = series.eq(series.shift()).fillna(False)
    run_length = run_lengths(same_as_prev)
    return (run_length >= min_repeats) & series.notna()


def detect_gradual_drift(series: pd.Series, min_consecutive_same_direction: int, min_magnitude: float = 0.0) -> pd.Series:
    """PROVISIONAL heuristic: flags a run of >= ``min_consecutive_same_direction``
    consecutive same-direction (monotonic) steps whose cumulative change
    (from the value just before the run started) also reaches
    ``min_magnitude`` — the signature the manuscript describes for a slow
    sensor-level shift, as distinct from a single reverting spike or a
    value stuck flat.

    ``min_magnitude`` matters: run-length alone is a weak signal, since any
    real, physically ordinary environmental trend (a room's CO2 slowly
    dropping after ventilation, temperature drifting through the
    afternoon) almost always contains 5+ consecutive same-direction 30 s
    steps — that's what smooth data looks like, not a fault. Gating on a
    magnitude tied to the channel's declared sensor uncertainty (see
    :func:`iaq_hfis.schema.channel_uncertainty`) keeps the flag reserved
    for shifts that are large relative to normal sensor noise, not every
    ordinary trend. Verified against live data: without this gate, CO2's
    normal ventilation dynamics alone triggered gradual_drift on the
    majority of SUSPECT-eligible samples in a single 30-minute run.
    """
    values = series.to_numpy(dtype=float)
    n = len(values)
    flags = np.zeros(n, dtype=bool)

    prev_sign = 0
    run_length = 1
    run_start: int | None = None  # index of the value just before the current run began

    for i in range(1, n):
        if np.isnan(values[i]) or np.isnan(values[i - 1]):
            prev_sign, run_length, run_start = 0, 1, None
            continue

        diff = values[i] - values[i - 1]
        sign = 0 if diff == 0 else (1 if diff > 0 else -1)
        if sign != 0 and sign == prev_sign:
            run_length += 1
        else:
            run_length = 1
            run_start = i - 1
        prev_sign = sign

        if run_start is not None and run_length >= min_consecutive_same_direction:
            magnitude = abs(values[i] - values[run_start])
            if magnitude >= min_magnitude:
                flags[run_start + 1 : i + 1] = True

    return pd.Series(flags, index=series.index)
