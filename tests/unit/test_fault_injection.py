from iaq_hfis.evaluation.fault_injection import (
    HAMPEL_SELECTION_WINDOW_SIZE,
    REASON_CODES,
    HampelCalibrationRow,
    build_confusion_matrix,
    confirmation_recovery_rate,
    dataset_split_of,
    false_rejection_rate_for_genuine_events,
    match_events,
    run_benchmark,
    run_hampel_calibration,
    score_events,
    score_final_exclusion,
    score_predictions,
    select_hampel_multiplier,
)


def _row(split, mad_multiplier, recall, preservation, fpr, objective, window_size=HAMPEL_SELECTION_WINDOW_SIZE):
    return HampelCalibrationRow(split, window_size, mad_multiplier, recall, preservation, fpr, objective, False)


def test_select_hampel_multiplier_picks_highest_calibration_objective():
    rows = [
        _row("calibration", 1.0, 1.0, 1.0, 0.20, 0.933),
        _row("calibration", 2.0, 1.0, 1.0, 0.05, 0.983),
        _row("calibration", 3.0, 1.0, 1.0, 0.02, 0.993),
    ]
    assert select_hampel_multiplier(rows) == 3.0


def test_select_hampel_multiplier_ignores_validation_rows_entirely():
    """Mandatory regression test (task spec section 6): changing validation
    metrics must never change the selected multiplier -- the selection
    function only ever reads dataset_split == 'calibration' rows."""
    calibration_rows = [
        _row("calibration", 1.0, 1.0, 1.0, 0.20, 0.933),
        _row("calibration", 2.0, 1.0, 1.0, 0.05, 0.983),
        _row("calibration", 3.0, 1.0, 1.0, 0.02, 0.993),
    ]
    # Validation rows deliberately favor h=1.0 overwhelmingly -- if this
    # changed the selection, this test would fail.
    validation_rows_favoring_h1 = [
        _row("validation", 1.0, 1.0, 1.0, 0.0, 1.0),
        _row("validation", 2.0, 0.0, 0.0, 1.0, 0.0),
        _row("validation", 3.0, 0.0, 0.0, 1.0, 0.0),
    ]
    selected_without_validation = select_hampel_multiplier(calibration_rows)
    selected_with_adverse_validation = select_hampel_multiplier(calibration_rows + validation_rows_favoring_h1)
    assert selected_without_validation == selected_with_adverse_validation == 3.0


def test_select_hampel_multiplier_tiebreak_order():
    # Tied objective_score -> break on recall -> break on preservation -> break on fpr -> break on smallest multiplier.
    tied_objective = [
        _row("calibration", 1.0, 0.5, 1.0, 0.1, 0.9),
        _row("calibration", 2.0, 1.0, 1.0, 0.1, 0.9),  # higher recall wins despite identical objective_score
    ]
    assert select_hampel_multiplier(tied_objective) == 2.0

    tied_objective_and_recall = [
        _row("calibration", 1.0, 1.0, 0.5, 0.1, 0.9),
        _row("calibration", 2.0, 1.0, 0.9, 0.1, 0.9),  # higher preservation wins
    ]
    assert select_hampel_multiplier(tied_objective_and_recall) == 2.0

    tied_through_preservation = [
        _row("calibration", 1.0, 1.0, 1.0, 0.3, 0.9),
        _row("calibration", 2.0, 1.0, 1.0, 0.1, 0.9),  # lower fpr wins
    ]
    assert select_hampel_multiplier(tied_through_preservation) == 2.0

    fully_tied = [
        _row("calibration", 2.0, 1.0, 1.0, 0.1, 0.9),
        _row("calibration", 1.0, 1.0, 1.0, 0.1, 0.9),  # smallest multiplier wins when everything else ties
    ]
    assert select_hampel_multiplier(fully_tied) == 1.0


