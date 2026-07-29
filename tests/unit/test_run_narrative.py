from iaq_hfis.reporting.narrative import CAUTIONS, WARNING_BANNER, build_run_narrative

MINIMAL_SUMMARY = {
    "pipeline_run_id": "abc123",
    "computed_ts_range": ["2026-07-23T00:00:00+00:00", "2026-07-23T00:15:00+00:00"],
    "window_minutes": 15,
    "n_timestamps_processed": 3,
    "completeness_summary": {"OK": 2, "PARTIAL": 1, "FAILED": 0},
    "provisional_parameters_used": ["room_profile:kitchen/warm_period"],
}

FULL_EVALUATION = {
    "evaluation_run_id": "eval123",
    "agreement": [{"method_a": "CRISP-MAX", "method_b": "PROPOSED-HFIS", "n": 3, "n_excluded": 0, "percent_agreement": 1.0, "cohens_kappa": 1.0}],
    "masking": [{"method": "WEIGHTED-MEAN", "severity_threshold": "Critical", "n_critical_events": 2, "n_masked": 1, "masking_rate": 0.5}],
    "reference_cases": {"PROPOSED-HFIS": {"n": 42, "n_excluded": 0, "macro_f1": 0.9166666666666666, "cohens_kappa": 0.8721461187214611}},
    "stability": {
        "n_samples": 5,
        "n_trials_per_sample": 30,
        "seed": 42,
        "by_method": {
            "PROPOSED-HFIS": {
                "n_trials_total": 150, "n_class_changes": 15, "class_change_rate": 0.1, "class_change_rate_ci95": [0.05, 0.15],
                "mean_abs_index_change": 1.234, "median_abs_index_change": 1.0, "p95_abs_index_change": 2.5, "max_abs_index_change": 3.0,
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
}


def test_opening_and_closing_warning_banner_present():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    lines = narrative.strip().splitlines()
    assert lines[0] == WARNING_BANNER
    assert lines[-1] == WARNING_BANNER


def test_all_scientific_cautions_present_verbatim():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    for caution in CAUTIONS:
        assert caution in narrative


def test_narrative_generated_without_evaluation_section():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    assert "was not run for this pipeline_run_id" in narrative
    assert WARNING_BANNER in narrative


def test_narrative_generated_for_zero_timestamps():
    summary = dict(MINIMAL_SUMMARY, n_timestamps_processed=0, completeness_summary={"OK": 0, "PARTIAL": 0, "FAILED": 0})
    narrative = build_run_narrative(summary)
    assert "No timestamps were processed" in narrative


def test_agreement_numbers_traceable_to_summary():
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    narrative = build_run_narrative(summary)
    a = FULL_EVALUATION["agreement"][0]
    assert f"{a['percent_agreement']:.1%}" in narrative
    assert f"{a['cohens_kappa']:.3f}" in narrative
    assert str(a["n"]) in narrative


def test_masking_numbers_traceable_to_summary():
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    narrative = build_run_narrative(summary)
    m = FULL_EVALUATION["masking"][0]
    assert f"{m['masking_rate']:.1%}" in narrative
    assert str(m["n_critical_events"]) in narrative


def test_reference_case_numbers_traceable_to_summary():
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    narrative = build_run_narrative(summary)
    score = FULL_EVALUATION["reference_cases"]["PROPOSED-HFIS"]
    assert f"{score['macro_f1']:.3f}" in narrative
    assert f"{score['cohens_kappa']:.3f}" in narrative
    assert "not empirical accuracy" in narrative


def test_stability_numbers_traceable_to_summary():
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    narrative = build_run_narrative(summary)
    stability = FULL_EVALUATION["stability"]
    assert str(stability["n_samples"]) in narrative
    assert str(stability["seed"]) in narrative
    s = stability["by_method"]["PROPOSED-HFIS"]
    assert f"{s['class_change_rate']:.1%}" in narrative


def test_masking_none_rate_explained_not_fabricated():
    ev = dict(FULL_EVALUATION, masking=[{"method": "CRISP-MAX", "severity_threshold": "Critical", "n_critical_events": 0, "n_masked": 0, "masking_rate": None}])
    summary = dict(MINIMAL_SUMMARY, evaluation=ev)
    narrative = build_run_narrative(summary)
    assert "could not be computed" in narrative


def test_completeness_counts_traceable():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    cs = MINIMAL_SUMMARY["completeness_summary"]
    assert str(cs["OK"]) in narrative
    assert str(cs["PARTIAL"]) in narrative
    assert str(cs["FAILED"]) in narrative


def test_provisional_parameters_named():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    assert "room_profile:kitchen/warm_period" in narrative


def test_agreement_never_called_accuracy():
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    narrative = build_run_narrative(summary)
    assert "accuracy" not in narrative.split("Scientific cautions")[0].lower() or "unlabeled agreement" in narrative.lower()
    # the agreement bullet itself must say "agreement", never "accuracy"
    assert "unlabeled agreement" in narrative
