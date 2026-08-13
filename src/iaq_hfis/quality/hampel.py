"""Hampel filter (median + MAD) for local outlier detection.

A flagged point is never removed or auto-corrected — it is only tentatively
marked as a SUSPECT candidate; :mod:`iaq_hfis.quality.soft_checks` decides
whether it is subsequently confirmed (usable) or stays unconfirmed
(unusable, but the SUSPECT label and reason are preserved for audit).

The manuscript describes a CAUSAL window: for measurement x_i, the window
is {x_{i-window_size+1}, ..., x_{i-1}, x_i} -- the current sample and the
window_size-1 immediately preceding samples, never a later one. This is
distinct from the shape used in the cited illustrative example (Pearson,
Neuvo, Astola, Gabbouj, "Generalized Hampel Filters", 2016, Sec. 2: a
centered window, j in [-K, K]) -- window_size=11 and mad_multiplier are
still sourced from that paper's worked example (see
:class:`iaq_hfis.config.HampelConfig`), but the window SHAPE follows the
manuscript's own causal definition, not the cited paper's centered one.
A centered window is NOT equivalent to this causal one and must never be
described as such: at any given x_i, a centered window includes up to
window_size//2 samples that occur strictly after x_i, which the causal
window never does.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Scale factor converting MAD to a standard-deviation-equivalent for a
#: normal distribution (standard consistency constant).
_MAD_TO_SIGMA = 1.4826


def hampel_flags(series: pd.Series, window_size: int, mad_multiplier: float) -> pd.DataFrame:
    """Causal rolling-window Hampel filter.

    For each point i, the window is {x_{i-window_size+1}, ..., x_i} --
    x_i and the window_size-1 samples immediately preceding it in
    ``series``'s index order. No sample later than x_i is ever read for
    x_i's own median/MAD/outlier decision (verified by
    ``tests/unit/test_hampel_causal.py``'s prefix-invariance test: changing
    any value after x_i cannot change x_i's result).

    Returns a DataFrame aligned to ``series.index`` with columns
    ``median``, ``mad``, ``is_outlier``. A point whose causal window has
    fewer than ``window_size`` finite samples (not enough valid history
    available yet -- e.g. near the very start of ``series`` with no
    historical context prepended) is left unflagged (NaN median/mad,
    is_outlier=False), matching the prior behavior's minimum-count policy:
    a value is never flagged without a full window of valid history.
    """
    if window_size < 3:
        raise ValueError("window_size must be >= 3")

    values = series.astype(float).to_numpy()
    n = len(values)

    median = np.full(n, np.nan)
    mad = np.full(n, np.nan)
    is_outlier = np.zeros(n, dtype=bool)

    for i in range(n):
        lo = max(0, i - window_size + 1)
        window = values[lo : i + 1]  # causal: x_i and up to window_size-1 samples strictly before it
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
