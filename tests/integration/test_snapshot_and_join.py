from datetime import datetime, timedelta, timezone
from pathlib import Path

from fixtures.build_synthetic_db import create_air_monitor_db, create_weather_db, default_weather_row, make_rows

from iaq_hfis.db import AirMonitorSource, make_snapshot

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


def test_snapshot_opens_independently_of_source(tmp_path, base_settings):
    rows = make_rows(NOW - timedelta(minutes=5), 10)
    db_path = Path(base_settings.paths.air_monitor_db_path)
    create_air_monitor_db(db_path, rows)
    path, retries = make_snapshot(db_path, Path(base_settings.paths.snapshot_dir))
    assert path.exists()
    assert retries == 0


def test_air_monitor_source_reads_raw_window(base_settings):
    rows = make_rows(NOW - timedelta(minutes=10), 20)
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), rows)
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(NOW - timedelta(hours=1))])

    with AirMonitorSource(base_settings) as source:
        columns = source.raw_schema_columns()
        assert "co2_ppm" in columns
        df = source.fetch_raw_window(NOW - timedelta(minutes=10), NOW)
        # fetch_raw_window is (start, end] -- exclusive of the row exactly at start
        assert len(df) == 19


def test_asof_join_never_returns_future_forecast(base_settings):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), make_rows(NOW, 1))
    weather_rows = [
        default_weather_row(NOW - timedelta(hours=2), pm2_5=1.0),
        default_weather_row(NOW - timedelta(hours=1), pm2_5=2.0),
        default_weather_row(NOW + timedelta(hours=1), pm2_5=999.0),  # future row, must never be returned
    ]
    create_weather_db(Path(base_settings.paths.weather_db_path), weather_rows)

    with AirMonitorSource(base_settings) as source:
        result = source.fetch_outdoor_asof(NOW)
        assert result is not None
        assert result["forecast_time"] <= NOW
        assert result["pm2_5"] == 2.0  # the most recent PAST row, never the future one


def test_asof_join_none_when_no_past_data(base_settings):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), make_rows(NOW, 1))
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(NOW + timedelta(hours=1))])

    with AirMonitorSource(base_settings) as source:
        assert source.fetch_outdoor_asof(NOW) is None
