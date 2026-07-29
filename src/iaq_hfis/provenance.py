"""Machine-readable provenance for every scientific/operational parameter
that shapes a computed result, plus a structured publication-readiness
assessment -- both merged into ``run_summary_{pipeline_run_id}.json``.

Comments in the YAML config files are not machine-readable and cannot be
tested; this module makes the same information queryable (one row per
parameter: effective value, unit, status, source file/key, scientific
rationale, pipeline stage, and whether it was actually engaged this run)
so the report can never silently say "no provisional parameters" while
another artifact disagrees.

**Single source of truth**: :func:`engaged_provisional_paths` is the ONLY
place that decides which parameters count as "engaged" for a run. Every
artifact that reports a provisional-parameter list or count (run_summary.json
top-level field, run_summary.md, run_narrative.md, publication_readiness,
article_results_summary.md, parameter_provenance.csv, latest_run.json) must
derive from this same function's output -- never recompute independently.
See ``iaq_hfis.validation``'s cross-artifact check for the regression test.

``status`` is one of:
    MANUSCRIPT_DEFINED    -- numeric value given directly in the manuscript
    STANDARD_BASED        -- from a cited external standard (e.g. DBN B.2.5-67:2013)
    SENSOR_SPECIFICATION  -- taken directly from a datasheet-declared uncertainty
    DERIVED                -- computed at runtime from other provenanced values
                              (e.g. the sum of two sensor_specification values)
    AUTHOR_DEFINED         -- a deliberate, documented author choice (not from
                              the manuscript or a standard, but not a guess either)
    PROVISIONAL            -- not given numerically anywhere cited; needs
                              confirmation or sensitivity analysis
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings
from iaq_hfis.schema import dual_channel_tolerance

STATUS_VALUES = {"MANUSCRIPT_DEFINED", "STANDARD_BASED", "SENSOR_SPECIFICATION", "DERIVED", "AUTHOR_DEFINED", "PROVISIONAL"}


@dataclass(frozen=True)
class ParameterProvenance:
    path: str
    effective_value: str
    unit: str | None
    status: str
    source_file: str
    source_key_path: str
    scientific_rationale: str
    pipeline_stage: str
    manuscript_reference: str | None
    engaged: bool
    sensitivity_coverage: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def collect_parameter_provenance(settings: Settings, sensor_specs: SensorSpecs, room_profiles: RoomProfilesConfig) -> list[ParameterProvenance]:
    """Every parameter is reported regardless of whether it was actually
    used by the computed timestamps in a given run (``engaged`` records
    that separately, and starts as a provisional default here -- the
    authoritative value is assigned by :func:`mark_engagement`) --
    provenance describes the *configuration*, not one run's coverage of it.
    """
    rows: list[ParameterProvenance] = []

    def add(
        path: str,
        value,
        unit: str | None,
        status: str,
        rationale: str,
        source_file: str = "config/iaq_hfis.yaml",
        source_key_path: str | None = None,
        pipeline_stage: str = "unspecified",
        manuscript_reference: str | None = None,
        sensitivity_coverage: str | None = None,
    ) -> None:
        assert status in STATUS_VALUES, f"unknown provenance status {status!r} for {path}"
        rows.append(
            ParameterProvenance(
                path=path, effective_value=str(value), unit=unit, status=status,
                source_file=source_file, source_key_path=source_key_path or path,
                scientific_rationale=rationale, pipeline_stage=pipeline_stage,
                manuscript_reference=manuscript_reference, engaged=True, sensitivity_coverage=sensitivity_coverage,
            )
        )

    add("cadence.sample_cadence_seconds", settings.cadence.sample_cadence_seconds, "seconds", "MANUSCRIPT_DEFINED",
        "Manuscript-specified 30 s collection cycle.", pipeline_stage="aggregation", manuscript_reference="Materials and Methods: data collection cadence")
    add("cadence.aggregation_window_minutes", settings.cadence.aggregation_window_minutes, "minutes", "MANUSCRIPT_DEFINED",
        "Manuscript-specified primary operational window.", pipeline_stage="aggregation", manuscript_reference="Materials and Methods: rolling window")
    add("cadence.recompute_interval_minutes", settings.cadence.recompute_interval_minutes, "minutes", "MANUSCRIPT_DEFINED",
        "Manuscript-specified recompute grid.", pipeline_stage="aggregation", manuscript_reference="Materials and Methods: recompute cadence")
    add("cadence.slot_match_tolerance_seconds", settings.cadence.slot_match_tolerance_seconds, "seconds", "PROVISIONAL",
        "Half the sensor sample cadence: computed_ts has an arbitrary phase offset from the sensor's own ~30s cadence, "
        "so a tighter tolerance would systematically miss real readings that were never dropped.", pipeline_stage="validation")
    add("coverage.min_ratio", settings.coverage.min_ratio, None, "MANUSCRIPT_DEFINED",
        "Manuscript-specified coverage threshold rho_i(t) >= 0.80.", pipeline_stage="completeness",
        manuscript_reference="Materials and Methods: coverage ratio", sensitivity_coverage="swept directly by the sensitivity experiment (coverage_threshold)")

    add("hampel.window_size", settings.hampel.window_size, "samples", "PROVISIONAL",
        "Pearson, Neuvo, Astola, Gabbouj, \"Generalized Hampel Filters\" (2016) -- the manuscript's own cited source's "
        "illustrative-example parameters (K=5 -> 11-point window); the paper states this as a worked example, not a "
        "general recommendation.", pipeline_stage="validation", manuscript_reference="Cited: Pearson et al. 2016, Hampel filter")
    add("hampel.mad_multiplier", settings.hampel.mad_multiplier, None, "PROVISIONAL",
        "Same source as hampel.window_size (t=1 in the cited paper's example).", pipeline_stage="validation",
        manuscript_reference="Cited: Pearson et al. 2016, Hampel filter")

    add("confirmation.persistence_min_consecutive_samples", settings.confirmation.persistence_min_consecutive_samples, "samples", "PROVISIONAL",
        "Not given numerically in the manuscript.", pipeline_stage="validation")
    add("confirmation.stuck_value_min_repeats", settings.confirmation.stuck_value_min_repeats, "samples", "PROVISIONAL",
        "Not given numerically in the manuscript. Exact-equality repeat count; there is no separate stuck-value tolerance parameter.", pipeline_stage="validation")
    add("confirmation.gradual_drift_min_consecutive_steps", settings.confirmation.gradual_drift_min_consecutive_steps, "samples", "PROVISIONAL",
        "Not given numerically in the manuscript.", pipeline_stage="validation")
    add("confirmation.gradual_drift_magnitude_multiplier", settings.confirmation.gradual_drift_magnitude_multiplier, "x declared sensor uncertainty", "PROVISIONAL",
        "Not given numerically in the manuscript; empirically verified against live data to avoid flagging ordinary "
        "environmental trends (e.g. CO2 falling after ventilation) as faults.", pipeline_stage="validation")
    add("confirmation.pm_cross_channel_tolerance_pct", settings.confirmation.pm_cross_channel_tolerance_pct, "%", "PROVISIONAL",
        "Not given numerically in the manuscript.", pipeline_stage="validation")
    for channel in ("temperature", "humidity"):
        tol = dual_channel_tolerance(channel, settings.schema_mapping, sensor_specs)
        add(f"derived.dual_channel_tolerance.{channel}", round(tol, 4), "channel units", "DERIVED",
            "Sum of the primary and secondary sensor's own declared_uncertainty from sensor_specs.yaml "
            "(schema.dual_channel_tolerance) -- not an independently configured value.",
            source_file="src/iaq_hfis/schema.py", source_key_path="dual_channel_tolerance()", pipeline_stage="validation")
    add("confirmation.outdoor_context_max_age_minutes", settings.confirmation.outdoor_context_max_age_minutes, "minutes", "AUTHOR_DEFINED",
        "2x the real outdoor weather fetch cadence (air-monitor/scripts/fetch_weather.py runs hourly via cron) -- "
        "tolerates one missed/delayed fetch cycle before flagging staleness.", pipeline_stage="validation")

    add("profile_selection.season_month_ranges", settings.profile_selection.season_month_ranges, "months", "PROVISIONAL",
        "Season cutover months not given in the manuscript.", pipeline_stage="profile_selection")

    for channel in ("pm2_5", "pm10", "co2"):
        region = getattr(settings.control_regions, channel)
        add(f"control_regions.{channel}.transition_widths", region.transition_widths, "channel units", "SENSOR_SPECIFICATION",
            f"Matches sensor_specs.yaml's declared_uncertainty for {channel} (datasheet-sourced).",
            source_file="config/sensor_specs.yaml", pipeline_stage="membership_construction")
        add(f"control_regions.{channel}.breakpoints", region.breakpoints, "channel units", "STANDARD_BASED",
            "WHO 2021 24h air-quality reference points, used as operational control points (not a WHO compliance assessment).",
            pipeline_stage="membership_construction", manuscript_reference="Table 2: control regions")
    add("control_regions.relative_humidity.breakpoints", "favorable/acceptable/degraded/critical bands", "%", "STANDARD_BASED",
        "DBN B.2.5-67:2013 (Ukrainian building-services standard), Додаток Д, Таблиця Д.5.",
        pipeline_stage="membership_construction", manuscript_reference="Table 2: control regions")
    add("control_regions.relative_humidity.transition_width", settings.control_regions.relative_humidity.transition_width, "%", "PROVISIONAL",
        "Matches sensor_specs.yaml bme_humidity.declared_uncertainty; the RH breakpoints themselves are standard-based (DBN B.2.5-67:2013) but this transition width is not separately specified there.",
        pipeline_stage="membership_construction")
    add("control_regions.output.breakpoints", settings.control_regions.output.breakpoints, "index points", "MANUSCRIPT_DEFINED",
        "The output index scale's own 25/50/75 class boundaries are fixed by the manuscript's method definition.",
        pipeline_stage="membership_construction", manuscript_reference="Output class boundaries 25/50/75")
    add("control_regions.output.transition_widths", settings.control_regions.output.transition_widths, "index points", "PROVISIONAL",
        "Not given numerically in the manuscript.", pipeline_stage="membership_construction")
    add("membership.output_transition_width", settings.membership.output_transition_width, "index points", "PROVISIONAL",
        "Not given numerically in the manuscript; same rationale as control_regions.output.transition_widths.", pipeline_stage="membership_construction")
    add("membership.dominant_component_tie_tolerance", settings.membership.dominant_component_tie_tolerance, "index points", "AUTHOR_DEFINED",
        "Not specified in the manuscript. A component within this many crisp-score points of the maximum is still reported as jointly dominant.",
        pipeline_stage="fuzzy_inference")

    for profile in room_profiles.profiles:
        key = f"{profile.room}/{profile.season}"
        status = "PROVISIONAL" if profile.provisional else "STANDARD_BASED"
        rationale = (
            "See room_profiles.yaml inline citation for the exact DBN B.2.5-67:2013 table row (or documented author decision) this profile maps to."
            if not profile.provisional
            else "No DBN B.2.5-67:2013 value found for this room/season combination; needs confirmation."
        )
        add(f"room_profiles.{key}.transition_width", profile.ranges.transition_width, "degC", status, rationale,
            source_file="config/room_profiles.yaml", pipeline_stage="profile_selection")

    add("evaluation.stability_seed", settings.evaluation.stability_seed, None, "PROVISIONAL",
        "The manuscript requires a fixed seed for reproducibility but gives no value.", pipeline_stage="evaluation_stability")
    add("evaluation.stability_n_trials", settings.evaluation.stability_n_trials, "trials", "PROVISIONAL",
        "Not given numerically in the manuscript.", pipeline_stage="evaluation_stability")
    add("evaluation.stability_max_boundary_samples", settings.evaluation.stability_max_boundary_samples, "samples", "AUTHOR_DEFINED",
        "Bounds multi-point stability runtime on Raspberry Pi 5; not a manuscript parameter.", pipeline_stage="evaluation_stability")
    add("evaluation.stability_max_random_samples", settings.evaluation.stability_max_random_samples, "samples", "AUTHOR_DEFINED",
        "Same rationale as stability_max_boundary_samples.", pipeline_stage="evaluation_stability")
    add("evaluation.sensitivity_window_minutes", settings.evaluation.sensitivity_window_minutes, "minutes", "MANUSCRIPT_DEFINED",
        "Manuscript-specified sensitivity window set.", pipeline_stage="evaluation_sensitivity",
        manuscript_reference="Sensitivity protocol: window set", sensitivity_coverage="this parameter IS the sensitivity experiment's own swept axis")
    add("evaluation.sensitivity_coverage_thresholds", settings.evaluation.sensitivity_coverage_thresholds, None, "MANUSCRIPT_DEFINED",
        "Manuscript-specified coverage-threshold set.", pipeline_stage="evaluation_sensitivity",
        manuscript_reference="Sensitivity protocol: coverage threshold set", sensitivity_coverage="this parameter IS the sensitivity experiment's own swept axis")
    add("evaluation.sensitivity_max_samples_per_stratum", settings.evaluation.sensitivity_max_samples_per_stratum, "samples", "AUTHOR_DEFINED",
        "Bounds multi-point sensitivity runtime.", pipeline_stage="evaluation_sensitivity")
    add("evaluation.masking_severity_threshold", settings.evaluation.masking_severity_threshold, None, "PROVISIONAL",
        "Which severity counts as 'hidden' by an aggregation baseline; not specified in the manuscript.", pipeline_stage="evaluation_masking")
    add("evaluation.continuity_grid_points", settings.evaluation.continuity_grid_points, "points", "AUTHOR_DEFINED",
        "Dense-grid resolution for the boundary continuity experiment; not a manuscript parameter.", pipeline_stage="evaluation_continuity")

    add("aggregation.time_weighted_mean_rule", "weight proportional to each usable sample's time interval to the next sample within the window",
        None, "MANUSCRIPT_DEFINED", "The manuscript specifies a time-weighted mean aggregation over the rolling window; see aggregation.py.",
        source_file="src/iaq_hfis/aggregation.py", source_key_path="aggregate_channel()", pipeline_stage="aggregation",
        manuscript_reference="Materials and Methods: time-weighted aggregation")
    add("evaluation.fault_injection_scenarios",
        "60 deterministic synthetic scenarios across 5 channels (co2, temperature, humidity, pm10, pm2_5) x "
        "5 reason codes (single_spike incl. one alternate magnitude, out_of_range, stuck_value, data_loss, gradual_drift) "
        "plus genuine-event preservation checks, split 30/30 into disjoint calibration/validation sets",
        None, "AUTHOR_DEFINED", "Not derived from the manuscript; a fixed, documented synthetic benchmark separate from real-data analysis.",
        source_file="src/iaq_hfis/evaluation/fault_injection.py", pipeline_stage="evaluation_fault_injection")
    add("evaluation.hampel_calibration_grid", "window_size in {7,11,15}, mad_multiplier in {1.0,2.0,3.0}", None, "AUTHOR_DEFINED",
        "Diagnostic-only candidate grid for the fault-injection Hampel calibration; the configured hampel.window_size/mad_multiplier are never auto-changed from this grid alone.",
        source_file="src/iaq_hfis/evaluation/fault_injection.py", pipeline_stage="evaluation_fault_injection")
    add("fuzzy_engine.partial_mode_inference_rule",
        "PARTIAL-mode index rules are regenerated directly from the available components (same worst-of consequent), not the full 3-input rule base with the missing component filtered out",
        None, "PROVISIONAL", "The manuscript does not specify PARTIAL-mode inference mechanics; see fuzzy_engine.infer_index docstring for why naive filtering of the full rule base would be unsound.",
        source_file="src/iaq_hfis/fuzzy_engine.py", source_key_path="infer_index()", pipeline_stage="fuzzy_inference")

    return rows


def engaged_provisional_paths(rows: list[ParameterProvenance], provisional_profile_events: list[str]) -> list[str]:
    """The single authoritative list of provisional-parameter paths engaged
    by a run. Every config-level PROVISIONAL row is engaged unconditionally
    (it applies to every computed_ts by construction, e.g. the Hampel
    window size). A ``room_profiles.*`` PROVISIONAL row is engaged only if
    ``provisional_profile_events`` (from the pipeline run's own
    ``room_profile:<room>/<season>`` selection events) actually names it.

    This is the ONE function every artifact must call (directly or via
    :func:`mark_engagement`) to determine the engaged list -- never
    recomputed independently, which is exactly how run_summary.md/
    run_narrative.md and publication_readiness previously disagreed.
    """
    engaged_events = set(provisional_profile_events)
    paths = []
    for row in rows:
        if row.status != "PROVISIONAL":
            continue
        if row.path.startswith("room_profiles."):
            profile_key = row.path.removeprefix("room_profiles.").rsplit(".", 1)[0]
            if any(f"room_profile:{profile_key}" in e for e in engaged_events):
                paths.append(row.path)
        else:
            paths.append(row.path)
    return sorted(paths)


def mark_engagement(rows: list[ParameterProvenance], provisional_profile_events: list[str]) -> list[ParameterProvenance]:
    """Returns ``rows`` with ``engaged`` set authoritatively for every row
    (not just PROVISIONAL ones -- non-provisional rows are always engaged,
    since they describe fixed manuscript/standard/sensor/derived/author
    values that apply to every computed_ts)."""
    engaged_paths = set(engaged_provisional_paths(rows, provisional_profile_events))
    return apply_known_engagement(rows, sorted(engaged_paths))


def apply_known_engagement(rows: list[ParameterProvenance], engaged_paths: list[str]) -> list[ParameterProvenance]:
    """Marks ``engaged`` from an ALREADY-DECIDED authoritative list of
    engaged provisional-parameter paths (e.g. read back from
    ``run_summary.json["provisional_parameters_used"]``, which was itself
    produced by :func:`mark_engagement` at ``run`` time). Non-provisional
    rows are always engaged. This is what ``report``-time code must use --
    it must never re-derive engagement from raw profile-selection events a
    second time, which is exactly how the two ended up disagreeing before.
    """
    engaged_set = set(engaged_paths)
    result = []
    for row in rows:
        engaged = True if row.status != "PROVISIONAL" else row.path in engaged_set
        result.append(
            ParameterProvenance(
                row.path, row.effective_value, row.unit, row.status, row.source_file, row.source_key_path,
                row.scientific_rationale, row.pipeline_stage, row.manuscript_reference, engaged, row.sensitivity_coverage,
            )
        )
    return result


def assess_publication_readiness(summary: dict, provenance: list[ParameterProvenance]) -> dict:
    """A lightweight, always-computable readiness signal based on the
    pipeline/evaluation status and provenance -- NOT a substitute for
    ``iaq_hfis validate-artifacts`` (a separate, artifact-level cross-check
    that requires the report's CSVs/plots to already exist; run it after
    ``iaq_hfis report`` and see ``artifact_validation`` in the tracked
    publication snapshot for the authoritative combined result).

    ``provisional_parameters_used`` here is always taken verbatim from
    ``summary["provisional_parameters_used"]`` (the single authoritative
    list set once at ``run`` time) -- never recomputed from ``provenance``
    independently, so this can never drift from run_summary.md/
    run_narrative.md, which read the same top-level field.
    """
    blocking: list[str] = []
    warnings: list[str] = []

    if summary.get("status") != "success":
        blocking.append(f"pipeline run status is '{summary.get('status')}', not 'success'")
    if summary.get("evaluation") is None:
        blocking.append("no evaluation has been run for this pipeline run -- run 'iaq_hfis evaluate' first")

    engaged_provisional = sorted(summary.get("provisional_parameters_used") or [])
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
