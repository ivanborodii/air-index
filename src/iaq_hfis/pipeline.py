"""Orchestration: one computed timestamp end-to-end, and a run over a
time range.

Phase 1 scope: validation, aggregation, membership, Mamdani inference,
completeness status, persistence, and minimal reproducibility metadata.
Baselines, evaluation, narrative generation and plotting are Phase 2.
"""

from __future__ import annotations

import json
import logging
import resource
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from iaq_hfis import membership, profiles, timegrid
from iaq_hfis.aggregation import aggregate_channel
from iaq_hfis.completeness import completeness_status
from iaq_hfis.config import RoomProfilesConfig, RoomTemperatureProfile, SensorSpecs, Settings, TemperatureProfileNotDefinedError, config_hash
from iaq_hfis.constants import COMPONENT_INPUTS, OUTPUT_MAX, OUTPUT_MIN
from iaq_hfis.db import AirMonitorSource, DerivedResultsWriter
from iaq_hfis.fuzzy_engine import MamdaniEngine
from iaq_hfis.models import ComponentInferenceResult, CompletenessResult, CoverageResult, IndexInferenceResult
from iaq_hfis.outdoor_context import fetch_outdoor_context
from iaq_hfis.provenance import collect_parameter_provenance, engaged_provisional_paths
from iaq_hfis.quality.hard_checks import run_hard_checks
from iaq_hfis.quality.soft_checks import run_soft_checks
from iaq_hfis.reproducibility import collect_environment_metadata
from iaq_hfis.rules import build_rule_base
from iaq_hfis.schema import channel_uncertainty, dual_channel_tolerance, validate_membership_config, validate_room_profile_widths, validate_schema_mapping

logger = logging.getLogger(__name__)

#: air_ml/ repository root (src/iaq_hfis/pipeline.py -> src/iaq_hfis -> src -> air_ml).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Direct-input channels the pipeline validates/aggregates every computed_ts.
DIRECT_INPUT_CHANNELS = ["pm2_5", "pm10", "co2", "temperature", "humidity"]

#: Discretization resolution for the centroid defuzzification integral.
_OUTPUT_UNIVERSE_STEPS = 401


@dataclass
class RuntimeContext:
    """Everything built once per run and reused across every computed_ts."""

    settings: Settings
    sensor_specs: SensorSpecs
    room_profiles: RoomProfilesConfig
    engine: MamdaniEngine
    static_shapes: dict[str, dict]
    temperature_shapes_by_profile: dict[tuple[str, str], dict]
    config_hash: str
    provisional_parameters_used: list[str] = field(default_factory=list)
    #: Mutated during the run: room/season profiles marked provisional:true
    #: that were actually selected for some computed_ts (e.g. the kitchen/
    #: warm_period stand-in). Distinct from provisional_parameters_used,
    #: which is fixed at startup from config validation alone.
    provisional_profiles_used: set[str] = field(default_factory=set)


