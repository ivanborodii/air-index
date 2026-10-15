"""Loads ``config/iaq_index.yaml`` into an immutable :class:`IndexConfig`.

All numeric limits come from the YAML; derived values (CO2 breakpoints from
outdoor + delta, b4 of CO2) are computed here, never hard-coded.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "iaq_index.yaml"

INDICATORS = ["pm25", "pm10", "co2", "t", "rh"]


@dataclass(frozen=True)
class IndicatorBreakpoints:
    name: str
    kind: str  # "monotonic" | "two_sided"
    high: tuple[float, ...]  # b0..b4 above the normative range (monotonic: the only set)
    low: tuple[float, ...] | None = None  # b0..b4 below the range (two-sided only), decreasing


@dataclass(frozen=True)
class IndexConfig:
    raw: dict = field(repr=False)
    indicators: dict[str, IndicatorBreakpoints]
    class_names: tuple[str, ...]
    points_per_class: float
    max_score: float
    pm10_separate: bool
    critical_threshold: float
    dominance_min_index: float
    dominance_tolerance: float

    @property
    def components(self) -> dict[str, list[str]]:
        """Component -> indicators, formulas (2)-(4) (or the 4-component variant)."""
        c = self.raw["components"]
        if self.pm10_separate:
            return {"A": ["pm25"], "P": ["pm10"], "V": list(c["V"]), "M": list(c["M"])}
        return {"A": list(c["A"]), "V": list(c["V"]), "M": list(c["M"])}

    def with_overrides(self, **kw) -> "IndexConfig":
        """Copy with a modified raw config, e.g. ``pm10_separate=True``,
        ``t_low=[...]``, ``co2_outdoor_ppm=400`` (sensitivity variants)."""
        raw = copy.deepcopy(self.raw)
        if "pm10_separate" in kw:
            raw["components"]["pm10_separate"] = bool(kw.pop("pm10_separate"))
        if "t_low" in kw:
            raw["indicators"]["t"]["low"] = list(kw.pop("t_low"))
        if "co2_outdoor_ppm" in kw:
            raw["indicators"]["co2"]["outdoor_ppm"] = kw.pop("co2_outdoor_ppm")
        if kw:
            raise KeyError(f"unknown overrides: {sorted(kw)}")
        return _from_raw(raw)


def _co2_breakpoints(spec: dict) -> tuple[float, ...]:
    b = [spec["outdoor_ppm"] + d for d in spec["delta_above_outdoor_ppm"]]
    b.append(spec["critical_limit_ppm"])
    b.append(b[3] + (b[3] - b[2]))  # b4 = b3 + (b3 - b2)
    return tuple(float(x) for x in b)


def _check_monotone(name: str, b: tuple[float, ...], increasing: bool) -> None:
    if len(b) != 5:
        raise ValueError(f"{name}: expected 5 breakpoints b0..b4, got {b}")
    pairs = zip(b, b[1:])
    if not all((x < y) if increasing else (x > y) for x, y in pairs):
        raise ValueError(f"{name}: breakpoints must be strictly {'in' if increasing else 'de'}creasing: {b}")


def _from_raw(raw: dict) -> IndexConfig:
    inds: dict[str, IndicatorBreakpoints] = {}
    for name in INDICATORS:
        spec = raw["indicators"][name]
        if name == "co2":
            high = _co2_breakpoints(spec)
        elif spec["kind"] == "monotonic":
            high = tuple(float(x) for x in spec["breakpoints"])
        else:
            high = tuple(float(x) for x in spec["high"])
        _check_monotone(name, high, increasing=True)
        low = None
        if spec["kind"] == "two_sided":
            low = tuple(float(x) for x in spec["low"])
            _check_monotone(name, low, increasing=False)
        inds[name] = IndicatorBreakpoints(name=name, kind=spec["kind"], high=high, low=low)
    agg = raw["aggregation"]
    return IndexConfig(
        raw=raw,
        indicators=inds,
        class_names=tuple(raw["classes"]["names"]),
        points_per_class=float(raw["score"]["points_per_class"]),
        max_score=float(raw["score"]["max_score"]),
        pm10_separate=bool(raw["components"]["pm10_separate"]),
        critical_threshold=float(agg["critical_threshold"]),
        dominance_min_index=float(agg["dominance_min_index"]),
        dominance_tolerance=float(agg["dominance_tolerance"]),
    )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> IndexConfig:
    with open(path, encoding="utf-8") as f:
        return _from_raw(yaml.safe_load(f))
