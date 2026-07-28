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
import uuid
from datetime import datetime, timezone
from pathlib import Path

from iaq_hfis import profiles
from iaq_hfis.baselines import crisp_max, weighted_mean
from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings, config_hash
from iaq_hfis.db import AirMonitorSource, DerivedResultsWriter
from iaq_hfis.evaluation.agreement import pairwise_agreement
from iaq_hfis.evaluation.faults import compute_reason_code_frequency, compute_status_proportions
from iaq_hfis.evaluation.masking import evaluate_masking
from iaq_hfis.evaluation.multi_point_sensitivity import select_sensitivity_samples, summarize_sensitivity
from iaq_hfis.evaluation.multi_point_stability import select_stability_samples, run_multi_point_stability, summarize_stability
from iaq_hfis.evaluation.reference_cases import generate_reference_cases, score_against_reference_cases
from iaq_hfis.evaluation.sensitivity import sweep_coverage_thresholds, sweep_window_minutes
from iaq_hfis.pipeline import build_runtime_context, infer_from_values

logger = logging.getLogger(__name__)


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
            stability_summaries = {}
            if computed_timestamps:
                stability_samples = select_stability_samples(
                    con, pipeline_run_id, window_minutes, from_ts, to_ts, settings.control_regions, representative_profile,
                    settings.evaluation.stability_seed, settings.evaluation.stability_max_boundary_samples, settings.evaluation.stability_max_random_samples,
                )
                if stability_samples:
                    stability_point_results = run_multi_point_stability(
                        ctx, representative_profile, stability_samples, settings.evaluation.stability_seed, settings.evaluation.stability_n_trials
                    )
                    stability_summaries = summarize_stability(stability_point_results)

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
                "by_method": {
                    method: {
                        "n_trials_total": s.n_trials_total,
                        "n_class_changes": s.n_class_changes,
                        "class_change_rate": s.class_change_rate,
                        "class_change_rate_ci95": list(s.class_change_rate_ci95) if s.class_change_rate_ci95 is not None else None,
                        "mean_abs_index_change": s.mean_abs_index_change,
                        "median_abs_index_change": s.median_abs_index_change,
                        "p95_abs_index_change": s.p95_abs_index_change,
                        "max_abs_index_change": s.max_abs_index_change,
                    }
                    for method, s in stability_summaries.items()
                },
            }
            if stability_point_results
            else None
        ),
        "sensitivity": {
            "n_sample_points": len(sensitivity_points),
            "strata": sorted({sp.stratum for sp, _ in sensitivity_points}),
            "by_parameter_value": summarize_sensitivity(sensitivity_points),
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
