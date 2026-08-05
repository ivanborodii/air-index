from iaq_hfis.provenance import (
    PROVISIONAL_LIKE_STATUSES,
    STATUS_VALUES,
    apply_known_engagement,
    assess_readiness,
    collect_parameter_provenance,
    engaged_provisional_paths,
    mark_engagement,
)


def test_every_provenance_row_has_a_valid_status(base_settings, sensor_specs, room_profiles):
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    assert len(rows) > 20
    for row in rows:
        assert row.status in STATUS_VALUES
        assert row.path
        assert row.scientific_rationale
        assert row.source_file
        assert row.pipeline_stage


def test_status_taxonomy_includes_manuscript_validation_task_categories():
    # spec section 5.2.8's example taxonomy -- STANDARD_BASED, DATASHEET_BASED,
    # LITERATURE_INFORMED, CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT,
    # AUTHOR_DEFINED_PROVISIONAL, DERIVED_FROM_SYSTEM_CADENCE.
    for expected in (
        "STANDARD_BASED", "DATASHEET_BASED", "LITERATURE_INFORMED",
        "CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT", "AUTHOR_DEFINED_PROVISIONAL", "DERIVED_FROM_SYSTEM_CADENCE",
    ):
        assert expected in STATUS_VALUES


def test_hampel_parameters_marked_literature_informed_not_calibrated(base_settings, sensor_specs, room_profiles):
    # Never call it "calibrated" merely because it came from a literature example.
    rows = {r.path: r for r in collect_parameter_provenance(base_settings, sensor_specs, room_profiles)}
    assert rows["hampel.window_size"].status == "LITERATURE_INFORMED"
    assert rows["hampel.window_size"].status not in ("PROVISIONAL", "CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT")
    assert "Pearson" in rows["hampel.window_size"].scientific_rationale
    assert rows["hampel.window_size"].status in PROVISIONAL_LIKE_STATUSES  # still unconfirmed for this deployment


def test_sensitivity_swept_parameters_have_sensitivity_coverage(base_settings, sensor_specs, room_profiles):
    rows = {r.path: r for r in collect_parameter_provenance(base_settings, sensor_specs, room_profiles)}
    assert rows["evaluation.sensitivity_window_minutes"].sensitivity_coverage is not None
    assert rows["evaluation.sensitivity_coverage_thresholds"].sensitivity_coverage is not None
    assert rows["hampel.window_size"].sensitivity_coverage is None


def test_mark_engagement_lists_only_actually_engaged_provisional_profiles(base_settings, sensor_specs, room_profiles):
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    # No provisional room profiles exist in the current room_profiles.yaml (all provisional: false),
    # so nothing should be marked as an engaged provisional profile.
    engaged = mark_engagement(rows, provisional_profile_events=["room_profile:kitchen/warm_period"])
    profile_rows = [r for r in engaged if r.path.startswith("room_profiles.")]
    assert all(r.status == "STANDARD_BASED" for r in profile_rows)


def test_engaged_provisional_paths_are_config_level_parameters_by_default(base_settings, sensor_specs, room_profiles):
    """Config-level PROVISIONAL parameters (e.g. hampel.window_size) apply to
    every computed_ts by construction, so they are engaged regardless of
    which room-profile-selection events occurred."""
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    engaged = engaged_provisional_paths(rows, provisional_profile_events=[])
    assert "hampel.window_size" in engaged
    assert "confirmation.persistence_min_consecutive_samples" in engaged


def test_apply_known_engagement_matches_mark_engagement(base_settings, sensor_specs, room_profiles):
    """report-time apply_known_engagement (from an already-decided list) must
    produce the identical engaged set as run-time mark_engagement (from raw
    profile-selection events) for the same underlying data -- this identity
    is exactly what keeps run_summary.md/run_narrative.md, readiness,
    and parameter_provenance.csv from disagreeing."""
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    events = ["room_profile:kitchen/warm_period"]
    via_mark_engagement = {r.path: r.engaged for r in mark_engagement(rows, provisional_profile_events=events)}
    authoritative_list = engaged_provisional_paths(rows, provisional_profile_events=events)
    via_apply_known = {r.path: r.engaged for r in apply_known_engagement(rows, authoritative_list)}
    assert via_mark_engagement == via_apply_known


