"""Small, pure, independently-tested helper functions shared by the
2026-08-17 research scripts under scripts/research/ (Hampel threshold
sweep, boundary/class-stability paired analysis, membership-function
audit). Kept here (importable, testable) rather than duplicated inline in
each standalone script.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


# ---------------------------------------------------------------------------
# 2026-08-18 peer-review revision: fixes for defects 5.1-5.4 of the revision
# task spec. Each function below is deliberately pure (no I/O, no DB access)
# so it can be unit-tested directly against the failure scenarios the task
# enumerates, then reused unchanged by the research scripts under
# scripts/research/.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CausalLocfResult:
    """Result of a single causal LOCF lookup (task section 5.1).

    ``fallback_required`` is True whenever no usable source value existed
    inside the lookback window (empty candidates, all invalid, or all too
    old) -- callers must fall back to another strategy in that case, never
    silently return None as if it were a real (missing) reading.
    """

    value: float | None
    source_ts: datetime | None
    age_seconds: float | None
    age_minutes: float | None
    source_valid: bool | None
    fallback_required: bool
    fallback_reason: str | None


def causal_locf(
    target_ts: datetime,
    candidates: list[tuple[datetime, float | None, bool]],
    lookback_seconds: float,
) -> CausalLocfResult:
    """Causal last-observation-carried-forward using actual elapsed time,
    not array/row position (the bug this replaces: a fixed count of
    previous *computed positions* was treated as a time limit, which is
    wrong across a data gap -- the Nth-previous row can be minutes or hours
    old depending on how many cycles were actually recorded in between).

    ``candidates`` is any list of (source_ts, value, is_valid) tuples in any
    order; every one strictly earlier than ``target_ts`` (age > 0 -- a
    future or exactly-simultaneous value is never used, preventing leakage)
    and within ``(0, lookback_seconds]`` of it is eligible. Among eligible
    candidates that also satisfy the normal data-validity rule
    (``is_valid`` and ``value is not None``), the nearest in time wins.

    A candidate that is the closest in time but invalid does NOT block an
    older-but-valid candidate still inside the window from being used --
    LOCF means "the last *valid* observation", not "the last row".
    """
    best: tuple[datetime, float] | None = None
    best_age: float | None = None
    for src_ts, value, is_valid in candidates:
        if value is None or not is_valid:
            continue
        age = (target_ts - src_ts).total_seconds()
        if age <= 0:
            continue  # future value or same instant: never used (no leakage)
        if age > lookback_seconds:
            continue  # boundary is inclusive: age == lookback_seconds IS accepted
        if best_age is None or age < best_age:
            best_age = age
            best = (src_ts, value)

    if best is None:
        return CausalLocfResult(
            value=None, source_ts=None, age_seconds=None, age_minutes=None,
            source_valid=None, fallback_required=True,
            fallback_reason="no_valid_source_within_lookback",
        )
    src_ts, value = best
    return CausalLocfResult(
        value=value, source_ts=src_ts, age_seconds=best_age, age_minutes=best_age / 60.0,
        source_valid=True, fallback_required=False, fallback_reason=None,
    )


def has_dominance_tie(co_dominant_components: list[str]) -> bool:
    """A tie exists only when MORE THAN ONE DISTINCT component remains
    co-dominant (task section 5.2). The bug this replaces treated any
    non-empty ``co_dominant_components`` list as a tie -- but that list
    always contains at least the single dominant component itself
    (:func:`iaq_hfis.fuzzy_engine.determine_dominance` always returns
    ``dominant = co_dominant[0]``), so a length-1 list (no tie at all) was
    being counted as a tie on essentially every row.
    """
    return len(set(co_dominant_components)) > 1


def most_adverse_direct_input(
    channel_class_degrees: dict[str, dict[str, float]],
    class_severity: dict[str, int],
    tie_tolerance: float = 1e-9,
) -> tuple[str | None, bool]:
    """Which direct input is most adverse, using the actual fuzzy membership
    definitions and class severity (task section 5.3) -- NOT percentile rank
    within the dataset, which the previous implementation used and which
    silently fails for two-sided channels (temperature, humidity): a very
    LOW value and a very HIGH value can both be adverse, but only one of
    them can hold the top percentile rank, so percentile rank could point at
    a merely-high-but-comfortable reading while ignoring a genuinely extreme
    low one.

    ``channel_class_degrees`` maps each candidate channel name to its own
    ``{class: degree}`` dict (e.g. from
    :func:`iaq_hfis.membership.evaluate_memberships`, the same shapes the
    production pipeline uses for that channel).

    Ranking rule: for each channel, find its most adverse ACTIVE class (the
    highest-severity class with degree > 0). Compare channels first by that
    class's severity rank; if equal, compare the membership degree in that
    (shared) class. Ties within ``tie_tolerance`` are preserved explicitly
    (returned tied=True) rather than arbitrarily broken.

    Returns (channel_name_or_None, tied). ``None`` only when
    ``channel_class_degrees`` is empty or every channel has no active class
    (all degrees zero, which should not happen for a valid membership
    partition but is reported rather than assumed away).
    """
    per_channel: dict[str, tuple[int, float]] = {}
    for channel, degrees in channel_class_degrees.items():
        active = [(class_severity[cls], deg) for cls, deg in degrees.items() if deg > 0 and cls in class_severity]
        if not active:
            continue
        worst_severity = max(sev for sev, _ in active)
        worst_degree = max(deg for sev, deg in active if sev == worst_severity)
        per_channel[channel] = (worst_severity, worst_degree)

    if not per_channel:
        return None, False

    max_severity = max(sev for sev, _ in per_channel.values())
    at_max_severity = {ch: deg for ch, (sev, deg) in per_channel.items() if sev == max_severity}
    max_degree = max(at_max_severity.values())
    tied_channels = [ch for ch, deg in at_max_severity.items() if abs(deg - max_degree) <= tie_tolerance]
    top = sorted(tied_channels)[0]
    return top, len(tied_channels) > 1


def is_chronologically_consecutive(ts_a: datetime, ts_b: datetime, max_gap_minutes: float = 10.0) -> bool:
    """Task section 5.4: two real sensor-time timestamps are only treated as
    consecutive (adjacent updates of the same evolving series) when the
    elapsed time between them is no more than ``max_gap_minutes`` -- NOT
    merely adjacent by array/row position, which is what the arbitrary
    perturbation-trial ordering the previous flapping computation used
    amounted to (trial_index order at a single fixed sample point has no
    relationship to real elapsed time at all).
    """
    gap = abs((ts_b - ts_a).total_seconds()) / 60.0
    return gap <= max_gap_minutes


def classify_class_transition(prev_class: str, curr_class: str, class_order: list[str]) -> str:
    """'none' (no change), 'adjacent' (severity rank differs by exactly 1,
    e.g. Acceptable<->Degraded), or 'nonadjacent' (differs by 2 or more,
    e.g. Favourable->Critical) -- task section 5.4's transition breakdown."""
    if prev_class == curr_class:
        return "none"
    i, j = class_order.index(prev_class), class_order.index(curr_class)
    return "adjacent" if abs(i - j) == 1 else "nonadjacent"


def is_aba_reversal(class_a: str, class_b: str, class_c: str) -> bool:
    """True when three chronologically-consecutive valid updates form an
    A -> B -> A reversal (task section 5.4): the class changes and then
    changes straight back, i.e. real oscillation rather than a one-way
    drift. Requires ``class_a == class_c`` and ``class_a != class_b``."""
    return class_a == class_c and class_a != class_b


def verify_grid_point_count(n_points_per_axis: int, actual_row_count: int) -> bool:
    """Task section 5.5's consistency check: a manifest claiming
    ``n_points_per_axis`` for the 3-component grid experiment must match a
    persisted row count of exactly ``n_points_per_axis ** 3`` -- this is
    what caught the original defect (manifest said 101, persisted grid had
    68,921 = 41**3 rows, from an evaluate call that was actually run with
    the smaller value)."""
    return actual_row_count == n_points_per_axis**3
