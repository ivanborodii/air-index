import numpy as np
import pytest

from iaq_hfis.constants import CLASS_ORDER, OUTPUT_MAX, OUTPUT_MIN
from iaq_hfis.fuzzy_engine import MamdaniEngine, classify_output, dominant_adverse_component, rule_level_contributors
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


# --- dominant_adverse_component: the manuscript's dominant adverse component ---


def test_dominant_adverse_component_unique_winner():
    scores = {"A": 90.0, "V": 40.0, "M": 20.0}
    assert dominant_adverse_component(scores, tie_tolerance=1.0) == ["A"]


def test_dominant_adverse_component_exact_tie_preserved():
    scores = {"A": 80.0, "V": 80.0, "M": 20.0}
    assert dominant_adverse_component(scores, tie_tolerance=1.0) == ["A", "V"]


def test_dominant_adverse_component_near_tie_within_tolerance_preserved():
    scores = {"A": 80.0, "V": 79.4, "M": 20.0}
    assert dominant_adverse_component(scores, tie_tolerance=1.0) == ["A", "V"]


def test_dominant_adverse_component_near_tie_outside_tolerance_excludes_lower():
    scores = {"A": 80.0, "V": 77.0, "M": 20.0}
    assert dominant_adverse_component(scores, tie_tolerance=1.0) == ["A"]


def test_dominant_adverse_component_partial_considers_only_available():
    # M has no crisp score at all (not passed in) -- PARTIAL naturally excludes it.
    scores = {"A": 50.0, "V": 90.0}
    assert dominant_adverse_component(scores, tie_tolerance=1.0) == ["V"]


def test_dominant_adverse_component_empty_for_failed():
    assert dominant_adverse_component({}, tie_tolerance=1.0) == []


# --- rule_level_contributors: diagnostic only, distinct from dominant_adverse_component ---


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
