from iaq_hfis.baselines import BaselineResult, fuzzy_component_max, weighted_mean
from iaq_hfis.evaluation.masking import evaluate_masking


def _critical_and_favorable_scenario() -> dict[str, float]:
    # One component deep in Critical (>=75), two deeply Favourable -- the
    # textbook masking setup: WEIGHTED_MEAN dilutes this to well below Critical.
    return {"A": 10.0, "V": 10.0, "M": 95.0}


def test_weighted_mean_detects_injected_masking_case():
    scores = _critical_and_favorable_scenario()
    wm_result = weighted_mean(scores)
    assert wm_result.index_class != "Critical"  # confirm the dilution actually happened

    result = evaluate_masking([scores], [wm_result], severity_threshold="Critical")
    assert result.n_critical_events == 1
    assert result.n_masked == 1
    assert result.masking_rate == 1.0


def test_crisp_max_masking_rate_is_always_zero_structurally():
    scenarios = [
        {"A": 95.0, "V": 10.0, "M": 10.0},
        {"A": 10.0, "V": 95.0, "M": 10.0},
        {"A": 10.0, "V": 10.0, "M": 95.0},
        {"A": 80.0, "V": 76.0, "M": 12.0},
    ]
    cm_results = [fuzzy_component_max(s) for s in scenarios]
    result = evaluate_masking(scenarios, cm_results, severity_threshold="Critical")
    assert result.n_critical_events == len(scenarios)
    assert result.n_masked == 0
    assert result.masking_rate == 0.0


def test_masking_rate_is_none_when_nothing_reaches_threshold():
    scores = {"A": 10.0, "V": 10.0, "M": 10.0}
    wm_result = weighted_mean(scores)
    result = evaluate_masking([scores], [wm_result], severity_threshold="Critical")
    assert result.n_critical_events == 0
    assert result.masking_rate is None  # explained, not fabricated as 0.0


def test_masking_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        evaluate_masking([{"A": 10.0}], [], severity_threshold="Critical")
