import numpy as np
import pytest

from iaq_hfis.constants import CLASS_ORDER, OUTPUT_MAX, OUTPUT_MIN
from iaq_hfis.fuzzy_engine import MamdaniEngine, classify_output, dominant_components
from iaq_hfis.membership import build_monotonic_classes
from iaq_hfis.models import FiredRule, Rule
from iaq_hfis.rules import build_rule_base


@pytest.fixture
def engine():
    output_shapes = build_monotonic_classes([25.0, 50.0, 75.0], [2.0, 2.0, 2.0])
    universe = np.linspace(OUTPUT_MIN, OUTPUT_MAX, 401)
    return MamdaniEngine(build_rule_base(), output_shapes, universe)


def _degrees(favorable_cls: str) -> dict:
    return {cls: (1.0 if cls == favorable_cls else 0.0) for cls in CLASS_ORDER}


@pytest.mark.parametrize("out_class,expected_low,expected_high", [("Favorable", 0, 25), ("Acceptable", 25, 50), ("Degraded", 50, 75), ("Critical", 75, 100)])
def test_pure_class_index_lands_in_expected_range(engine, out_class, expected_low, expected_high):
    degrees = {"A": _degrees(out_class), "V": _degrees(out_class), "M": _degrees(out_class)}
    result = engine.infer_index(degrees, {"A", "V", "M"})
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
    result = engine.infer_index(degrees, {"A", "V", "M"})
    assert result.index_class == "Favorable"


def test_one_critical_component_prevents_favorable_result(engine):
    degrees = {"A": _degrees("Critical"), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
    result = engine.infer_index(degrees, {"A", "V", "M"})
    assert result.index_class != "Favorable"
    assert result.index_class == "Critical"


def test_monotonic_worsening_never_improves_index(engine):
    prior_value = 0.0
    for cls in CLASS_ORDER:
        degrees = {"A": _degrees(cls), "V": _degrees("Favorable"), "M": _degrees("Favorable")}
        result = engine.infer_index(degrees, {"A", "V", "M"})
        assert result.index_value >= prior_value - 1e-9
        prior_value = result.index_value


def test_centroid_is_deterministic(engine):
    degrees = {"A": _degrees("Degraded"), "V": _degrees("Acceptable"), "M": _degrees("Favorable")}
    r1 = engine.infer_index(degrees, {"A", "V", "M"})
    r2 = engine.infer_index(degrees, {"A", "V", "M"})
    assert r1.index_value == r2.index_value


def test_partial_mode_two_components_favorable_gives_favorable(engine):
    degrees = {"A": _degrees("Favorable"), "V": _degrees("Favorable")}
    result = engine.infer_index(degrees, {"A", "V"})
    assert result.index_class == "Favorable"
    assert result.index_value < 25.0


def test_partial_mode_one_critical_component_gives_critical(engine):
    degrees = {"A": _degrees("Critical"), "M": _degrees("Favorable")}
    result = engine.infer_index(degrees, {"A", "M"})
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


def test_dominant_component_single_winner():
    rule = Rule(antecedents=(("A", "Critical"), ("V", "Favorable")), consequent_class="Critical", level=2)
    fired = [FiredRule(rule=rule, antecedent_degrees={"A": 0.3, "V": 0.9}, firing_strength=0.3)]
    assert dominant_components(fired) == ["A"]


def test_dominant_component_ties_preserved():
    rule = Rule(antecedents=(("A", "Critical"), ("V", "Critical")), consequent_class="Critical", level=2)
    fired = [FiredRule(rule=rule, antecedent_degrees={"A": 0.5, "V": 0.5}, firing_strength=0.5)]
    assert dominant_components(fired) == ["A", "V"]


def test_dominant_component_empty_when_nothing_fires():
    rule = Rule(antecedents=(("A", "Favorable"),), consequent_class="Favorable", level=1)
    fired = [FiredRule(rule=rule, antecedent_degrees={"A": 0.0}, firing_strength=0.0)]
    assert dominant_components(fired) == []


def test_v_component_is_pass_through(engine):
    co2_degrees = {"Favorable": 0.0, "Acceptable": 1.0, "Degraded": 0.0, "Critical": 0.0}
    result = engine.infer_component("V", {"co2": co2_degrees})
    assert result.class_degrees == co2_degrees
    assert result.fired_rules == []
