from iaq_hfis.evaluation.fault_injection import HampelCalibrationRow
from iaq_hfis.reporting.parameter_selection import SYNTHETIC_CALIBRATION_DISCLAIMER, build_parameter_selection_artifact

ROWS = [
    HampelCalibrationRow(dataset_split="calibration", window_size=7, mad_multiplier=1.0, fault_recall=0.8, genuine_event_preservation_rate=0.9, objective_score=0.85, selected=False),
    HampelCalibrationRow(dataset_split="calibration", window_size=11, mad_multiplier=1.0, fault_recall=0.7, genuine_event_preservation_rate=0.95, objective_score=0.90, selected=True),
    HampelCalibrationRow(dataset_split="validation", window_size=11, mad_multiplier=1.0, fault_recall=0.65, genuine_event_preservation_rate=0.93, objective_score=0.88, selected=True),
]


def test_candidate_grid_reflects_real_hampel_grid():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    assert 11 in artifact["candidate_grid"]["window_size"]
    assert 1.0 in artifact["candidate_grid"]["mad_multiplier"]
    assert artifact["candidate_grid"]["n_combinations"] == len(artifact["candidate_grid"]["window_size"]) * len(artifact["candidate_grid"]["mad_multiplier"])


def test_selected_parameters_are_literature_informed_not_calibrated():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    assert artifact["selected_parameters"] == {"window_size": 11, "mad_multiplier": 1.0, "status": "LITERATURE_INFORMED"}
    assert "NOT selected from this calibration grid" in artifact["selection_rationale"]


def test_best_calibration_result_is_the_max_objective_on_calibration_split():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    assert artifact["best_calibration_split_result"] == {"window_size": 11, "mad_multiplier": 1.0, "objective_score": 0.90}


def test_validation_metrics_are_for_the_configured_value_only():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    vm = artifact["validation_split_metrics_for_configured_value"]
    assert vm["window_size"] == 11 and vm["objective_score"] == 0.88


def test_missing_validation_row_for_configured_value_is_none_not_fabricated():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=15, current_mad_multiplier=3.0, config_hash="abc123")
    assert artifact["validation_split_metrics_for_configured_value"] is None


def test_disclaimer_present_verbatim():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    assert artifact["synthetic_calibration_disclaimer"] == SYNTHETIC_CALIBRATION_DISCLAIMER
    assert "does not equal validation on manually labelled real faults" in SYNTHETIC_CALIBRATION_DISCLAIMER


def test_config_hash_recorded_verbatim():
    artifact = build_parameter_selection_artifact(ROWS, current_window_size=11, current_mad_multiplier=1.0, config_hash="the-real-hash")
    assert artifact["frozen_effective_config_hash"] == "the-real-hash"


def test_empty_rows_gives_none_results_not_crash():
    artifact = build_parameter_selection_artifact([], current_window_size=11, current_mad_multiplier=1.0, config_hash="abc123")
    assert artifact["best_calibration_split_result"] is None
    assert artifact["validation_split_metrics_for_configured_value"] is None
