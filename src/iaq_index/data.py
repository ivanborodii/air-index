"""Loading and preprocessing of the Kępa & Rogulski (2025) Zenodo dataset
(DOI 10.5281/zenodo.22045167): regular hourly grid per home, invalid values
set to missing, season label. No imputation or interpolation anywhere."""

from __future__ import annotations

import numpy as np
import pandas as pd

from iaq_index.config import INDICATORS

RAW_COLUMNS = {
    "Home ID": "home",
    "Time Point": "time",
    "PM10 (µg/m³)": "pm10",
    "PM2.5 (µg/m³)": "pm25",
    "CO2 (ppm)": "co2",
    "Rhumid (%)": "rh",
    "Temp (C)": "t",
}

HEATING, WARM = "heating", "warm"


def load_raw(path) -> pd.DataFrame:
    """Reads the CSV as published (';', UTF-8 with BOM, dd.mm.yyyy HH:MM).
    Timestamps are used as they are, without time-zone conversion."""
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    # tolerate the "(dd.mm.yyyy HH:MM)" suffix some copies carry in the header
    df.columns = [c.split(" (dd")[0].strip() for c in df.columns]
    missing = set(RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"unexpected header, missing columns: {sorted(missing)}")
    df = df.rename(columns=RAW_COLUMNS)[list(RAW_COLUMNS.values())]
    df["time"] = pd.to_datetime(df["time"], format="%d.%m.%Y %H:%M")
    return df


def invalid_masks(df: pd.DataFrame, pp: dict) -> dict[str, tuple[str, pd.Series]]:
    """rule name -> (indicator, boolean mask of values to set missing)."""
    t_lo, t_hi = pp["t_range_c"]
    rh_lo, rh_hi = pp["rh_range_pct"]
    return {
        "co2_below_min": ("co2", df["co2"] < pp["co2_min_ppm"]),
        "co2_error_code": ("co2", df["co2"] == pp["co2_error_code"]),
        "pm25_above_max": ("pm25", df["pm25"] > pp["pm_max_ugm3"]),
        "pm10_above_max": ("pm10", df["pm10"] > pp["pm_max_ugm3"]),
        "t_out_of_range": ("t", (df["t"] < t_lo) | (df["t"] > t_hi)),
        "rh_out_of_range": ("rh", (df["rh"] < rh_lo) | (df["rh"] > rh_hi)),
    }


def apply_invalid_rules(df: pd.DataFrame, pp: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sets invalid values to NaN. Returns the cleaned frame and a table of
    removed-value counts per rule (computed on the original values, so a
    value matching two rules is counted under both)."""
    out = df.copy()
    rows = []
    masks = invalid_masks(df, pp)
    for rule, (col, m) in masks.items():
        rows.append({"rule": rule, "indicator": col, "n_values_removed": int(m.sum()),
                     "n_values_present_before": int(df[col].notna().sum())})
    for rule, (col, m) in masks.items():
        out.loc[m, col] = np.nan
    return out, pd.DataFrame(rows)


def season_of(time: pd.Series, pp: dict) -> pd.Series:
    m = time.dt.month
    s = pd.Series(np.where(m.isin(pp["heating_months"]), HEATING, np.where(m.isin(pp["warm_months"]), WARM, None)),
                  index=time.index)
    if s.isna().any():
        raise ValueError("months not covered by heating_months/warm_months")
    return s


def hourly_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Regular hourly grid per home from its first to last record; missing
    hours become rows with NaN indicators (never filled)."""
    parts = []
    for home, g in df.groupby("home", sort=True):
        g = g.set_index("time").sort_index()
        if g.index.has_duplicates:
            raise ValueError(f"{home}: duplicate timestamps")
        full = pd.date_range(g.index.min(), g.index.max(), freq="1h")
        g["observed"] = True  # a record exists in the file for this hour
        g = g.reindex(full)
        g.index.name = "time"
        g["home"] = home
        g["observed"] = g["observed"].fillna(False).astype(bool)
        parts.append(g.reset_index())
    out = pd.concat(parts, ignore_index=True)
    return out[["home", "time", "observed", *INDICATORS]]


def prepare(path, pp: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """raw -> (raw frame, removed-values table, cleaned hourly grid with season)."""
    raw = load_raw(path)
    clean, removed = apply_invalid_rules(raw, pp)
    grid = hourly_grid(clean)
    grid["season"] = season_of(grid["time"], pp)
    return raw, removed, grid
