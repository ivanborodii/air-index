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


@dataclass
class IndexInferenceResult:
    """Output of the second-level (index) Mamdani inference.

    ``dominant_components`` is the manuscript's dominant adverse
    component(s): the available component(s) with the highest adverse crisp
    score, ties preserved only within a configurable tolerance (see
    :func:`iaq_hfis.fuzzy_engine.dominant_adverse_component`).
    ``rule_level_contributors`` is a separate diagnostic: which
    component(s) "bound" the min() in the fired Mamdani rules -- useful for
    debugging rule activation, but NOT the manuscript's dominant adverse
    component and must never be confused with it.
    """

    output_class_degrees: dict[str, float]
    index_value: float | None
    index_class: str | None
    dominant_components: list[str]
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
