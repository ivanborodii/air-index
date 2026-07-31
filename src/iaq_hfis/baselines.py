"""FUZZY_COMPONENT_MAX, CRISP_CLASS_MAX, and WEIGHTED_MEAN baselines from the
manuscript's comparative evaluation protocol.

FUZZY_COMPONENT_MAX and WEIGHTED_MEAN are computed from the *same*
per-component crisp scores the Mamdani engine already produces
(:class:`iaq_hfis.models.ComponentInferenceResult.crisp_score`, a centroid
on the identical 0-100 output scale as the proposed index) — no separate
scoring logic, only a different aggregation. CRISP_CLASS_MAX instead
classifies the raw direct-input *values* against hard control-region
breakpoints (no membership overlap), so it is the only baseline that
actually reproduces the discontinuous step behavior the manuscript
criticises — FUZZY_COMPONENT_MAX still inherits smooth per-component
membership degrees and is not a hard baseline.

- **FUZZY_COMPONENT_MAX** reproduces a prior paper's logic: the hard max of
  the already-fuzzified, normalized component scores. A single unfavorable
  component always dominates the result, but each component score itself
  still varies smoothly with its inputs (diagnostic baseline only).
- **CRISP_CLASS_MAX** is the genuinely hard baseline: every available direct
  input is assigned exactly one crisp class via the control-region
  breakpoints, components take the most adverse of their inputs' classes,
  and the overall result is the most adverse available component class,
  deterministically mapped to a fixed representative value on the output
  scale. Exhibits a true step discontinuity at every boundary.
- **WEIGHTED_MEAN** is a neutral baseline: the equal-weight arithmetic mean
  of the available component scores. No expert weighting.

All three degrade over available components only, exactly like
PROPOSED_HFIS's own PARTIAL-mode handling — not a special case.
"""

from __future__ import annotations

from dataclasses import dataclass

from iaq_hfis.config import ControlRegions, TwoSidedRanges
from iaq_hfis.constants import CLASS_SEVERITY
from iaq_hfis.fuzzy_engine import classify_output

#: Deterministic mapping from a hard-assigned class to a single representative
#: value on the 0-100 output scale: the midpoint of that class's span between
#: iaq_hfis.constants.OUTPUT_BOUNDARIES = [25, 50, 75]. AUTHOR_DEFINED: the
#: manuscript does not specify a numeric representative value for a crisp
#: class baseline -- the midpoint is the natural, bias-free choice.
CLASS_MIDPOINT: dict[str, float] = {"Favorable": 12.5, "Acceptable": 37.5, "Degraded": 62.5, "Critical": 87.5}


@dataclass(frozen=True)
class BaselineResult:
    method: str  # "FUZZY_COMPONENT_MAX" | "CRISP_CLASS_MAX" | "WEIGHTED_MEAN"
    index_value: float | None
    index_class: str | None
    n_components: int


def fuzzy_component_max(component_crisp_scores: dict[str, float]) -> BaselineResult:
    """Hard max of the available component scores.

    Structurally cannot mask a critical component: if any component's
    crisp_score falls in the Critical range [75,100], the max is >= 75 too,
    so the classified output is Critical as well (see
    :mod:`iaq_hfis.evaluation.masking` for the corresponding test).
    """
    if not component_crisp_scores:
        return BaselineResult(method="FUZZY_COMPONENT_MAX", index_value=None, index_class=None, n_components=0)
    value = max(component_crisp_scores.values())
    return BaselineResult(method="FUZZY_COMPONENT_MAX", index_value=value, index_class=classify_output(value), n_components=len(component_crisp_scores))


def weighted_mean(component_crisp_scores: dict[str, float]) -> BaselineResult:
    """Equal-weight arithmetic mean of the available component scores."""
    if not component_crisp_scores:
        return BaselineResult(method="WEIGHTED_MEAN", index_value=None, index_class=None, n_components=0)
    value = sum(component_crisp_scores.values()) / len(component_crisp_scores)
    return BaselineResult(method="WEIGHTED_MEAN", index_value=value, index_class=classify_output(value), n_components=len(component_crisp_scores))


