"""Machine-readable provenance for every scientific/operational parameter
that shapes a computed result, plus a structured publication-readiness
assessment -- both merged into ``run_summary_{pipeline_run_id}.json``.

Comments in the YAML config files are not machine-readable and cannot be
tested; this module makes the same information queryable (one row per
parameter: effective value, unit, status, source, whether it was actually
engaged this run) so the report can never silently say "no provisional
parameters" while comments elsewhere say otherwise.

``status`` is one of:
    manuscript_defined    -- numeric value given directly in the manuscript
    standard_based        -- from a cited external standard (e.g. DBN B.2.5-67:2013)
    sensor_specification  -- derived from a datasheet-declared uncertainty
    author_defined        -- a deliberate, documented author choice (not from
                              the manuscript or a standard, but not a guess either)
    provisional           -- not given numerically anywhere cited; needs
                              confirmation or sensitivity analysis
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings
from iaq_hfis.schema import dual_channel_tolerance

STATUS_VALUES = {"manuscript_defined", "standard_based", "sensor_specification", "author_defined", "provisional"}


@dataclass(frozen=True)
class ParameterProvenance:
    path: str
    effective_value: str
    unit: str | None
    status: str
    source: str
    engaged: bool
    sensitivity_coverage: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def collect_parameter_provenance(settings: Settings, sensor_specs: SensorSpecs, room_profiles: RoomProfilesConfig) -> list[ParameterProvenance]:
    """Every parameter is reported regardless of whether it was actually
    used by the computed timestamps in a given run (``engaged`` records
    that separately) -- provenance describes the *configuration*, not one
    run's coverage of it."""
    rows: list[ParameterProvenance] = []

    def add(path: str, value, unit: str | None, status: str, source: str, engaged: bool = True, sensitivity_coverage: str | None = None) -> None:
        assert status in STATUS_VALUES, f"unknown provenance status {status!r} for {path}"
        rows.append(ParameterProvenance(path=path, effective_value=str(value), unit=unit, status=status, source=source, engaged=engaged, sensitivity_coverage=sensitivity_coverage))

    add("cadence.sample_cadence_seconds", settings.cadence.sample_cadence_seconds, "seconds", "manuscript_defined", "Manuscript-specified 30 s collection cycle.")
    add("cadence.aggregation_window_minutes", settings.cadence.aggregation_window_minutes, "minutes", "manuscript_defined", "Manuscript-specified primary operational window.")
    add("cadence.recompute_interval_minutes", settings.cadence.recompute_interval_minutes, "minutes", "manuscript_defined", "Manuscript-specified recompute grid.")
    add(
        "cadence.slot_match_tolerance_seconds", settings.cadence.slot_match_tolerance_seconds, "seconds", "provisional",
        "Half the sensor sample cadence: computed_ts has an arbitrary phase offset from the sensor's own ~30s cadence, "
        "so a tighter tolerance would systematically miss real readings that were never dropped.",
    )
    add("coverage.min_ratio", settings.coverage.min_ratio, None, "manuscript_defined", "Manuscript-specified coverage threshold rho_i(t) >= 0.80.", sensitivity_coverage="swept directly by the sensitivity experiment (coverage_threshold)")

    add(
        "hampel.window_size", settings.hampel.window_size, "samples", "provisional",
        "Pearson, Neuvo, Astola, Gabbouj, \"Generalized Hampel Filters\" (2016) -- the manuscript's own cited source's "
        "illustrative-example parameters (K=5 -> 11-point window); the paper states this as a worked example, not a "
        "general recommendation.",
    )
    add(
        "hampel.mad_multiplier", settings.hampel.mad_multiplier, None, "provisional",
        "Same source as hampel.window_size (t=1 in the cited paper's example).",
    )

    add("confirmation.persistence_min_consecutive_samples", settings.confirmation.persistence_min_consecutive_samples, "samples", "provisional", "Not given numerically in the manuscript.")
    add(
        "confirmation.stuck_value_min_repeats", settings.confirmation.stuck_value_min_repeats, "samples", "provisional",
        "Not given numerically in the manuscript. Exact-equality repeat count; there is no separate stuck-value tolerance parameter.",
    )
    add("confirmation.gradual_drift_min_consecutive_steps", settings.confirmation.gradual_drift_min_consecutive_steps, "samples", "provisional", "Not given numerically in the manuscript.")
    add(
        "confirmation.gradual_drift_magnitude_multiplier", settings.confirmation.gradual_drift_magnitude_multiplier, "x declared sensor uncertainty", "provisional",
        "Not given numerically in the manuscript; empirically verified against live data to avoid flagging ordinary "
        "environmental trends (e.g. CO2 falling after ventilation) as faults.",
    )
    add("confirmation.pm_cross_channel_tolerance_pct", settings.confirmation.pm_cross_channel_tolerance_pct, "%", "provisional", "Not given numerically in the manuscript.")
    for channel in ("temperature", "humidity"):
        tol = dual_channel_tolerance(channel, settings.schema_mapping, sensor_specs)
        add(
            f"derived.dual_channel_tolerance.{channel}", round(tol, 4), "channel units", "sensor_specification",
            "Sum of the primary and secondary sensor's own declared_uncertainty from sensor_specs.yaml "
            "(schema.dual_channel_tolerance) -- not an independently configured value.",
        )
    add(
        "confirmation.outdoor_context_max_age_minutes", settings.confirmation.outdoor_context_max_age_minutes, "minutes", "author_defined",
        "2x the real outdoor weather fetch cadence (air-monitor/scripts/fetch_weather.py runs hourly via cron) -- "
        "tolerates one missed/delayed fetch cycle before flagging staleness.",
    )

    add("profile_selection.season_month_ranges", settings.profile_selection.season_month_ranges, "months", "provisional", "Season cutover months not given in the manuscript.")

    for channel in ("pm2_5", "pm10", "co2"):
        region = getattr(settings.control_regions, channel)
        add(
            f"control_regions.{channel}.transition_widths", region.transition_widths, "channel units", "sensor_specification",
            f"Matches sensor_specs.yaml's declared_uncertainty for {channel} (datasheet-sourced).",
        )
        add(f"control_regions.{channel}.breakpoints", region.breakpoints, "channel units", "standard_based", "WHO 2021 24h air-quality reference points, used as operational control points (not a WHO compliance assessment).")
    add(
        "control_regions.relative_humidity.breakpoints",
        "favorable/acceptable/degraded/critical bands", "%", "standard_based",
        "DBN B.2.5-67:2013 (Ukrainian building-services standard), Додаток Д, Таблиця Д.5.",
    )
    add(
        "control_regions.relative_humidity.transition_width", settings.control_regions.relative_humidity.transition_width, "%", "provisional",
        "Matches sensor_specs.yaml bme_humidity.declared_uncertainty; the RH breakpoints themselves are standard_based (DBN B.2.5-67:2013) but this transition width is not separately specified there.",
    )
    add(
        "control_regions.output.breakpoints", settings.control_regions.output.breakpoints, "index points", "manuscript_defined",
        "The output index scale's own 25/50/75 class boundaries are fixed by the manuscript's method definition.",
    )
    add("control_regions.output.transition_widths", settings.control_regions.output.transition_widths, "index points", "provisional", "Not given numerically in the manuscript.")
    add("membership.output_transition_width", settings.membership.output_transition_width, "index points", "provisional", "Not given numerically in the manuscript; same rationale as control_regions.output.transition_widths.")
    add(
        "membership.dominant_component_tie_tolerance", settings.membership.dominant_component_tie_tolerance, "index points", "author_defined",
        "Not specified in the manuscript. A component within this many crisp-score points of the maximum is still reported as jointly dominant.",
    )

    for profile in room_profiles.profiles:
        key = f"{profile.room}/{profile.season}"
        status = "provisional" if profile.provisional else "standard_based"
        source = (
            "See room_profiles.yaml inline citation for the exact DBN B.2.5-67:2013 table row (or documented author decision) this profile maps to."
            if not profile.provisional
            else "No DBN B.2.5-67:2013 value found for this room/season combination; needs confirmation."
        )
        add(f"room_profiles.{key}.transition_width", profile.ranges.transition_width, "degC", status, source)

    add("evaluation.stability_seed", settings.evaluation.stability_seed, None, "provisional", "The manuscript requires a fixed seed for reproducibility but gives no value.")
    add("evaluation.stability_n_trials", settings.evaluation.stability_n_trials, "trials", "provisional", "Not given numerically in the manuscript.")
    add("evaluation.stability_max_boundary_samples", settings.evaluation.stability_max_boundary_samples, "samples", "author_defined", "Bounds multi-point stability runtime on Raspberry Pi 5; not a manuscript parameter.")
    add("evaluation.stability_max_random_samples", settings.evaluation.stability_max_random_samples, "samples", "author_defined", "Same rationale as stability_max_boundary_samples.")
    add(
        "evaluation.sensitivity_window_minutes", settings.evaluation.sensitivity_window_minutes, "minutes", "manuscript_defined",
        "Manuscript-specified sensitivity window set.", sensitivity_coverage="this parameter IS the sensitivity experiment's own swept axis",
    )
    add(
        "evaluation.sensitivity_coverage_thresholds", settings.evaluation.sensitivity_coverage_thresholds, None, "manuscript_defined",
        "Manuscript-specified coverage-threshold set.", sensitivity_coverage="this parameter IS the sensitivity experiment's own swept axis",
    )
    add("evaluation.sensitivity_max_samples_per_stratum", settings.evaluation.sensitivity_max_samples_per_stratum, "samples", "author_defined", "Bounds multi-point sensitivity runtime.")
    add("evaluation.masking_severity_threshold", settings.evaluation.masking_severity_threshold, None, "provisional", "Which severity counts as 'hidden' by an aggregation baseline; not specified in the manuscript.")
    add("evaluation.continuity_grid_points", settings.evaluation.continuity_grid_points, "points", "author_defined", "Dense-grid resolution for the boundary continuity experiment; not a manuscript parameter.")

    add(
        "aggregation.time_weighted_mean_rule", "weight proportional to each usable sample's time interval to the next sample within the window", None, "manuscript_defined",
        "The manuscript specifies a time-weighted mean aggregation over the rolling window; see aggregation.py.",
    )
    add(
        "evaluation.fault_injection_scenarios", "8 deterministic synthetic scenarios (single_spike, out_of_range, stuck_value, data_loss, gradual_drift, 2x genuine_event, pm_order_violation)", None, "author_defined",
        "Not derived from the manuscript; a fixed, documented synthetic benchmark separate from real-data analysis. See evaluation/fault_injection.py.",
    )
    add(
        "evaluation.hampel_calibration_grid", "window_size in {7,11,15}, mad_multiplier in {1.0,2.0,3.0}", None, "author_defined",
        "Diagnostic-only candidate grid for the fault-injection Hampel calibration; the configured hampel.window_size/mad_multiplier are never auto-changed from this grid alone.",
    )
    add(
        "fuzzy_engine.partial_mode_inference_rule",
        "PARTIAL-mode index rules are regenerated directly from the available components (same worst-of consequent), not the full 3-input rule base with the missing component filtered out",
        None, "provisional",
        "The manuscript does not specify PARTIAL-mode inference mechanics; see fuzzy_engine.infer_index docstring for why naive filtering of the full rule base would be unsound.",
    )

    return rows


