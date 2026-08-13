import pytest

from iaq_hfis.evaluation.fault_injection import HampelCalibrationRow
from iaq_hfis.reporting.parameter_selection import SYNTHETIC_CALIBRATION_DISCLAIMER, build_parameter_selection_artifact


def _row(split, window_size, mad_multiplier, recall, preservation, fpr, objective):
    return HampelCalibrationRow(split, window_size, mad_multiplier, recall, preservation, fpr, objective, False)


ROWS = [
    # window_size=7 rows must be ignored by selection (only window_size=11 is the main comparison).
    _row("calibration", 7, 1.0, 0.8, 0.9, 0.3, 0.80),
    # window_size=11, calibration split: h=3.0 has the highest objective_score.
    _row("calibration", 11, 1.0, 1.0, 1.0, 0.20, 0.933),
    _row("calibration", 11, 2.0, 1.0, 1.0, 0.05, 0.983),
    _row("calibration", 11, 3.0, 1.0, 1.0, 0.02, 0.993),
    # validation split for the same three multipliers.
    _row("validation", 11, 1.0, 0.9, 0.95, 0.25, 0.867),
    _row("validation", 11, 2.0, 0.9, 0.95, 0.10, 0.917),
    _row("validation", 11, 3.0, 0.95, 0.98, 0.03, 0.967),
]


def test_candidate_grid_reflects_real_hampel_grid():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
    assert 11 in artifact["candidate_grid"]["window_size"]
    assert 1.0 in artifact["candidate_grid"]["mad_multiplier"]
    assert artifact["candidate_grid"]["n_combinations"] == len(artifact["candidate_grid"]["window_size"]) * len(artifact["candidate_grid"]["mad_multiplier"])


def test_selected_multiplier_is_the_best_calibration_objective_at_window_11():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
    assert artifact["selected_parameters"] == {
        "window_size": 11,
        "mad_multiplier": 3.0,
        "window_size_status": "LITERATURE_INFORMED",
        "mad_multiplier_status": "CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT",
    }
    assert "calibration split" in artifact["selection_rationale"]


def test_configured_value_matches_selection_flag():
    matching = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
    assert matching["configured_value_matches_selection"] is True
    mismatched = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    assert mismatched["configured_value_matches_selection"] is False


def test_calibration_split_results_only_cover_window_11_selection_grid():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
    results = artifact["calibration_split_results"]
    assert {r["mad_multiplier"] for r in results} == {1.0, 2.0, 3.0}
    assert all(r["window_size"] == 11 for r in results)


def test_validation_metrics_are_for_the_selected_value_never_used_to_pick_it():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
    vm = artifact["validation_split_metrics_for_selected_value"]
    assert vm["window_size"] == 11 and vm["mad_multiplier"] == 3.0
    assert vm["objective_score"] == 0.967


def test_disclaimer_present_verbatim():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
    assert artifact["synthetic_calibration_disclaimer"] == SYNTHETIC_CALIBRATION_DISCLAIMER
    assert "does not equal validation on manually labelled real faults" in SYNTHETIC_CALIBRATION_DISCLAIMER


def test_config_hash_recorded_verbatim():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=3.0, config_hash="the-real-hash")
    assert artifact["frozen_effective_config_hash"] == "the-real-hash"


def test_empty_rows_raises_rather_than_fabricating_a_selection():
    with pytest.raises(ValueError, match="no calibration-split rows found"):
        build_parameter_selection_artifact([], current_window_size=11, current_mad_multiplier=3.0, config_hash="abc123")
