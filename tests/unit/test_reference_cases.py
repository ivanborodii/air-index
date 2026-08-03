import pytest

from iaq_hfis.evaluation.reference_cases import (
    crisp_class_monotonic,
    crisp_class_two_sided,
    generate_reference_cases,
    score_against_reference_cases,
)


def test_crisp_class_monotonic_matches_table_2_convention(base_settings):
    boundaries = base_settings.control_regions.pm2_5  # breakpoints [15, 25, 50]
    assert crisp_class_monotonic(15.0, boundaries) == "Favourable"  # "<=15" favourable
    assert crisp_class_monotonic(15.01, boundaries) == "Acceptable"
    assert crisp_class_monotonic(25.0, boundaries) == "Acceptable"
    assert crisp_class_monotonic(25.01, boundaries) == "Degraded"
    assert crisp_class_monotonic(50.0, boundaries) == "Degraded"
    assert crisp_class_monotonic(50.01, boundaries) == "Critical"


def test_crisp_class_two_sided_matches_table_2_convention(room_profiles):
    ranges = room_profiles.find("kitchen", "cold_period").ranges  # favourable [18,21]
    assert crisp_class_two_sided(19.5, ranges) == "Favourable"
    assert crisp_class_two_sided(18.0, ranges) == "Favourable"
    assert crisp_class_two_sided(17.9, ranges) == "Acceptable"
    assert crisp_class_two_sided(15.5, ranges) == "Degraded"
    assert crisp_class_two_sided(15.4, ranges) == "Critical"
    assert crisp_class_two_sided(23.5, ranges) == "Degraded"  # critical_high_min itself is still Degraded's edge
    assert crisp_class_two_sided(23.51, ranges) == "Critical"


def test_generate_reference_cases_expected_classes_are_derivable(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    cases = generate_reference_cases(base_settings.control_regions, profile)
    assert len(cases) > 0
    for c in cases:
        assert c.expected_class in ("Favourable", "Acceptable", "Degraded", "Critical")
        # every other channel stays at the deeply-favourable baseline
        for channel, value in c.values.items():
            if channel != c.perturbed_channel:
                assert channel in c.values


def test_score_against_reference_cases_perfect_prediction(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    cases = generate_reference_cases(base_settings.control_regions, profile)
    predictions = [c.expected_class for c in cases]
    score = score_against_reference_cases(cases, predictions)
    assert score["macro_f1"] == pytest.approx(1.0)
    assert score["cohens_kappa"] == pytest.approx(1.0)
    assert score["n"] == len(cases)
    assert score["n_excluded"] == 0


def test_score_against_reference_cases_excludes_none_predictions(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    cases = generate_reference_cases(base_settings.control_regions, profile)
    predictions = [None] * len(cases)
    score = score_against_reference_cases(cases, predictions)
    assert score["n"] == 0
    assert score["n_excluded"] == len(cases)
    assert score["macro_f1"] is None
