from iaq_hfis.evaluation.fault_injection import (
    confirmation_recovery_rate,
    false_rejection_rate_for_genuine_events,
    run_benchmark,
    run_hampel_calibration,
    score_predictions,
)


def test_fault_injection_recovers_known_expected_outcomes(base_settings, sensor_specs):
    """Mandatory regression test: the fault-injection benchmark's metrics
    correctly recover known expected outcomes for every injected fault
    type -- the whole point of using labeled synthetic data instead of
    unlabeled real observations."""
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    assert len(events) == 8
    metrics = {m.reason_code: m for m in score_predictions(predictions)}

    # Every fault type must be detected at least once (recall > 0) at the injected location.
    for code in ("single_spike", "stuck_value", "data_loss", "gradual_drift", "out_of_range"):
        assert metrics[code].recall == 1.0, f"{code} was not detected at its known injected location"
        assert metrics[code].tp >= 1

    # Genuine sustained events must not be discarded as faults.
    assert false_rejection_rate_for_genuine_events(predictions) == 0.0
    assert confirmation_recovery_rate(predictions) == 1.0


def test_pm_order_violation_detected(base_settings, sensor_specs):
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    pm_predictions = [p for p in predictions if p.scenario_id == "pm2_5_order_violation"]
    assert any(p.true_fault_type == "pm_order_violation" and "out_of_range" in p.predicted_reason_codes for p in pm_predictions)


def test_hampel_calibration_grid_covers_dev_and_holdout(base_settings, sensor_specs):
    rows = run_hampel_calibration(
        base_settings.schema_mapping, sensor_specs, base_settings.confirmation, base_settings.confirmation.pm_cross_channel_tolerance_pct,
        base_settings.cadence.sample_cadence_seconds, base_settings.hampel.window_size, base_settings.hampel.mad_multiplier,
    )
    splits = {r.dataset_split for r in rows}
    assert splits == {"development", "holdout"}
    selected = [r for r in rows if r.selected]
    assert len(selected) == 2  # exactly one per split: the currently configured combination
    assert all(r.window_size == base_settings.hampel.window_size and r.mad_multiplier == base_settings.hampel.mad_multiplier for r in selected)
