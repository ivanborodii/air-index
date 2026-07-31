from iaq_hfis.reporting.publication_claims import build_publication_claims_matrix

MINIMAL_SUMMARY = {
    "completeness_summary": {"OK": 3, "PARTIAL": 1, "FAILED": 1},
    "dominant_component_frequency": {"A": 2, "V": 1},
    "performance": {
        "platform": "Linux-6.6-x86_64", "processor": "x86_64",
        "per_timestamp_latency_ms": {"mean": 12.5}, "total_runtime_seconds": 1.0, "peak_memory_mb": 100.0,
    },
    "readiness": {
        "manuscript_readiness": {"ready": True, "blocking_issues": [], "unsupported_claims": [], "warnings": []},
    },
    "evaluation": {
        "fault_injection": {
            "false_rejection_rate_for_genuine_events_by_split": {"validation": 0.0},
            "row_level_metrics_by_split": {"validation": [{"reason_code": "single_spike", "precision": 0.02}, {"reason_code": "data_loss", "precision": 1.0}]},
        },
        "masking": [{"method": "WEIGHTED_MEAN", "severity_threshold": "Critical", "n_critical_events": 4, "n_masked": 3, "masking_rate": 0.75}],
        "continuity": {
            "smoothness_comparison_vs_crisp_class_max": {
                "baseline_method": "CRISP_CLASS_MAX", "n_boundary_context_pairs_compared": 10,
                "hfis_smoother_count": 7, "baseline_smoother_count": 1, "tied_count": 2, "conclusion": "hfis smoother",
            },
        },
        "stability": {"by_method": {"PROPOSED_HFIS": {"class_change_rate": 0.05}, "CRISP_CLASS_MAX": {"class_change_rate": 0.20}}},
    },
}


def test_all_nine_claims_present():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    assert len(rows) == 9
    assert [r.claim_id for r in rows] == [f"claim_{i:02d}" for i in range(1, 10)]


def test_claim_status_is_one_of_the_four_allowed_values():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    for r in rows:
        assert r.status in {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "BLOCKED"}


def test_masking_claim_supported_when_masking_observed():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    claim3 = next(r for r in rows if r.claim_id == "claim_03")
    assert claim3.status == "SUPPORTED"
    assert claim3.metric_value == "0.750"


def test_fault_injection_claim_partially_supported_on_weak_precision():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    claim2 = next(r for r in rows if r.claim_id == "claim_02")
    assert claim2.status == "PARTIALLY_SUPPORTED"
    assert "single_spike" in claim2.limitation


def test_smoothness_claim_supported_when_hfis_smoother_more_often():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    claim5 = next(r for r in rows if r.claim_id == "claim_05")
    assert claim5.status == "SUPPORTED"


def test_stability_claim_supported_when_hfis_more_stable():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    claim6 = next(r for r in rows if r.claim_id == "claim_06")
    assert claim6.status == "SUPPORTED"


def test_rpi5_claim_unsupported_off_pi_hardware():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    claim7 = next(r for r in rows if r.claim_id == "claim_07")
    assert claim7.status == "UNSUPPORTED"
    assert "not a Raspberry Pi 5" in claim7.limitation


def test_microclimate_claim_supported_when_manuscript_ready():
    rows = build_publication_claims_matrix(MINIMAL_SUMMARY)
    claim9 = next(r for r in rows if r.claim_id == "claim_09")
    assert claim9.status == "SUPPORTED"


def test_microclimate_claim_blocked_when_temperature_profile_provisional():
    summary = dict(MINIMAL_SUMMARY)
    summary["readiness"] = {
        "manuscript_readiness": {
            "ready": False,
            "blocking_issues": ["room/season temperature profile is provisional, not directly DBN-supported: ['room_profiles.kitchen/warm_period.transition_width']"],
            "unsupported_claims": [], "warnings": [],
        },
    }
    rows = build_publication_claims_matrix(summary)
    claim9 = next(r for r in rows if r.claim_id == "claim_09")
    assert claim9.status == "BLOCKED"
    assert "temperature profile" in claim9.limitation


def test_claim_never_supported_just_because_code_exists():
    # Empty/absent evaluation data everywhere -- must never default to SUPPORTED.
    empty_summary = {"completeness_summary": {}, "dominant_component_frequency": {}, "performance": {}, "readiness": {}}
    rows = build_publication_claims_matrix(empty_summary)
    supported = [r for r in rows if r.status == "SUPPORTED"]
    # claim_08 (outdoor data structural guarantee) is the only claim allowed to be
    # evidence-independent of this run's specific data, since it's a code-level invariant.
    assert {r.claim_id for r in supported} <= {"claim_08"}
