"""Completeness status (OK / PARTIAL / FAILED), independent of air-quality class.

Per the manuscript: OK requires all three components with every direct
input at sufficient coverage; PARTIAL is exactly one missing component
(the numeric result is still produced, alongside the list of missing
inputs); FAILED is two or more missing components (or equivalently, at
most one available) — index value and class must then be null, never a
placeholder number.
"""

from __future__ import annotations

from iaq_hfis.constants import COMPONENT_INPUTS
from iaq_hfis.models import CompletenessResult, CoverageResult


def component_availability(coverage: dict[str, CoverageResult]) -> dict[str, bool]:
    """A component is available only if every one of its direct inputs has
    sufficient coverage — aerosol (A) needs BOTH pm2_5 and pm10; microclimate
    (M) needs BOTH temperature and humidity; ventilation (V) needs co2."""
    return {
        component: all(channel in coverage and coverage[channel].ok for channel in inputs)
        for component, inputs in COMPONENT_INPUTS.items()
    }


def completeness_status(coverage: dict[str, CoverageResult]) -> CompletenessResult:
    availability = component_availability(coverage)
    missing_components = sorted(c for c, ok in availability.items() if not ok)
    missing_inputs = sorted(ch for ch, cov in coverage.items() if not cov.ok)

    n_missing = len(missing_components)
    if n_missing == 0:
        status = "OK"
    elif n_missing == 1:
        status = "PARTIAL"
    else:
        status = "FAILED"

    return CompletenessResult(status=status, missing_components=missing_components, missing_inputs=missing_inputs)