def test_artifact_readiness_blocks_on_non_success_status():
    summary = {"status": "failed", "evaluation": {"n_computed_ts_evaluated": 0}, "provisional_parameters_used": []}
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["artifact_readiness"]["ready"] is False
    assert any("status is 'failed'" in issue for issue in readiness["artifact_readiness"]["blocking_issues"])


def test_artifact_readiness_blocks_when_no_evaluation():
    summary = {"status": "success", "evaluation": None, "provisional_parameters_used": []}
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["artifact_readiness"]["ready"] is False
    assert any("no evaluation" in issue for issue in readiness["artifact_readiness"]["blocking_issues"])


def test_artifact_readiness_ready_when_success_and_evaluated_with_no_provisional_engaged():
    summary = {"status": "success", "evaluation": {"n_computed_ts_evaluated": 5}, "provisional_parameters_used": []}
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["artifact_readiness"]["ready"] is True
    assert readiness["artifact_readiness"]["blocking_issues"] == []
    assert readiness["provisional_parameters_used"] == []


def test_manuscript_readiness_requires_publication_mode_and_ok_completeness():
    # Artifact-clean, but not manuscript-eligible without mode=publication and an OK result.
    summary = {
        "status": "success", "evaluation": {"n_computed_ts_evaluated": 5}, "provisional_parameters_used": [],
        "mode": "exploratory", "completeness_summary": {"OK": 0, "PARTIAL": 5, "FAILED": 0},
    }
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["artifact_readiness"]["ready"] is True
    assert readiness["manuscript_readiness"]["ready"] is False
    assert "Full three-component (A/V/M/I) proposed-method result" in readiness["unsupported_claims"]


def test_manuscript_readiness_ready_with_publication_mode_and_ok_result():
    summary = {
        "status": "success", "evaluation": {"n_computed_ts_evaluated": 5}, "provisional_parameters_used": [],
        "mode": "publication", "completeness_summary": {"OK": 3, "PARTIAL": 2, "FAILED": 0},
    }
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["manuscript_readiness"]["ready"] is True
    assert readiness["manuscript_readiness"]["unsupported_claims"] == []
    assert readiness["scientific_blockers"] == []


def test_manuscript_readiness_blocked_by_provisional_room_profile():
    summary = {
        "status": "success", "evaluation": {"n_computed_ts_evaluated": 5},
        "provisional_parameters_used": ["room_profiles.kitchen/warm_period.transition_width"],
        "mode": "publication", "completeness_summary": {"OK": 3, "PARTIAL": 0, "FAILED": 0},
    }
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["manuscript_readiness"]["ready"] is False
    assert any("provisional" in issue for issue in readiness["manuscript_readiness"]["blocking_issues"])


def test_readiness_reads_provisional_count_from_summary_not_provenance():
    """Mandatory regression test: readiness's provisional-parameter list must
    come verbatim from summary['provisional_parameters_used'] (the single
    authoritative field set at run time), never recomputed from the
    provenance list independently -- that independent recomputation is
    exactly how run_summary.md ('None engaged') and the readiness assessment
    (16 engaged) previously disagreed."""
    summary = {
        "status": "success",
        "evaluation": {"n_computed_ts_evaluated": 5},
        "provisional_parameters_used": ["hampel.window_size", "hampel.mad_multiplier"],
    }
    readiness = assess_readiness(summary, provenance=[])
    assert readiness["provisional_parameters_used"] == ["hampel.mad_multiplier", "hampel.window_size"]


def test_provenance_and_run_summary_agree_on_engaged_count(base_settings, sensor_specs, room_profiles):
    """End-to-end check that the full authoritative pipeline (collect ->
    engaged_provisional_paths -> summary field -> assess_readiness)
    produces one single, self-consistent count."""
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    authoritative_list = sorted(engaged_provisional_paths(rows, provisional_profile_events=[]))
    summary = {"status": "success", "evaluation": {"n_computed_ts_evaluated": 5}, "provisional_parameters_used": authoritative_list}
    readiness = assess_readiness(summary, apply_known_engagement(rows, authoritative_list))
    assert readiness["provisional_parameters_used"] == authoritative_list
    assert len(authoritative_list) > 0
