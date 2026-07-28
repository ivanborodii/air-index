from iaq_hfis.provenance import assess_publication_readiness, collect_parameter_provenance, mark_engagement


def test_every_provenance_row_has_a_valid_status(base_settings, sensor_specs, room_profiles):
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    assert len(rows) > 20
    for row in rows:
        assert row.status in {"manuscript_defined", "standard_based", "sensor_specification", "author_defined", "provisional"}
        assert row.path
        assert row.source


def test_hampel_parameters_marked_provisional_with_citation(base_settings, sensor_specs, room_profiles):
    rows = {r.path: r for r in collect_parameter_provenance(base_settings, sensor_specs, room_profiles)}
    assert rows["hampel.window_size"].status == "provisional"
    assert "Pearson" in rows["hampel.window_size"].source


def test_sensitivity_swept_parameters_have_sensitivity_coverage(base_settings, sensor_specs, room_profiles):
    rows = {r.path: r for r in collect_parameter_provenance(base_settings, sensor_specs, room_profiles)}
    assert rows["evaluation.sensitivity_window_minutes"].sensitivity_coverage is not None
    assert rows["evaluation.sensitivity_coverage_thresholds"].sensitivity_coverage is not None
    assert rows["hampel.window_size"].sensitivity_coverage is None


def test_mark_engagement_lists_only_actually_engaged_provisional_profiles(base_settings, sensor_specs, room_profiles):
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    # No provisional room profiles exist in the current room_profiles.yaml (all provisional: false),
    # so nothing should be marked as an engaged provisional profile.
    engaged = mark_engagement(rows, provisional_parameters_used=["room_profile:kitchen/warm_period"])
    profile_rows = [r for r in engaged if r.path.startswith("room_profiles.")]
    assert all(r.status == "standard_based" for r in profile_rows)


def test_publication_readiness_blocks_on_non_success_status():
    summary = {"status": "failed", "evaluation": {"n_computed_ts_evaluated": 0}}
    readiness = assess_publication_readiness(summary, provenance=[])
    assert readiness["ready"] is False
    assert any("status is 'failed'" in issue for issue in readiness["blocking_issues"])


def test_publication_readiness_blocks_when_no_evaluation():
    summary = {"status": "success", "evaluation": None}
    readiness = assess_publication_readiness(summary, provenance=[])
    assert readiness["ready"] is False
    assert any("no evaluation" in issue for issue in readiness["blocking_issues"])


def test_publication_readiness_ready_when_success_and_evaluated_with_no_provisional_engaged():
    summary = {"status": "success", "evaluation": {"n_computed_ts_evaluated": 5}}
    readiness = assess_publication_readiness(summary, provenance=[])
    assert readiness["ready"] is True
    assert readiness["blocking_issues"] == []


def test_publication_readiness_never_says_none_engaged_when_provisional_params_are_engaged(base_settings, sensor_specs, room_profiles):
    """Mandatory regression test: the report must never claim 'no
    provisional parameters engaged' when the machine-readable provenance
    disagrees."""
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    engaged = mark_engagement(rows, provisional_parameters_used=[])
    summary = {"status": "success", "evaluation": {"n_computed_ts_evaluated": 5}}
    readiness = assess_publication_readiness(summary, engaged)
    # hampel.window_size etc. are config-level provisional parameters that apply to every
    # computed_ts by construction, so they are always "engaged" regardless of provisional_parameters_used.
    assert len(readiness["provisional_parameters_used"]) > 0
    assert "hampel.window_size" in readiness["provisional_parameters_used"]
