"""Hampel filter (median + MAD) for local outlier detection.

A flagged point is never removed or auto-corrected — it is only tentatively
marked as a SUSPECT candidate; :mod:`iaq_hfis.quality.soft_checks` decides
whether it is subsequently confirmed (usable) or stays unconfirmed
(unusable, but the SUSPECT label and reason are preserved for audit).

Window size and MAD multiplier are configurable
(:class:`iaq_hfis.config.HampelConfig`) — the manuscript names the Hampel
filter but does not give numeric defaults, so these are PROVISIONAL.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Scale factor converting MAD to a standard-deviation-equivalent for a
#: normal distribution (standard consistency constant).
_MAD_TO_SIGMA = 1.4826


def hampel_flags(series: pd.Series, window_size: int, mad_multiplier: float) -> pd.DataFrame:
    """Centered rolling-window Hampel filter.

    For each point i, the window is centered on i (±window_size//2 samples,
    clipped at the series edges). Because this pipeline only ever computes
    aggregates over a window that has already fully elapsed by the time of
    computation, a centered window does not introduce any future-data
    leakage into the recompute schedule itself.

    Returns a DataFrame aligned to ``series.index`` with columns
    ``median``, ``mad``, ``is_outlier``. Points whose window has fewer than
    ``window_size`` finite samples are left unflagged (NaN median/mad,
    is_outlier=False) — such points are already MISSING/INVALID from stage 1
    hard checks, which is a separate, prior concern.
    """
    if window_size < 3:
        raise ValueError("window_size must be >= 3")

    values = series.astype(float).to_numpy()
    n = len(values)
    half = window_size // 2

    median = np.full(n, np.nan)
    mad = np.full(n, np.nan)
    is_outlier = np.zeros(n, dtype=bool)

    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        window = values[lo:hi]
        valid = window[~np.isnan(window)]
        if len(valid) < window_size or np.isnan(values[i]):
            continue

        m = float(np.median(valid))
        d = float(np.median(np.abs(valid - m))) * _MAD_TO_SIGMA
        median[i] = m
        mad[i] = d

        if d > 0:
            is_outlier[i] = abs(values[i] - m) > mad_multiplier * d
        else:
            is_outlier[i] = values[i] != m

    return pd.DataFrame({"median": median, "mad": mad, "is_outlier": is_outlier}, index=series.index)
