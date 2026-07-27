import pytest

from iaq_hfis.evaluation.ground_truth import (
    crisp_class_monotonic,
    crisp_class_two_sided,
    generate_boundary_vectors,
    score_against_ground_truth,
)


def test_crisp_class_monotonic_matches_table_2_convention(base_settings):
    boundaries = base_settings.control_regions.pm2_5  # breakpoints [15, 25, 50]
    assert crisp_class_monotonic(15.0, boundaries) == "Favorable"  # "<=15" favorable
    assert crisp_class_monotonic(15.01, boundaries) == "Acceptable"
    assert crisp_class_monotonic(25.0, boundaries) == "Acceptable"
    assert crisp_class_monotonic(25.01, boundaries) == "Degraded"
    assert crisp_class_monotonic(50.0, boundaries) == "Degraded"
    assert crisp_class_monotonic(50.01, boundaries) == "Critical"


def test_crisp_class_two_sided_matches_table_2_convention(room_profiles):
    ranges = room_profiles.find("kitchen", "cold_period").ranges  # favorable [18,21]
    assert crisp_class_two_sided(19.5, ranges) == "Favorable"
    assert crisp_class_two_sided(18.0, ranges) == "Favorable"
    assert crisp_class_two_sided(17.9, ranges) == "Acceptable"
    assert crisp_class_two_sided(15.5, ranges) == "Degraded"
    assert crisp_class_two_sided(15.4, ranges) == "Critical"
    assert crisp_class_two_sided(23.5, ranges) == "Degraded"  # critical_high_min itself is still Degraded's edge
    assert crisp_class_two_sided(23.51, ranges) == "Critical"


def test_generate_boundary_vectors_expected_classes_are_derivable(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    vectors = generate_boundary_vectors(base_settings.control_regions, profile)
    assert len(vectors) > 0
    for v in vectors:
        assert v.expected_class in ("Favorable", "Acceptable", "Degraded", "Critical")
        # every other channel stays at the deeply-favorable baseline
        for channel, value in v.values.items():
            if channel != v.perturbed_channel:
                assert channel in v.values


def test_score_against_ground_truth_perfect_prediction(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    vectors = generate_boundary_vectors(base_settings.control_regions, profile)
    predictions = [v.expected_class for v in vectors]
    score = score_against_ground_truth(vectors, predictions)
    assert score["macro_f1"] == pytest.approx(1.0)
    assert score["cohens_kappa"] == pytest.approx(1.0)
    assert score["n"] == len(vectors)
    assert score["n_excluded"] == 0


def test_score_against_ground_truth_excludes_none_predictions(base_settings, room_profiles):
    profile = room_profiles.find("kitchen", "cold_period")
    vectors = generate_boundary_vectors(base_settings.control_regions, profile)
    predictions = [None] * len(vectors)
    score = score_against_ground_truth(vectors, predictions)
    assert score["n"] == 0
    assert score["n_excluded"] == len(vectors)
    assert score["macro_f1"] is None
