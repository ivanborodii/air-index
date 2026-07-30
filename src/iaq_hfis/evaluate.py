"""Orchestrates the quantitative evaluation protocol: baselines, agreement,
masking, reference-case consistency, stability, sensitivity, and
status/fault proportions.

Deliberately a separate entry point from :func:`iaq_hfis.pipeline.run_pipeline`
rather than a parameter grafted onto it -- keeps the already-tested core
computation untouched, and lets evaluation be re-run independently against
an already-populated derived DB (``iaq_index_results`` / ``component_scores``
/ ``window_aggregates`` for the given ``pipeline_run_id`` must already exist
-- i.e. ``iaq_hfis run`` first).

Run isolation: ``pipeline_run_id`` identifies which pipeline run's already-
persisted rows to evaluate (every read is filtered by it). Every call to
:func:`run_evaluation` creates a brand-new ``evaluation_run_id`` and writes
an ``evaluation_runs`` row for it -- two evaluation executions over the same
pipeline_run_id never mix rows, even if run back to back. The run summary
records exactly one *selected* evaluation_run_id (the most recent
successful one) under ``selected_evaluation_run_id``; older evaluation runs
remain in the database for audit but are not referenced by the summary.

Uses its own fresh snapshot of ``air_monitor.duckdb`` (only for schema
validation and, for the sensitivity window sweep, re-aggregating raw data)
rather than reusing a prior run's now-closed connection.
"""

from __future__ import annotations

import json
import logging
import resource
import uuid
from datetime import datetime, timezone
from pathlib import Path

from iaq_hfis import profiles
from iaq_hfis.baselines import crisp_max, weighted_mean
from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings, config_hash
from iaq_hfis.db import AirMonitorSource, DerivedResultsWriter
from iaq_hfis.evaluation.agreement import pairwise_agreement
from iaq_hfis.evaluation.continuity import run_continuity_experiment, summarize_continuity_smoothness
from iaq_hfis.evaluation.fault_injection import (
    HAMPEL_MULTIPLIER_GRID,
    HAMPEL_WINDOW_GRID,
    build_confusion_matrix,
    confirmation_recovery_rate,
    false_rejection_rate_for_genuine_events,
    run_benchmark,
    run_hampel_calibration,
    score_events,
    score_predictions,
)
from iaq_hfis.evaluation.faults import compute_reason_code_frequency, compute_status_proportions
from iaq_hfis.evaluation.masking import evaluate_masking
from iaq_hfis.evaluation.multi_point_sensitivity import compute_sensitivity_summary, select_sensitivity_samples
from iaq_hfis.evaluation.multi_point_stability import (
    select_stability_samples,
    run_multi_point_stability,
    compute_stability_summary_overall,
    compute_stability_summary_by_variable,
    compute_stability_summary_by_original_class,
)
from iaq_hfis.evaluation.reference_cases import generate_reference_cases, score_against_reference_cases
from iaq_hfis.evaluation.sensitivity import sweep_coverage_thresholds, sweep_window_minutes
from iaq_hfis.pipeline import build_runtime_context, infer_from_values

logger = logging.getLogger(__name__)


def _jsonify_stability_row(row: dict) -> dict:
    """Confidence-interval tuples -> JSON-serializable lists; otherwise a
    verbatim copy of the aggregation row (never recomputed)."""
    out = dict(row)
    for key in ("class_change_rate_ci95", "prob_moved_better_ci95", "prob_moved_worse_ci95"):
        if out.get(key) is not None:
            out[key] = list(out[key])
    return out


