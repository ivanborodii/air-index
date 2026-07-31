"""Multi-component grid experiment (manuscript-validation task spec section
7.2): a fully reproducible, deterministic sweep of independent (A, V, M)
component crisp scores across a configurable regular grid (default 41
values per axis, 0-100 -> 41^3 = 68,921 combinations), comparing all four
methods directly at the component level.

This converts the standalone ad-hoc script referenced in
docs/hfis_vs_crispmax_audit.md section 2 (which first established that
PROPOSED_HFIS is NOT numerically equivalent to FUZZY_COMPONENT_MAX once more
than one component carries a non-trivial score) into a first-class, tested,
CLI-integrated, exported evaluation artifact -- same underlying comparison,
now reproducible and part of the persisted run record rather than a one-off.

Component crisp scores already share the exact same 0-100 scale and
[25, 50, 75] class boundaries as the final index (see
:func:`iaq_hfis.fuzzy_engine.classify_output` and
:mod:`iaq_hfis.baselines`'s module docstring), so:

- PROPOSED_HFIS is evaluated via the *real* 2nd-level Mamdani engine
  (``ctx.engine.infer_index``), fed class-degree vectors derived from that
  same output-scale membership -- not a separate/simplified computation.
- CRISP_CLASS_MAX hard-classifies each component score with the identical
  [25, 50, 75] breakpoints (:func:`iaq_hfis.fuzzy_engine.classify_output`):
  there is no raw direct-input value at this abstraction level to classify
  with a channel-specific control region, unlike
  :func:`iaq_hfis.baselines.crisp_class_max`, which operates on real direct
  inputs elsewhere in the evaluation suite.

Rows are stored WIDE (one row per (A, V, M) combination, one column pair per
method) rather than long/tidy-per-method -- deliberately, since this
experiment is 41^3 = 68,921 points; a long table would be 4x that many rows
for no analytical benefit here (every downstream consumer wants all four
methods' outcomes for the same triple side by side).

This is a deterministic numerical experiment, not a statistical one: the
same grid every time, no randomness, so results are exactly reproducible.
It also does not depend on any pipeline run's actual sensor data -- only on
the configured rule base and membership shapes -- so it is identical for
every evaluation run over the same effective config.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from iaq_hfis import membership
from iaq_hfis.baselines import CLASS_MIDPOINT, BaselineResult, fuzzy_component_max, weighted_mean
from iaq_hfis.constants import CLASS_SEVERITY
from iaq_hfis.fuzzy_engine import classify_output
from iaq_hfis.pipeline import RuntimeContext

METHODS = ["PROPOSED_HFIS", "FUZZY_COMPONENT_MAX", "CRISP_CLASS_MAX", "WEIGHTED_MEAN"]


@dataclass(frozen=True)
class GridRow:
    a: float
    v: float
    m: float
    hfis_index_value: float | None
    hfis_index_class: str | None
    fuzzy_component_max_index_value: float | None
    fuzzy_component_max_index_class: str | None
    crisp_class_max_index_value: float | None
    crisp_class_max_index_class: str | None
    weighted_mean_index_value: float | None
    weighted_mean_index_class: str | None

    def value_and_class(self, method: str) -> tuple[float | None, str | None]:
        return {
            "PROPOSED_HFIS": (self.hfis_index_value, self.hfis_index_class),
            "FUZZY_COMPONENT_MAX": (self.fuzzy_component_max_index_value, self.fuzzy_component_max_index_class),
            "CRISP_CLASS_MAX": (self.crisp_class_max_index_value, self.crisp_class_max_index_class),
            "WEIGHTED_MEAN": (self.weighted_mean_index_value, self.weighted_mean_index_class),
        }[method]


@dataclass(frozen=True)
class GridPairSummary:
    method_a: str
    method_b: str
    n_points: int
    mean_abs_diff: float | None
    median_abs_diff: float | None
    p95_abs_diff: float | None
    max_abs_diff: float | None
    mean_signed_diff: float | None  # mean(method_a - method_b)
    class_agreement_rate: float | None
    n_class_disagreements: int


def _crisp_class_max_from_component_scores(scores: dict[str, float]) -> BaselineResult:
    """CRISP_CLASS_MAX at the component-score level (no raw direct inputs
    exist here -- see module docstring): hard-classify each component score
    with the shared output-scale breakpoints, take the most adverse."""
    classes = {c: classify_output(v) for c, v in scores.items()}
    overall = max(classes.values(), key=lambda c: CLASS_SEVERITY[c])
    return BaselineResult(method="CRISP_CLASS_MAX", index_value=CLASS_MIDPOINT[overall], index_class=overall, n_components=len(scores))


def _hfis_from_component_scores(ctx: RuntimeContext, scores: dict[str, float]) -> tuple[float | None, str | None]:
    output_shapes = ctx.static_shapes["output"]
    component_degrees = {c: membership.evaluate_memberships(v, output_shapes) for c, v in scores.items()}
    index_result = ctx.engine.infer_index(
        component_degrees, set(scores.keys()), scores, ctx.settings.membership.dominant_component_tie_tolerance
    )
    return index_result.index_value, index_result.index_class


def run_multi_component_grid(ctx: RuntimeContext, n_points_per_axis: int) -> list[GridRow]:
    """Every combination of a linspace(0, 100, n_points_per_axis) grid across
    A, V, M -- e.g. n_points_per_axis=41 gives 41^3 = 68,921 combinations,
    matching the task spec's own worked example exactly. All three
    components are always present (this is a synthetic, fully-populated
    grid -- completeness/PARTIAL behavior is exercised elsewhere)."""
    axis = np.linspace(0.0, 100.0, n_points_per_axis)
    rows: list[GridRow] = []
    for a in axis:
        for v in axis:
            for m in axis:
                scores = {"A": float(a), "V": float(v), "M": float(m)}
                hfis_value, hfis_class = _hfis_from_component_scores(ctx, scores)
                cm = fuzzy_component_max(scores)
                ccm = _crisp_class_max_from_component_scores(scores)
                wm = weighted_mean(scores)
                rows.append(
                    GridRow(
                        a=float(a), v=float(v), m=float(m),
                        hfis_index_value=hfis_value, hfis_index_class=hfis_class,
                        fuzzy_component_max_index_value=cm.index_value, fuzzy_component_max_index_class=cm.index_class,
                        crisp_class_max_index_value=ccm.index_value, crisp_class_max_index_class=ccm.index_class,
                        weighted_mean_index_value=wm.index_value, weighted_mean_index_class=wm.index_class,
                    )
                )
    return rows


def summarize_multi_component_grid(rows: list[GridRow]) -> list[GridPairSummary]:
    """One row per unordered method pair (6 pairs for 4 methods), computed
    directly from ``rows`` -- never independently recomputed, so this is the
    same object run_summary.json, the narrative, and the artifact validator
    all see."""
    summaries = []
    for method_a, method_b in combinations(METHODS, 2):
        diffs: list[float] = []
        signed: list[float] = []
        n_agree = 0
        n_compared = 0
        for row in rows:
            va, ca = row.value_and_class(method_a)
            vb, cb = row.value_and_class(method_b)
            if va is None or vb is None:
                continue
            diffs.append(abs(va - vb))
            signed.append(va - vb)
            n_compared += 1
            if ca == cb:
                n_agree += 1
        arr = np.array(diffs) if diffs else None
        summaries.append(
            GridPairSummary(
                method_a=method_a,
                method_b=method_b,
                n_points=n_compared,
                mean_abs_diff=float(arr.mean()) if arr is not None else None,
                median_abs_diff=float(np.median(arr)) if arr is not None else None,
                p95_abs_diff=float(np.percentile(arr, 95)) if arr is not None else None,
                max_abs_diff=float(arr.max()) if arr is not None else None,
                mean_signed_diff=float(np.mean(signed)) if signed else None,
                class_agreement_rate=(n_agree / n_compared) if n_compared else None,
                n_class_disagreements=n_compared - n_agree,
            )
        )
    return summaries


def weighted_mean_masking_rate(rows: list[GridRow], severity_threshold: str = "Critical") -> dict:
    """Adverse-component masking on the grid: among triples where at least
    one component reaches ``severity_threshold`` or worse, what fraction
    does WEIGHTED_MEAN fail to classify at that severity? Same masking
    definition as :mod:`iaq_hfis.evaluation.masking`, applied here to the
    full synthetic grid rather than real timestamps."""
    threshold_severity = CLASS_SEVERITY[severity_threshold]
    n_critical_events = 0
    n_masked = 0
    for row in rows:
        component_classes = {"A": classify_output(row.a), "V": classify_output(row.v), "M": classify_output(row.m)}
        if not any(CLASS_SEVERITY[cls] >= threshold_severity for cls in component_classes.values()):
            continue
        n_critical_events += 1
        wm_severity = CLASS_SEVERITY[row.weighted_mean_index_class] if row.weighted_mean_index_class else -1
        if wm_severity < threshold_severity:
            n_masked += 1
    return {
        "severity_threshold": severity_threshold,
        "n_critical_events": n_critical_events,
        "n_masked": n_masked,
        "masking_rate": (n_masked / n_critical_events) if n_critical_events else None,
    }
