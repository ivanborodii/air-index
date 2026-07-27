"""Synthetic air_monitor.duckdb / weather.duckdb builders for tests.

Mirrors the relevant subset of air-monitor/storage/schema.sql and
weather_schema.sql (intentionally duplicated rather than imported, to keep
the test suite independent of the live project's internals).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

RAW_OBSERVATIONS_SCHEMA = """
CREATE TABLE raw_observations (
    ts                  TIMESTAMPTZ NOT NULL,
    measured_at         TIMESTAMPTZ NOT NULL,
    loaded_at           TIMESTAMPTZ NOT NULL,
    batch_id            VARCHAR     NOT NULL,
    row_in_batch        INTEGER     NOT NULL,
    co2_ppm             DOUBLE,
    scd_temp_c          DOUBLE,
    scd_humidity_pct    DOUBLE,
    bme_temp_c          DOUBLE,
    bme_humidity_pct    DOUBLE,
    pressure_hpa        DOUBLE,
    gas_resistance_ohm  DOUBLE,
    mass_pm1_0          DOUBLE,
    mass_pm2_5          DOUBLE,
    mass_pm4_0          DOUBLE,
    mass_pm10           DOUBLE,
    number_pm0_5        DOUBLE,
    number_pm1_0        DOUBLE,
    number_pm2_5        DOUBLE,
    number_pm4_0        DOUBLE,
    number_pm10         DOUBLE,
    typical_size_um     DOUBLE,
    sensor_status       VARCHAR,
    scd41_status        VARCHAR,
    bme688_status       VARCHAR,
    sps30_status        VARCHAR
)
"""

WEATHER_OBSERVATIONS_SCHEMA = """
CREATE TABLE weather_observations (
    ts                      TIMESTAMPTZ NOT NULL,
    forecast_time           TIMESTAMPTZ NOT NULL,
    temperature_2m          DOUBLE,
    relative_humidity_2m    DOUBLE,
    dew_point_2m            DOUBLE,
    surface_pressure        DOUBLE,
    wind_speed_10m          DOUBLE,
    wind_direction_10m      DOUBLE,
    precipitation           DOUBLE,
    cloud_cover             DOUBLE,
    vapour_pressure_deficit DOUBLE,
    pm2_5                   DOUBLE,
    pm10                    DOUBLE,
    carbon_monoxide         DOUBLE,
    nitrogen_dioxide        DOUBLE,
    ozone                   DOUBLE,
    dust                    DOUBLE,
    european_aqi            DOUBLE
)
"""

DEFAULT_ROW = {
    "co2_ppm": 700.0,
    "scd_temp_c": 24.0,
    "scd_humidity_pct": 40.0,
    "bme_temp_c": 24.2,
    "bme_humidity_pct": 41.0,
    "pressure_hpa": 1000.0,
    "gas_resistance_ohm": 102400000.0,
    "mass_pm1_0": 3.0,
    "mass_pm2_5": 4.0,
    "mass_pm4_0": 4.5,
    "mass_pm10": 5.0,
    "number_pm0_5": 10.0,
    "number_pm1_0": 9.0,
    "number_pm2_5": 8.0,
    "number_pm4_0": 7.0,
    "number_pm10": 6.0,
    "typical_size_um": 0.5,
    "sensor_status": "ok",
    "scd41_status": "ok",
    "bme688_status": "ok",
    "sps30_status": "ok",
}


def make_rows(start_ts: datetime, n: int, cadence_seconds: int = 30, overrides: dict[int, dict] | None = None) -> list[dict]:
    """``n`` consecutive rows starting at ``start_ts``, all otherwise-default
    and VALID, with per-index field overrides (e.g. ``{5: {"mass_pm2_5": None}}``)."""
    overrides = overrides or {}
    rows = []
    for i in range(n):
        ts = start_ts + timedelta(seconds=cadence_seconds * i)
        row = dict(DEFAULT_ROW)
        row.update(overrides.get(i, {}))
        row["ts"] = ts
        row["measured_at"] = ts
        row["loaded_at"] = ts
        row["batch_id"] = f"batch-{i // 10}"
        row["row_in_batch"] = i % 10
        rows.append(row)
    return rows


def create_air_monitor_db(path: Path, rows: list[dict]) -> None:
    """(Re)creates raw_observations from scratch -- safe to call more than
    once against the same path (e.g. to simulate two separate scenarios in
    one test)."""
    con = duckdb.connect(str(path))
    con.execute("DROP TABLE IF EXISTS raw_observations")
    con.execute(RAW_OBSERVATIONS_SCHEMA)
    if rows:
        columns = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(columns))
        con.executemany(
            f"INSERT INTO raw_observations ({','.join(columns)}) VALUES ({placeholders})",
            [[row[c] for c in columns] for row in rows],
        )
    con.close()


def create_weather_db(path: Path, rows: list[dict]) -> None:
    """(Re)creates weather_observations from scratch -- see create_air_monitor_db."""
    con = duckdb.connect(str(path))
    con.execute("DROP TABLE IF EXISTS weather_observations")
    con.execute(WEATHER_OBSERVATIONS_SCHEMA)
    if rows:
        columns = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(columns))
        con.executemany(
            f"INSERT INTO weather_observations ({','.join(columns)}) VALUES ({placeholders})",
            [[row[c] for c in columns] for row in rows],
        )
    con.close()


def default_weather_row(forecast_time: datetime, **overrides) -> dict:
    row = {
        "ts": forecast_time,
        "forecast_time": forecast_time,
        "temperature_2m": 20.0,
        "relative_humidity_2m": 55.0,
        "dew_point_2m": 12.0,
        "surface_pressure": 1005.0,
        "wind_speed_10m": 10.0,
        "wind_direction_10m": 180.0,
        "precipitation": 0.0,
        "cloud_cover": 20.0,
        "vapour_pressure_deficit": 0.5,
        "pm2_5": 5.0,
        "pm10": 8.0,
        "carbon_monoxide": 150.0,
        "nitrogen_dioxide": 10.0,
        "ozone": 30.0,
        "dust": 1.0,
        "european_aqi": 20.0,
    }
    row.update(overrides)
    return row