def _fetch_computed_timestamps(con, pipeline_run_id: str, from_ts: datetime, to_ts: datetime, window_minutes: int) -> list[datetime]:
    rows = con.execute(
        "SELECT DISTINCT computed_ts FROM iaq_index_results "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    return [r[0] for r in rows]


def _fetch_component_crisp_scores(con, pipeline_run_id: str, computed_ts: datetime, window_minutes: int) -> dict[str, float]:
    rows = con.execute(
        "SELECT component, crisp_score FROM component_scores "
        "WHERE pipeline_run_id = ? AND computed_ts = ? AND window_minutes = ? AND available = TRUE",
        [pipeline_run_id, computed_ts, window_minutes],
    ).fetchall()
    return {component: score for component, score in rows if score is not None}


def _fetch_proposed_class(con, pipeline_run_id: str, computed_ts: datetime, window_minutes: int) -> str | None:
    row = con.execute(
        "SELECT index_class FROM iaq_index_results WHERE pipeline_run_id = ? AND computed_ts = ? AND window_minutes = ?",
        [pipeline_run_id, computed_ts, window_minutes],
    ).fetchone()
    return row[0] if row else None


def _fetch_weighted_means(con, pipeline_run_id: str, computed_ts: datetime, window_minutes: int) -> dict[str, float]:
    rows = con.execute(
        "SELECT channel, weighted_mean FROM window_aggregates "
        "WHERE pipeline_run_id = ? AND computed_ts = ? AND window_minutes = ? AND weighted_mean IS NOT NULL",
        [pipeline_run_id, computed_ts, window_minutes],
    ).fetchall()
    return {channel: value for channel, value in rows}


def run_evaluation(
    settings: Settings,
    sensor_specs: SensorSpecs,
    room_profiles: RoomProfilesConfig,
    pipeline_run_id: str,
    from_ts: datetime,
    to_ts: datetime,
    window_minutes: int | None = None,
) -> dict:
    """Runs the full evaluation suite over every computed_ts already
    persisted (by a prior ``iaq_hfis run``) for ``pipeline_run_id`` in
    ``(from_ts, to_ts]``. Always creates a new ``evaluation_run_id``;
    results are merged into ``run_summary_{pipeline_run_id}.json`` under an
    ``"evaluation"`` key, and that summary's ``selected_evaluation_run_id``
    is updated to point at this evaluation run.
    """
    window_minutes = window_minutes or settings.cadence.aggregation_window_minutes
    evaluation_run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []
    warnings: list[str] = []

    with AirMonitorSource(settings) as source:
        ctx = build_runtime_context(settings, sensor_specs, room_profiles, source.raw_schema_columns())
        writer = DerivedResultsWriter(settings.paths.derived_db_path)
        con = writer.connection
        now = datetime.now(timezone.utc)

        try:
            computed_timestamps = _fetch_computed_timestamps(con, pipeline_run_id, from_ts, to_ts, window_minutes)
            if not computed_timestamps:
                msg = f"no persisted iaq_index_results found for pipeline_run_id={pipeline_run_id} in ({from_ts}, {to_ts}] -- run 'iaq_hfis run' first"
                logger.warning(msg)
                warnings.append(msg)

            # --- Baselines, per computed_ts, from already-persisted component crisp scores ---
            proposed_classes: list[str | None] = []
            crisp_max_classes: list[str | None] = []
            weighted_mean_classes: list[str | None] = []
            crisp_scores_per_ts: list[dict[str, float]] = []
            crisp_max_results = []
            weighted_mean_results = []

            for computed_ts in computed_timestamps:
                scores = _fetch_component_crisp_scores(con, pipeline_run_id, computed_ts, window_minutes)
                crisp_scores_per_ts.append(scores)
                cm = crisp_max(scores)
                wm = weighted_mean(scores)
                crisp_max_results.append(cm)
                weighted_mean_results.append(wm)
                proposed_classes.append(_fetch_proposed_class(con, pipeline_run_id, computed_ts, window_minutes))
                crisp_max_classes.append(cm.index_class)
                weighted_mean_classes.append(wm.index_class)

                con.execute(
                    "INSERT OR REPLACE INTO baseline_results (pipeline_run_id, evaluation_run_id, computed_ts, window_minutes, method, index_value, index_class, n_components) VALUES (?,?,?,?,?,?,?,?)",
                    [pipeline_run_id, evaluation_run_id, computed_ts, window_minutes, "CRISP-MAX", cm.index_value, cm.index_class, cm.n_components],
                )
                con.execute(
                    "INSERT OR REPLACE INTO baseline_results (pipeline_run_id, evaluation_run_id, computed_ts, window_minutes, method, index_value, index_class, n_components) VALUES (?,?,?,?,?,?,?,?)",
                    [pipeline_run_id, evaluation_run_id, computed_ts, window_minutes, "WEIGHTED-MEAN", wm.index_value, wm.index_class, wm.n_components],
                )

            # --- Agreement (unlabeled real data): PROPOSED-HFIS vs each baseline ---
            agreement_results = []
            if computed_timestamps:
                agreement_results = pairwise_agreement(
                    {"PROPOSED-HFIS": proposed_classes, "CRISP-MAX": crisp_max_classes, "WEIGHTED-MEAN": weighted_mean_classes}
                )
                for a in agreement_results:
                    con.execute(
                        "INSERT OR REPLACE INTO evaluation_agreement (evaluation_run_id, pipeline_run_id, method_a, method_b, n, n_excluded, percent_agreement, cohens_kappa, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        [evaluation_run_id, pipeline_run_id, a.method_a, a.method_b, a.n, a.n_excluded, a.percent_agreement, a.cohens_kappa, now],
                    )

            # --- Masking ---
            masking_results = []
            for method_name, results in (("CRISP-MAX", crisp_max_results), ("WEIGHTED-MEAN", weighted_mean_results)):
                if not results:
                    continue
                m = evaluate_masking(crisp_scores_per_ts, results, settings.evaluation.masking_severity_threshold)
                masking_results.append(m)
                con.execute(
                    "INSERT OR REPLACE INTO evaluation_masking (evaluation_run_id, pipeline_run_id, method, severity_threshold, n_critical_events, n_masked, masking_rate, computed_at) VALUES (?,?,?,?,?,?,?,?)",
                    [evaluation_run_id, pipeline_run_id, m.method, m.severity_threshold, m.n_critical_events, m.n_masked, m.masking_rate, now],
                )

            # --- Reference cases (synthetic, pre-labeled boundary vectors -- consistency, not empirical accuracy) ---
            reference_case_results = {}
            representative_profile = profiles.select_room_season(room_profiles, to_ts, settings.profile_selection)
            cases = generate_reference_cases(settings.control_regions, representative_profile)
            rc_proposed, rc_crisp_max, rc_weighted_mean = [], [], []
            for case in cases:
                component_results, index_result = infer_from_values(ctx, case.values, {"A", "V", "M"}, representative_profile)
                rc_proposed.append(index_result.index_class if index_result else None)
                scores = {c: r.crisp_score for c, r in component_results.items()}
                rc_crisp_max.append(crisp_max(scores).index_class)
                rc_weighted_mean.append(weighted_mean(scores).index_class)

            for method_name, predictions in (("PROPOSED-HFIS", rc_proposed), ("CRISP-MAX", rc_crisp_max), ("WEIGHTED-MEAN", rc_weighted_mean)):
                score = score_against_reference_cases(cases, predictions)
                reference_case_results[method_name] = score
                con.execute(
                    "INSERT OR REPLACE INTO evaluation_reference_cases (evaluation_run_id, pipeline_run_id, method, n, n_excluded, macro_f1, cohens_kappa, computed_at) VALUES (?,?,?,?,?,?,?,?)",
                    [evaluation_run_id, pipeline_run_id, method_name, score["n"], score["n_excluded"], score["macro_f1"], score["cohens_kappa"], now],
                )

            # --- Multi-point stability: deterministic boundary-adjacent + random-comparison
            # sample across the whole evaluated range, all 3 methods, N perturbation trials each. ---
            stability_point_results = []
            stability_summary_overall: list[dict] = []
            stability_summary_by_variable: list[dict] = []
            stability_summary_by_original_class: list[dict] = []
            if computed_timestamps:
                stability_samples = select_stability_samples(
                    con, pipeline_run_id, window_minutes, from_ts, to_ts, settings.control_regions, representative_profile,
                    settings.evaluation.stability_seed, settings.evaluation.stability_max_boundary_samples, settings.evaluation.stability_max_random_samples,
                )
                if stability_samples:
                    stability_point_results = run_multi_point_stability(
                        ctx, representative_profile, stability_samples, settings.evaluation.stability_seed, settings.evaluation.stability_n_trials
                    )

                    for r in stability_point_results:
                        s = r.sample
                        con.execute(
                            """INSERT OR REPLACE INTO evaluation_stability_samples
                               (evaluation_run_id, pipeline_run_id, sample_id, computed_ts, selection_reason, boundary_channel,
                                baseline_class_hfis, baseline_index_hfis, baseline_class_crisp_max, baseline_index_crisp_max,
                                baseline_class_weighted_mean, baseline_index_weighted_mean)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            [evaluation_run_id, pipeline_run_id, s.sample_id, s.computed_ts, s.selection_reason, s.boundary_channel,
                             r.baseline["PROPOSED-HFIS"].index_class, r.baseline["PROPOSED-HFIS"].index_value,
                             r.baseline["CRISP-MAX"].index_class, r.baseline["CRISP-MAX"].index_value,
                             r.baseline["WEIGHTED-MEAN"].index_class, r.baseline["WEIGHTED-MEAN"].index_value],
                        )
                        for method, trials in r.trials.items():
                            baseline_class = r.baseline[method].index_class
                            for trial_index, trial in enumerate(trials):
                                changed = trial.index_class != baseline_class
                                abs_change = (
                                    abs(trial.index_value - r.baseline[method].index_value)
                                    if trial.index_value is not None and r.baseline[method].index_value is not None
                                    else None
                                )
                                con.execute(
                                    """INSERT OR REPLACE INTO evaluation_stability_trials
                                       (evaluation_run_id, pipeline_run_id, sample_id, method, trial_index, trial_class, trial_index_value, changed_from_baseline, abs_index_change)
                                       VALUES (?,?,?,?,?,?,?,?,?)""",
                                    [evaluation_run_id, pipeline_run_id, s.sample_id, method, trial_index, trial.index_class, trial.index_value, changed, abs_change],
                                )

                    # Computed from the just-persisted trial/sample rows (never from the in-memory
                    # stability_point_results objects above) -- the single deterministic aggregation
                    # function also used by reporting/exports.py's CSV exports, so JSON and CSV can
                    # never numerically disagree.
                    stability_summary_overall = compute_stability_summary_overall(con, evaluation_run_id)
                    stability_summary_by_variable = compute_stability_summary_by_variable(con, evaluation_run_id)
                    stability_summary_by_original_class = compute_stability_summary_by_original_class(con, evaluation_run_id)

            # --- Multi-point sensitivity: window-length and coverage-threshold sweeps at a
            # deterministic, stratified sample of computed_ts across the whole evaluated range. ---
            sensitivity_points = []  # list[(SensitivitySamplePoint, list[SensitivityResult])]
            if computed_timestamps:
                sensitivity_samples = select_sensitivity_samples(
                    con, pipeline_run_id, window_minutes, from_ts, to_ts, settings.control_regions, representative_profile,
                    settings.evaluation.stability_seed, settings.evaluation.sensitivity_max_samples_per_stratum,
                )
                for sp in sensitivity_samples:
                    point_results = sweep_window_minutes(ctx, source, sp.computed_ts, settings.evaluation.sensitivity_window_minutes)
                    point_results += sweep_coverage_thresholds(
                        settings, sensor_specs, room_profiles, source, sp.computed_ts, window_minutes, settings.evaluation.sensitivity_coverage_thresholds
                    )
                    sensitivity_points.append((sp, point_results))
                    for s in point_results:
                        con.execute(
                            """INSERT OR REPLACE INTO evaluation_sensitivity
                               (evaluation_run_id, pipeline_run_id, sample_id, computed_ts, stratum, reference_completeness_status,
                                reference_index_class, reference_index_value, varied_parameter, value, completeness_status, index_value, index_class, computed_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            [evaluation_run_id, pipeline_run_id, sp.sample_id, sp.computed_ts, sp.stratum, sp.reference_completeness_status,
                             sp.reference_index_class, sp.reference_index_value, s.varied_parameter, s.value, s.completeness_status, s.index_value, s.index_class, now],
                        )

            # Computed from the just-persisted rows (never from the in-memory sensitivity_points
            # objects above) -- the single deterministic aggregation function also used by
            # reporting/exports.py's CSV export, so JSON and CSV can never numerically disagree.
            sensitivity_summary_rows = compute_sensitivity_summary(con, evaluation_run_id) if sensitivity_points else []

            # --- Boundary continuity experiment: PROPOSED-HFIS vs CRISP-MAX vs WEIGHTED-MEAN,
            # dense deterministic grids around every control-region boundary, each swept under
            # favorable/acceptable/degraded "other components" contexts (see
            # iaq_hfis.evaluation.continuity module docstring and docs/hfis_vs_crispmax_audit.md
            # for why a single favorable-only context cannot distinguish HFIS from CRISP-MAX). ---
            continuity_points, continuity_summaries = run_continuity_experiment(
                ctx, settings.control_regions, room_profiles, representative_profile, settings.evaluation.continuity_grid_points
            )
            for p in continuity_points:
                con.execute(
                    """INSERT OR REPLACE INTO evaluation_continuity_grid
                       (evaluation_run_id, pipeline_run_id, boundary_id, channel, context, boundary_value, grid_index, input_value, method, index_value, index_class)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    [evaluation_run_id, pipeline_run_id, p.boundary_id, p.channel, p.context, p.boundary_value, p.grid_index, p.input_value, p.method, p.index_value, p.index_class],
                )
            for s in continuity_summaries:
                con.execute(
                    """INSERT OR REPLACE INTO evaluation_continuity_summary
                       (evaluation_run_id, pipeline_run_id, boundary_id, channel, context, method, max_adjacent_jump, mean_adjacent_jump,
                        median_adjacent_jump, p95_adjacent_jump, total_variation, local_lipschitz_ratio, n_class_transitions,
                        class_transition_positions, index_range, monotonicity_violations, masked_by_favorable, area_between_curves_vs_crisp_max)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [evaluation_run_id, pipeline_run_id, s.boundary_id, s.channel, s.context, s.method, s.max_adjacent_jump, s.mean_adjacent_jump,
                     s.median_adjacent_jump, s.p95_adjacent_jump, s.total_variation, s.local_lipschitz_ratio, s.n_class_transitions,
                     ";".join(str(v) for v in s.class_transition_positions), s.index_range,
                     s.monotonicity_violations, s.masked_by_favorable, s.area_between_curves_vs_crisp_max],
                )

            # --- Fault-injection benchmark: deterministic, labeled synthetic scenarios,
            # fully separate from the unlabeled real-data reason-code frequency below.
            # Every scenario belongs to exactly one of two disjoint dataset splits
            # (calibration, validation -- different scenario_ids AND a different
            # deterministic scale/phase, see fault_injection.build_channel_scenarios),
            # so the headline, publication-facing numbers (validation split) never
            # reuse anything the calibration split (or Hampel calibration, below) saw. ---
            fault_events, fault_predictions = run_benchmark(
                settings.schema_mapping, sensor_specs, settings.hampel, settings.confirmation,
                settings.confirmation.pm_cross_channel_tolerance_pct, settings.cadence.sample_cadence_seconds,
            )
            for e in fault_events:
                con.execute(
                    """INSERT OR REPLACE INTO fault_injection_events
                       (evaluation_run_id, pipeline_run_id, scenario_id, dataset_split, channel, fault_type, injected_at_index, duration_samples, description)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    [evaluation_run_id, pipeline_run_id, e.scenario_id, e.dataset_split, e.channel, e.fault_type, e.injected_at_index, e.duration_samples, e.description],
                )
            for p in fault_predictions:
                con.execute(
                    """INSERT OR REPLACE INTO fault_detection_predictions
                       (evaluation_run_id, pipeline_run_id, scenario_id, dataset_split, channel, sample_index, true_fault_type, predicted_reason_codes, stage2_state, usable)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [evaluation_run_id, pipeline_run_id, p.scenario_id, p.dataset_split, p.channel, p.sample_index, p.true_fault_type, p.predicted_reason_codes, p.stage2_state, p.usable],
                )

            fault_metrics_by_split: dict[str, list] = {}
            fault_event_metrics_by_split: dict[str, list] = {}
            fault_false_rejection_rate_by_split: dict[str, float | None] = {}
            fault_confirmation_recovery_rate_by_split: dict[str, float | None] = {}
            for split in ("calibration", "validation"):
                split_metrics = score_predictions(fault_predictions, dataset_split=split)
                fault_metrics_by_split[split] = split_metrics
                for m in split_metrics:
                    con.execute(
                        """INSERT OR REPLACE INTO fault_detection_metrics
                           (evaluation_run_id, pipeline_run_id, dataset_split, reason_code, tp, fp, fn, tn,
                            precision, recall, f1, specificity, false_positive_rate, mean_detection_delay)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [evaluation_run_id, pipeline_run_id, split, m.reason_code, m.tp, m.fp, m.fn, m.tn,
                         m.precision, m.recall, m.f1, m.specificity, m.false_positive_rate, m.mean_detection_delay],
                    )

                split_event_metrics = score_events(fault_events, fault_predictions, split, temporal_tolerance_samples=1)
                fault_event_metrics_by_split[split] = split_event_metrics
                for m in split_event_metrics:
                    con.execute(
                        """INSERT OR REPLACE INTO fault_detection_event_metrics
                           (evaluation_run_id, pipeline_run_id, dataset_split, reason_code, temporal_tolerance_samples,
                            n_true_events, n_predicted_events, tp, fp, fn, precision, recall, f1, mean_detection_delay)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [evaluation_run_id, pipeline_run_id, split, m.reason_code, m.temporal_tolerance_samples,
                         m.n_true_events, m.n_predicted_events, m.tp, m.fp, m.fn, m.precision, m.recall, m.f1, m.mean_detection_delay],
                    )

                for cell in build_confusion_matrix(fault_predictions, split):
                    con.execute(
                        """INSERT OR REPLACE INTO fault_detection_confusion_matrix
                           (evaluation_run_id, pipeline_run_id, dataset_split, true_label, predicted_label, count)
                           VALUES (?,?,?,?,?,?)""",
                        [evaluation_run_id, pipeline_run_id, split, cell.true_label, cell.predicted_label, cell.count],
                    )

                fault_false_rejection_rate_by_split[split] = false_rejection_rate_for_genuine_events(fault_predictions, dataset_split=split)
                fault_confirmation_recovery_rate_by_split[split] = confirmation_recovery_rate(fault_predictions, dataset_split=split)

            # Legacy/headline aliases: the validation split is the publication-facing
            # result (never the split any provisional parameter was tuned against).
            fault_metrics = fault_metrics_by_split["validation"]
            fault_false_rejection_rate = fault_false_rejection_rate_by_split["validation"]
            fault_confirmation_recovery_rate = fault_confirmation_recovery_rate_by_split["validation"]

            hampel_calibration_rows = run_hampel_calibration(
                settings.schema_mapping, sensor_specs, settings.confirmation, settings.confirmation.pm_cross_channel_tolerance_pct,
                settings.cadence.sample_cadence_seconds, settings.hampel.window_size, settings.hampel.mad_multiplier,
            )
            for c in hampel_calibration_rows:
                con.execute(
                    """INSERT OR REPLACE INTO hampel_calibration
                       (evaluation_run_id, pipeline_run_id, dataset_split, window_size, mad_multiplier, fault_recall,
                        genuine_event_preservation_rate, objective_score, selected)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    [evaluation_run_id, pipeline_run_id, c.dataset_split, c.window_size, c.mad_multiplier, c.fault_recall,
                     c.genuine_event_preservation_rate, c.objective_score, c.selected],
                )

            # --- Status proportions + fault reason-code frequency over the whole range, this pipeline_run_id only ---
            status_proportions = compute_status_proportions(con, pipeline_run_id, window_minutes, from_ts, to_ts)
            reason_frequency = compute_reason_code_frequency(con, pipeline_run_id, from_ts, to_ts)

            finished_at = datetime.now(timezone.utc)
            eval_config_hash = config_hash(settings, sensor_specs, room_profiles)
            con.execute(
                """INSERT OR REPLACE INTO evaluation_runs
                   (evaluation_run_id, pipeline_run_id, started_at, finished_at, status, evaluated_range_from, evaluated_range_to,
                    window_minutes, config_hash, evaluation_config_hash, stability_seed, stability_n_trials, sample_strategy,
                    n_computed_ts_evaluated, errors, warnings)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [evaluation_run_id, pipeline_run_id, started_at, finished_at, "success" if not errors else "failed", from_ts, to_ts,
                 window_minutes, ctx.config_hash, eval_config_hash, settings.evaluation.stability_seed, settings.evaluation.stability_n_trials,
                 "stability=boundary_adjacent+random_comparison(deterministic seed); sensitivity=latest_computed_ts_single_point",
                 len(computed_timestamps), errors, warnings],
            )
        finally:
            writer.close()

    evaluation_summary = {
        "evaluation_run_id": evaluation_run_id,
        "pipeline_run_id": pipeline_run_id,
        "n_computed_ts_evaluated": len(computed_timestamps),
        "performance": {
            "total_runtime_seconds": (finished_at - started_at).total_seconds(),
            "peak_memory_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        },
        "agreement": [
            {"method_a": a.method_a, "method_b": a.method_b, "n": a.n, "n_excluded": a.n_excluded, "percent_agreement": a.percent_agreement, "cohens_kappa": a.cohens_kappa}
            for a in agreement_results
        ],
        "masking": [
            {"method": m.method, "severity_threshold": m.severity_threshold, "n_critical_events": m.n_critical_events, "n_masked": m.n_masked, "masking_rate": m.masking_rate}
            for m in masking_results
        ],
        "reference_cases": reference_case_results,
        "stability": (
            {
                "n_samples": len(stability_point_results),
                "n_trials_per_sample": settings.evaluation.stability_n_trials,
                "seed": settings.evaluation.stability_seed,
                "by_method": {row["method"]: _jsonify_stability_row(row) for row in stability_summary_overall},
                "by_variable": [_jsonify_stability_row(row) for row in stability_summary_by_variable],
                "by_original_class": [_jsonify_stability_row(row) for row in stability_summary_by_original_class],
            }
            if stability_point_results
            else None
        ),
        "sensitivity": {
            "n_sample_points": len(sensitivity_points),
            "strata": sorted({sp.stratum for sp, _ in sensitivity_points}),
            "by_parameter_value": sensitivity_summary_rows,
            "baseline_config": {"window_minutes": settings.cadence.aggregation_window_minutes, "recompute_interval_minutes": settings.cadence.recompute_interval_minutes, "coverage_min_ratio": settings.coverage.min_ratio},
        },
        "continuity": {
            "n_boundaries": len({s.boundary_id for s in continuity_summaries}),
            "n_contexts": len({s.context for s in continuity_summaries}),
            "contexts": sorted({s.context for s in continuity_summaries}),
            "grid_points_per_boundary": settings.evaluation.continuity_grid_points,
            "by_boundary_method": [
                {
                    "boundary_id": s.boundary_id, "channel": s.channel, "context": s.context, "method": s.method,
                    "max_adjacent_jump": s.max_adjacent_jump, "mean_adjacent_jump": s.mean_adjacent_jump,
                    "median_adjacent_jump": s.median_adjacent_jump, "p95_adjacent_jump": s.p95_adjacent_jump,
                    "total_variation": s.total_variation, "local_lipschitz_ratio": s.local_lipschitz_ratio,
                    "n_class_transitions": s.n_class_transitions,
                    "index_range": s.index_range, "monotonicity_violations": s.monotonicity_violations,
                    "masked_by_favorable": s.masked_by_favorable,
                    "area_between_curves_vs_crisp_max": s.area_between_curves_vs_crisp_max,
                }
                for s in continuity_summaries
            ],
            "smoothness_comparison": summarize_continuity_smoothness(continuity_summaries),
        },
        "fault_injection": {
            "n_scenarios": len({e.scenario_id for e in fault_events}),
            "channels_covered": sorted({e.channel for e in fault_events}),
            "headline_dataset_split": "validation",
            "row_level_metrics_by_split": {
                split: [
                    {"reason_code": m.reason_code, "tp": m.tp, "fp": m.fp, "fn": m.fn, "tn": m.tn,
                     "precision": m.precision, "recall": m.recall, "f1": m.f1, "specificity": m.specificity,
                     "false_positive_rate": m.false_positive_rate, "mean_detection_delay": m.mean_detection_delay}
                    for m in metrics
                ]
                for split, metrics in fault_metrics_by_split.items()
            },
            "event_level_metrics_by_split": {
                split: [
                    {"reason_code": m.reason_code, "temporal_tolerance_samples": m.temporal_tolerance_samples,
                     "n_true_events": m.n_true_events, "n_predicted_events": m.n_predicted_events,
                     "tp": m.tp, "fp": m.fp, "fn": m.fn, "precision": m.precision, "recall": m.recall, "f1": m.f1,
                     "mean_detection_delay": m.mean_detection_delay}
                    for m in metrics
                ]
                for split, metrics in fault_event_metrics_by_split.items()
            },
            # Legacy/headline alias kept for existing consumers (narrative, article_summary): the
            # validation split's row-level metrics -- never calibration, which is what any
            # explicitly-provisional parameter (e.g. Hampel window/multiplier) was tuned against.
            "metrics_by_reason_code": [
                {"reason_code": m.reason_code, "tp": m.tp, "fp": m.fp, "fn": m.fn, "precision": m.precision, "recall": m.recall,
                 "f1": m.f1, "false_positive_rate": m.false_positive_rate, "mean_detection_delay": m.mean_detection_delay}
                for m in fault_metrics
            ],
            "false_rejection_rate_for_genuine_events_by_split": fault_false_rejection_rate_by_split,
            "confirmation_recovery_rate_by_split": fault_confirmation_recovery_rate_by_split,
            "false_rejection_rate_for_genuine_events": fault_false_rejection_rate,
            "confirmation_recovery_rate": fault_confirmation_recovery_rate,
            "hampel_calibration": {
                "current_window_size": settings.hampel.window_size,
                "current_mad_multiplier": settings.hampel.mad_multiplier,
                "candidate_grid": {"window_size": HAMPEL_WINDOW_GRID, "mad_multiplier": HAMPEL_MULTIPLIER_GRID},
                "validation_objective_score_for_current_config": next(
                    (c.objective_score for c in hampel_calibration_rows if c.selected and c.dataset_split == "validation"), None
                ),
                "best_calibration_objective_score": max(
                    (c.objective_score for c in hampel_calibration_rows if c.dataset_split == "calibration" and c.objective_score is not None), default=None
                ),
                "note": "Current configured (window_size, mad_multiplier) is retained regardless of this grid's outcome -- "
                        "a change is only adopted after separate empirical verification against real live data, not from "
                        "synthetic-benchmark evidence alone. See hampel_calibration.csv for the full grid.",
            },
        },
        "status_proportions": {"n_total": status_proportions.n_total, "OK": status_proportions.ok, "PARTIAL": status_proportions.partial, "FAILED": status_proportions.failed},
        "reason_code_frequency": {"n_total_quality_rows": reason_frequency.n_total_quality_rows, "counts": reason_frequency.counts},
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "errors": errors,
        "warnings": warnings,
    }

    summary_dir = Path(settings.paths.run_summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"run_summary_{pipeline_run_id}.json"

    if summary_path.is_file():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        existing["evaluation"] = evaluation_summary
        existing["selected_evaluation_run_id"] = evaluation_run_id
        summary_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return existing

    standalone = {"pipeline_run_id": pipeline_run_id, "selected_evaluation_run_id": evaluation_run_id, "evaluation": evaluation_summary}
    summary_path.write_text(json.dumps(standalone, indent=2), encoding="utf-8")
    return standalone
