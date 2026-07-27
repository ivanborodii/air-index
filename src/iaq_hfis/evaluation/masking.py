"""Masking: how often a baseline's aggregation hides a component that was
individually unfavorable.

A "masking event" is a computed_ts where at least one available component's
own class (via ``classify_output(component.crisp_score)``, the same 0-100
scale and boundaries the final index uses) reaches ``severity_threshold``,
but the baseline's aggregated class does not.

CRISP-MAX cannot mask by construction: it IS the max of the component
scores, so if any component reaches the threshold severity, so does the
max — this is a structural property, verified directly rather than only
empirically (see the corresponding test).
"""

from __future__ import annotations

from dataclasses import dataclass

from iaq_hfis.baselines import BaselineResult
from iaq_hfis.constants import CLASS_SEVERITY
from iaq_hfis.fuzzy_engine import classify_output


@dataclass(frozen=True)
class MaskingResult:
    method: str
    severity_threshold: str
    n_critical_events: int
    n_masked: int
    masking_rate: float | None  # None (not 0.0) when there is nothing to mask -- explained, not fabricated


def evaluate_masking(component_crisp_scores_per_ts: list[dict[str, float]], baseline_results: list[BaselineResult], severity_threshold: str) -> MaskingResult:
    if len(component_crisp_scores_per_ts) != len(baseline_results):
        raise ValueError("component_crisp_scores_per_ts and baseline_results must be the same length")

    threshold_severity = CLASS_SEVERITY[severity_threshold]
    n_critical_events = 0
    n_masked = 0
    for scores, baseline in zip(component_crisp_scores_per_ts, baseline_results):
        component_classes = {c: classify_output(s) for c, s in scores.items()}
        any_unfavorable = any(CLASS_SEVERITY[cls] >= threshold_severity for cls in component_classes.values())
        if not any_unfavorable:
            continue
        n_critical_events += 1
        baseline_severity = CLASS_SEVERITY[baseline.index_class] if baseline.index_class is not None else -1
        if baseline_severity < threshold_severity:
            n_masked += 1

    method = baseline_results[0].method if baseline_results else ""
    rate = (n_masked / n_critical_events) if n_critical_events > 0 else None
    return MaskingResult(method=method, severity_threshold=severity_threshold, n_critical_events=n_critical_events, n_masked=n_masked, masking_rate=rate)
