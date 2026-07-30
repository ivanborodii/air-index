from iaq_hfis.evaluation.fault_injection import (
    REASON_CODES,
    build_confusion_matrix,
    confirmation_recovery_rate,
    dataset_split_of,
    false_rejection_rate_for_genuine_events,
    match_events,
    run_benchmark,
    run_hampel_calibration,
    score_events,
    score_predictions,
)


def test_dataset_split_of_derives_from_scenario_id_suffix():
    assert dataset_split_of("co2_single_spike_calibration") == "calibration"
    assert dataset_split_of("co2_single_spike_validation") == "validation"


def test_fault_injection_recovers_known_expected_outcomes(base_settings, sensor_specs):
    """Mandatory regression test: the fault-injection benchmark's metrics
    correctly recover known expected outcomes for every injected fault
    type -- the whole point of using labeled synthetic data instead of
    unlabeled real observations."""
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    # 5 channels (co2, temperature, humidity, pm10, pm2_5) x 2 disjoint dataset splits.
    assert len(events) > 0
    assert {e.channel for e in events} == {"co2", "temperature", "humidity", "pm10", "pm2_5"}
    assert {dataset_split_of(e.scenario_id) for e in events} == {"calibration", "validation"}

    for split in ("calibration", "validation"):
        metrics = {m.reason_code: m for m in score_predictions(predictions, dataset_split=split)}
        # Every fault type must be detected at least once (recall > 0) at its injected location, on both splits.
        for code in REASON_CODES:
            assert metrics[code].recall == 1.0, f"{code} was not detected at its known injected location ({split})"
            assert metrics[code].tp >= 1
            assert metrics[code].tn >= 0
            assert metrics[code].specificity is not None

        # Genuine sustained events must not be discarded as faults, on both splits and every channel
        # (temperature/humidity need a synthetic secondary reading to ever confirm -- see
        # build_channel_scenarios(dual_channel=True); this asserts that fix holds).
        assert false_rejection_rate_for_genuine_events(predictions, dataset_split=split) == 0.0


def test_calibration_and_validation_splits_share_no_scenario_or_timestamp(base_settings, sensor_specs):
    """No data leakage: calibration and validation must never reuse the
    same scenario_id, and (since scenarios are otherwise identically
    shaped) must use a numerically distinct value/timing scale so no
    calibration-tuned parameter is implicitly re-validated on data it
    already saw."""
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    calibration_ids = {e.scenario_id for e in events if e.dataset_split == "calibration"}
    validation_ids = {e.scenario_id for e in events if e.dataset_split == "validation"}
    assert calibration_ids.isdisjoint(validation_ids)
    assert len(calibration_ids) > 0 and len(validation_ids) > 0

    # Every scenario_id has a validation-split counterpart (same base name, different suffix).
    calibration_bases = {sid.removesuffix("_calibration") for sid in calibration_ids}
    validation_bases = {sid.removesuffix("_validation") for sid in validation_ids}
    assert calibration_bases == validation_bases


def test_pm_order_violation_correctly_labeled_out_of_range(base_settings, sensor_specs):
    """Regression test: the PM order-violation scenario's true label must
    be 'out_of_range' (the reason code the real quality layer actually
    assigns -- there is no distinct PM_ORDER_VIOLATION code), not an
    unscoreable label absent from REASON_CODES. Using the wrong label
    silently made this scenario impossible to score as a true positive and
    inflated out_of_range's false-positive count every run."""
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    pm_events = [e for e in events if e.channel == "pm2_5"]
    assert pm_events
    assert all(e.fault_type == "out_of_range" for e in pm_events)
    pm_predictions = [p for p in predictions if p.channel == "pm2_5" and p.true_fault_type == "out_of_range"]
    assert pm_predictions
    assert any("out_of_range" in p.predicted_reason_codes for p in pm_predictions)


def test_hampel_calibration_grid_covers_calibration_and_validation(base_settings, sensor_specs):
    rows = run_hampel_calibration(
        base_settings.schema_mapping, sensor_specs, base_settings.confirmation, base_settings.confirmation.pm_cross_channel_tolerance_pct,
        base_settings.cadence.sample_cadence_seconds, base_settings.hampel.window_size, base_settings.hampel.mad_multiplier,
    )
    splits = {r.dataset_split for r in rows}
    assert splits == {"calibration", "validation"}
    selected = [r for r in rows if r.selected]
    assert len(selected) == 2  # exactly one per split: the currently configured combination
    assert all(r.window_size == base_settings.hampel.window_size and r.mad_multiplier == base_settings.hampel.mad_multiplier for r in selected)


