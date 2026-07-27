from iaq_hfis.reporting.summary import SECTIONS, build_run_summary_markdown

MINIMAL_SUMMARY = {
    "run_id": "abc123",
    "status": "success",
    "started_at": "2026-07-23T00:00:00+00:00",
    "finished_at": "2026-07-23T00:01:00+00:00",
    "computed_ts_range": ["2026-07-23T00:00:00+00:00", "2026-07-23T00:15:00+00:00"],
    "window_minutes": 15,
    "n_timestamps_processed": 3,
    "n_snapshot_retries": 0,
    "config_hash": "deadbeef",
    "engine_version": "0.1.0",
    "environment": {"iaq_hfis_version": "0.1.0", "python_version": "3.13.5"},
    "completeness_summary": {"OK": 2, "PARTIAL": 1, "FAILED": 0},
    "provisional_parameters_used": ["room_profile:kitchen/warm_period"],
}

FULL_EVALUATION = {
    "n_computed_ts_evaluated": 3,
    "agreement": [{"method_a": "CRISP-MAX", "method_b": "PROPOSED-HFIS", "n": 3, "n_excluded": 0, "percent_agreement": 1.0, "cohens_kappa": 1.0}],
    "masking": [{"method": "WEIGHTED-MEAN", "severity_threshold": "Critical", "n_critical_events": 2, "n_masked": 1, "masking_rate": 0.5}],
    "ground_truth": {"PROPOSED-HFIS": {"n": 42, "n_excluded": 0, "macro_f1": 0.9, "cohens_kappa": 0.87}},
    "stability": {"computed_ts": "2026-07-23T00:15:00", "seed": 42, "n_trials": 30, "baseline_class": "Favorable", "class_change_rate": 0.1},
    "sensitivity": [{"varied_parameter": "window_minutes", "value": 15, "completeness_status": "OK", "index_value": 20.0, "index_class": "Favorable"}],
    "status_proportions": {"n_total": 3, "OK": 0.667, "PARTIAL": 0.333, "FAILED": 0.0},
    "reason_code_frequency": {"n_total_quality_rows": 10, "counts": {"stuck_value": 3}},
}


def test_all_mandatory_sections_present_without_evaluation():
    md = build_run_summary_markdown(MINIMAL_SUMMARY)
    for section in SECTIONS:
        assert f"## {section}" in md or any(line.startswith(f"## {section}") for line in md.splitlines())


def test_all_mandatory_sections_present_with_evaluation():
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    md = build_run_summary_markdown(summary)
    for section in SECTIONS:
        assert section in md


def test_run_id_and_key_numbers_present():
    md = build_run_summary_markdown(MINIMAL_SUMMARY)
    assert "abc123" in md
    assert "deadbeef" in md
    assert "success" in md


def test_no_evaluation_explains_rather_than_omits():
    md = build_run_summary_markdown(MINIMAL_SUMMARY)
    assert "iaq_hfis evaluate" in md  # tells the reader how to get it, doesn't just silently skip


def test_provisional_parameters_listed():
    md = build_run_summary_markdown(MINIMAL_SUMMARY)
    assert "room_profile:kitchen/warm_period" in md


def test_no_provisional_parameters_says_so_explicitly():
    summary = dict(MINIMAL_SUMMARY, provisional_parameters_used=[])
    md = build_run_summary_markdown(summary)
    assert "None engaged this run" in md
