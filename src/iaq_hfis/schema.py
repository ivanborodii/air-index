"""Cross-checks between configuration and the real world: actual DuckDB
columns and declared sensor uncertainty.

Two independent checks live here:

- :func:`validate_schema_mapping` — does ``schema_mapping`` in
  ``config/iaq_hfis.yaml`` actually match the live ``raw_observations``
  schema?
- :func:`validate_membership_config` — is every configured membership
  transition (overlap) width at least as wide as the declared uncertainty
  of the sensor channel it's built from?
"""

from __future__ import annotations

from dataclasses import dataclass, field

from iaq_hfis.config import ControlRegions, RoomProfilesConfig, SchemaMappingConfig, SensorSpecs

# Maps a raw_observations column name to its config/sensor_specs.yaml key.
# Kept as an explicit table (rather than a naming convention) so schema_mapping
# stays free to point at any raw column without constraining its name.
RAW_COLUMN_TO_SENSOR_SPEC: dict[str, str] = {
    "co2_ppm": "co2",
    "scd_temp_c": "scd_temp",
    "scd_humidity_pct": "scd_humidity",
    "bme_temp_c": "bme_temp",
    "bme_humidity_pct": "bme_humidity",
    "pressure_hpa": "pressure",
    # SPS30 datasheet groups PM1/PM2.5 under one precision spec and PM4/PM10
    # under a materially different (larger) one -- see sensor_specs.yaml.
    "mass_pm1_0": "pm_mass_fine",
    "mass_pm2_5": "pm_mass_fine",
    "mass_pm4_0": "pm_mass_coarse",
    "mass_pm10": "pm_mass_coarse",
}


class SchemaMappingError(Exception):
    """Raised when schema_mapping references columns absent from raw_observations."""


class MembershipConfigError(Exception):
    """Raised when a configured transition width is narrower than the
    declared sensor uncertainty and overlap_width_policy == 'reject'."""


def validate_schema_mapping(schema_mapping: SchemaMappingConfig, actual_columns: set[str]) -> None:
    """Raise :class:`SchemaMappingError` listing every configured column
    that does not exist in the actual ``raw_observations`` schema."""
    missing: list[str] = []
    for col in schema_mapping.required_raw_columns:
        if col not in actual_columns:
            missing.append(col)
    for ch in schema_mapping.channels:
        for col in (ch.source_column, ch.device_status_column, ch.secondary_column):
            if col is not None and col not in actual_columns:
                missing.append(col)
    if missing:
        unique_missing = sorted(set(missing))
        raise SchemaMappingError(
            "schema_mapping references columns not present in raw_observations: "
            + ", ".join(unique_missing)
        )


def _sensor_spec_uncertainty(source_column: str, sensor_specs: SensorSpecs) -> float | None:
    key = RAW_COLUMN_TO_SENSOR_SPEC.get(source_column)
    if key is None or key not in sensor_specs.channels:
        return None
    return sensor_specs.channels[key].declared_uncertainty


def channel_uncertainty(channel: str, schema_mapping: SchemaMappingConfig, sensor_specs: SensorSpecs) -> float:
    """Declared sensor uncertainty for a canonical channel (0.0 if
    unmapped). Shared by stability perturbation
    (:mod:`iaq_hfis.evaluation.stability`) and gradual-drift magnitude
    gating (:mod:`iaq_hfis.quality.reasons`) -- both need "how much is this
    channel's normal noise floor" from the same source."""
    source_column = schema_mapping.channel(channel).source_column
    return _sensor_spec_uncertainty(source_column, sensor_specs) or 0.0


def dual_channel_tolerance(channel: str, schema_mapping: SchemaMappingConfig, sensor_specs: SensorSpecs) -> float:
    """How far apart the primary and secondary (confirmation-only) readings
    of a dual-sensor channel (temperature, humidity) may be and still count
    as agreeing: the sum of both sensors' own declared uncertainty.

    Replaces a separately-guessed tolerance constant with one derived
    entirely from numbers already established in ``sensor_specs.yaml`` --
    one fewer independent provisional value to confirm, and it can't drift
    out of sync with the uncertainty figures used everywhere else (Hampel
    perturbation, membership width validation, drift-magnitude gating).
    Two independent-error sensors agreeing within the sum of their stated
    tolerances is the standard, conservative way to combine them (as
    opposed to quadrature sum, which assumes independence more precisely
    than these datasheet figures likely warrant).
    """
    entry = schema_mapping.channel(channel)
    primary = _sensor_spec_uncertainty(entry.source_column, sensor_specs) or 0.0
    secondary = 0.0
    if entry.secondary_column is not None:
        secondary = _sensor_spec_uncertainty(entry.secondary_column, sensor_specs) or 0.0
    return primary + secondary


