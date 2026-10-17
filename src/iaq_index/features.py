"""Causal feature vector z(t) (task section 7) and forecast targets.

Features at time t use only grid rows with timestamp <= t of the same home.
Windows are time-based ``(t - w, t]`` on the regular hourly grid.
A time t is dropped when any indicator has < ``min_coverage`` of the hours
of any window present, or when I(t) is unavailable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from iaq_index.config import INDICATORS

WINDOWS_H = (3, 6, 24)
STATS = ("mean", "min", "max", "std")
MIN_COVERAGE = 0.8


def feature_columns(component_cols: list[str]) -> list[str]:
    cols = [f"cur_{x}" for x in INDICATORS]
    cols += [f"{x}_{s}_{w}h" for x in INDICATORS for w in WINDOWS_H for s in STATS]
    cols += [f"diff1_{x}" for x in INDICATORS]
    cols += list(component_cols) + ["I"]
    cols += ["hour_sin", "hour_cos", "weekend", "season_heating"]
    return cols


def _home_features(g: pd.DataFrame, component_cols: list[str]) -> pd.DataFrame:
    """``g``: one home's grid rows (time-sorted, regular hourly)."""
    g = g.set_index("time")
    out = pd.DataFrame(index=g.index)
    ok = g["I"].notna().to_numpy().copy()
    for x in INDICATORS:
        s = g[x]
        out[f"cur_{x}"] = s
        for w in WINDOWS_H:
            r = s.rolling(f"{w}h", closed="right", min_periods=1)
            cnt = r.count()
            ok &= (cnt / w >= MIN_COVERAGE).to_numpy()
            out[f"{x}_mean_{w}h"] = r.mean()
            out[f"{x}_min_{w}h"] = r.min()
            out[f"{x}_max_{w}h"] = r.max()
            out[f"{x}_std_{w}h"] = r.std()
        prev = s.reindex(g.index - pd.Timedelta(hours=1)).to_numpy()
        out[f"diff1_{x}"] = s.to_numpy() - prev
    for c in component_cols + ["I"]:
        out[c] = g[c]
    hour = g.index.hour.to_numpy()
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["weekend"] = (g.index.dayofweek >= 5).astype(np.int8)
    out["season_heating"] = (g["season"] == "heating").astype(np.int8).to_numpy()
    ok &= out[[f"diff1_{x}" for x in INDICATORS]].notna().all(axis=1).to_numpy()
    out = out[ok]
    out.insert(0, "home", g["home"].iloc[0])
    return out.reset_index()


def build_features(frame: pd.DataFrame, component_cols: list[str]) -> pd.DataFrame:
    """``frame``: hourly grid with indicators, season, component scores and I."""
    parts = [_home_features(g.sort_values("time"), component_cols) for _, g in frame.groupby("home", sort=True)]
    out = pd.concat(parts, ignore_index=True)
    return out[["home", "time", *feature_columns(component_cols)]]


def features_at(history: pd.DataFrame, t: pd.Timestamp, component_cols: list[str]) -> pd.DataFrame | None:
    """Single time point (online use): computes z(t) from one home's grid
    rows in (t - 24h, t] only. Returns a 1-row frame or None if t is not
    eligible. Must agree with :func:`build_features` (tested)."""
    lo = t - pd.Timedelta(hours=max(WINDOWS_H))
    h = history[(history["time"] > lo) & (history["time"] <= t)]
    if h.empty or h["time"].iloc[-1] != t:
        return None
    f = _home_features(h, component_cols)
    f = f[f["time"] == t]
    return None if f.empty else f[["home", "time", *feature_columns(component_cols)]]


def features_at_fast(times: np.ndarray, values: np.ndarray, current: dict[str, float], t: pd.Timestamp,
                     season_heating: int, component_cols: list[str]) -> np.ndarray | None:
    """NumPy version of :func:`features_at` for online use (same values,
    tested): ``times``/``values`` are one home's grid rows in (t - 24h, t]
    (``values`` columns in INDICATORS order), ``current`` holds the
    component scores and I at t. Returns the feature vector (order of
    :func:`feature_columns`) or None if t is not eligible."""
    w_max = max(WINDOWS_H)
    lag = ((t - pd.DatetimeIndex(times)) // pd.Timedelta(hours=1)).to_numpy()
    arr = np.full((w_max, values.shape[1]), np.nan)
    keep = (lag >= 0) & (lag < w_max)
    arr[w_max - 1 - lag[keep]] = values[keep]  # row w_max-1 = t
    if np.isnan(current.get("I", np.nan)):
        return None
    cur, prev = arr[-1], arr[-2]
    out = [cur]
    stats = np.empty((values.shape[1], len(WINDOWS_H), len(STATS)))
    for j, w in enumerate(WINDOWS_H):
        win = arr[-w:]
        cnt = (~np.isnan(win)).sum(axis=0)
        if (cnt / w < MIN_COVERAGE).any():
            return None
        stats[:, j, 0] = np.nanmean(win, axis=0)
        stats[:, j, 1] = np.nanmin(win, axis=0)
        stats[:, j, 2] = np.nanmax(win, axis=0)
        stats[:, j, 3] = np.nanstd(win, axis=0, ddof=1)
    out.append(stats.reshape(-1))
    diff = cur - prev
    if np.isnan(diff).any():
        return None
    out.append(diff)
    out.append(np.array([current[c] for c in component_cols] + [current["I"]]))
    hour = t.hour
    out.append(np.array([np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
                         float(t.dayofweek >= 5), float(season_heating)]))
    return np.concatenate(out)


def add_targets(frame: pd.DataFrame, horizons, cols: list[str]) -> pd.DataFrame:
    """For each h: columns ``<col>__h<h>`` = value at t+h and
    ``<col>__h<h>_lag24`` = value at t+h-24, looked up by timestamp within
    the home."""
    out = []
    for _, g in frame.groupby("home", sort=True):
        g = g.set_index("time").sort_index()
        res = g.copy()
        for h in horizons:
            fut = g[cols].reindex(g.index + pd.Timedelta(hours=h))
            lag = g[cols].reindex(g.index + pd.Timedelta(hours=h - 24))
            for c in cols:
                res[f"{c}__h{h}"] = fut[c].to_numpy()
                res[f"{c}__h{h}_lag24"] = lag[c].to_numpy()
        out.append(res.reset_index())
    return pd.concat(out, ignore_index=True)
