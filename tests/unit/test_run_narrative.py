from iaq_hfis.reporting.narrative import CAUTIONS, FORBIDDEN_OVERCLAIMS, WARNING_BANNER, build_run_narrative

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


def test_dedicated_limitations_section_present():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    assert "## Limitations" in narrative
    # Limitations must appear before the closing warning banner and before Scientific cautions.
    assert narrative.index("## Limitations") < narrative.rindex(WARNING_BANNER)


def test_forbidden_overclaims_section_present_verbatim():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    assert "## Forbidden overclaims" in narrative
    for overclaim in FORBIDDEN_OVERCLAIMS:
        assert overclaim in narrative


def test_hfis_crispmax_near_total_agreement_stated_explicitly():
    """If PROPOSED-HFIS and CRISP-MAX agree on >=95% of real-data
    timestamps, the narrative must say so explicitly and discuss what
    HFIS's remaining value is, rather than silently omitting the finding."""
    summary = dict(MINIMAL_SUMMARY, evaluation=FULL_EVALUATION)
    narrative = build_run_narrative(summary)
    assert "effectively equivalent at the classification level" in narrative
    assert "continuous within-class severity" in narrative
    assert "docs/hfis_vs_crispmax_audit.md" in narrative


def test_hfis_crispmax_equivalence_note_absent_when_agreement_is_low():
    """The equivalence claim must be data-driven -- it must NOT appear when
    the two methods do not actually agree near-totally this run."""
    ev = dict(FULL_EVALUATION, agreement=[{"method_a": "CRISP-MAX", "method_b": "PROPOSED-HFIS", "n": 10, "n_excluded": 0, "percent_agreement": 0.4, "cohens_kappa": 0.1}])
    summary = dict(MINIMAL_SUMMARY, evaluation=ev)
    narrative = build_run_narrative(summary)
    assert "effectively equivalent at the classification level" not in narrative
    # but the plain agreement number must still be reported
    assert "40.0%" in narrative


def test_continuity_full_tie_triggers_equivalence_note_even_with_low_agreement():
    ev = dict(
        FULL_EVALUATION,
        agreement=[{"method_a": "CRISP-MAX", "method_b": "PROPOSED-HFIS", "n": 10, "n_excluded": 0, "percent_agreement": 0.4, "cohens_kappa": 0.1}],
        continuity={
            "n_boundaries": 1, "grid_points_per_boundary": 5, "by_boundary_method": [],
            "smoothness_comparison": {"n_boundary_context_pairs_compared": 3, "hfis_smoother_count": 0, "crisp_max_smoother_count": 0, "tied_count": 3, "conclusion": "tied"},
        },
    )
    summary = dict(MINIMAL_SUMMARY, evaluation=ev)
    narrative = build_run_narrative(summary)
    assert "numerically tied on every one of 3 boundary/context pairs" in narrative
    assert "effectively equivalent at the classification level" in narrative


def test_fault_injection_weak_codes_surfaced_in_limitations():
    fi = {
        "n_scenarios": 4, "channels_covered": ["co2"], "headline_dataset_split": "validation",
        "metrics_by_reason_code": [
            {"reason_code": "single_spike", "tp": 1, "fp": 50, "fn": 0, "precision": 0.02, "recall": 1.0, "f1": 0.04, "false_positive_rate": 0.1, "mean_detection_delay": 0.0},
            {"reason_code": "data_loss", "tp": 5, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0, "false_positive_rate": 0.0, "mean_detection_delay": 0.0},
        ],
        "event_level_metrics_by_split": {}, "false_rejection_rate_for_genuine_events": 0.0, "hampel_calibration": {},
    }
    ev = dict(FULL_EVALUATION, fault_injection=fi)
    summary = dict(MINIMAL_SUMMARY, evaluation=ev)
    narrative = build_run_narrative(summary)
    limitations_section = narrative.split("## Limitations")[1].split("## Forbidden overclaims")[0]
    assert "single_spike" in limitations_section
    assert "data_loss" not in limitations_section  # only the weak (F1<0.5) code belongs here


def test_limitations_present_even_without_evaluation():
    narrative = build_run_narrative(MINIMAL_SUMMARY)
    limitations_section = narrative.split("## Limitations")[1].split("## Forbidden overclaims")[0]
    assert "deterministic, bounded SAMPLES" in limitations_section
    assert "No empirical, ground-truth-labeled accuracy claim" in limitations_section
