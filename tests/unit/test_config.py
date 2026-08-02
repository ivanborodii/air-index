import pytest

from iaq_hfis.config import (
    ChannelTechnicalRange,
    ClassBoundaries,
    ConfigError,
    Settings,
    load_room_profiles,
    load_sensor_specs,
    load_settings,
)
from conftest import CONFIG_DIR


def test_valid_config_loads():
    settings = load_settings(CONFIG_DIR / "iaq_hfis.yaml")
    assert settings.cadence.aggregation_window_minutes == 15
    assert settings.coverage.min_ratio == 0.80


def test_missing_required_settings_fail_clearly(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("paths:\n  air_monitor_db_path: x\n")  # missing everything else
    with pytest.raises(ConfigError) as exc_info:
        load_settings(bad)
    msg = str(exc_info.value)
    assert "cadence" in msg  # field-path-annotated, not a raw traceback dump


def test_config_file_not_found(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "does_not_exist.yaml")


def test_unknown_key_rejected(tmp_path):
    import shutil

    good = CONFIG_DIR / "iaq_hfis.yaml"
    text = good.read_text() + "\nnot_a_real_key: 123\n"
    bad = tmp_path / "bad.yaml"
    bad.write_text(text)
    with pytest.raises(ConfigError):
        load_settings(bad)


def test_incompatible_class_boundaries_fail():
    with pytest.raises(Exception):
        ClassBoundaries(breakpoints=[50, 25, 15], transition_widths=[2, 2, 2])


def test_boundaries_must_be_positive_width():
    with pytest.raises(Exception):
        ClassBoundaries(breakpoints=[15, 25, 50], transition_widths=[2, 0, 2])


def test_technical_range_min_lt_max():
    with pytest.raises(Exception):
        ChannelTechnicalRange(min=100, max=50, unit="ppm", source="x", declared_uncertainty=1.0)


def test_schema_mapping_rejects_carbon_monoxide_as_co2(tmp_path):
    good = CONFIG_DIR / "iaq_hfis.yaml"
    text = good.read_text().replace("source_column: co2_ppm", "source_column: carbon_monoxide")
    bad = tmp_path / "bad.yaml"
    bad.write_text(text)
    with pytest.raises(ConfigError) as exc_info:
        load_settings(bad)
    assert "carbon_monoxide" in str(exc_info.value)


def test_cadence_window_must_be_in_allowed_list():
    from iaq_hfis.config import CadenceConfig

    with pytest.raises(Exception):
        CadenceConfig(aggregation_window_minutes=17, allowed_window_minutes=[5, 15, 30, 60])


def test_sensor_specs_and_room_profiles_load():
    specs = load_sensor_specs(CONFIG_DIR / "sensor_specs.yaml")
    assert "co2" in specs.channels
    profiles = load_room_profiles(CONFIG_DIR / "room_profiles.yaml")
    kitchen_cold = profiles.find("kitchen", "cold_period")
    assert kitchen_cold is not None and kitchen_cold.provisional is False  # real manuscript/DBN profile
    # DBN Table D.4 has no room-specific value for a standalone kitchen in the warm
    # period (literal dash in the table), so this profile is sourced instead to
    # DSTU B EN 15251:2011 Table A.2 (a substitute standard, per the manuscript's
    # own stated fallback rule) -- never a silent reuse of general_residential/
    # warm_period's numbers, which come from a different DBN row.
    kitchen_warm = profiles.find("kitchen", "warm_period")
    assert kitchen_warm is not None and kitchen_warm.provisional is False
    assert profiles.find("general_residential", "cold_period") is None  # still genuinely missing
