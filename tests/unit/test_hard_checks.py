from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from iaq_hfis.constants import QualityState
from iaq_hfis.quality.hard_checks import (
    check_numeric_format,
    check_pm_ordering,
    check_technical_range,
    run_hard_checks,
)

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("value,expected", [(1.0, True), (0, True), (None, False), (float("nan"), False), (float("inf"), False), (float("-inf"), False), ("not a number", False)])
def test_check_numeric_format(value, expected):
    assert check_numeric_format(value) is expected


def test_check_technical_range():
    from iaq_hfis.config import ChannelTechnicalRange

    spec = ChannelTechnicalRange(min=0, max=1000, unit="ppm", source="x", declared_uncertainty=1)
    assert check_technical_range(500, spec) is True
    assert check_technical_range(-1, spec) is False
    assert check_technical_range(1001, spec) is False


def test_pm_ordering_violation_detected_with_tolerance():
    assert check_pm_ordering(1, 2, 3, 4, tolerance_pct=10) is True
    assert check_pm_ordering(10, 2, 3, 4, tolerance_pct=10) is False  # pm1 grossly > pm2.5
    assert check_pm_ordering(2.05, 2.0, 3.0, 4.0, tolerance_pct=10) is True  # within tolerance
    assert check_pm_ordering(None, 2.0, 3.0, 4.0, tolerance_pct=10) is True  # missing value -> not this check's job


def _hard_checks_for_channel(sensor_specs, channel, source_column, device_status_column, matched_slots, raw_df, status_map, tol=20.0):
    from iaq_hfis.config import ChannelMapEntry

    channel_map = ChannelMapEntry(canonical_name=channel, source_column=source_column, device_status_column=device_status_column)
    return run_hard_checks(raw_df, matched_slots, channel, channel_map, sensor_specs, status_map, pm_ordering_tolerance_pct=tol)


def test_missing_record_becomes_missing(sensor_specs, base_settings):
    slots = [NOW, NOW + timedelta(seconds=30)]
    matched = {slots[0]: None, slots[1]: None}
    raw_df = pd.DataFrame(columns=["ts", "co2_ppm", "scd41_status"])
    result = _hard_checks_for_channel(sensor_specs, "co2", "co2_ppm", "scd41_status", matched, raw_df, base_settings.device_status_state_map)
    assert (result["stage1_state"] == QualityState.MISSING.value).all()


def test_nonnumeric_and_infinite_become_invalid(sensor_specs, base_settings):
    slots = [NOW, NOW + timedelta(seconds=30)]
    raw_df = pd.DataFrame({"ts": slots, "co2_ppm": [float("inf"), "garbage"], "scd41_status": ["ok", "ok"]})
    matched = {slots[0]: slots[0], slots[1]: slots[1]}
    result = _hard_checks_for_channel(sensor_specs, "co2", "co2_ppm", "scd41_status", matched, raw_df, base_settings.device_status_state_map)
    assert (result["stage1_state"] == QualityState.INVALID.value).all()


def test_technical_range_failure_becomes_invalid(sensor_specs, base_settings):
    slots = [NOW]
    raw_df = pd.DataFrame({"ts": slots, "co2_ppm": [999999.0], "scd41_status": ["ok"]})
    matched = {slots[0]: slots[0]}
    result = _hard_checks_for_channel(sensor_specs, "co2", "co2_ppm", "scd41_status", matched, raw_df, base_settings.device_status_state_map)
    assert result.iloc[0]["stage1_state"] == QualityState.INVALID.value


def test_device_status_failed_overrides_to_invalid(sensor_specs, base_settings):
    slots = [NOW]
    raw_df = pd.DataFrame({"ts": slots, "co2_ppm": [700.0], "scd41_status": ["failed"]})
    matched = {slots[0]: slots[0]}
    result = _hard_checks_for_channel(sensor_specs, "co2", "co2_ppm", "scd41_status", matched, raw_df, base_settings.device_status_state_map)
    assert result.iloc[0]["stage1_state"] == QualityState.INVALID.value


def test_device_status_disabled_overrides_to_missing(sensor_specs, base_settings):
    slots = [NOW]
    raw_df = pd.DataFrame({"ts": slots, "co2_ppm": [700.0], "scd41_status": ["disabled"]})
    matched = {slots[0]: slots[0]}
    result = _hard_checks_for_channel(sensor_specs, "co2", "co2_ppm", "scd41_status", matched, raw_df, base_settings.device_status_state_map)
    assert result.iloc[0]["stage1_state"] == QualityState.MISSING.value


def test_valid_reading_passes(sensor_specs, base_settings):
    slots = [NOW]
    raw_df = pd.DataFrame(
        {
            "ts": slots,
            "mass_pm2_5": [4.0],
            "mass_pm1_0": [3.0],
            "mass_pm4_0": [4.5],
            "mass_pm10": [5.0],
            "sps30_status": ["ok"],
        }
    )
    matched = {slots[0]: slots[0]}
    result = _hard_checks_for_channel(sensor_specs, "pm2_5", "mass_pm2_5", "sps30_status", matched, raw_df, base_settings.device_status_state_map)
    assert result.iloc[0]["stage1_state"] == QualityState.VALID.value
    assert result.iloc[0]["raw_value"] == 4.0


def test_pm_ordering_violation_flags_invalid(sensor_specs, base_settings):
    slots = [NOW]
    raw_df = pd.DataFrame(
        {
            "ts": slots,
            "mass_pm2_5": [4.0],
            "mass_pm1_0": [50.0],  # PM1 grossly exceeds PM2.5 -- physically inconsistent
            "mass_pm4_0": [4.5],
            "mass_pm10": [5.0],
            "sps30_status": ["ok"],
        }
    )
    matched = {slots[0]: slots[0]}
    result = _hard_checks_for_channel(sensor_specs, "pm2_5", "mass_pm2_5", "sps30_status", matched, raw_df, base_settings.device_status_state_map)
    assert result.iloc[0]["stage1_state"] == QualityState.INVALID.value
    assert "out_of_range" in result.iloc[0]["reason_codes"]


def test_raw_dataframe_never_modified(sensor_specs, base_settings):
    slots = [NOW]
    raw_df = pd.DataFrame({"ts": slots, "co2_ppm": [700.0], "scd41_status": ["ok"]})
    original = raw_df.copy(deep=True)
    _hard_checks_for_channel(sensor_specs, "co2", "co2_ppm", "scd41_status", {slots[0]: slots[0]}, raw_df, base_settings.device_status_state_map)
    pd.testing.assert_frame_equal(raw_df, original)
