import numpy as np
import pytest

from iaq_hfis.constants import CLASS_ORDER, OUTPUT_MAX, OUTPUT_MIN
from iaq_hfis.fuzzy_engine import MamdaniEngine, classify_output, determine_dominance, rule_level_contributors
from iaq_hfis.membership import build_monotonic_classes
from iaq_hfis.models import FiredRule, Rule
from iaq_hfis.rules import build_rule_base

#: Representative crisp scores (0-100) per class, for tests that need a
#: plausible component_crisp_scores dict but don't assert on it directly.
_REPRESENTATIVE_SCORE = {"Favorable": 10.0, "Acceptable": 35.0, "Degraded": 60.0, "Critical": 90.0}


@pytest.fixture
def engine():
    output_shapes = build_monotonic_classes([25.0, 50.0, 75.0], [2.0, 2.0, 2.0])
    universe = np.linspace(OUTPUT_MIN, OUTPUT_MAX, 401)
    return MamdaniEngine(build_rule_base(), output_shapes, universe)


def _degrees(favorable_cls: str) -> dict:
    return {cls: (1.0 if cls == favorable_cls else 0.0) for cls in CLASS_ORDER}


def _scores(component_classes: dict) -> dict:
    return {c: _REPRESENTATIVE_SCORE[cls] for c, cls in component_classes.items()}


def _infer(engine, degrees: dict, available: set, component_classes: dict, tie_tolerance: float = 1.0):
    return engine.infer_index(degrees, available, _scores(component_classes), tie_tolerance)


@pytest.mark.parametrize("out_class,expected_low,expected_high", [("Favorable", 0, 25), ("Acceptable", 25, 50), ("Degraded", 50, 75), ("Critical", 75, 100)])
def test_pure_class_index_lands_in_expected_range(engine, out_class, expected_low, expected_high):
    degrees = {"A": _degrees(out_class), "V": _degrees(out_class), "M": _degrees(out_class)}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": out_class, "V": out_class, "M": out_class})
    assert expected_low <= result.index_value <= expected_high


def test_output_boundaries_are_25_50_75_closed_worse_side():
    assert classify_output(24.999) == "Favorable"
    assert classify_output(25.0) == "Acceptable"
    assert classify_output(49.999) == "Acceptable"
    assert classify_output(50.0) == "Degraded"
    assert classify_output(74.999) == "Degraded"
    assert classify_output(75.0) == "Critical"
    assert classify_output(100.0) == "Critical"


