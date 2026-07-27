"""CRISP-MAX and WEIGHTED-MEAN baselines from the manuscript's comparative
evaluation protocol.

Both baselines are computed from the *same* per-component crisp scores the
Mamdani engine already produces (:class:`iaq_hfis.models.ComponentInferenceResult.crisp_score`,
a centroid on the identical 0-100 output scale as the proposed index) —
no separate scoring logic, only a different aggregation.

- **CRISP-MAX** reproduces a prior paper's logic: the hard max of the
  normalized component scores. A single unfavorable component always
  dominates the result.
- **WEIGHTED-MEAN** is a neutral baseline: the equal-weight arithmetic mean
  of the available component scores. No expert weighting.

Both degrade over available components only, exactly like PROPOSED-HFIS's
own PARTIAL-mode handling — not a special case.
"""

from __future__ import annotations

from dataclasses import dataclass

from iaq_hfis.fuzzy_engine import classify_output


@dataclass(frozen=True)
class BaselineResult:
    method: str  # "CRISP-MAX" | "WEIGHTED-MEAN"
    index_value: float | None
    index_class: str | None
    n_components: int


def crisp_max(component_crisp_scores: dict[str, float]) -> BaselineResult:
    """Hard max of the available component scores.

    Structurally cannot mask a critical component: if any component's
    crisp_score falls in the Critical range [75,100], the max is >= 75 too,
    so the classified output is Critical as well (see
    :mod:`iaq_hfis.evaluation.masking` for the corresponding test).
    """
    if not component_crisp_scores:
        return BaselineResult(method="CRISP-MAX", index_value=None, index_class=None, n_components=0)
    value = max(component_crisp_scores.values())
    return BaselineResult(method="CRISP-MAX", index_value=value, index_class=classify_output(value), n_components=len(component_crisp_scores))


def weighted_mean(component_crisp_scores: dict[str, float]) -> BaselineResult:
    """Equal-weight arithmetic mean of the available component scores."""
    if not component_crisp_scores:
        return BaselineResult(method="WEIGHTED-MEAN", index_value=None, index_class=None, n_components=0)
    value = sum(component_crisp_scores.values()) / len(component_crisp_scores)
    return BaselineResult(method="WEIGHTED-MEAN", index_value=value, index_class=classify_output(value), n_components=len(component_crisp_scores))
