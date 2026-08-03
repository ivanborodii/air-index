from iaq_hfis.evaluation.stability import channel_uncertainty, run_stability_analysis
from iaq_hfis.pipeline import build_runtime_context
from iaq_hfis.profiles import select_room_season
from datetime import datetime, timezone


def _build_ctx(settings, sensor_specs, room_profiles):
    actual_columns = set(settings.schema_mapping.required_raw_columns)
    return build_runtime_context(settings, sensor_specs, room_profiles, actual_columns)


def test_channel_uncertainty_matches_sensor_specs(base_settings, sensor_specs):
    u = channel_uncertainty("co2", base_settings.schema_mapping, sensor_specs)
    assert u == sensor_specs.channels["co2"].declared_uncertainty
    assert u > 0


def test_fixed_seed_gives_byte_identical_repeated_results(base_settings, sensor_specs, room_profiles):
    ctx = _build_ctx(base_settings, sensor_specs, room_profiles)
    profile = select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    weighted_means = {"pm2_5": 5.0, "pm10": 10.0, "co2": 700.0, "temperature": 19.5, "humidity": 40.0}
    available = {"A", "V", "M"}

    r1 = run_stability_analysis(ctx, weighted_means, available, profile, seed=42, n_trials=20)
    r2 = run_stability_analysis(ctx, weighted_means, available, profile, seed=42, n_trials=20)

    assert r1.trial_classes == r2.trial_classes
    assert r1.class_change_rate == r2.class_change_rate
    assert r1.baseline_class == r2.baseline_class


def test_different_seeds_can_give_different_trial_sequences(base_settings, sensor_specs, room_profiles):
    ctx = _build_ctx(base_settings, sensor_specs, room_profiles)
    profile = select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    # Values placed exactly at a boundary so perturbation can plausibly flip class.
    weighted_means = {"pm2_5": 15.0, "pm10": 10.0, "co2": 700.0, "temperature": 19.5, "humidity": 40.0}
    available = {"A", "V", "M"}

    r1 = run_stability_analysis(ctx, weighted_means, available, profile, seed=1, n_trials=20)
    r2 = run_stability_analysis(ctx, weighted_means, available, profile, seed=2, n_trials=20)
    assert r1.trial_classes != r2.trial_classes  # different seeds explore different perturbations


def test_stability_deep_in_favorable_band_has_zero_class_change(base_settings, sensor_specs, room_profiles):
    ctx = _build_ctx(base_settings, sensor_specs, room_profiles)
    profile = select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    # Values far from any boundary, well beyond declared uncertainty in every direction.
    weighted_means = {"pm2_5": 2.0, "pm10": 5.0, "co2": 500.0, "temperature": 19.5, "humidity": 40.0}
    available = {"A", "V", "M"}

    result = run_stability_analysis(ctx, weighted_means, available, profile, seed=42, n_trials=30)
    assert result.class_change_rate == 0.0
    assert result.baseline_class == "Favourable"
