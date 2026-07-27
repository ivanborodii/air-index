"""Fixed vocabulary shared across the pipeline: enums and lookup tables.

Numeric thresholds live in config (see :mod:`iaq_hfis.config`); this module
only holds names and structural relationships that are not configuration.
"""

from __future__ import annotations

from enum import Enum


class QualityState(str, Enum):
    """Per-record data-quality state assigned during validation.

    These describe *data quality*, not air-quality severity: a MISSING or
    INVALID reading carries no information about whether the air was clean
    or polluted.
    """

    VALID = "VALID"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"
    MISSING = "MISSING"


class ReasonCode(str, Enum):
    """Explanatory fault categories attached to SUSPECT/INVALID records."""

    SINGLE_SPIKE = "single_spike"
    STUCK_VALUE = "stuck_value"
    DATA_LOSS = "data_loss"
    GRADUAL_DRIFT = "gradual_drift"
    OUT_OF_RANGE = "out_of_range"


class IaqClass(str, Enum):
    """The four linguistic classes shared by every direct input and the output index."""

    FAVORABLE = "Favorable"
    ACCEPTABLE = "Acceptable"
    DEGRADED = "Degraded"
    CRITICAL = "Critical"


#: Severity rank used by the worst-of rule consequent (higher = worse).
CLASS_SEVERITY: dict[str, int] = {
    IaqClass.FAVORABLE.value: 0,
    IaqClass.ACCEPTABLE.value: 1,
    IaqClass.DEGRADED.value: 2,
    IaqClass.CRITICAL.value: 3,
}

#: Canonical class ordering, index-aligned with CLASS_SEVERITY.
CLASS_ORDER: list[str] = [
    IaqClass.FAVORABLE.value,
    IaqClass.ACCEPTABLE.value,
    IaqClass.DEGRADED.value,
    IaqClass.CRITICAL.value,
]

#: First-level components and the direct inputs (canonical channel names) each one requires.
#: A (aerosol) and M (microclimate) each require BOTH listed inputs to be available;
#: V (ventilation) requires its single input.
COMPONENT_INPUTS: dict[str, list[str]] = {
    "A": ["pm2_5", "pm10"],
    "V": ["co2"],
    "M": ["temperature", "humidity"],
}

#: Direct-input channels that are monotonic (higher is never better) vs two-sided
#: (both low and high deviations are unfavorable).
MONOTONIC_CHANNELS: list[str] = ["pm2_5", "pm10", "co2"]
TWO_SIDED_CHANNELS: list[str] = ["temperature", "humidity"]

#: Output index universe of discourse.
OUTPUT_MIN: float = 0.0
OUTPUT_MAX: float = 100.0
OUTPUT_BOUNDARIES: list[float] = [25.0, 50.0, 75.0]