def mark_engagement(rows: list[ParameterProvenance], provisional_parameters_used: list[str]) -> list[ParameterProvenance]:
    """``provisional_parameters_used`` (from run_pipeline's own runtime
    validation report) names the subset of provisional/room-profile
    parameters that were actually engaged by some computed_ts this run.
    Everything else defaults to engaged=True (config-level parameters that
    apply to every computed_ts by construction, e.g. Hampel window size).
    Only room-profile and membership-auto-expansion provenance rows can
    legitimately be "not engaged" (a provisional profile that was never
    selected this run)."""
    engaged_paths = set(provisional_parameters_used)
    result = []
    for row in rows:
        if row.path.startswith("room_profiles.") and row.status == "provisional":
            profile_key = row.path.removeprefix("room_profiles.").rsplit(".", 1)[0]
            engaged = any(f"room_profile:{profile_key}" in p for p in engaged_paths)
            result.append(ParameterProvenance(row.path, row.effective_value, row.unit, row.status, row.source, engaged, row.sensitivity_coverage))
        else:
            result.append(row)
    return result


def assess_publication_readiness(summary: dict, provenance: list[ParameterProvenance]) -> dict:
    """A lightweight, always-computable readiness signal based on the
    pipeline/evaluation status and provenance -- NOT a substitute for
    ``iaq_hfis validate-artifacts`` (a separate, artifact-level cross-check
    that requires the report's CSVs/plots to already exist; run it after
    ``iaq_hfis report` and see ``artifact_validation`` in the tracked
    publication snapshot for the authoritative combined result).
    """
    blocking: list[str] = []
    warnings: list[str] = []

    if summary.get("status") != "success":
        blocking.append(f"pipeline run status is '{summary.get('status')}', not 'success'")
    if summary.get("evaluation") is None:
        blocking.append("no evaluation has been run for this pipeline run -- run 'iaq_hfis evaluate' first")

    engaged_provisional = sorted({p.path for p in provenance if p.status == "provisional" and p.engaged})
    if engaged_provisional:
        warnings.append(f"{len(engaged_provisional)} provisional parameter(s) engaged this run -- disclosed in provisional_parameters_used, not resolved")

    sensitivity_covered = sorted({p.path for p in provenance if p.sensitivity_coverage})
    uncovered_provisional = [p for p in engaged_provisional if p not in sensitivity_covered]
    if uncovered_provisional:
        warnings.append(f"{len(uncovered_provisional)} engaged provisional parameter(s) have no sensitivity-analysis coverage: {', '.join(uncovered_provisional)}")

    return {
        "ready": len(blocking) == 0,
        "blocking_issues": blocking,
        "warnings": warnings,
        "provisional_parameters_used": engaged_provisional,
        "parameters_covered_by_sensitivity_analysis": sensitivity_covered,
        "tests_executed": None,
        "artifact_validation": None,
    }