def _hard_classify_monotonic(value: float, breakpoints: list[float]) -> str:
    """No membership overlap: a boundary value maps to the less-favorable
    class, matching :func:`iaq_hfis.fuzzy_engine.classify_output`'s
    convention on the output scale."""
    b0, b1, b2 = breakpoints
    if value < b0:
        return "Favorable"
    if value < b1:
        return "Acceptable"
    if value < b2:
        return "Degraded"
    return "Critical"


def _hard_classify_two_sided(value: float, ranges: TwoSidedRanges) -> str:
    """No membership overlap, no transition band -- a genuine step function
    of ``value`` (temperature/humidity control regions are two-sided: both
    low and high deviations from favorable are unfavorable)."""
    if ranges.favorable[0] <= value <= ranges.favorable[1]:
        return "Favorable"
    if ranges.acceptable_low[0] <= value < ranges.favorable[0] or ranges.favorable[1] < value <= ranges.acceptable_high[1]:
        return "Acceptable"
    if ranges.degraded_low[0] <= value < ranges.acceptable_low[0] or ranges.acceptable_high[1] < value <= ranges.degraded_high[1]:
        return "Degraded"
    return "Critical"


def crisp_class_max(
    direct_input_values: dict[str, float],
    control_regions: ControlRegions,
    temperature_ranges: TwoSidedRanges | None,
) -> BaselineResult:
    """The genuinely hard/discontinuous baseline (spec section 6.2): each
    available direct input is assigned exactly one crisp class via the
    class control-region breakpoints (no fuzzy overlap), components take
    the most adverse of their inputs' classes, and the overall result is
    the most adverse available component class, deterministically mapped to
    the output scale via its class midpoint. Unlike FUZZY_COMPONENT_MAX
    (which still operates on smoothly-varying fuzzy component scores), this
    baseline exhibits a true step discontinuity at every control-region
    boundary -- the behavior the manuscript's continuity experiment
    contrasts PROPOSED_HFIS against.

    ``temperature_ranges`` is the room/season profile's control region
    (``None`` if no DBN profile applies, e.g. exploratory-mode runs) -- the
    M component is omitted, never fabricated, whenever it is ``None`` or
    either of temperature/humidity is missing from ``direct_input_values``.
    """
    component_classes: dict[str, str] = {}

    if "pm2_5" in direct_input_values and "pm10" in direct_input_values:
        classes = [
            _hard_classify_monotonic(direct_input_values["pm2_5"], control_regions.pm2_5.breakpoints),
            _hard_classify_monotonic(direct_input_values["pm10"], control_regions.pm10.breakpoints),
        ]
        component_classes["A"] = max(classes, key=lambda c: CLASS_SEVERITY[c])

    if "co2" in direct_input_values:
        component_classes["V"] = _hard_classify_monotonic(direct_input_values["co2"], control_regions.co2.breakpoints)

    if "temperature" in direct_input_values and "humidity" in direct_input_values and temperature_ranges is not None:
        classes = [
            _hard_classify_two_sided(direct_input_values["temperature"], temperature_ranges),
            _hard_classify_two_sided(direct_input_values["humidity"], control_regions.relative_humidity),
        ]
        component_classes["M"] = max(classes, key=lambda c: CLASS_SEVERITY[c])

    if not component_classes:
        return BaselineResult(method="CRISP_CLASS_MAX", index_value=None, index_class=None, n_components=0)

    overall_class = max(component_classes.values(), key=lambda c: CLASS_SEVERITY[c])
    value = CLASS_MIDPOINT[overall_class]
    return BaselineResult(method="CRISP_CLASS_MAX", index_value=value, index_class=overall_class, n_components=len(component_classes))