@dataclass
class WidthAdjustment:
    channel: str
    index: int | None  # position within transition_widths, or None for a single-width channel
    configured: float
    required_minimum: float


@dataclass
class MembershipValidationReport:
    """Effective transition widths to use when building membership functions,
    after applying overlap_width_policy. Always safe to use directly —
    'reject' mode never returns without raising if there were violations."""

    policy: str
    violations: list[WidthAdjustment] = field(default_factory=list)
    adjustments: list[WidthAdjustment] = field(default_factory=list)
    effective_monotonic_widths: dict[str, list[float]] = field(default_factory=dict)
    effective_rh_width: float | None = None
    effective_output_widths: list[float] = field(default_factory=list)


def validate_membership_config(
    control_regions: ControlRegions,
    schema_mapping: SchemaMappingConfig,
    sensor_specs: SensorSpecs,
    policy: str,
) -> MembershipValidationReport:
    """Check every configured transition width against the declared
    uncertainty of the sensor channel that feeds it.

    ``policy == "reject"``: raise :class:`MembershipConfigError` listing
    every width narrower than the channel's declared uncertainty.
    ``policy == "auto_expand"``: clamp each narrow width up to the declared
    uncertainty and return the adjustments made (embedded later in the run's
    reproducibility metadata) instead of raising.

    The output channel (index scale, 0-100) has no underlying physical
    sensor, so its transition width is not checked here.
    """
    report = MembershipValidationReport(policy=policy)

    monotonic_channels = {"pm2_5": control_regions.pm2_5, "pm10": control_regions.pm10, "co2": control_regions.co2}
    for name, boundaries in monotonic_channels.items():
        source_column = schema_mapping.channel(name).source_column
        min_width = _sensor_spec_uncertainty(source_column, sensor_specs)
        effective = list(boundaries.transition_widths)
        for i, w in enumerate(effective):
            if min_width is not None and w < min_width:
                adj = WidthAdjustment(channel=name, index=i, configured=w, required_minimum=min_width)
                if policy == "auto_expand":
                    effective[i] = min_width
                    report.adjustments.append(adj)
                else:
                    report.violations.append(adj)
        report.effective_monotonic_widths[name] = effective

    rh = control_regions.relative_humidity
    rh_source = schema_mapping.channel("humidity").source_column
    rh_min = _sensor_spec_uncertainty(rh_source, sensor_specs)
    rh_effective = rh.transition_width
    if rh_min is not None and rh_effective < rh_min:
        adj = WidthAdjustment(channel="relative_humidity", index=None, configured=rh_effective, required_minimum=rh_min)
        if policy == "auto_expand":
            rh_effective = rh_min
            report.adjustments.append(adj)
        else:
            report.violations.append(adj)
    report.effective_rh_width = rh_effective

    # Output (index) transition width has no physical sensor to validate against.
    report.effective_output_widths = list(control_regions.output.transition_widths)

    if policy == "reject" and report.violations:
        lines = [
            f"  - {v.channel}[{v.index}]: width={v.configured} < required minimum "
            f"(declared sensor uncertainty)={v.required_minimum}"
            for v in report.violations
        ]
        raise MembershipConfigError(
            "membership transition width(s) narrower than declared sensor uncertainty "
            "(overlap_width_policy=reject):\n" + "\n".join(lines)
        )

    return report


def validate_room_profile_widths(
    room_profiles: RoomProfilesConfig,
    schema_mapping: SchemaMappingConfig,
    sensor_specs: SensorSpecs,
    policy: str,
) -> MembershipValidationReport:
    """Same check as :func:`validate_membership_config`, applied to every
    temperature room/season profile (a separate config file, so it needs
    its own pass)."""
    report = MembershipValidationReport(policy=policy)
    temp_source = schema_mapping.channel("temperature").source_column
    temp_min = _sensor_spec_uncertainty(temp_source, sensor_specs)

    for profile in room_profiles.profiles:
        key = f"{profile.room}/{profile.season}"
        width = profile.ranges.transition_width
        if temp_min is not None and width < temp_min:
            adj = WidthAdjustment(channel=key, index=None, configured=width, required_minimum=temp_min)
            if policy == "auto_expand":
                report.adjustments.append(adj)
            else:
                report.violations.append(adj)

    if policy == "reject" and report.violations:
        lines = [
            f"  - {v.channel}: transition_width={v.configured} < required minimum "
            f"(declared sensor uncertainty)={v.required_minimum}"
            for v in report.violations
        ]
        raise MembershipConfigError(
            "room profile transition width(s) narrower than declared sensor uncertainty "
            "(overlap_width_policy=reject):\n" + "\n".join(lines)
        )
    return report