def build_runtime_context(settings: Settings, sensor_specs: SensorSpecs, room_profiles: RoomProfilesConfig, actual_raw_columns: set[str]) -> RuntimeContext:
    """One-time setup: schema/membership validation, membership function
    construction, and the (config-invariant) Mamdani engine."""
    validate_schema_mapping(settings.schema_mapping, actual_raw_columns)

    policy = settings.membership.overlap_width_policy
    width_report = validate_membership_config(settings.control_regions, settings.schema_mapping, sensor_specs, policy)
    room_width_report = validate_room_profile_widths(room_profiles, settings.schema_mapping, sensor_specs, policy)

    provisional: list[str] = []
    for adj in width_report.adjustments + room_width_report.adjustments:
        provisional.append(f"membership.overlap_width_auto_expanded:{adj.channel}[{adj.index}]")

    control_regions = settings.control_regions
    static_shapes = {
        "pm2_5": membership.build_monotonic_classes(control_regions.pm2_5.breakpoints, width_report.effective_monotonic_widths["pm2_5"]),
        "pm10": membership.build_monotonic_classes(control_regions.pm10.breakpoints, width_report.effective_monotonic_widths["pm10"]),
        "co2": membership.build_monotonic_classes(control_regions.co2.breakpoints, width_report.effective_monotonic_widths["co2"]),
        "relative_humidity": membership.build_two_sided_classes(control_regions.relative_humidity, width_report.effective_rh_width),
        "output": membership.build_monotonic_classes(control_regions.output.breakpoints, width_report.effective_output_widths),
    }

    room_adjustment_by_key = {adj.channel: adj.required_minimum for adj in room_width_report.adjustments}
    temperature_shapes_by_profile: dict[tuple[str, str], dict] = {}
    for profile in room_profiles.profiles:
        key_str = f"{profile.room}/{profile.season}"
        width = room_adjustment_by_key.get(key_str, profile.ranges.transition_width)
        temperature_shapes_by_profile[(profile.room, profile.season)] = membership.build_two_sided_classes(profile.ranges, width)

    rule_base = build_rule_base()
    output_universe = np.linspace(OUTPUT_MIN, OUTPUT_MAX, _OUTPUT_UNIVERSE_STEPS)
    engine = MamdaniEngine(rule_base, static_shapes["output"], output_universe)

    return RuntimeContext(
        settings=settings,
        sensor_specs=sensor_specs,
        room_profiles=room_profiles,
        engine=engine,
        static_shapes=static_shapes,
        temperature_shapes_by_profile=temperature_shapes_by_profile,
        config_hash=config_hash(settings, sensor_specs, room_profiles),
        provisional_parameters_used=provisional,
    )


def _compute_outdoor_trend_sign(outdoor_ctx: dict, channel: str) -> int | None:
    field_by_channel = {"pm2_5": "pm2_5", "pm10": "pm10", "temperature": "temperature", "humidity": "humidity"}
    key = field_by_channel.get(channel)
    if key is None:
        return None
    return outdoor_ctx["trend_signs"].get(key)


def infer_from_values(
    ctx: RuntimeContext, values: dict[str, float], available_components: set[str], profile: RoomTemperatureProfile | None
) -> tuple[dict[str, ComponentInferenceResult], IndexInferenceResult | None]:
    """Pure inference from already-aggregated channel values (no I/O, no DB
    writes): builds membership degrees, runs the two-level Mamdani engine,
    and returns per-component results plus the final index result (None if
    no components are available).

    ``profile`` may be ``None`` only when "M" has already been excluded from
    ``available_components`` (exploratory mode with no DBN-supported
    temperature profile for this room/season) -- it is never dereferenced
    in that case.

    Reused by :func:`compute_index_at` (the live pipeline) and by
    :mod:`iaq_hfis.evaluation.stability` / :mod:`iaq_hfis.baselines` callers
    that need to recompute from perturbed or synthetic values without
    re-running validation/aggregation.
    """
    component_results: dict[str, ComponentInferenceResult] = {}
    for component, inputs in COMPONENT_INPUTS.items():
        if component not in available_components:
            continue
        input_memberships = {}
        for ch in inputs:
            if ch == "temperature":
                shapes = ctx.temperature_shapes_by_profile[(profile.room, profile.season)]
            else:
                shapes = ctx.static_shapes["relative_humidity" if ch == "humidity" else ch]
            input_memberships[ch] = membership.evaluate_memberships(values[ch], shapes)
        component_results[component] = ctx.engine.infer_component(component, input_memberships)

    index_result = None
    if available_components:
        component_degrees = {c: r.class_degrees for c, r in component_results.items()}
        component_crisp_scores = {c: r.crisp_score for c, r in component_results.items()}
        index_result = ctx.engine.infer_index(
            component_degrees, available_components, component_crisp_scores, ctx.settings.membership.dominant_component_tie_tolerance
        )
    return component_results, index_result


