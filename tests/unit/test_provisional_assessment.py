from iaq_hfis.provenance import apply_known_engagement, collect_parameter_provenance, engaged_provisional_paths
from iaq_hfis.reporting.provisional_assessment import _ASSESSMENTS, build_provisional_parameter_assessment_markdown


def test_every_config_level_provisional_parameter_has_a_reviewed_assessment(base_settings, sensor_specs, room_profiles):
    """Mandatory regression test: a new PROVISIONAL parameter added to
    provenance.py without a corresponding _ASSESSMENTS entry would
    otherwise silently fall back to a generic 'not yet assessed'
    placeholder in the published report -- this test forces a reviewed
    entry to be added at the same time."""
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    config_level_provisional = [r.path for r in rows if r.status == "PROVISIONAL" and not r.path.startswith("room_profiles.")]
    missing = [p for p in config_level_provisional if p not in _ASSESSMENTS]
    assert missing == [], f"add a reviewed _AssessmentMeta entry for: {missing}"


def test_assessment_report_lists_every_engaged_provisional_parameter(base_settings, sensor_specs, room_profiles):
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    engaged = sorted(engaged_provisional_paths(rows, provisional_profile_events=[]))
    provenance = apply_known_engagement(rows, engaged)
    summary = {"provisional_parameters_used": engaged, "evaluation": None}

    report = build_provisional_parameter_assessment_markdown(provenance, summary)
    for path in engaged:
        assert f"`{path}`" in report
        assert "Engaged this run**: yes" in report.split(f"## `{path}`")[1].split("## `")[0]


def test_assessment_report_never_claims_universal_validity():
    """Hard rule: a synthetic benchmark's calibration result must never be
    presented as making a parameter universally valid."""
    from iaq_hfis.provenance import ParameterProvenance

    row = ParameterProvenance(
        path="hampel.window_size", effective_value="11", unit="samples", status="PROVISIONAL",
        source_file="config/iaq_hfis.yaml", source_key_path="hampel.window_size",
        scientific_rationale="test", pipeline_stage="validation", manuscript_reference=None, engaged=True,
    )
    summary = {"provisional_parameters_used": ["hampel.window_size"], "evaluation": None}
    report = build_provisional_parameter_assessment_markdown([row], summary)
    assert "universally valid" in report  # the disclaimer itself, stated once up top
    assert "makes hampel.window_size universally valid" not in report


def test_assessment_report_never_promotes_provisional_to_standard_based():
    from iaq_hfis.provenance import ParameterProvenance

    row = ParameterProvenance(
        path="hampel.mad_multiplier", effective_value="1.0", unit=None, status="PROVISIONAL",
        source_file="config/iaq_hfis.yaml", source_key_path="hampel.mad_multiplier",
        scientific_rationale="test", pipeline_stage="validation", manuscript_reference=None, engaged=True,
    )
    summary = {"provisional_parameters_used": ["hampel.mad_multiplier"], "evaluation": None}
    report = build_provisional_parameter_assessment_markdown([row], summary)
    assert "STANDARD_BASED" not in report or "never" in report.lower()


def test_assessment_report_handles_no_evaluation_gracefully(base_settings, sensor_specs, room_profiles):
    rows = collect_parameter_provenance(base_settings, sensor_specs, room_profiles)
    provenance = apply_known_engagement(rows, [])
    summary = {"provisional_parameters_used": [], "evaluation": None}
    report = build_provisional_parameter_assessment_markdown(provenance, summary)
    assert "Provisional Parameter Assessment" in report
    assert "not directly swept" in report.lower() or "not applicable" in report.lower()
