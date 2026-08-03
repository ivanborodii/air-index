"""Typed configuration models and loaders for iaq_hfis.

Three YAML files are loaded independently and combined:

- ``config/iaq_hfis.yaml``      -> :class:`Settings`
- ``config/sensor_specs.yaml``  -> :class:`SensorSpecs`
- ``config/room_profiles.yaml`` -> :class:`RoomProfilesConfig`

All models use ``extra="forbid"`` so a typo'd or unknown key fails loudly at
load time rather than being silently ignored. Validation errors are
re-raised as :class:`ConfigError` with a flattened, field-path-annotated
message.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigError(Exception):
    """Raised when configuration fails to load or validate.

    Always carries a human-readable, field-path-annotated message so the
    caller does not need to inspect a wrapped exception to know what is
    wrong ("missing required settings fail clearly").
    """


class TemperatureProfileNotDefinedError(ConfigError):
    """Raised by :func:`iaq_hfis.profiles.select_room_season` when the
    requested (room, season) has no DBN-supported temperature control
    region. Carries structured fields (not just a message) so callers can
    decide programmatically whether a run is manuscript-eligible, per the
    strict-selection rule: no fallback to another room, no fallback to
    another season, no interpolation, no reuse of a different room's
    profile, no outdoor-temperature substitution, no hidden default.
    """

    def __init__(self, requested_room: str, requested_season: str, available_profiles: list[tuple[str, str]]):
        self.requested_room = requested_room
        self.requested_season = requested_season
        self.available_profiles = available_profiles
        self.dbn_source = "DBN V.2.5-67:2013, mandatory Appendix D, Table D.4"
        message = (
            "TEMPERATURE_PROFILE_NOT_DEFINED\n"
            f"  requested room:   {requested_room}\n"
            f"  requested season: {requested_season}\n"
            f"  available profiles: {available_profiles}\n"
            f"  standard: {self.dbn_source}\n"
            "  No standards-based temperature control region is defined for this "
            "room/season combination, and this system never falls back to another "
            "room, another season, interpolation, or outdoor temperature as a "
            "substitute. A full three-component (A/V/M/I) manuscript result cannot "
            "be produced for this room/season until a DBN-supported profile is added."
        )
        super().__init__(message)


# ---------------------------------------------------------------------------
# config/iaq_hfis.yaml
# ---------------------------------------------------------------------------


class PathsConfig(BaseModel):
    """Filesystem locations. The two ``air_monitor_db_path``/``weather_db_path``
    paths are READ-ONLY sources owned by the separate air-monitor pipeline;
    iaq_hfis never writes to them."""

    model_config = ConfigDict(extra="forbid")

    air_monitor_db_path: str
    weather_db_path: str
    derived_db_path: str
    snapshot_dir: str
    log_path: str
    run_summary_dir: str


class CadenceConfig(BaseModel):
    """Sampling cadence and the rolling-window schedule."""

    model_config = ConfigDict(extra="forbid")

    sample_cadence_seconds: int = Field(gt=0, default=30)
    aggregation_window_minutes: int = 15
    allowed_window_minutes: list[int] = Field(default_factory=lambda: [5, 15, 30, 60])
    recompute_interval_minutes: int = Field(gt=0, default=5)
    # PROVISIONAL default: half the sample cadence. The expected-slot grid is
    # anchored at computed_ts, which has an arbitrary phase offset from the
    # sensor's own ~30s cadence (it is not epoch-aligned) — a tolerance below
    # half the cadence would systematically miss real readings even when the
    # sensor never actually dropped a sample.
    slot_match_tolerance_seconds: float = Field(gt=0, default=15.0)

    @model_validator(mode="after")
    def _window_is_allowed(self) -> "CadenceConfig":
        if self.aggregation_window_minutes not in self.allowed_window_minutes:
            raise ValueError(
                f"aggregation_window_minutes={self.aggregation_window_minutes} "
                f"is not in allowed_window_minutes={self.allowed_window_minutes}"
            )
        return self

    @property
    def expected_slots_per_window(self) -> int:
        return (self.aggregation_window_minutes * 60) // self.sample_cadence_seconds


class CoverageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_ratio: float = Field(ge=0.0, le=1.0, default=0.80)


class HampelConfig(BaseModel):
    """PROVISIONAL: the manuscript names the Hampel filter (citing Pearson,
    Neuvo, Astola, Gabbouj, "Generalized Hampel Filters", 2016) but gives no
    numeric window/threshold. window_size=11, mad_multiplier=1.0 are that
    exact paper's own illustrative-example parameters (K=5, i.e. j in
    [-K,K] = 11 points, and t=1 -- see its Sec. 2 and Figs. 3/5), verified
    2026-07-24 against the paper's EUSIPCO 2015 conference precursor
    (same authors, same Hampel filter definition). The paper does not state
    these as a general recommendation ("results ... preliminary, based on
    limited experimentation with a single example") -- still provisional,
    but now grounded in the manuscript's own cited source rather than an
    unsourced guess. Verified empirically against live data: relative to a
    window=5/mad_multiplier=3.0 guess, this roughly doubles the SUSPECT
    candidate rate (6.0%->12.5% in one test run) but confirmation still
    validates ~98% of them as usable either way -- no completeness regression.
    """

    model_config = ConfigDict(extra="forbid")

    window_size: int = Field(ge=3, default=11)
    mad_multiplier: float = Field(gt=0, default=1.0)


class ConfirmationConfig(BaseModel):
    """PROVISIONAL: cross-channel/persistence tolerances not given numerically in the manuscript."""

    model_config = ConfigDict(extra="forbid")

    pm_cross_channel_tolerance_pct: float = Field(gt=0, default=20.0)
    # dual-channel T/RH agreement tolerance is NOT configured here -- it is
    # derived at runtime as the sum of both channels' own declared_uncertainty
    # (schema.py:dual_channel_tolerance), so it can't drift out of sync with
    # sensor_specs.yaml and isn't a second independently-guessed number.
    persistence_min_consecutive_samples: int = Field(ge=1, default=2)
    stuck_value_min_repeats: int = Field(ge=2, default=5)
    gradual_drift_min_consecutive_steps: int = Field(ge=2, default=5)
    # PROVISIONAL: cumulative run magnitude must reach this multiple of the
    # channel's declared_uncertainty to be flagged -- run-length alone is a
    # weak signal, since ordinary environmental trends routinely contain
    # 5+ consecutive same-direction 30s steps with no fault involved
    # (verified against live data). See quality/reasons.py:detect_gradual_drift.
    gradual_drift_magnitude_multiplier: float = Field(gt=0, default=3.0)
    outdoor_context_max_age_minutes: float = Field(gt=0, default=90.0)


class ChannelMapEntry(BaseModel):
    """Maps one canonical channel name to its source column(s) in ``raw_observations``."""

    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    source_column: str
    device_status_column: str
    secondary_column: str | None = None


class SchemaMappingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_raw_columns: list[str]
    channels: list[ChannelMapEntry]

    @model_validator(mode="after")
    def _no_carbon_monoxide_as_co2(self) -> "SchemaMappingConfig":
        for ch in self.channels:
            cols = {ch.source_column, ch.secondary_column}
            if ch.canonical_name == "co2" and "carbon_monoxide" in cols:
                raise ValueError(
                    "schema_mapping.channels: outdoor 'carbon_monoxide' (CO) must never "
                    "be mapped to canonical channel 'co2' (CO2) — they are different gases"
                )
        return self

    def channel(self, canonical_name: str) -> ChannelMapEntry:
        for ch in self.channels:
            if ch.canonical_name == canonical_name:
                return ch
        raise ConfigError(f"schema_mapping.channels: no entry for canonical channel '{canonical_name}'")


class MembershipConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_transition_width: float = Field(gt=0, default=2.0)
    overlap_width_policy: Literal["reject", "auto_expand"] = "reject"
    # AUTHOR_DEFINED: the manuscript does not specify a numeric tie
    # tolerance for dominant-adverse-component attribution. Two available
    # components are both reported as dominant only when their crisp scores
    # (0-100 scale) differ by no more than this amount; otherwise only the
    # strictly higher one is reported. See fuzzy_engine.determine_dominance.
    dominant_component_tie_tolerance: float = Field(ge=0, default=1.0)


class DeploymentConfig(BaseModel):
    """Explicit, author-attested evidence for the physical deployment room.
    Never inferred from sensor values or from wanting a different DBN
    profile to exist -- room_type_evidence documents *why* the room is
    classified this way, so no one can quietly reclassify a standalone
    kitchen as a kitchen-dining space just to unblock a warm-period result.
    """

    model_config = ConfigDict(extra="forbid")

    room_type: str
    room_type_evidence: str
    season_source: Literal["timestamp"] = "timestamp"


class ProfileSelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room: str
    season_month_ranges: dict[str, list[int]]

    @field_validator("season_month_ranges")
    @classmethod
    def _valid_months(cls, v: dict[str, list[int]]) -> dict[str, list[int]]:
        for season, months in v.items():
            for m in months:
                if not (1 <= m <= 12):
                    raise ValueError(f"season_month_ranges[{season}] contains invalid month {m}")
        return v


class ClassBoundaries(BaseModel):
    """Control region for a monotonic (right-shoulder) channel: 3 breakpoints
    separating the 4 classes, each with its own transition half-width."""

    model_config = ConfigDict(extra="forbid")

    breakpoints: list[float] = Field(min_length=3, max_length=3)
    transition_widths: list[float] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _strictly_increasing(self) -> "ClassBoundaries":
        bp = self.breakpoints
        if not (bp[0] < bp[1] < bp[2]):
            raise ValueError(f"breakpoints must be strictly increasing, got {bp} (incompatible class boundaries)")
        if any(w <= 0 for w in self.transition_widths):
            raise ValueError(f"transition_widths must all be positive, got {self.transition_widths}")
        return self


class TwoSidedRanges(BaseModel):
    """Control region for a two-sided channel (temperature or RH): both low
    and high deviations from the favourable band are unfavorable."""

    model_config = ConfigDict(extra="forbid")

    favourable: tuple[float, float]
    acceptable_low: tuple[float, float]
    acceptable_high: tuple[float, float]
    degraded_low: tuple[float, float]
    degraded_high: tuple[float, float]
    critical_low_max: float
    critical_high_min: float
    transition_width: float = Field(gt=0)

    @model_validator(mode="after")
    def _nested_and_increasing(self) -> "TwoSidedRanges":
        chain = [
            self.critical_low_max,
            self.degraded_low[0],
            self.degraded_low[1],
            self.acceptable_low[0],
            self.acceptable_low[1],
            self.favourable[0],
            self.favourable[1],
            self.acceptable_high[0],
            self.acceptable_high[1],
            self.degraded_high[0],
            self.degraded_high[1],
            self.critical_high_min,
        ]
        for a, b in zip(chain, chain[1:]):
            if a > b:
                raise ValueError(
                    f"TwoSidedRanges boundaries must be non-decreasing low-to-high, got {chain} "
                    "(incompatible class boundaries)"
                )
        return self


class ControlRegions(BaseModel):
    """Table 2 of the manuscript. Temperature is intentionally absent here —
    it is room/season dependent and comes from :class:`RoomProfilesConfig`."""

    model_config = ConfigDict(extra="forbid")

    pm2_5: ClassBoundaries
    pm10: ClassBoundaries
    co2: ClassBoundaries
    relative_humidity: TwoSidedRanges
    output: ClassBoundaries


class EvaluationConfig(BaseModel):
    """Parameters for the manuscript's comparative-evaluation protocol
    (FUZZY_COMPONENT_MAX / WEIGHTED_MEAN baselines, stability, sensitivity, masking).
    ``sensitivity_window_minutes`` and ``sensitivity_coverage_thresholds``
    are given explicitly in the manuscript, not provisional; the rest are.
    """

    model_config = ConfigDict(extra="forbid")

    stability_seed: int = 42  # PROVISIONAL: manuscript requires a fixed seed but gives no value
    stability_n_trials: int = Field(ge=1, default=30)  # PROVISIONAL
    # AUTHOR_DEFINED: multi-point stability sample sizes -- bounded so evaluation runtime
    # stays predictable on Raspberry Pi 5. See evaluation/multi_point_stability.py.
    stability_max_boundary_samples: int = Field(ge=0, default=20)
    stability_max_random_samples: int = Field(ge=0, default=10)
    sensitivity_window_minutes: list[int] = Field(default_factory=lambda: [5, 15, 30, 60])
    sensitivity_coverage_thresholds: list[float] = Field(default_factory=lambda: [0.70, 0.80, 0.90])
    # AUTHOR_DEFINED: multi-point sensitivity stratified sample size -- bounded for the same reason.
    sensitivity_max_samples_per_stratum: int = Field(ge=1, default=5)
    masking_severity_threshold: Literal["Acceptable", "Degraded", "Critical"] = "Critical"  # PROVISIONAL
    # AUTHOR_DEFINED: dense grid resolution for the boundary continuity experiment
    # (points per +/-1 declared-uncertainty span around each control-region boundary).
    # Kept modest: this experiment re-runs on every 'iaq_hfis evaluate' call, not just once.
    continuity_grid_points: int = Field(ge=5, default=21)
    # AUTHOR_DEFINED: resolution per axis for the independent multi-component (A, V, M) grid
    # experiment. Kept modest by default (11^3 = 1,331 combinations, matching
    # continuity_grid_points' own "re-runs on every evaluate call" rationale above) --
    # the manuscript-validation task spec's own worked example (41 -> 68,921 combinations)
    # is used explicitly for the final manuscript regeneration via
    # 'iaq_hfis evaluate --multi-component-grid-points 41', not as the routine default.
    multi_component_grid_points_per_axis: int = Field(ge=2, default=11)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: PathsConfig
    cadence: CadenceConfig
    coverage: CoverageConfig
    hampel: HampelConfig
    confirmation: ConfirmationConfig
    schema_mapping: SchemaMappingConfig
    device_status_state_map: dict[str, str]
    membership: MembershipConfig
    deployment: DeploymentConfig
    profile_selection: ProfileSelectionConfig
    control_regions: ControlRegions
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    engine_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# config/sensor_specs.yaml
# ---------------------------------------------------------------------------


class ChannelTechnicalRange(BaseModel):
    """Datasheet-sourced technical (passport) range for one raw sensor channel."""

    model_config = ConfigDict(extra="forbid")

    min: float
    max: float
    unit: str
    source: str
    declared_uncertainty: float = Field(ge=0)

    @model_validator(mode="after")
    def _min_lt_max(self) -> "ChannelTechnicalRange":
        if self.min >= self.max:
            raise ValueError(f"technical range min ({self.min}) must be < max ({self.max})")
        return self


class SensorSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: dict[str, ChannelTechnicalRange]


# ---------------------------------------------------------------------------
# config/room_profiles.yaml
# ---------------------------------------------------------------------------


class RoomTemperatureProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room: str
    season: str
    provisional: bool = False
    ranges: TwoSidedRanges


class RoomProfilesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: list[RoomTemperatureProfile]

    def find(self, room: str, season: str) -> RoomTemperatureProfile | None:
        for p in self.profiles:
            if p.room == room and p.season == season:
                return p
        return None


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ConfigError(f"config file is empty: {path}")
    return data


def _flatten_validation_error(exc: ValidationError, model_name: str) -> str:
    lines = [f"Invalid {model_name}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_settings(path: str | Path) -> Settings:
    data = _load_yaml(path)
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_flatten_validation_error(exc, "Settings")) from exc


def load_sensor_specs(path: str | Path) -> SensorSpecs:
    data = _load_yaml(path)
    try:
        return SensorSpecs.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_flatten_validation_error(exc, "SensorSpecs")) from exc


def load_room_profiles(path: str | Path) -> RoomProfilesConfig:
    data = _load_yaml(path)
    try:
        return RoomProfilesConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_flatten_validation_error(exc, "RoomProfilesConfig")) from exc


def config_hash(settings: Settings, sensor_specs: SensorSpecs, room_profiles: RoomProfilesConfig) -> str:
    """SHA-256 over the three config models' canonical JSON, for reproducibility metadata."""
    payload = {
        "settings": settings.model_dump(mode="json"),
        "sensor_specs": sensor_specs.model_dump(mode="json"),
        "room_profiles": room_profiles.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
