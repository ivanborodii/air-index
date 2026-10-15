"""Components Q_c (formulas (2)-(4)), integral index I (formulas (5)-(7))
and dominance shares S_c (formulas (8)-(9))."""

from __future__ import annotations

import numpy as np
import pandas as pd

from iaq_index.config import INDICATORS, IndexConfig
from iaq_index.scores import class_from_score, deviation_score


def integral_index(Q: np.ndarray, cfg: IndexConfig) -> dict[str, np.ndarray]:
    """``Q``: (n, n_components) array of component scores.
    Returns Q_mean (5), Q_max, Delta (6) and I (7). Rows with any NaN give NaN."""
    Q = np.asarray(Q, dtype=float)
    q_mean = Q.mean(axis=1)
    q_max = Q.max(axis=1)
    delta = np.maximum(0.0, cfg.critical_threshold - q_max)
    index = np.maximum(q_mean, q_max - delta)
    return {"Q_mean": q_mean, "Q_max": q_max, "Delta": delta, "I": index}


def compute_scores(df: pd.DataFrame, cfg: IndexConfig) -> pd.DataFrame:
    """Adds d_<indicator> for the 5 indicator columns of ``df``."""
    out = {}
    for name in INDICATORS:
        out[f"d_{name}"] = deviation_score(df[name].to_numpy(), cfg.indicators[name], cfg)
    return pd.DataFrame(out, index=df.index)


def compute_index_frame(df: pd.DataFrame, cfg: IndexConfig) -> pd.DataFrame:
    """Full model on a frame holding the 5 indicator columns. I and every
    derived column are NaN unless all five indicators are present."""
    d = compute_scores(df, cfg)
    complete = df[INDICATORS].notna().all(axis=1).to_numpy()
    out = d.copy()
    comps = cfg.components
    for c, members in comps.items():
        q = d[[f"d_{m}" for m in members]].max(axis=1, skipna=False).to_numpy()
        out[f"Q_{c}"] = np.where(complete, q, np.nan)
    Q = out[[f"Q_{c}" for c in comps]].to_numpy()
    res = integral_index(Q, cfg)
    for k, v in res.items():
        out[k] = np.where(complete, v, np.nan)
    out["class_I"] = class_from_score(out["I"].to_numpy())
    for c in comps:
        out[f"class_{c}"] = class_from_score(out[f"Q_{c}"].to_numpy())
    return out


def component_names(cfg: IndexConfig) -> list[str]:
    return list(cfg.components)


def dominance_flags(frame: pd.DataFrame, cfg: IndexConfig) -> pd.DataFrame:
    """Per hour with I > dominance_min_index: boolean Q_c >= Q_max - tol per
    component (formula (9)). Other hours are dropped."""
    comps = component_names(cfg)
    sel = frame[frame["I"] > cfg.dominance_min_index]
    flags = pd.DataFrame(index=sel.index)
    for c in comps:
        flags[c] = sel[f"Q_{c}"] >= sel["Q_max"] - cfg.dominance_tolerance
    return flags


def dominance_shares(frame: pd.DataFrame, cfg: IndexConfig) -> dict[str, float]:
    """S_c = N_c / N (formula (8)), plus N and the share of hours attributed
    to more than one component."""
    flags = dominance_flags(frame, cfg)
    n = len(flags)
    out: dict[str, float] = {"N": float(n)}
    for c in flags.columns:
        out[f"S_{c}"] = float(flags[c].sum() / n) if n else np.nan
    out["share_multi"] = float((flags.sum(axis=1) > 1).sum() / n) if n else np.nan
    return out


def index_from_indicators(values: dict[str, np.ndarray], cfg: IndexConfig) -> pd.DataFrame:
    """Formula (11): I computed with (1)-(7) from (forecast) indicator values."""
    return compute_index_frame(pd.DataFrame(values), cfg)