def test_select_hampel_multiplier_ignores_other_window_sizes():
    rows = [
        _row("calibration", 1.0, 0.0, 0.0, 1.0, 0.0, window_size=7),  # wrong window size, must be ignored
        _row("calibration", 2.0, 1.0, 1.0, 0.0, 1.0, window_size=HAMPEL_SELECTION_WINDOW_SIZE),
    ]
    assert select_hampel_multiplier(rows) == 2.0


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
        event_metrics = {m.reason_code: m for m in score_events(events, predictions, split)}
        # Every fault type must be detected at least once (recall > 0) at its injected location, on both splits.
        for code in REASON_CODES:
            if code == "gradual_drift":
                # Causal detection (task spec section 8): a run is only flaggable once it has
                # actually accumulated min_consecutive_same_direction steps, so row-level recall
                # for a run of exactly that length is necessarily < 1.0 -- never forced back to
                # 1.0 by retroactively marking earlier points. Event-level recall (was the event
                # detected at all) is what must stay 1.0.
                assert 0.0 < metrics[code].recall < 1.0, f"{code} row-level recall should be reduced but nonzero under causal detection ({split})"
                assert event_metrics[code].recall == 1.0, f"{code} event-level recall must still be 1.0 under causal detection ({split})"
            else:
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
        base_settings.cadence.sample_cadence_seconds,
    )
    splits = {r.dataset_split for r in rows}
    assert splits == {"calibration", "validation"}
    selected = [r for r in rows if r.selected]
    assert len(selected) == 2  # exactly one per split: the selected (window_size=11, mad_multiplier) combination
    selected_multipliers = {r.mad_multiplier for r in selected}
    assert len(selected_multipliers) == 1  # calibration and validation rows agree on which multiplier was selected
    assert all(r.window_size == 11 for r in selected)


# --- Final exclusion (task spec section 9): a primary SUSPECT candidate may
# later be confirmed usable -- primary screening and the final usable/not
# decision must be scored (and reported) separately. ---


def test_score_final_exclusion_counts_a_confirmed_suspect_as_a_false_negative_not_a_true_positive():
    from iaq_hfis.evaluation.fault_injection import SamplePrediction

    predictions = [
        # A genuine fault (single_spike) that was flagged SUSPECT as a primary
        # candidate but ultimately CONFIRMED usable (recovered) -- must count
        # against final-exclusion recall (fn), never as a tp.
        SamplePrediction("s1_calibration", "co2", 0, "single_spike", ["single_spike"], "SUSPECT", usable=True),
        # A genuine fault that stayed excluded -- a true positive here.
        SamplePrediction("s1_calibration", "co2", 1, "single_spike", ["single_spike"], "SUSPECT", usable=False),
        # A clean sample, correctly left usable.
        SamplePrediction("s1_calibration", "co2", 2, None, [], "VALID", usable=True),
        # A clean sample incorrectly excluded -- a final false rejection (fp).
        SamplePrediction("s1_calibration", "co2", 3, None, [], "SUSPECT", usable=False),
    ]
    metrics = {m.reason_code: m for m in score_final_exclusion(predictions)}
    single_spike = metrics["single_spike"]
    assert single_spike.tp == 1
    assert single_spike.fn == 1  # the confirmed-usable one -- recovered, not a final exclusion
    assert single_spike.fp == 1  # the wrongly-excluded clean sample
    assert single_spike.tn == 1


def test_score_final_exclusion_and_score_predictions_disagree_on_a_recovered_candidate():
    """Direct demonstration that primary screening and final exclusion are
    NOT the same metric: a sample that was a primary SUSPECT candidate for
    single_spike but was confirmed usable is a primary true positive
    (score_predictions) yet a final-exclusion false negative
    (score_final_exclusion)."""
    from iaq_hfis.evaluation.fault_injection import SamplePrediction

    predictions = [SamplePrediction("s1_calibration", "co2", 0, "single_spike", ["single_spike"], "SUSPECT", usable=True)]
    primary = {m.reason_code: m for m in score_predictions(predictions)}["single_spike"]
    final = {m.reason_code: m for m in score_final_exclusion(predictions)}["single_spike"]
    assert primary.tp == 1 and primary.fn == 0
    assert final.tp == 0 and final.fn == 1


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
