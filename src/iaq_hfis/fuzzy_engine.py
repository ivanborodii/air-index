"""Mamdani inference: AND = min, rule combination = max, defuzzification =
centroid, evaluated over both hierarchy levels.

The engine needs class-shaped output curves (built from
``control_regions.output`` via :mod:`iaq_hfis.membership`) to defuzzify. The
same curves are reused to give A and M a numeric ``crisp_score`` alongside
their fuzzy class degrees — this is NOT required by the manuscript's core
index computation (which only ever needs class degrees to feed the next
level's rules) but is exposed now so the Phase 2 FUZZY_COMPONENT_MAX / WEIGHTED_MEAN
baselines can reuse it without changes here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from iaq_hfis.constants import CLASS_ORDER, CLASS_SEVERITY, OUTPUT_BOUNDARIES
from iaq_hfis.membership import Shape, evaluate_memberships
from iaq_hfis.models import ComponentInferenceResult, DominanceResult, FiredRule, IndexInferenceResult, Rule
from iaq_hfis.rules import RuleBase, generate_component_rules

#: Floating-point tolerance for "same firing strength" (step 1 of
#: determine_dominance) -- deliberately tiny and NOT the configured
#: membership.dominant_component_tie_tolerance (which is a much coarser,
#: index-point-scale tolerance used only at the final score tie-break step).
_FIRING_STRENGTH_EPS = 1e-9


def _own_dominant_class(class_degrees: dict[str, float]) -> str | None:
    """The single class a component's own membership degrees favor most.
    Ties in degree (e.g. exactly at a crossover point) resolve to the
    more severe of the tied classes, consistent with this codebase's
    worst-of philosophy everywhere else (rules.py, masking, etc.)."""
    if not class_degrees:
        return None
    max_degree = max(class_degrees.values())
    tied = [c for c in CLASS_ORDER if class_degrees.get(c) == max_degree]
    if not tied:
        return None
    return max(tied, key=lambda c: CLASS_SEVERITY[c])


def determine_dominance(
    fired_rules: list[FiredRule],
    component_degrees: dict[str, dict[str, float]],
    component_crisp_scores: dict[str, float],
    tie_tolerance: float,
) -> DominanceResult:
    """The manuscript's dominant adverse component, via a deterministic
    priority hierarchy over the 2nd-level (index) fired rules:

    1. The max-firing rule(s), within a tiny floating-point tolerance
       (:data:`_FIRING_STRENGTH_EPS` -- NOT the configured score tolerance).
    2. Among those, the rule(s) with the most severe consequent class.
    3. The antecedent component(s) that CAUSED that consequent -- i.e.
       whichever antecedent(s) attained each such rule's own minimum degree
       (the one(s) that actually constrained its firing strength).
    4. Among those causing components, keep only the one(s) whose own
       antecedent class (in the rules that named them) reached the highest
       severity.
    5. Tie-break by larger normalized crisp score, using the configured
       ``tie_tolerance`` (index points) -- components remaining within
       tolerance of the maximum score are kept as a documented co-dominant
       tie; the deterministic primary is the alphabetically-first of them.

    See :class:`iaq_hfis.models.DominanceResult` for the returned fields.
    """
    scored = {c: s for c, s in component_crisp_scores.items() if s is not None}
    largest_component_score = max(scored.values()) if scored else None
    own_classes = [cls for cls in (_own_dominant_class(cd) for cd in component_degrees.values()) if cls is not None]
    worst_component_class = max(own_classes, key=lambda c: CLASS_SEVERITY[c]) if own_classes else None

    active = [fr for fr in fired_rules if fr.firing_strength > 0]
    if not active:
        return DominanceResult(
            dominant_component=None, co_dominant_components=[],
            worst_component_class=worst_component_class, largest_component_score=largest_component_score,
            dominance_reason="no_rules_fired",
        )

    # Step 1: max-firing rule(s), floating-point-safe tolerance only.
    max_strength = max(fr.firing_strength for fr in active)
    top_by_strength = [fr for fr in active if max_strength - fr.firing_strength <= _FIRING_STRENGTH_EPS]

    # Step 2: among those, the most severe consequent class.
    max_consequent_severity = max(CLASS_SEVERITY[fr.rule.consequent_class] for fr in top_by_strength)
    top_by_consequent = [fr for fr in top_by_strength if CLASS_SEVERITY[fr.rule.consequent_class] == max_consequent_severity]

    # Step 3 + 4: the antecedent component(s) causing that consequent, kept only at
    # the highest severity any of them actually attained across the selected rules.
    component_best_severity: dict[str, int] = {}
    for fr in top_by_consequent:
        min_degree = min(fr.antecedent_degrees.values())
        for name, cls in fr.rule.antecedents:
            if fr.antecedent_degrees[name] == min_degree:
                sev = CLASS_SEVERITY[cls]
                component_best_severity[name] = max(component_best_severity.get(name, -1), sev)
    max_component_severity = max(component_best_severity.values())
    finalists = sorted(name for name, sev in component_best_severity.items() if sev == max_component_severity)

    # Step 5: tie-break by larger normalized score.
    finalist_scores = {c: scored[c] for c in finalists if c in scored}
    if not finalist_scores:
        co_dominant = finalists
        reason = "tied_no_score_available"
    else:
        max_score = max(finalist_scores.values())
        co_dominant = sorted(c for c in finalists if c in finalist_scores and (max_score - finalist_scores[c]) <= tie_tolerance)
        if len(top_by_strength) == 1 and len(top_by_consequent) == 1 and len(co_dominant) == 1:
            reason = "unique_max_firing_rule"
        elif len(co_dominant) > 1:
            reason = "co_dominant_tie"
        else:
            reason = "tie_broken_by_normalized_score"

    dominant = co_dominant[0] if co_dominant else (finalists[0] if finalists else None)
    return DominanceResult(
        dominant_component=dominant, co_dominant_components=co_dominant,
        worst_component_class=worst_component_class, largest_component_score=largest_component_score,
        dominance_reason=reason,
    )


def rule_level_contributors(fired_rules: list[FiredRule]) -> list[str]:
    """Diagnostic only -- NOT the manuscript's dominant adverse component
    (see :func:`determine_dominance`). The component(s) most
    responsible for the activated rules: for every rule with
    firing_strength > 0, its "binding" component(s) are whichever
    antecedent(s) attained the rule's minimum degree (the one(s) that
    actually constrained the min). Each binding component accumulates the
    rule's firing strength; the result is every component tied for the
    highest accumulated score -- ties are preserved, never arbitrarily
    broken.
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
    """Favourable [0,25) / Acceptable [25,50) / Degraded [50,75) / Critical [75,100] —
    boundary values map to the less-favourable class (manuscript, output scale only)."""
    b0, b1, b2 = OUTPUT_BOUNDARIES
    if value < b0:
        return "Favourable"
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

    def infer_index(
        self,
        component_degrees: dict[str, dict[str, float]],
        available_components: set[str],
        component_crisp_scores: dict[str, float],
        dominant_component_tie_tolerance: float,
    ) -> IndexInferenceResult:
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
        # Dominance is computed from available components only -- PARTIAL
        # naturally considers only those, since unavailable components have
        # no crisp score and never appear in component_degrees/fired rules.
        available_crisp_scores = {c: s for c, s in component_crisp_scores.items() if c in available_components}
        available_degrees = {c: d for c, d in component_degrees.items() if c in available_components}
        dominance = determine_dominance(fired, available_degrees, available_crisp_scores, dominant_component_tie_tolerance)
        contributors = rule_level_contributors(fired)
        return IndexInferenceResult(
            output_class_degrees=class_activation,
            index_value=index_value,
            index_class=index_class,
            dominance=dominance,
            rule_level_contributors=contributors,
            fired_rules=fired,
        )
