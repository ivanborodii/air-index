"""Mamdani inference: AND = min, rule combination = max, defuzzification =
centroid, evaluated over both hierarchy levels.

The engine needs class-shaped output curves (built from
``control_regions.output`` via :mod:`iaq_hfis.membership`) to defuzzify. The
same curves are reused to give A and M a numeric ``crisp_score`` alongside
their fuzzy class degrees — this is NOT required by the manuscript's core
index computation (which only ever needs class degrees to feed the next
level's rules) but is exposed now so the Phase 2 CRISP-MAX / WEIGHTED-MEAN
baselines can reuse it without changes here.
"""

from __future__ import annotations

import numpy as np

from iaq_hfis.constants import CLASS_ORDER, OUTPUT_BOUNDARIES
from iaq_hfis.membership import Shape, evaluate_memberships
from iaq_hfis.models import ComponentInferenceResult, FiredRule, IndexInferenceResult, Rule
from iaq_hfis.rules import RuleBase, generate_component_rules


def dominant_components(fired_rules: list[FiredRule]) -> list[str]:
    """The component(s) most responsible for the activated rules.

    For every rule with firing_strength > 0, its "binding" component(s) are
    whichever antecedent(s) attained the rule's minimum degree (the one(s)
    that actually constrained the min). Each binding component accumulates
    the rule's firing strength; the result is every component tied for the
    highest accumulated score — ties are preserved, never arbitrarily broken.
    """
    scores: dict[str, float] = {}
    for fr in fired_rules:
        if fr.firing_strength <= 0:
            continue
        min_degree = min(fr.antecedent_degrees.values())
        for name, degree in fr.antecedent_degrees.items():
            if degree == min_degree:
                scores[name] = scores.get(name, 0.0) + fr.firing_strength
    if not scores:
        return []
    max_score = max(scores.values())
    return sorted(name for name, s in scores.items() if s == max_score)


def classify_output(value: float) -> str:
    """Favorable [0,25) / Acceptable [25,50) / Degraded [50,75) / Critical [75,100] —
    boundary values map to the less-favorable class (manuscript, output scale only)."""
    b0, b1, b2 = OUTPUT_BOUNDARIES
    if value < b0:
        return "Favorable"
    if value < b1:
        return "Acceptable"
    if value < b2:
        return "Degraded"
    return "Critical"


class MamdaniEngine:
    def __init__(self, rule_base: RuleBase, output_class_shapes: dict[str, list[Shape]], output_universe: np.ndarray) -> None:
        self.rule_base = rule_base
        self.output_universe = output_universe
        self._output_class_curves = {
            cls: np.array([evaluate_memberships(u, output_class_shapes)[cls] for u in output_universe]) for cls in CLASS_ORDER
        }

    def _fire_rules(self, rules: tuple[Rule, ...], input_memberships: dict[str, dict[str, float]]) -> tuple[dict[str, float], list[FiredRule]]:
        class_activation = {c: 0.0 for c in CLASS_ORDER}
        fired: list[FiredRule] = []
        for rule in rules:
            degrees = {name: input_memberships[name][cls] for name, cls in rule.antecedents}
            strength = min(degrees.values())
            fired.append(FiredRule(rule=rule, antecedent_degrees=degrees, firing_strength=strength))
            if strength > class_activation[rule.consequent_class]:
                class_activation[rule.consequent_class] = strength
        return class_activation, fired

    def _centroid(self, class_activation: dict[str, float]) -> float | None:
        agg = np.zeros_like(self.output_universe, dtype=float)
        for cls, alpha in class_activation.items():
            if alpha <= 0:
                continue
            agg = np.maximum(agg, np.minimum(self._output_class_curves[cls], alpha))
        total = agg.sum()
        if total <= 0:
            return None
        return float((self.output_universe * agg).sum() / total)

    def infer_component(self, component: str, input_memberships: dict[str, dict[str, float]]) -> ComponentInferenceResult:
        """``component`` is "A", "V", or "M". V is a single-input pass-through
        (its class degrees ARE the CO2 membership degrees, no rule firing)."""
        if component == "V":
            ((_name, degrees),) = input_memberships.items()
            crisp = self._centroid(degrees)
            return ComponentInferenceResult(component="V", class_degrees=degrees, crisp_score=crisp if crisp is not None else 0.0, fired_rules=[])

        rules = self.rule_base.aerosol_rules if component == "A" else self.rule_base.microclimate_rules
        class_activation, fired = self._fire_rules(rules, input_memberships)
        crisp = self._centroid(class_activation)
        return ComponentInferenceResult(component=component, class_degrees=class_activation, crisp_score=crisp if crisp is not None else 0.0, fired_rules=fired)

    def infer_index(self, component_degrees: dict[str, dict[str, float]], available_components: set[str]) -> IndexInferenceResult:
        """Second-level inference. When ``available_components`` is a proper
        subset of {A, V, M} (completeness status PARTIAL), a fresh worst-of
        rule set is generated over just the available components, rather
        than reusing the full 3-input rule base with the missing component
        filtered out of each rule's antecedents.

        Filtering antecedents while keeping a rule's original 3-input
        consequent is unsound: for a fixed pair of available-component
        classes, every one of the 4 original rules that vary only in the
        missing component's class would fire with the same (filtered)
        strength but different original consequents, activating all 4
        output classes at once. Regenerating the rules directly from the
        available inputs (same worst-of consequent rule as the full rule
        base) avoids that entirely. PROVISIONAL design choice: the
        manuscript does not specify PARTIAL-mode inference mechanics.
        """
        if available_components == {"A", "V", "M"}:
            rules = self.rule_base.index_rules
        else:
            rules = generate_component_rules(sorted(available_components), level=2)

        class_activation, fired = self._fire_rules(rules, component_degrees)

        index_value = self._centroid(class_activation)
        index_class = classify_output(index_value) if index_value is not None else None
        dominant = dominant_components(fired)
        return IndexInferenceResult(
            output_class_degrees=class_activation,
            index_value=index_value,
            index_class=index_class,
            dominant_components=dominant,
            fired_rules=fired,
        )
