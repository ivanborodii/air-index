"""Orchestrates Phase 2A's quantitative evaluation protocol: baselines,
agreement, masking, ground-truth scoring, stability, sensitivity, and
status/fault proportions.

Deliberately a separate entry point from :func:`iaq_hfis.pipeline.run_pipeline`
rather than a parameter grafted onto it — keeps the already-tested Phase 1
core computation untouched, and lets evaluation be re-run independently
against an already-populated derived DB (``iaq_index_results`` /
``component_scores`` / ``window_aggregates`` must already exist for the
requested range — i.e. ``iaq_hfis run`` first).

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

from iaq_hfis import profiles, timegrid
from iaq_hfis.baselines import crisp_max, weighted_mean
from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings
from iaq_hfis.db import AirMonitorSource, DerivedResultsWriter
from iaq_hfis.evaluation.agreement import pairwise_agreement
from iaq_hfis.evaluation.faults import compute_reason_code_frequency, compute_status_proportions
from iaq_hfis.evaluation.ground_truth import generate_boundary_vectors, score_against_ground_truth
from iaq_hfis.evaluation.masking import evaluate_masking
from iaq_hfis.evaluation.sensitivity import sweep_coverage_thresholds, sweep_window_minutes
from iaq_hfis.evaluation.stability import run_stability_analysis
from iaq_hfis.pipeline import build_runtime_context, infer_from_values

logger = logging.getLogger(__name__)


def _fetch_computed_timestamps(con, from_ts: datetime, to_ts: datetime, window_minutes: int) -> list[datetime]:
    rows = con.execute(
        "SELECT DISTINCT computed_ts FROM iaq_index_results WHERE window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts",
        [window_minutes, from_ts, to_ts],
    ).fetchall()
    return [r[0] for r in rows]


def _fetch_component_crisp_scores(con, computed_ts: datetime, window_minutes: int) -> dict[str, float]:
    rows = con.execute(
        "SELECT component, crisp_score FROM component_scores WHERE computed_ts = ? AND window_minutes = ? AND available = TRUE",
        [computed_ts, window_minutes],
    ).fetchall()
    return {component: score for component, score in rows if score is not None}


def _fetch_proposed_class(con, computed_ts: datetime, window_minutes: int) -> str | None:
    row = con.execute("SELECT index_class FROM iaq_index_results WHERE computed_ts = ? AND window_minutes = ?", [computed_ts, window_minutes]).fetchone()
    return row[0] if row else None


def _fetch_weighted_means(con, computed_ts: datetime, window_minutes: int) -> dict[str, float]:
    rows = con.execute(
        "SELECT channel, weighted_mean FROM window_aggregates WHERE computed_ts = ? AND window_minutes = ? AND weighted_mean IS NOT NULL",
        [computed_ts, window_minutes],
    ).fetchall()
    return {channel: value for channel, value in rows}


def run_evaluation(
    settings: Settings,
    sensor_specs: SensorSpecs,
    room_profiles: RoomProfilesConfig,
    from_ts: datetime,
    to_ts: datetime,
    window_minutes: int | None = None,
    run_id: str | None = None,
) -> dict:
    """Runs the full Phase 2A evaluation suite over every computed_ts already
    persisted (by a prior ``iaq_hfis run``) in ``(from_ts, to_ts]``.

    If ``run_id`` names an existing ``run_summary_{run_id}.json`` (from the
    core run), evaluation results are merged into it under an
    ``"evaluation"`` key, preserving the manuscript's "every numeric claim
    traceable to run_summary.json" requirement. Otherwise a fresh
    standalone summary is written.
    """
    window_minutes = window_minutes or settings.cadence.aggregation_window_minutes
    eval_run_id = run_id or uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)

    with AirMonitorSource(settings) as source:
        ctx = build_runtime_context(settings, sensor_specs, room_profiles, source.raw_schema_columns())
        writer = DerivedResultsWriter(settings.paths.derived_db_path)
        con = writer.connection
        now = datetime.now(timezone.utc)

        try:
            computed_timestamps = _fetch_computed_timestamps(con, from_ts, to_ts, window_minutes)
            if not computed_timestamps:
                logger.warning("no persisted iaq_index_results found in (%s, %s] at window_minutes=%s -- run 'iaq_hfis run' first", from_ts, to_ts, window_minutes)

            # --- Baselines, per computed_ts, from already-persisted component crisp scores ---
            proposed_classes: list[str | None] = []
            crisp_max_classes: list[str | None] = []
            weighted_mean_classes: list[str | None] = []
            crisp_scores_per_ts: list[dict[str, float]] = []
            crisp_max_results = []
            weighted_mean_results = []

            for computed_ts in computed_timestamps:
                scores = _fetch_component_crisp_scores(con, computed_ts, window_minutes)
                crisp_scores_per_ts.append(scores)
                cm = crisp_max(scores)
                wm = weighted_mean(scores)
                crisp_max_results.append(cm)
                weighted_mean_results.append(wm)
                proposed_classes.append(_fetch_proposed_class(con, computed_ts, window_minutes))
                crisp_max_classes.append(cm.index_class)
                weighted_mean_classes.append(wm.index_class)

                con.execute(
                    "INSERT OR REPLACE INTO baseline_results (computed_ts, window_minutes, method, index_value, index_class, n_components) VALUES (?,?,?,?,?,?)",
                    [computed_ts, window_minutes, "CRISP-MAX", cm.index_value, cm.index_class, cm.n_components],
                )
                con.execute(
                    "INSERT OR REPLACE INTO baseline_results (computed_ts, window_minutes, method, index_value, index_class, n_components) VALUES (?,?,?,?,?,?)",
                    [computed_ts, window_minutes, "WEIGHTED-MEAN", wm.index_value, wm.index_class, wm.n_components],
                )

            # --- Agreement (unlabeled real data): PROPOSED-HFIS vs each baseline ---
            agreement_results = []
            if computed_timestamps:
                agreement_results = pairwise_agreement(
                    {"PROPOSED-HFIS": proposed_classes, "CRISP-MAX": crisp_max_classes, "WEIGHTED-MEAN": weighted_mean_classes}
                )
                for a in agreement_results:
                    con.execute(
                        "INSERT OR REPLACE INTO evaluation_agreement (run_id, method_a, method_b, n, n_excluded, percent_agreement, cohens_kappa, computed_at) VALUES (?,?,?,?,?,?,?,?)",
                        [eval_run_id, a.method_a, a.method_b, a.n, a.n_excluded, a.percent_agreement, a.cohens_kappa, now],
                    )

            # --- Masking ---
            masking_results = []
            for method_name, results in (("CRISP-MAX", crisp_max_results), ("WEIGHTED-MEAN", weighted_mean_results)):
                if not results:
                    continue
                m = evaluate_masking(crisp_scores_per_ts, results, settings.evaluation.masking_severity_threshold)
                masking_results.append(m)
                con.execute(
                    "INSERT OR REPLACE INTO evaluation_masking (run_id, method, severity_threshold, n_critical_events, n_masked, masking_rate, computed_at) VALUES (?,?,?,?,?,?,?)",
                    [eval_run_id, m.method, m.severity_threshold, m.n_critical_events, m.n_masked, m.masking_rate, now],
                )

            # --- Ground truth (synthetic boundary vectors, labeled, never real unlabeled data) ---
            ground_truth_results = {}
            representative_profile = profiles.select_room_season(room_profiles, to_ts, settings.profile_selection)
            vectors = generate_boundary_vectors(settings.control_regions, representative_profile)
            gt_proposed, gt_crisp_max, gt_weighted_mean = [], [], []
            for v in vectors:
                component_results, index_result = infer_from_values(ctx, v.values, {"A", "V", "M"}, representative_profile)
                gt_proposed.append(index_result.index_class if index_result else None)
                scores = {c: r.crisp_score for c, r in component_results.items()}
                gt_crisp_max.append(crisp_max(scores).index_class)
                gt_weighted_mean.append(weighted_mean(scores).index_class)

            for method_name, predictions in (("PROPOSED-HFIS", gt_proposed), ("CRISP-MAX", gt_crisp_max), ("WEIGHTED-MEAN", gt_weighted_mean)):
                score = score_against_ground_truth(vectors, predictions)
                ground_truth_results[method_name] = score
                con.execute(
                    "INSERT OR REPLACE INTO evaluation_ground_truth (run_id, method, n, n_excluded, macro_f1, cohens_kappa, computed_at) VALUES (?,?,?,?,?,?,?)",
                    [eval_run_id, method_name, score["n"], score["n_excluded"], score["macro_f1"], score["cohens_kappa"], now],
                )

            # --- Stability + sensitivity, sampled at the latest computed_ts (bounded runtime) ---
            stability_result = None
            sensitivity_results = []
            if computed_timestamps:
                sample_ts = computed_timestamps[-1]
                weighted_means = _fetch_weighted_means(con, sample_ts, window_minutes)
                availability_row = con.execute(
                    "SELECT component FROM component_scores WHERE computed_ts = ? AND window_minutes = ? AND available = TRUE", [sample_ts, window_minutes]
                ).fetchall()
                available_components = {r[0] for r in availability_row}

                if weighted_means and available_components:
                    stability_result = run_stability_analysis(
                        ctx, weighted_means, available_components, representative_profile, settings.evaluation.stability_seed, settings.evaluation.stability_n_trials
                    )
                    con.execute(
                        "INSERT OR REPLACE INTO evaluation_stability (run_id, computed_ts, seed, n_trials, baseline_class, n_class_changes, class_change_rate, trial_classes, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        [eval_run_id, sample_ts, stability_result.seed, stability_result.n_trials, stability_result.baseline_class, stability_result.n_class_changes, stability_result.class_change_rate, stability_result.trial_classes, now],
                    )

                sensitivity_results = sweep_window_minutes(ctx, source, sample_ts, settings.evaluation.sensitivity_window_minutes)
                sensitivity_results += sweep_coverage_thresholds(
                    settings, sensor_specs, room_profiles, source, sample_ts, window_minutes, settings.evaluation.sensitivity_coverage_thresholds
                )
                for s in sensitivity_results:
                    con.execute(
                        "INSERT OR REPLACE INTO evaluation_sensitivity (run_id, computed_ts, varied_parameter, value, completeness_status, index_value, index_class, computed_at) VALUES (?,?,?,?,?,?,?,?)",
                        [eval_run_id, sample_ts, s.varied_parameter, s.value, s.completeness_status, s.index_value, s.index_class, now],
                    )

            # --- Status proportions + fault reason-code frequency over the whole range ---
            status_proportions = compute_status_proportions(con, window_minutes, from_ts, to_ts)
            reason_frequency = compute_reason_code_frequency(con, from_ts, to_ts)

        finally:
            writer.close()

    finished_at = datetime.now(timezone.utc)

    evaluation_summary = {
        "n_computed_ts_evaluated": len(computed_timestamps),
        "agreement": [
            {"method_a": a.method_a, "method_b": a.method_b, "n": a.n, "n_excluded": a.n_excluded, "percent_agreement": a.percent_agreement, "cohens_kappa": a.cohens_kappa}
            for a in agreement_results
        ],
        "masking": [
            {"method": m.method, "severity_threshold": m.severity_threshold, "n_critical_events": m.n_critical_events, "n_masked": m.n_masked, "masking_rate": m.masking_rate}
            for m in masking_results
        ],
        "ground_truth": ground_truth_results,
        "stability": (
            {
                "computed_ts": computed_timestamps[-1].isoformat(),
                "seed": stability_result.seed,
                "n_trials": stability_result.n_trials,
                "baseline_class": stability_result.baseline_class,
                "class_change_rate": stability_result.class_change_rate,
            }
            if stability_result is not None
            else None
        ),
        "sensitivity": [
            {"varied_parameter": s.varied_parameter, "value": s.value, "completeness_status": s.completeness_status, "index_value": s.index_value, "index_class": s.index_class}
            for s in sensitivity_results
        ],
        "status_proportions": {"n_total": status_proportions.n_total, "OK": status_proportions.ok, "PARTIAL": status_proportions.partial, "FAILED": status_proportions.failed},
        "reason_code_frequency": {"n_total_quality_rows": reason_frequency.n_total_quality_rows, "counts": reason_frequency.counts},
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }

    summary_dir = Path(settings.paths.run_summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"run_summary_{eval_run_id}.json"

    if run_id is not None and summary_path.is_file():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        existing["evaluation"] = evaluation_summary
        summary_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return existing

    standalone = {"run_id": eval_run_id, "evaluation": evaluation_summary}
    summary_path.write_text(json.dumps(standalone, indent=2), encoding="utf-8")
    return standalone
