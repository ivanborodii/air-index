"""Regression tests for exploratory-mode support in the evaluation suite
(reference cases, multi-point stability boundary targets, continuity) --
none of these must ever dereference a None room profile, and none must
fabricate the microclimate component when no DBN profile exists."""

from datetime import datetime, timezone

from iaq_hfis import profiles
from iaq_hfis.evaluation.continuity import _context_values, enumerate_boundaries, sweep_boundary
from iaq_hfis.evaluation.multi_point_stability import boundary_targets
from iaq_hfis.evaluation.reference_cases import generate_reference_cases
from iaq_hfis.pipeline import build_runtime_context

RAW_COLUMNS = {
    "ts", "co2_ppm", "scd_temp_c", "scd_humidity_pct", "bme_temp_c", "bme_humidity_pct",
    "mass_pm1_0", "mass_pm2_5", "mass_pm4_0", "mass_pm10", "number_pm0_5", "number_pm1_0",
    "number_pm2_5", "number_pm4_0", "number_pm10", "typical_size_um",
    "sensor_status", "scd41_status", "bme688_status", "sps30_status",
}


def test_generate_reference_cases_with_no_profile_omits_temperature(base_settings):
    cases = generate_reference_cases(base_settings.control_regions, None)
    assert cases  # pm2_5/pm10/co2/humidity cases still generated
    assert not any(c.perturbed_channel == "temperature" for c in cases)
    assert any(c.perturbed_channel == "humidity" for c in cases)
    assert all("temperature" not in c.values for c in cases)


def test_generate_reference_cases_with_profile_includes_temperature(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    cases = generate_reference_cases(base_settings.control_regions, profile)
    assert any(c.perturbed_channel == "temperature" for c in cases)


def test_boundary_targets_with_no_profile_omits_temperature(base_settings):
    targets = boundary_targets(base_settings.control_regions, None)
    assert "temperature" not in targets
    assert "humidity" in targets and "pm2_5" in targets


def test_boundary_targets_with_profile_includes_temperature(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    targets = boundary_targets(base_settings.control_regions, profile)
    assert "temperature" in targets


def test_context_values_with_no_profile_omits_temperature(base_settings):
    values = _context_values(base_settings.control_regions, None, "favorable")
    assert "temperature" not in values
    assert "humidity" in values


def test_sweep_boundary_with_no_fallback_profile_never_crashes_on_non_temperature_boundary(base_settings, sensor_specs, room_profiles):
    ctx = build_runtime_context(base_settings, sensor_specs, room_profiles, RAW_COLUMNS)
    boundaries = enumerate_boundaries(base_settings.control_regions, room_profiles)
    pm25_boundary = next(b for b in boundaries if b.channel == "pm2_5")
    points = sweep_boundary(ctx, base_settings.control_regions, room_profiles, None, pm25_boundary, "favorable", 5)
    assert points
    assert all(p.method in ("PROPOSED_HFIS", "FUZZY_COMPONENT_MAX", "CRISP_CLASS_MAX", "WEIGHTED_MEAN") for p in points)
    # Never fabricates M: PROPOSED_HFIS rows here come from a 2-component (A, V) inference.
    hfis_points = [p for p in points if p.method == "PROPOSED_HFIS"]
    assert all(p.index_value is not None for p in hfis_points)  # A+V alone still produce a PARTIAL-equivalent result


def test_sweep_boundary_temperature_boundary_unaffected_by_missing_fallback(base_settings, sensor_specs, room_profiles):
    # Temperature boundaries always carry their OWN specific, real profile (from
    # enumerate_boundaries), so a None fallback_profile must not affect them at all.
    ctx = build_runtime_context(base_settings, sensor_specs, room_profiles, RAW_COLUMNS)
    boundaries = enumerate_boundaries(base_settings.control_regions, room_profiles)
    temp_boundary = next(b for b in boundaries if b.channel == "temperature" and b.room == "kitchen" and b.season == "cold_period")
    points_with_fallback = sweep_boundary(ctx, base_settings.control_regions, room_profiles, None, temp_boundary, "favorable", 5)
    profile = room_profiles.find("kitchen", "cold_period")
    points_with_real_fallback = sweep_boundary(ctx, base_settings.control_regions, room_profiles, profile, temp_boundary, "favorable", 5)
    assert [p.index_value for p in points_with_fallback] == [p.index_value for p in points_with_real_fallback]
