"""Small, pure, independently-tested helper functions shared by the
2026-08-17 research scripts under scripts/research/ (Hampel threshold
sweep, boundary/class-stability paired analysis, membership-function
audit). Kept here (importable, testable) rather than duplicated inline in
each standalone script.
"""
from __future__ import annotations

from math import comb


def f1_of(precision: float | None, recall: float | None) -> float | None:
    """Harmonic mean of precision and recall; None if either input is None
    or their sum is zero (undefined, not silently zero)."""
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def s_new_objective(f1_spike: float | None, preservation_rate: float | None) -> float | None:
    """S_new = (F1_spike + P_event) / 2, the task's requested alternative
    Hampel-multiplier selection objective."""
    if f1_spike is None or preservation_rate is None:
        return None
    return (f1_spike + preservation_rate) / 2.0


def scenario_family(scenario_id: str) -> str:
    """Strips the '_calibration'/'_validation' variant suffix every
    fault-injection scenario builder appends, so a seeded group split can
    guarantee no family straddles both groups."""
    for suffix in ("_calibration", "_validation"):
        if scenario_id.endswith(suffix):
            return scenario_id[: -len(suffix)]
    return scenario_id


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar test (binomial sign test on discordant pairs)
    for paired binary outcomes. ``b`` = count where A=True,B=False; ``c`` =
    count where A=False,B=True. Returns the p-value; 1.0 when there are no
    discordant pairs (b == c == 0)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def classify_estimation_direction(
    true_class: str | None, predicted_class: str | None, class_severity: dict[str, int]
) -> str | None:
    """Task section 6.4's underestimation/overestimation definition: a
    predicted class LESS adverse (lower severity) than the complete record
    reference's true class is 'under'; MORE adverse is 'over'; equal
    severity is 'exact'. Returns None when either class is missing/unknown
    (not comparable) rather than guessing a direction."""
    if true_class is None or predicted_class is None:
        return None
    if true_class not in class_severity or predicted_class not in class_severity:
        return None
    t, p = class_severity[true_class], class_severity[predicted_class]
    if p < t:
        return "under"
    if p > t:
        return "over"
    return "exact"


def is_within_requested_interval(ts, start_inclusive, end_exclusive) -> bool:
    """Task section 3's exact interval semantics: start inclusive, end
    exclusive. A single shared predicate so every script that filters by
    this interval (and every test that checks nothing leaked outside it)
    uses the identical comparison."""
    return start_inclusive <= ts < end_exclusive


def monotonic_shape_type(a: float, b: float, c: float, d: float) -> str:
    """Classifies a monotonic-channel trapezoid (a, b, c, d) built by
    iaq_hfis.membership.build_monotonic_classes: 'trapezoidal' if there is a
    flat membership=1 plateau (b < c), 'triangular' if the rising and
    falling edges meet exactly at one point (b == c), or
    'INVALID_CROSSED_EDGES' if they cross (b > c) -- which should never
    happen for a config that has passed iaq_hfis.schema.validate_membership_config,
    but is reported explicitly rather than silently misclassified as
    trapezoidal if it ever does."""
    if b < c:
        return "trapezoidal"
    if b == c:
        return "triangular"
    return "INVALID_CROSSED_EDGES"
