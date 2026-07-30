"""Plain data containers passed between pipeline stages.

These are intentionally not pydantic models: they are internal computation
results (produced many times per run, in hot loops), not user-facing
configuration that needs parsing/validation from YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CoverageResult:
    """Result of the coverage check ρ = n_usable / n_expected for one channel/window."""

    n_expected: int
    n_usable: int
    ratio: float
    ok: bool


@dataclass(frozen=True)
class AggregateResult:
    """Time-weighted aggregate for one direct-input channel over one window."""

    channel: str
    window_start: datetime
    window_end: datetime
    coverage: CoverageResult
    weighted_mean: float | None


@dataclass(frozen=True)
class Rule:
    """One Mamdani rule.

    ``antecedents`` is a tuple of (input_name, class_name) pairs, kept sorted
    by input_name so equal rules compare equal and rule bases are
    deterministically ordered.
    """

    antecedents: tuple[tuple[str, str], ...]
    consequent_class: str
    level: int

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.antecedents, key=lambda pair: pair[0]))
        object.__setattr__(self, "antecedents", ordered)


@dataclass(frozen=True)
class FiredRule:
    """A rule together with its computed firing strength for one evaluation."""

    rule: Rule
    antecedent_degrees: dict[str, float]
    firing_strength: float


@dataclass
class ComponentInferenceResult:
    """Output of evaluating one first-level component (A, V, or M)."""

    component: str
    class_degrees: dict[str, float]
    crisp_score: float
    fired_rules: list[FiredRule] = field(default_factory=list)


@dataclass(frozen=True)
class DominanceResult:
    """The manuscript's dominant adverse component, determined by a
    deterministic priority hierarchy over the fired 2nd-level rules (see
    :func:`iaq_hfis.fuzzy_engine.determine_dominance` for the full
    algorithm): (1) the max-firing 2nd-level rule(s), within a tiny
    floating-point tolerance; (2) among those, the most severe consequent
    class; (3) the antecedent component(s) that caused it (bound the rule's
    own min()); (4) among those, the highest-severity antecedent class
    actually attained; (5) tie-break by larger normalized crisp score,
    using the configured ``membership.dominant_component_tie_tolerance``.

    ``dominant_component`` is the single, deterministically-chosen primary
    component (first alphabetically among any final tie).
    ``co_dominant_components`` is every component tied for dominance at the
    end of the hierarchy (length 1 unless a genuine, documented tie
    survived every step, including ``dominant_component`` itself).
    ``worst_component_class`` is the highest-severity class reached by ANY
    available component's own dominant class -- independent of the
    tie-breaking mechanics above, a plain summary of "how bad did any one
    component get".
    ``largest_component_score`` is simply max(component_crisp_scores) among
    available components.
    ``dominance_reason`` documents which step of the hierarchy actually
    resolved the choice (or that no rule fired at all).
    """

    dominant_component: str | None
    co_dominant_components: list[str]
    worst_component_class: str | None
    largest_component_score: float | None
    dominance_reason: str


@dataclass
class IndexInferenceResult:
    """Output of the second-level (index) Mamdani inference.

    ``dominance`` is the manuscript's dominant adverse component, see
    :class:`DominanceResult`. ``rule_level_contributors`` is a SEPARATE,
    older diagnostic: which component(s) "bound" the min() across every
    fired rule regardless of firing strength or consequent severity --
    useful for debugging overall rule activation, but NOT the manuscript's
    dominant adverse component and must never be confused with it.
    """

    output_class_degrees: dict[str, float]
    index_value: float | None
    index_class: str | None
    dominance: DominanceResult
    rule_level_contributors: list[str] = field(default_factory=list)
    fired_rules: list[FiredRule] = field(default_factory=list)

    @property
    def n_rules_fired(self) -> int:
        return sum(1 for fr in self.fired_rules if fr.firing_strength > 0.0)


@dataclass(frozen=True)
class CompletenessResult:
    """OK / PARTIAL / FAILED status for one computed timestamp."""

    status: str
    missing_components: list[str]
    missing_inputs: list[str]
