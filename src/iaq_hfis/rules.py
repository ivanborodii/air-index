"""Fuzzy rule-base generation.

Every combination rule uses a worst-of (max severity rank) consequent. This
single choice is what makes the three "priority of the worst component"
properties from the manuscript hold simultaneously and provably, rather
than needing to be checked rule-by-rule:

- **Monotonic**: worsening any one antecedent input can only raise (or
  leave unchanged) ``max(severity(...))`` — it can never lower it, so
  worsening an input never improves the consequent.
- **One critical input forces Critical**: if any antecedent class is
  Critical (severity 3, the maximum), the max is 3 regardless of the other
  antecedents.
- **All-favorable implies Favorable**: the max of an all-zero-severity
  tuple is 0 (Favorable) only when every antecedent is Favorable.

``V`` (ventilation, single input CO2) needs no combination rules — it is
evaluated directly from CO2's own membership degrees in
:mod:`iaq_hfis.fuzzy_engine`.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from iaq_hfis.constants import CLASS_ORDER, CLASS_SEVERITY
from iaq_hfis.models import Rule

#: Identifies the rule-GENERATION algorithm itself (Cartesian product +
#: worst-of/max-severity consequent), independent of the package version --
#: bump this if the generation strategy ever changes, for reproducibility
#: metadata (see iaq_hfis.reproducibility).
RULE_GENERATION_VERSION = "worst-of-max-severity-v1"


def generate_component_rules(input_names: list[str], level: int) -> list[Rule]:
    """Cartesian product over CLASS_ORDER for each input; consequent = the
    antecedent class with the highest severity rank (ties broken by rank
    equality — CLASS_SEVERITY has no ties, so this is always unambiguous)."""
    rules = []
    for combo in itertools.product(CLASS_ORDER, repeat=len(input_names)):
        antecedents = tuple(zip(input_names, combo))
        worst = max(combo, key=lambda c: CLASS_SEVERITY[c])
        rules.append(Rule(antecedents=antecedents, consequent_class=worst, level=level))
    return sorted(rules, key=lambda r: r.antecedents)


@dataclass(frozen=True)
class RuleBase:
    aerosol_rules: tuple[Rule, ...]       # A <- (pm2_5, pm10), 16 rules
    microclimate_rules: tuple[Rule, ...]  # M <- (temperature, humidity), 16 rules
    index_rules: tuple[Rule, ...]         # I <- (A, V, M), 64 rules

    @property
    def total_count(self) -> int:
        return len(self.aerosol_rules) + len(self.microclimate_rules) + len(self.index_rules)


def build_rule_base() -> RuleBase:
    """Deterministic rule base: 16 + 16 + 64 = 96 combination rules total."""
    return RuleBase(
        aerosol_rules=tuple(generate_component_rules(["pm2_5", "pm10"], level=1)),
        microclimate_rules=tuple(generate_component_rules(["temperature", "humidity"], level=1)),
        index_rules=tuple(generate_component_rules(["A", "V", "M"], level=2)),
    )
