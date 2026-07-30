from iaq_hfis.reporting.summary import SECTIONS, build_run_summary_markdown

MINIMAL_SUMMARY = {
    "pipeline_run_id": "abc123",
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
    "selected_evaluation_run_id": None,
}

FULL_EVALUATION = {
    "evaluation_run_id": "eval123",
    "pipeline_run_id": "abc123",
    "n_computed_ts_evaluated": 3,
    "agreement": [{"method_a": "CRISP-MAX", "method_b": "PROPOSED-HFIS", "n": 3, "n_excluded": 0, "percent_agreement": 1.0, "cohens_kappa": 1.0}],
    "masking": [{"method": "WEIGHTED-MEAN", "severity_threshold": "Critical", "n_critical_events": 2, "n_masked": 1, "masking_rate": 0.5}],
    "reference_cases": {"PROPOSED-HFIS": {"n": 42, "n_excluded": 0, "macro_f1": 0.9, "cohens_kappa": 0.87}},
    "stability": {
        "n_samples": 5,
        "n_trials_per_sample": 30,
        "seed": 42,
        "by_method": {
            "PROPOSED-HFIS": {
                "n_trials_total": 150, "n_class_changes": 15, "class_change_rate": 0.1, "class_change_rate_ci95": [0.05, 0.15],
                "mean_abs_index_change": 1.2, "median_abs_index_change": 1.0, "p95_abs_index_change": 2.5, "max_abs_index_change": 3.0,
                "n_comparable_for_direction": 150, "n_moved_better": 5, "n_moved_worse": 10,
                "prob_moved_better": 0.0333, "prob_moved_worse": 0.0667,
                "prob_moved_better_ci95": [0.01, 0.07], "prob_moved_worse_ci95": [0.04, 0.11],
            }
        },
        "by_variable": [],
        "by_original_class": [],
    },
    "sensitivity": {
        "n_sample_points": 10,
        "strata": ["class_Favorable", "ordinary"],
        "by_parameter_value": [
            {"varied_parameter": "window_minutes", "value": 15, "n_samples": 10, "n_status_transitions": 0, "n_class_transitions": 0, "class_agreement_with_reference": 1.0, "mean_abs_index_diff": 0.0, "median_abs_index_diff": 0.0, "p95_abs_index_diff": 0.0, "max_abs_index_diff": 0.0}
        ],
    },
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