def compute_index_at(
    ctx: RuntimeContext,
    source: AirMonitorSource,
    computed_ts: datetime,
    window_minutes: int,
    writer: DerivedResultsWriter | None,
    pipeline_run_id: str | None = None,
    mode: Literal["publication", "exploratory"] = "publication",
) -> dict:
    """Full pipeline for one (computed_ts, window_minutes) pair: validate,
    aggregate, infer, classify completeness, and (if ``writer`` given)
    persist every derived row tagged with ``pipeline_run_id`` (required
    whenever ``writer`` is given -- every persisted row must be run-isolated).
    Returns a small summary dict for run-level logging/metadata.
    """
    if writer is not None and pipeline_run_id is None:
        raise ValueError("pipeline_run_id is required when writer is given (every persisted row must be run-isolated)")
    settings = ctx.settings
    window_start = computed_ts - _minutes(window_minutes)
    now = datetime.now(timezone.utc)

    expected = timegrid.expected_slots(computed_ts, window_minutes, settings.cadence.sample_cadence_seconds)
    raw_df = source.fetch_raw_window(window_start, computed_ts)
    outdoor_ctx = fetch_outdoor_context(source, computed_ts, settings.confirmation.outdoor_context_max_age_minutes)

    coverage: dict[str, CoverageResult] = {}
    weighted_means: dict[str, float | None] = {}

    for channel in DIRECT_INPUT_CHANNELS:
        channel_map = settings.schema_mapping.channel(channel)
        matched_slots = timegrid.match_actual_to_slots(expected, raw_df["ts"] if "ts" in raw_df.columns else raw_df, settings.cadence.slot_match_tolerance_seconds)

        stage1_df = run_hard_checks(
            raw_df, matched_slots, channel, channel_map, ctx.sensor_specs, settings.device_status_state_map,
            pm_ordering_tolerance_pct=settings.confirmation.pm_cross_channel_tolerance_pct,
        )
        aligned_raw = timegrid.align_columns_to_slots(raw_df, matched_slots, list(raw_df.columns))
        outdoor_trend_sign = _compute_outdoor_trend_sign(outdoor_ctx, channel)

        drift_min_magnitude = channel_uncertainty(channel, settings.schema_mapping, ctx.sensor_specs) * settings.confirmation.gradual_drift_magnitude_multiplier
        dual_tolerance = dual_channel_tolerance(channel, settings.schema_mapping, ctx.sensor_specs) if channel in ("temperature", "humidity") else 0.0
        stage2_df = run_soft_checks(stage1_df, channel, channel_map, aligned_raw, outdoor_trend_sign, settings.hampel, settings.confirmation, drift_min_magnitude, dual_tolerance)
        stage2_df["channel"] = channel

        aggregate = aggregate_channel(stage2_df, channel, window_start, computed_ts, settings.coverage.min_ratio)
        coverage[channel] = aggregate.coverage
        weighted_means[channel] = aggregate.weighted_mean

        if writer is not None:
            _persist_quality(writer, stage2_df, now, pipeline_run_id)
            writer.connection.execute(
                """INSERT OR REPLACE INTO window_aggregates
                   (pipeline_run_id, computed_ts, window_minutes, channel, n_expected, n_usable, coverage_ratio, coverage_ok, weighted_mean)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [pipeline_run_id, computed_ts, window_minutes, channel, aggregate.coverage.n_expected, aggregate.coverage.n_usable, aggregate.coverage.ratio, aggregate.coverage.ok, aggregate.weighted_mean],
            )

    completeness = completeness_status(coverage)

    try:
        profile = profiles.select_room_season(ctx.room_profiles, computed_ts, settings.profile_selection)
    except TemperatureProfileNotDefinedError:
        if mode == "publication":
            # Publication mode: a missing temperature profile is a blocking
            # configuration error. The full A/V/M/I manuscript run must not
            # proceed at all -- propagate and abort the whole pipeline run
            # rather than silently degrading this one timestamp.
            raise
        # Exploratory mode: the microclimate component is structurally
        # omitted (never fabricated) for this timestamp; A and V may still
        # be computed. This is never eligible for research_results/final.
        profile = None

    if profile is not None and profile.provisional:
        ctx.provisional_profiles_used.add(f"room_profile:{profile.room}/{profile.season}")

    availability = {comp: comp not in completeness.missing_components for comp in COMPONENT_INPUTS}
    if profile is None:
        availability["M"] = False
    available_components = {comp for comp, ok in availability.items() if ok}

    if profile is None:
        # Re-derive completeness so a profile-caused M exclusion is reflected
        # consistently in the persisted status/missing_components, not just
        # in local component selection.
        missing_components = sorted(set(completeness.missing_components) | {"M"})
        missing_inputs = sorted(set(completeness.missing_inputs) | {"temperature", "humidity"})
        n_missing = len(missing_components)
        status = "OK" if n_missing == 0 else "PARTIAL" if n_missing == 1 else "FAILED"
        completeness = CompletenessResult(status=status, missing_components=missing_components, missing_inputs=missing_inputs)

    component_results, index_result = infer_from_values(ctx, weighted_means, available_components, profile)
    if completeness.status == "FAILED":
        # FAILED can still have exactly one component technically available (e.g. only V) --
        # the manuscript requires index/class stay unformed regardless, not a placeholder number.
        index_result = None

    profile_room = profile.room if profile is not None else None
    profile_season = profile.season if profile is not None else None
    if writer is not None:
        for component, result in component_results.items():
            cd = result.class_degrees
            writer.connection.execute(
                """INSERT OR REPLACE INTO component_scores
                   (pipeline_run_id, computed_ts, window_minutes, component, available, missing_inputs,
                    membership_favorable, membership_acceptable, membership_degraded, membership_critical,
                    crisp_score, room, season)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [pipeline_run_id, computed_ts, window_minutes, component, True, [], cd.get("Favorable"), cd.get("Acceptable"), cd.get("Degraded"), cd.get("Critical"), result.crisp_score, profile_room, profile_season],
            )
        for component in COMPONENT_INPUTS:
            if not availability[component]:
                missing = [ch for ch in COMPONENT_INPUTS[component] if ch in completeness.missing_inputs]
                writer.connection.execute(
                    """INSERT OR REPLACE INTO component_scores
                       (pipeline_run_id, computed_ts, window_minutes, component, available, missing_inputs,
                        membership_favorable, membership_acceptable, membership_degraded, membership_critical,
                        crisp_score, room, season)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [pipeline_run_id, computed_ts, window_minutes, component, False, missing, None, None, None, None, None, profile_room, profile_season],
                )

    if writer is not None:
        index_value = index_result.index_value if index_result else None
        index_class = index_result.index_class if index_result else None
        dominance = index_result.dominance if index_result else None
        contributors = index_result.rule_level_contributors if index_result else []
        n_fired = index_result.n_rules_fired if index_result else None
        writer.connection.execute(
            """INSERT OR REPLACE INTO iaq_index_results
               (pipeline_run_id, computed_ts, window_minutes, completeness_status, missing_components, missing_inputs,
                index_value, index_class, dominant_component, co_dominant_components, worst_component_class,
                largest_component_score, dominance_reason, rule_level_contributors, n_rules_fired, engine_version, config_hash, computed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [pipeline_run_id, computed_ts, window_minutes, completeness.status, completeness.missing_components, completeness.missing_inputs,
             index_value, index_class,
             dominance.dominant_component if dominance else None,
             dominance.co_dominant_components if dominance else [],
             dominance.worst_component_class if dominance else None,
             dominance.largest_component_score if dominance else None,
             dominance.dominance_reason if dominance else None,
             contributors, n_fired, settings.engine_version, ctx.config_hash, now],
        )
        writer.connection.execute(
            """INSERT OR REPLACE INTO outdoor_context
               (pipeline_run_id, computed_ts, outdoor_forecast_time, age_minutes, is_stale, pm2_5, pm10, temperature_2m, relative_humidity_2m)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [pipeline_run_id, computed_ts, outdoor_ctx["forecast_time"], outdoor_ctx["age_minutes"], outdoor_ctx["is_stale"], outdoor_ctx["pm2_5"], outdoor_ctx["pm10"], outdoor_ctx["temperature_2m"], outdoor_ctx["relative_humidity_2m"]],
        )

    return {
        "computed_ts": computed_ts,
        "completeness_status": completeness.status,
        "index_value": index_result.index_value if index_result else None,
        "index_class": index_result.index_class if index_result else None,
    }


def _persist_quality(writer: DerivedResultsWriter, stage2_df, computed_at: datetime, pipeline_run_id: str) -> None:
    for _, row in stage2_df.iterrows():
        writer.connection.execute(
            """INSERT OR REPLACE INTO observation_quality
               (pipeline_run_id, ts, channel, raw_value, stage1_state, stage2_state, usable, confirmed, reason_codes,
                hampel_median, hampel_mad, computed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [pipeline_run_id, row["ts"], row["channel"], row["raw_value"], row["stage1_state"], row["stage2_state"], bool(row["usable"]), row["confirmed"], row["reason_codes"], row["hampel_median"], row["hampel_mad"], computed_at],
        )


def _minutes(n: int):
    from datetime import timedelta

    return timedelta(minutes=n)


def run_pipeline(
    settings: Settings,
    sensor_specs: SensorSpecs,
    room_profiles: RoomProfilesConfig,
    from_ts: datetime,
    to_ts: datetime,
    window_minutes: int | None = None,
    mode: Literal["publication", "exploratory"] = "publication",
) -> dict:
    """Runs the full pipeline over every recompute instant in
    ``(from_ts, to_ts]`` and writes a minimal reproducibility-metadata
    run_summary.json. Opens exactly one snapshot of air_monitor.duckdb for
    the whole range (see :mod:`iaq_hfis.db`).

    Every persisted row is tagged with a freshly generated
    ``pipeline_run_id``: a second call over an overlapping or identical
    range writes rows under its own distinct pipeline_run_id and never
    overwrites or reads the first call's rows (see :mod:`iaq_hfis.db`'s
    run-isolated schema).

    ``mode="publication"`` (default, strict): a missing DBN temperature
    profile for any computed_ts aborts the entire run --
    :class:`iaq_hfis.config.TemperatureProfileNotDefinedError` propagates
    out uncaught, since a full A/V/M/I manuscript result must never be
    produced with a substituted or omitted microclimate component.
    ``mode="exploratory"``: the microclimate component is structurally
    omitted (never fabricated) wherever no profile is defined; the run is
    tagged ``mode="exploratory"`` in ``pipeline_runs`` and must never be
    promoted into ``research_results/final`` (enforced in
    :mod:`iaq_hfis.final_snapshot`).
    """
    window_minutes = window_minutes or settings.cadence.aggregation_window_minutes
    pipeline_run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)

    with AirMonitorSource(settings) as source:
        ctx = build_runtime_context(settings, sensor_specs, room_profiles, source.raw_schema_columns())

        computed_timestamps = timegrid.align_computed_timestamps(from_ts, to_ts, settings.cadence.recompute_interval_minutes)

        writer = DerivedResultsWriter(settings.paths.derived_db_path)
        status_counts = {"OK": 0, "PARTIAL": 0, "FAILED": 0}
        per_timestamp_seconds: list[float] = []
        try:
            for computed_ts in computed_timestamps:
                t0 = time.perf_counter()
                result = compute_index_at(ctx, source, computed_ts, window_minutes, writer, pipeline_run_id, mode=mode)
                per_timestamp_seconds.append(time.perf_counter() - t0)
                status_counts[result["completeness_status"]] += 1

            finished_at = datetime.now(timezone.utc)
            run_status = "success" if status_counts["FAILED"] < len(computed_timestamps) else "failed"
            environment = collect_environment_metadata(REPO_ROOT)
            writer.connection.execute(
                """INSERT OR REPLACE INTO pipeline_runs
                   (pipeline_run_id, started_at, finished_at, status, computed_ts_min, computed_ts_max,
                    window_minutes, n_timestamps_processed, n_snapshot_retries, config_hash, engine_version, source_git_commit, mode)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [pipeline_run_id, started_at, finished_at, run_status,
                 computed_timestamps[0] if computed_timestamps else None,
                 computed_timestamps[-1] if computed_timestamps else None,
                 window_minutes, len(computed_timestamps), source.snapshot_retry_count, ctx.config_hash,
                 settings.engine_version, environment.get("git_commit"), mode],
            )
            derived_row_counts = {
                table: writer.connection.execute(f"SELECT COUNT(*) FROM {table} WHERE pipeline_run_id = ?", [pipeline_run_id]).fetchone()[0]
                for table in ("observation_quality", "window_aggregates", "component_scores", "iaq_index_results")
            }
            # Dominant-component frequency: how often each component (A/V/M) was the
            # deterministic winner of fuzzy_engine.determine_dominance's priority
            # hierarchy, across every OK/PARTIAL computed_ts this run (FAILED rows
            # have a null dominant_component and are excluded automatically).
            dominant_component_frequency = dict(
                writer.connection.execute(
                    "SELECT dominant_component, COUNT(*) FROM iaq_index_results "
                    "WHERE pipeline_run_id = ? AND dominant_component IS NOT NULL GROUP BY 1 ORDER BY 1",
                    [pipeline_run_id],
                ).fetchall()
            )
        finally:
            writer.close()

        source_raw_row_count = source.connection.execute("SELECT COUNT(*) FROM raw_observations WHERE ts > ? AND ts <= ?", [from_ts, to_ts]).fetchone()[0]

    per_ts_ms = sorted(s * 1000.0 for s in per_timestamp_seconds)
    performance = {
        "platform": environment["platform"],
        "processor": environment["processor"],
        "cpu_count": environment["cpu_count"],
        "total_runtime_seconds": (finished_at - started_at).total_seconds(),
        "peak_memory_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,  # ru_maxrss is KB on Linux
        "per_timestamp_latency_ms": {
            "mean": (sum(per_ts_ms) / len(per_ts_ms)) if per_ts_ms else None,
            "median": float(np.median(per_ts_ms)) if per_ts_ms else None,
            "p95": float(np.percentile(per_ts_ms, 95)) if per_ts_ms else None,
            "max": max(per_ts_ms) if per_ts_ms else None,
        },
        "source_raw_row_count": source_raw_row_count,
        "derived_row_counts": derived_row_counts,
    }

    summary = {
        "pipeline_run_id": pipeline_run_id,
        "mode": mode,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": run_status,
        "config_hash": ctx.config_hash,
        "engine_version": settings.engine_version,
        "window_minutes": window_minutes,
        "computed_ts_range": [from_ts.isoformat(), to_ts.isoformat()],
        "n_timestamps_processed": len(computed_timestamps),
        "n_snapshot_retries": source.snapshot_retry_count,
        "completeness_summary": status_counts,
        "dominant_component_frequency": dominant_component_frequency,
        "provisional_parameters_used": (
            sorted(engaged_provisional_paths(collect_parameter_provenance(settings, sensor_specs, room_profiles), sorted(ctx.provisional_profiles_used)))
            + ctx.provisional_parameters_used
        ),
        "environment": environment,
        "performance": performance,
        "selected_evaluation_run_id": None,
        "errors": [],
        "warnings": [],
    }

    summary_dir = Path(settings.paths.run_summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"run_summary_{pipeline_run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary
