import pytest

from iaq_hfis.schema import (
    MembershipConfigError,
    SchemaMappingError,
    validate_membership_config,
    validate_room_profile_widths,
    validate_schema_mapping,
)


def test_schema_mapping_ok_against_real_columns(base_settings):
    real_columns = set(base_settings.schema_mapping.required_raw_columns)
    validate_schema_mapping(base_settings.schema_mapping, real_columns)  # no raise


def test_schema_mapping_reports_missing_columns(base_settings):
    incomplete = set(base_settings.schema_mapping.required_raw_columns) - {"co2_ppm", "sps30_status"}
    with pytest.raises(SchemaMappingError) as exc_info:
        validate_schema_mapping(base_settings.schema_mapping, incomplete)
    msg = str(exc_info.value)
    assert "co2_ppm" in msg and "sps30_status" in msg


def test_narrow_transition_width_rejected(base_settings, sensor_specs):
    base_settings.control_regions.pm2_5.transition_widths = [0.01, 0.01, 0.01]
    with pytest.raises(MembershipConfigError):
        validate_membership_config(base_settings.control_regions, base_settings.schema_mapping, sensor_specs, "reject")


def test_narrow_transition_width_auto_expanded_and_reported(base_settings, sensor_specs):
    base_settings.control_regions.pm2_5.transition_widths = [0.01, 0.01, 0.01]
    report = validate_membership_config(base_settings.control_regions, base_settings.schema_mapping, sensor_specs, "auto_expand")
    assert report.violations == []
    assert len(report.adjustments) == 3
    expected_min = sensor_specs.channels["pm_mass_fine"].declared_uncertainty  # pm2_5 -> mass_pm2_5 -> pm_mass_fine
    assert report.effective_monotonic_widths["pm2_5"] == [expected_min] * 3


def test_wide_transition_width_not_flagged(base_settings, sensor_specs):
    report = validate_membership_config(base_settings.control_regions, base_settings.schema_mapping, sensor_specs, "reject")
    assert report.violations == []


def test_room_profile_widths_validated_independently(base_settings, sensor_specs, room_profiles):
    for profile in room_profiles.profiles:
        profile.ranges.transition_width = 0.001
    with pytest.raises(MembershipConfigError):
        validate_room_profile_widths(room_profiles, base_settings.schema_mapping, sensor_specs, "reject")