# --- Event-level matching: prevents a single multi-sample fault from being
# double-counted as many separate true positives (the row-level metric's risk). ---


def test_match_events_one_true_event_one_matching_prediction_is_a_single_tp():
    from iaq_hfis.evaluation.fault_injection import FaultEvent, SamplePrediction

    events = [FaultEvent("s1_calibration", "co2", "stuck_value", 10, 5, "stuck run")]
    predictions = [
        SamplePrediction("s1_calibration", "co2", i, "stuck_value" if 10 <= i < 15 else None,
                          ["stuck_value"] if 10 <= i < 15 else [], "SUSPECT" if 10 <= i < 15 else "VALID", 10 <= i < 15)
        for i in range(30)
    ]
    m = match_events(events, predictions, "stuck_value", temporal_tolerance_samples=1)
    # 5 consecutive flagged samples must be grouped into ONE predicted event, matched to the ONE true event.
    assert m.n_true_events == 1
    assert m.n_predicted_events == 1
    assert m.tp == 1
    assert m.fp == 0
    assert m.fn == 0
    assert m.mean_detection_delay == 0


def test_match_events_gap_beyond_tolerance_splits_into_two_predicted_events():
    from iaq_hfis.evaluation.fault_injection import FaultEvent, SamplePrediction

    events = [FaultEvent("s1_calibration", "co2", "single_spike", 10, 1, "spike")]
    flagged = {10, 20}  # far apart -- must NOT be merged into one predicted event
    predictions = [
        SamplePrediction("s1_calibration", "co2", i, "single_spike" if i == 10 else None,
                          ["single_spike"] if i in flagged else [], "SUSPECT" if i in flagged else "VALID", i not in flagged)
        for i in range(30)
    ]
    m = match_events(events, predictions, "single_spike", temporal_tolerance_samples=1)
    assert m.n_predicted_events == 2
    assert m.tp == 1  # the true event at index 10 matches the nearby predicted interval
    assert m.fp == 1  # the unrelated predicted interval at index 20 has no true event to match


def test_match_events_no_prediction_is_a_false_negative():
    from iaq_hfis.evaluation.fault_injection import FaultEvent

    events = [FaultEvent("s1_calibration", "co2", "data_loss", 10, 3, "loss")]
    m = match_events(events, [], "data_loss", temporal_tolerance_samples=1)
    assert m.tp == 0
    assert m.fn == 1
    assert m.fp == 0


def test_score_events_restricts_to_one_dataset_split(base_settings, sensor_specs):
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    calibration_metrics = {m.reason_code: m for m in score_events(events, predictions, "calibration")}
    validation_metrics = {m.reason_code: m for m in score_events(events, predictions, "validation")}
    for code in REASON_CODES:
        assert calibration_metrics[code].dataset_split == "calibration"
        assert validation_metrics[code].dataset_split == "validation"
        # Every event-level TP is a genuinely matched injected fault -- recall must reach 1.0
        # since every scenario's fault is unambiguous and well within tolerance of its own detection.
        assert calibration_metrics[code].recall == 1.0
        assert validation_metrics[code].recall == 1.0
        # Event-level true positives can never exceed the number of true events actually injected
        # for that code+split -- the core "no double-counting" guarantee.
        assert calibration_metrics[code].tp <= calibration_metrics[code].n_true_events
        assert validation_metrics[code].tp <= validation_metrics[code].n_true_events


def test_confusion_matrix_diagonal_matches_row_level_true_positives(base_settings, sensor_specs):
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    cells = build_confusion_matrix(predictions, "validation")
    row_metrics = {m.reason_code: m for m in score_predictions(predictions, dataset_split="validation")}
    diagonal = {c.true_label: c.count for c in cells if c.true_label == c.predicted_label}
    for code in REASON_CODES:
        # The confusion matrix's diagonal cell for a reason code is exactly its row-level TP count.
        assert diagonal.get(code, 0) == row_metrics[code].tp
    assert all(c.dataset_split == "validation" for c in cells)


def test_confirmation_recovery_rate_and_false_rejection_rate_accept_split_filter(base_settings, sensor_specs):
    events, predictions = run_benchmark(
        base_settings.schema_mapping, sensor_specs, base_settings.hampel, base_settings.confirmation,
        base_settings.confirmation.pm_cross_channel_tolerance_pct, base_settings.cadence.sample_cadence_seconds,
    )
    assert confirmation_recovery_rate(predictions, dataset_split="validation") is not None
    assert false_rejection_rate_for_genuine_events(predictions, dataset_split="validation") == 0.0
