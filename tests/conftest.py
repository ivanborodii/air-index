from __future__ import annotations

from pathlib import Path

import pytest

from iaq_hfis.config import load_room_profiles, load_sensor_specs, load_settings

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


@pytest.fixture
def sensor_specs():
    return load_sensor_specs(CONFIG_DIR / "sensor_specs.yaml")


@pytest.fixture
def room_profiles():
    return load_room_profiles(CONFIG_DIR / "room_profiles.yaml")


@pytest.fixture
def base_settings(tmp_path):
    """The real project config, repointed at tmp_path for every generated path."""
    settings = load_settings(CONFIG_DIR / "iaq_hfis.yaml")
    settings.paths.air_monitor_db_path = str(tmp_path / "air_monitor.duckdb")
    settings.paths.weather_db_path = str(tmp_path / "weather.duckdb")
    settings.paths.derived_db_path = str(tmp_path / "derived" / "iaq_hfis.duckdb")
    settings.paths.snapshot_dir = str(tmp_path / "snapshots")
    settings.paths.log_path = str(tmp_path / "logs" / "iaq_hfis.log")
    settings.paths.run_summary_dir = str(tmp_path / "run_summaries")
    return settings