def test_all_favorable_gives_favorable_result(engine):
    degrees = {"A": _degrees("Favorable"), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": "Favorable", "V": "Favorable", "M": "Favorable"})
    assert result.index_class == "Favorable"


def test_one_critical_component_prevents_favorable_result(engine):
    degrees = {"A": _degrees("Critical"), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": "Critical", "V": "Favorable", "M": "Favorable"})
    assert result.index_class != "Favorable"
    assert result.index_class == "Critical"


def test_monotonic_worsening_never_improves_index(engine):
    prior_value = 0.0
    for cls in CLASS_ORDER:
        degrees = {"A": _degrees(cls), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
        result = _infer(engine, degrees, {"A", "V", "M"}, {"A": cls, "V": "Favorable", "M": "Favorable"})
        assert result.index_value >= prior_value - 1e-9
        prior_value = result.index_value


def test_centroid_is_deterministic(engine):
    degrees = {"A": _degrees("Degraded"), "V": _degrees("Acceptable"), "M": _degrees("Favorable")}
    classes = {"A": "Degraded", "V": "Acceptable", "M": "Favorable"}
    r1 = _infer(engine, degrees, {"A", "V", "M"}, classes)
    r2 = _infer(engine, degrees, {"A", "V", "M"}, classes)
    assert r1.index_value == r2.index_value


def test_partial_mode_two_components_favorable_gives_favorable(engine):
    degrees = {"A": _degrees("Favorable"), "V": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "V"}, {"A": "Favorable", "V": "Favorable"})
    assert result.index_class == "Favorable"
    assert result.index_value < 25.0


def test_partial_mode_one_critical_component_gives_critical(engine):
    degrees = {"A": _degrees("Critical"), "M": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "M"}, {"A": "Critical", "M": "Favorable"})
    assert result.index_class == "Critical"


def test_temperature_and_humidity_both_directions_worsen_microclimate(engine):
    # Low, mid, high membership vectors for a two-sided channel (favorable in the middle)
    mid = {"Favorable": 1.0, "Acceptable": 0.0, "Degraded": 0.0, "Critical": 0.0}
    low_extreme = {"Favorable": 0.0, "Acceptable": 0.0, "Degraded": 0.0, "Critical": 1.0}
    high_extreme = {"Favorable": 0.0, "Acceptable": 0.0, "Degraded": 0.0, "Critical": 1.0}

    mid_result = engine.infer_component("M", {"temperature": mid, "humidity": mid})
    low_result = engine.infer_component("M", {"temperature": low_extreme, "humidity": mid})
    high_result = engine.infer_component("M", {"temperature": high_extreme, "humidity": mid})

    assert mid_result.class_degrees["Favorable"] == 1.0
    assert low_result.class_degrees["Critical"] == 1.0
    assert high_result.class_degrees["Critical"] == 1.0


def test_v_component_is_pass_through(engine):
    co2_degrees = {"Favorable": 0.0, "Acceptable": 1.0, "Degraded": 0.0, "Critical": 0.0}
    result = engine.infer_component("V", {"co2": co2_degrees})
    assert result.class_degrees == co2_degrees
    assert result.fired_rules == []


# --- determine_dominance: the manuscript's dominant adverse component, via
# the full priority hierarchy (max-firing rule -> most severe consequent ->
# causing antecedent(s) -> highest severity -> tie-break by normalized
# score). Exercised through the real engine (engine.infer_index), which is
# what actually calls determine_dominance in production -- these are not
# synthetic FiredRule lists, they are the real 2nd-level rule base firing
# against real membership degrees, matching every other test in this file. ---


def test_dominance_clearly_dominant_component(engine):
    degrees = {"A": _degrees("Critical"), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": "Critical", "V": "Favorable", "M": "Favorable"})
    dom = result.dominance
    assert dom.dominant_component == "A"
    assert dom.co_dominant_components == ["A"]
    assert dom.worst_component_class == "Critical"
    assert dom.largest_component_score == _REPRESENTATIVE_SCORE["Critical"]
    assert dom.dominance_reason == "unique_max_firing_rule"


def test_dominance_two_components_tied(engine):
    degrees = {"A": _degrees("Critical"), "V": _degrees("Favorable"), "M": _degrees("Critical")}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": "Critical", "V": "Favorable", "M": "Critical"})
    dom = result.dominance
    assert dom.co_dominant_components == ["A", "M"]
    assert dom.dominant_component == "A"  # alphabetically-first of the tie, deterministic
    assert dom.dominance_reason == "co_dominant_tie"


def test_dominance_all_favorable_ties_every_component(engine):
    degrees = {"A": _degrees("Favorable"), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": "Favorable", "V": "Favorable", "M": "Favorable"})
    dom = result.dominance
    assert dom.co_dominant_components == ["A", "M", "V"]
    assert dom.worst_component_class == "Favorable"
    assert dom.dominance_reason == "co_dominant_tie"


def test_dominance_one_critical_component_among_lesser_severities(engine):
    degrees = {"A": _degrees("Critical"), "V": _degrees("Degraded"), "M": _degrees("Acceptable")}
    result = _infer(engine, degrees, {"A", "V", "M"}, {"A": "Critical", "V": "Degraded", "M": "Acceptable"})
    dom = result.dominance
    assert dom.dominant_component == "A"
    assert dom.co_dominant_components == ["A"]
    assert dom.worst_component_class == "Critical"


def test_dominance_missing_component_under_partial_is_never_consulted(engine):
    # V is missing entirely (PARTIAL) -- must not appear anywhere in the result.
    degrees = {"A": _degrees("Critical"), "M": _degrees("Favorable")}
    result = _infer(engine, degrees, {"A", "M"}, {"A": "Critical", "M": "Favorable"})
    dom = result.dominance
    assert dom.dominant_component == "A"
    assert "V" not in dom.co_dominant_components
    assert dom.largest_component_score == _REPRESENTATIVE_SCORE["Critical"]


def test_dominance_equal_crisp_scores_but_different_memberships_favors_higher_severity_membership(engine):
    """The key case the priority hierarchy is FOR: two components with the
    SAME crisp score can still have a clear, non-arbitrary winner, because
    dominance is decided by rule-firing/antecedent severity, not by naive
    crisp-score comparison. A is purely Degraded (degree 1.0); M is half
    Degraded / half Critical (0.5 each) -- despite an engineered tie in
    crisp_score, M's antecedent reaches Critical severity and wins."""
    degrees = {
        "A": {"Favorable": 0.0, "Acceptable": 0.0, "Degraded": 1.0, "Critical": 0.0},
        "V": _degrees("Favorable"),
        "M": {"Favorable": 0.0, "Acceptable": 0.0, "Degraded": 0.5, "Critical": 0.5},
    }
    scores = {"A": 60.0, "V": 10.0, "M": 60.0}  # equal scores for A and M by construction
    result = engine.infer_index(degrees, {"A", "V", "M"}, scores, dominant_component_tie_tolerance=1.0)
    dom = result.dominance
    assert dom.dominant_component == "M"
    assert dom.co_dominant_components == ["M"]
    assert dom.dominance_reason == "tie_broken_by_normalized_score"


def test_determine_dominance_no_rules_fired_returns_none():
    result = determine_dominance(fired_rules=[], component_degrees={}, component_crisp_scores={}, tie_tolerance=1.0)
    assert result.dominant_component is None
    assert result.co_dominant_components == []
    assert result.dominance_reason == "no_rules_fired"


# --- rule_level_contributors: diagnostic only, distinct from determine_dominance ---


def test_rule_level_contributors_single_winner():
    rule = Rule(antecedents=(("A", "Critical"), ("V", "Favorable")), consequent_class="Critical", level=2)
    fired = [FiredRule(rule=rule, antecedent_degrees={"A": 0.3, "V": 0.9}, firing_strength=0.3)]
    assert rule_level_contributors(fired) == ["A"]


def test_rule_level_contributors_ties_preserved():
    rule = Rule(antecedents=(("A", "Critical"), ("V", "Critical")), consequent_class="Critical", level=2)
    fired = [FiredRule(rule=rule, antecedent_degrees={"A": 0.5, "V": 0.5}, firing_strength=0.5)]
    assert rule_level_contributors(fired) == ["A", "V"]


def test_rule_level_contributors_empty_when_nothing_fires():
    rule = Rule(antecedents=(("A", "Favorable"),), consequent_class="Favorable", level=1)
    fired = [FiredRule(rule=rule, antecedent_degrees={"A": 0.0}, firing_strength=0.0)]
    assert rule_level_contributors(fired) == []
