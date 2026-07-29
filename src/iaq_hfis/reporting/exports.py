"""Graph-ready CSV exports from the derived DuckDB, all scoped to one
exact ``pipeline_run_id`` (and, for evaluation-derived tables, one exact
``evaluation_run_id``) -- never mixing rows from a different run.

Every export function pulls from an already-persisted table (never
recomputes anything) and returns the path written, or ``None`` if there was
nothing to export for this run (e.g. no masking events, no stability
sample) -- callers must report that explicitly rather than writing an
empty/misleading file.

``COLUMNS`` is the single source of truth for column metadata, shared with
:mod:`iaq_hfis.reporting.data_dictionary` so the two can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str
    unit: str
    description: str


INDEX_TIMESERIES = "index_timeseries.csv"
COMPONENT_SCORES_TIMESERIES = "component_scores_timeseries.csv"
METHOD_COMPARISON = "method_comparison.csv"
DATA_QUALITY_SUMMARY = "data_quality_summary.csv"
REASON_CODE_FREQUENCY = "reason_code_frequency.csv"
STABILITY_SAMPLES = "stability_samples.csv"
STABILITY_TRIALS = "stability_trials.csv"
STABILITY_BY_POINT = "stability_by_point.csv"
STABILITY_SUMMARY = "stability_summary.csv"
SENSITIVITY_WINDOW_BY_POINT = "sensitivity_window_by_point.csv"
SENSITIVITY_WINDOW_SUMMARY = "sensitivity_window_summary.csv"
SENSITIVITY_COVERAGE_BY_POINT = "sensitivity_coverage_by_point.csv"
SENSITIVITY_COVERAGE_SUMMARY = "sensitivity_coverage_summary.csv"
MASKING_SUMMARY = "masking_summary.csv"
REFERENCE_CASE_SUMMARY = "reference_case_consistency.csv"
OUTDOOR_CONTEXT_TIMESERIES = "outdoor_context_timeseries.csv"
CONTINUITY_GRID = "continuity_grid.csv"
CONTINUITY_SUMMARY = "continuity_summary.csv"
FAULT_INJECTION_EVENTS = "fault_injection_events.csv"
FAULT_DETECTION_PREDICTIONS = "fault_detection_predictions.csv"
FAULT_DETECTION_METRICS = "fault_detection_metrics.csv"
HAMPEL_CALIBRATION = "hampel_calibration.csv"

COLUMNS: dict[str, list[ColumnSpec]] = {
    INDEX_TIMESERIES: [
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "Instant the index was computed for (end of the rolling window)."),
        ColumnSpec("window_minutes", "int", "minutes", "Aggregation window size used for this row."),
        ColumnSpec("completeness_status", "str", "-", "OK | PARTIAL | FAILED."),
        ColumnSpec("index_value", "float", "0-100", "Defuzzified PROPOSED-HFIS index value; null if FAILED."),
        ColumnSpec("index_class", "str", "-", "Favorable | Acceptable | Degraded | Critical; null if FAILED."),
        ColumnSpec("dominant_component", "str", "-", "Semicolon-joined dominant adverse component(s) (A/V/M), tie-tolerant; empty if FAILED."),
        ColumnSpec("rule_level_contributors", "str", "-", "Diagnostic only: semicolon-joined component(s) that bound the min() in fired rules -- NOT the dominant adverse component."),
        ColumnSpec("n_rules_fired", "int", "count", "Number of Mamdani rules with nonzero firing strength."),
    ],
    COMPONENT_SCORES_TIMESERIES: [
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "Instant the component was computed for."),
        ColumnSpec("window_minutes", "int", "minutes", "Aggregation window size used."),
        ColumnSpec("component", "str", "-", "A (aerosol) | V (ventilation) | M (microclimate)."),
        ColumnSpec("available", "bool", "-", "Whether this component had sufficient coverage to be computed."),
        ColumnSpec("crisp_score", "float", "0-100", "Centroid crisp score on the same scale as the final index; null if unavailable."),
        ColumnSpec("membership_favorable", "float", "0-1", "Degree of membership in Favorable."),
        ColumnSpec("membership_acceptable", "float", "0-1", "Degree of membership in Acceptable."),
        ColumnSpec("membership_degraded", "float", "0-1", "Degree of membership in Degraded."),
        ColumnSpec("membership_critical", "float", "0-1", "Degree of membership in Critical."),
        ColumnSpec("room", "str", "-", "Room profile used for the microclimate component (temperature range selection)."),
        ColumnSpec("season", "str", "-", "Season profile used (cold_period | warm_period)."),
    ],
    METHOD_COMPARISON: [
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "Instant compared across all three methods."),
        ColumnSpec("proposed_status", "str", "-", "PROPOSED-HFIS completeness status."),
        ColumnSpec("proposed_index_value", "float", "0-100", "PROPOSED-HFIS index value."),
        ColumnSpec("proposed_index_class", "str", "-", "PROPOSED-HFIS index class."),
        ColumnSpec("crisp_max_index_value", "float", "0-100", "CRISP-MAX baseline index value."),
        ColumnSpec("crisp_max_index_class", "str", "-", "CRISP-MAX baseline index class."),
        ColumnSpec("weighted_mean_index_value", "float", "0-100", "WEIGHTED-MEAN baseline index value."),
        ColumnSpec("weighted_mean_index_class", "str", "-", "WEIGHTED-MEAN baseline index class."),
    ],
    DATA_QUALITY_SUMMARY: [
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "Window this coverage figure applies to."),
        ColumnSpec("window_minutes", "int", "minutes", "Aggregation window size."),
        ColumnSpec("channel", "str", "-", "pm2_5 | pm10 | co2 | temperature | humidity."),
        ColumnSpec("n_expected", "int", "count", "Expected samples in the window at the configured cadence."),
        ColumnSpec("n_usable", "int", "count", "VALID + confirmed-SUSPECT samples."),
        ColumnSpec("coverage_ratio", "float", "0-1", "n_usable / n_expected."),
        ColumnSpec("coverage_ok", "bool", "-", "coverage_ratio >= configured min_ratio."),
        ColumnSpec("weighted_mean", "float", "channel units", "Time-weighted mean; null if coverage_ok is false."),
    ],
    REASON_CODE_FREQUENCY: [
        ColumnSpec("reason_code", "str", "-", "single_spike | stuck_value | data_loss | gradual_drift | out_of_range."),
        ColumnSpec("count", "int", "count", "Number of observation_quality rows carrying this reason code."),
    ],
    STABILITY_SAMPLES: [
        ColumnSpec("sample_id", "str", "-", "Unique identifier for this sampled computed_ts."),
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "The sampled instant."),
        ColumnSpec("selection_reason", "str", "-", "boundary_adjacent | random_comparison."),
        ColumnSpec("boundary_channel", "str", "-", "Channel whose boundary this sample is nearest to (boundary_adjacent samples only)."),
        ColumnSpec("baseline_class_hfis", "str", "-", "Unperturbed PROPOSED-HFIS class at this sample."),
        ColumnSpec("baseline_index_hfis", "float", "0-100", "Unperturbed PROPOSED-HFIS index value."),
        ColumnSpec("baseline_class_crisp_max", "str", "-", "Unperturbed CRISP-MAX class."),
        ColumnSpec("baseline_index_crisp_max", "float", "0-100", "Unperturbed CRISP-MAX index value."),
        ColumnSpec("baseline_class_weighted_mean", "str", "-", "Unperturbed WEIGHTED-MEAN class."),
        ColumnSpec("baseline_index_weighted_mean", "float", "0-100", "Unperturbed WEIGHTED-MEAN index value."),
    ],
    STABILITY_TRIALS: [
        ColumnSpec("sample_id", "str", "-", "Which sampled computed_ts this trial belongs to."),
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("trial_index", "int", "-", "0-based perturbation trial number within this sample/method."),
        ColumnSpec("trial_class", "str", "-", "Index class recomputed after perturbing every available channel within its declared uncertainty."),
        ColumnSpec("trial_index_value", "float", "0-100", "Index value for this trial."),
        ColumnSpec("changed_from_baseline", "bool", "-", "Whether this trial's class differs from this sample/method's own baseline class."),
        ColumnSpec("abs_index_change", "float", "index points", "Absolute difference between this trial's index value and the baseline."),
    ],
    STABILITY_BY_POINT: [
        ColumnSpec("sample_id", "str", "-", "Sampled computed_ts identifier."),
        ColumnSpec("selection_reason", "str", "-", "boundary_adjacent | random_comparison."),
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("n_trials", "int", "count", "Number of perturbation trials at this point."),
        ColumnSpec("n_class_changes", "int", "count", "Trials whose class differed from the baseline."),
        ColumnSpec("class_change_rate", "float", "0-1", "n_class_changes / n_trials."),
        ColumnSpec("mean_abs_index_change", "float", "index points", "Mean absolute index change across trials at this point."),
    ],
    STABILITY_SUMMARY: [
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("n_samples", "int", "count", "Number of sampled computed_ts points."),
        ColumnSpec("n_trials_total", "int", "count", "Total perturbation trials across all sampled points."),
        ColumnSpec("n_class_changes", "int", "count", "Total trials whose class differed from that point's baseline."),
        ColumnSpec("class_change_rate", "float", "0-1", "Aggregate class-change rate across all sampled points."),
        ColumnSpec("class_change_rate_ci95_low", "float", "0-1", "95% Wilson score confidence interval lower bound."),
        ColumnSpec("class_change_rate_ci95_high", "float", "0-1", "95% Wilson score confidence interval upper bound."),
        ColumnSpec("mean_abs_index_change", "float", "index points", "Mean absolute index change across all trials."),
        ColumnSpec("median_abs_index_change", "float", "index points", "Median absolute index change."),
        ColumnSpec("p95_abs_index_change", "float", "index points", "95th percentile absolute index change."),
        ColumnSpec("max_abs_index_change", "float", "index points", "Maximum absolute index change observed."),
    ],
    SENSITIVITY_WINDOW_BY_POINT: [
        ColumnSpec("sample_id", "str", "-", "Sampled computed_ts identifier."),
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "The sampled instant."),
        ColumnSpec("stratum", "str", "-", "Which stratification group this sample was drawn from."),
        ColumnSpec("reference_completeness_status", "str", "-", "Completeness status at the configured (15-minute) window."),
        ColumnSpec("reference_index_class", "str", "-", "Index class at the configured (15-minute) window."),
        ColumnSpec("reference_index_value", "float", "0-100", "Index value at the configured (15-minute) window; null if not OK."),
        ColumnSpec("value", "int", "minutes", "Window size tested (manuscript-specified: 5, 15, 30, 60)."),
        ColumnSpec("completeness_status", "str", "-", "OK | PARTIAL | FAILED at this window size."),
        ColumnSpec("index_value", "float", "0-100", "Index value at this window size; null if FAILED."),
        ColumnSpec("index_class", "str", "-", "Index class at this window size; null if FAILED."),
    ],
    SENSITIVITY_WINDOW_SUMMARY: [
        ColumnSpec("varied_parameter", "str", "-", "Always 'window_minutes' in this file."),
        ColumnSpec("value", "int", "minutes", "Window size tested."),
        ColumnSpec("n_eligible", "int", "count", "Sampled points selected for this window size (denominator before availability filtering)."),
        ColumnSpec("n_evaluated", "int", "count", "Of those, how many produced a non-null completeness_status (the sweep actually ran)."),
        ColumnSpec("n_unavailable", "int", "count", "n_eligible - n_evaluated."),
        ColumnSpec("n_valid_comparisons", "int", "count", "Of the evaluated points, how many had both a swept and reference index_value (denominator for the index-difference statistics)."),
        ColumnSpec("n_samples", "int", "count", "Alias of n_eligible, kept for backward-compatible column naming."),
        ColumnSpec("n_status_transitions", "int", "count", "Evaluated samples whose completeness status differed from the reference."),
        ColumnSpec("n_class_transitions", "int", "count", "Evaluated samples whose index class differed from the reference."),
        ColumnSpec("n_agreement", "int", "count", "n_evaluated - n_class_transitions."),
        ColumnSpec("class_agreement_with_reference", "float", "0-1", "n_agreement / n_evaluated; null if n_evaluated is 0."),
        ColumnSpec("mean_abs_index_diff", "float", "index points", "Mean absolute index difference from the reference, over n_valid_comparisons."),
        ColumnSpec("median_abs_index_diff", "float", "index points", "Median absolute index difference from the reference."),
        ColumnSpec("p95_abs_index_diff", "float", "index points", "95th percentile absolute index difference from the reference."),
        ColumnSpec("max_abs_index_diff", "float", "index points", "Maximum absolute index difference from the reference."),
    ],
    SENSITIVITY_COVERAGE_BY_POINT: [
        ColumnSpec("sample_id", "str", "-", "Sampled computed_ts identifier."),
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "The sampled instant."),
        ColumnSpec("stratum", "str", "-", "Which stratification group this sample was drawn from."),
        ColumnSpec("reference_completeness_status", "str", "-", "Completeness status at the configured coverage threshold."),
        ColumnSpec("reference_index_class", "str", "-", "Index class at the configured coverage threshold."),
        ColumnSpec("reference_index_value", "float", "0-100", "Index value at the configured coverage threshold; null if not OK."),
        ColumnSpec("value", "float", "0-1", "Coverage threshold tested (manuscript-specified: 0.70, 0.80, 0.90)."),
        ColumnSpec("completeness_status", "str", "-", "OK | PARTIAL | FAILED at this threshold."),
        ColumnSpec("index_value", "float", "0-100", "Index value at this threshold; null if FAILED."),
        ColumnSpec("index_class", "str", "-", "Index class at this threshold; null if FAILED."),
    ],
    SENSITIVITY_COVERAGE_SUMMARY: [
        ColumnSpec("varied_parameter", "str", "-", "Always 'coverage_threshold' in this file."),
        ColumnSpec("value", "float", "0-1", "Coverage threshold tested."),
        ColumnSpec("n_eligible", "int", "count", "Sampled points selected for this threshold (denominator before availability filtering)."),
        ColumnSpec("n_evaluated", "int", "count", "Of those, how many produced a non-null completeness_status (the sweep actually ran)."),
        ColumnSpec("n_unavailable", "int", "count", "n_eligible - n_evaluated."),
        ColumnSpec("n_valid_comparisons", "int", "count", "Of the evaluated points, how many had both a swept and reference index_value (denominator for the index-difference statistics)."),
        ColumnSpec("n_samples", "int", "count", "Alias of n_eligible, kept for backward-compatible column naming."),
        ColumnSpec("n_status_transitions", "int", "count", "Evaluated samples whose completeness status differed from the reference."),
        ColumnSpec("n_class_transitions", "int", "count", "Evaluated samples whose index class differed from the reference."),
        ColumnSpec("n_agreement", "int", "count", "n_evaluated - n_class_transitions."),
        ColumnSpec("class_agreement_with_reference", "float", "0-1", "n_agreement / n_evaluated; null if n_evaluated is 0."),
        ColumnSpec("mean_abs_index_diff", "float", "index points", "Mean absolute index difference from the reference, over n_valid_comparisons."),
        ColumnSpec("median_abs_index_diff", "float", "index points", "Median absolute index difference from the reference."),
        ColumnSpec("p95_abs_index_diff", "float", "index points", "95th percentile absolute index difference from the reference."),
        ColumnSpec("max_abs_index_diff", "float", "index points", "Maximum absolute index difference from the reference."),
    ],
    MASKING_SUMMARY: [
        ColumnSpec("method", "str", "-", "CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("severity_threshold", "str", "-", "Severity a component must reach to count as 'hidden' if the baseline doesn't also reach it."),
        ColumnSpec("n_critical_events", "int", "count", "Computed_ts where at least one component reached severity_threshold."),
        ColumnSpec("n_masked", "int", "count", "Of those, how many the baseline's aggregated class did not also reach."),
        ColumnSpec("masking_rate", "float", "0-1", "n_masked / n_critical_events; null if n_critical_events is 0 (nothing to mask, not a fabricated 0)."),
    ],
    REFERENCE_CASE_SUMMARY: [
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("n", "int", "count", "Synthetic, pre-labeled boundary-adjacent reference cases scored."),
        ColumnSpec("n_excluded", "int", "count", "Cases excluded for lack of a predicted class (e.g. FAILED)."),
        ColumnSpec("macro_f1", "float", "0-1", "Unweighted mean per-class F1 against the predefined synthetic labels -- consistency, NOT empirical accuracy."),
        ColumnSpec("cohens_kappa", "float", "-1 to 1", "Cohen's kappa against the predefined synthetic labels -- consistency, NOT empirical accuracy."),
    ],
    OUTDOOR_CONTEXT_TIMESERIES: [
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "Instant the outdoor context was fetched for."),
        ColumnSpec("outdoor_forecast_time", "datetime", "UTC timestamp", "Timestamp of the outdoor observation actually used (as-of, never future)."),
        ColumnSpec("age_minutes", "float", "minutes", "computed_ts minus outdoor_forecast_time."),
        ColumnSpec("is_stale", "bool", "-", "age_minutes exceeds the configured staleness threshold."),
        ColumnSpec("pm2_5", "float", "ug/m3", "Outdoor PM2.5 (context only, never a direct index input)."),
        ColumnSpec("pm10", "float", "ug/m3", "Outdoor PM10 (context only)."),
        ColumnSpec("temperature_2m", "float", "degC", "Outdoor temperature at 2m (context only)."),
    ],
    CONTINUITY_GRID: [
        ColumnSpec("boundary_id", "str", "-", "Identifier for the control-region boundary under test (channel + breakpoint)."),
        ColumnSpec("channel", "str", "-", "pm2_5 | pm10 | co2 | temperature | humidity."),
        ColumnSpec("boundary_value", "float", "channel units", "The control-region breakpoint this grid straddles."),
        ColumnSpec("grid_index", "int", "-", "0-based position within the dense input grid."),
        ColumnSpec("input_value", "float", "channel units", "The perturbed channel's value at this grid point."),
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("index_value", "float", "0-100", "Index value at this grid point."),
        ColumnSpec("index_class", "str", "-", "Index class at this grid point."),
    ],
    CONTINUITY_SUMMARY: [
        ColumnSpec("boundary_id", "str", "-", "Identifier for the control-region boundary under test."),
        ColumnSpec("channel", "str", "-", "pm2_5 | pm10 | co2 | temperature | humidity."),
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("max_adjacent_jump", "float", "index points", "Largest index-value change between adjacent grid points."),
        ColumnSpec("mean_adjacent_jump", "float", "index points", "Mean index-value change between adjacent grid points."),
        ColumnSpec("total_variation", "float", "index points", "Sum of absolute adjacent index-value changes across the whole grid."),
        ColumnSpec("n_class_transitions", "int", "count", "Number of grid points where the index class changed from the previous point."),
        ColumnSpec("class_transition_positions", "str", "-", "Semicolon-joined input_values where a class transition occurred."),
        ColumnSpec("index_range", "float", "index points", "max(index_value) - min(index_value) across the grid."),
        ColumnSpec("monotonicity_violations", "int", "count", "Adjacent-point decreases for a monotonic (higher-is-worse) pollutant channel."),
        ColumnSpec("masked_by_favorable", "bool", "-", "Whether a favorable component prevented the adverse channel from dominating the aggregated result."),
    ],
    FAULT_INJECTION_EVENTS: [
        ColumnSpec("scenario_id", "str", "-", "Synthetic scenario identifier."),
        ColumnSpec("channel", "str", "-", "Channel the fault was injected into."),
        ColumnSpec("fault_type", "str", "-", "single_spike | stuck_value | data_loss | gradual_drift | out_of_range | pm_order_violation."),
        ColumnSpec("injected_at_index", "int", "-", "0-based sample index within the scenario where the fault begins."),
        ColumnSpec("duration_samples", "int", "count", "Number of consecutive samples the fault spans."),
        ColumnSpec("description", "str", "-", "Human-readable description of the injected fault."),
    ],
    FAULT_DETECTION_PREDICTIONS: [
        ColumnSpec("scenario_id", "str", "-", "Synthetic scenario identifier."),
        ColumnSpec("channel", "str", "-", "Channel under test."),
        ColumnSpec("sample_index", "int", "-", "0-based sample index within the scenario."),
        ColumnSpec("true_fault_type", "str", "-", "Injected fault type at this sample, or null if genuinely clean."),
        ColumnSpec("predicted_reason_codes", "str", "-", "Semicolon-joined reason codes the quality layer actually assigned."),
        ColumnSpec("stage2_state", "str", "-", "VALID | SUSPECT | INVALID | MISSING assigned by the quality layer."),
        ColumnSpec("usable", "bool", "-", "Whether the quality layer counted this sample toward coverage."),
    ],
    FAULT_DETECTION_METRICS: [
        ColumnSpec("reason_code", "str", "-", "single_spike | stuck_value | data_loss | gradual_drift | out_of_range."),
        ColumnSpec("tp", "int", "count", "True positives."),
        ColumnSpec("fp", "int", "count", "False positives."),
        ColumnSpec("fn", "int", "count", "False negatives."),
        ColumnSpec("precision", "float", "0-1", "tp / (tp + fp)."),
        ColumnSpec("recall", "float", "0-1", "tp / (tp + fn)."),
        ColumnSpec("f1", "float", "0-1", "Harmonic mean of precision and recall."),
        ColumnSpec("false_positive_rate", "float", "0-1", "fp / (fp + true negatives)."),
        ColumnSpec("mean_detection_delay", "float", "samples", "Mean number of samples between fault onset and first detection, for sequential faults."),
    ],
    HAMPEL_CALIBRATION: [
        ColumnSpec("dataset_split", "str", "-", "development | holdout."),
        ColumnSpec("window_size", "int", "samples", "Hampel filter window size tested."),
        ColumnSpec("mad_multiplier", "float", "-", "Hampel filter MAD multiplier tested."),
        ColumnSpec("fault_recall", "float", "0-1", "Recall for single_spike detection on this split."),
        ColumnSpec("genuine_event_preservation_rate", "float", "0-1", "Fraction of genuine rapid environmental events not falsely flagged."),
        ColumnSpec("objective_score", "float", "-", "Balanced objective combining fault_recall and genuine_event_preservation_rate."),
        ColumnSpec("selected", "bool", "-", "Whether this configuration was the one selected from development results."),
    ],
}


def _join_if_array(value):
    if isinstance(value, (list, tuple, np.ndarray)):
        return ";".join(str(v) for v in value)
    return value


def _write(df: pd.DataFrame, columns: list[ColumnSpec], out_dir: Path, filename: str) -> Path:
    ordered = [c.name for c in columns]
    for col in ordered:
        if col not in df.columns:
            df[col] = None
    df = df[ordered]
    # DuckDB VARCHAR[] columns come back as numpy arrays (object dtype); only
    # object-dtype columns can possibly hold them, so skip datetime/numeric
    # columns entirely (touching them at all trips a pandas dtype edge case).
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_join_if_array)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    df.to_csv(path, index=False)
    return path


def export_index_timeseries(con: duckdb.DuckDBPyConnection, out_dir: Path, pipeline_run_id: str, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        "SELECT computed_ts, window_minutes, completeness_status, index_value, index_class, dominant_component, rule_level_contributors, n_rules_fired "
        "FROM iaq_index_results WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[INDEX_TIMESERIES], out_dir, INDEX_TIMESERIES)


def export_component_scores_timeseries(con: duckdb.DuckDBPyConnection, out_dir: Path, pipeline_run_id: str, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        "SELECT computed_ts, window_minutes, component, available, crisp_score, "
        "membership_favorable, membership_acceptable, membership_degraded, membership_critical, room, season "
        "FROM component_scores WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts, component",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[COMPONENT_SCORES_TIMESERIES], out_dir, COMPONENT_SCORES_TIMESERIES)


def export_method_comparison(con: duckdb.DuckDBPyConnection, out_dir: Path, pipeline_run_id: str, evaluation_run_id: str | None, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        """
        SELECT
            p.computed_ts,
            p.completeness_status AS proposed_status,
            p.index_value AS proposed_index_value,
            p.index_class AS proposed_index_class,
            cm.index_value AS crisp_max_index_value,
            cm.index_class AS crisp_max_index_class,
            wm.index_value AS weighted_mean_index_value,
            wm.index_class AS weighted_mean_index_class
        FROM iaq_index_results p
        LEFT JOIN baseline_results cm ON cm.pipeline_run_id = p.pipeline_run_id AND cm.computed_ts = p.computed_ts
            AND cm.window_minutes = p.window_minutes AND cm.method = 'CRISP-MAX' AND cm.evaluation_run_id = ?
        LEFT JOIN baseline_results wm ON wm.pipeline_run_id = p.pipeline_run_id AND wm.computed_ts = p.computed_ts
            AND wm.window_minutes = p.window_minutes AND wm.method = 'WEIGHTED-MEAN' AND wm.evaluation_run_id = ?
        WHERE p.pipeline_run_id = ? AND p.window_minutes = ? AND p.computed_ts > ? AND p.computed_ts <= ?
        ORDER BY p.computed_ts
        """,
        [evaluation_run_id, evaluation_run_id, pipeline_run_id, window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[METHOD_COMPARISON], out_dir, METHOD_COMPARISON)


def export_data_quality_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, pipeline_run_id: str, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        "SELECT computed_ts, window_minutes, channel, n_expected, n_usable, coverage_ratio, coverage_ok, weighted_mean "
        "FROM window_aggregates WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts, channel",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[DATA_QUALITY_SUMMARY], out_dir, DATA_QUALITY_SUMMARY)


def export_reason_code_frequency(con: duckdb.DuckDBPyConnection, out_dir: Path, pipeline_run_id: str, from_ts: datetime, to_ts: datetime) -> Path | None:
    from iaq_hfis.evaluation.faults import compute_reason_code_frequency

    freq = compute_reason_code_frequency(con, pipeline_run_id, from_ts, to_ts)
    if freq.n_total_quality_rows == 0:
        return None
    df = pd.DataFrame({"reason_code": list(freq.counts.keys()), "count": list(freq.counts.values())})
    return _write(df, COLUMNS[REASON_CODE_FREQUENCY], out_dir, REASON_CODE_FREQUENCY)


def export_stability_samples(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT sample_id, computed_ts, selection_reason, boundary_channel, baseline_class_hfis, baseline_index_hfis, "
        "baseline_class_crisp_max, baseline_index_crisp_max, baseline_class_weighted_mean, baseline_index_weighted_mean "
        "FROM evaluation_stability_samples WHERE evaluation_run_id = ? ORDER BY computed_ts",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[STABILITY_SAMPLES], out_dir, STABILITY_SAMPLES)


def export_stability_trials(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT sample_id, method, trial_index, trial_class, trial_index_value, changed_from_baseline, abs_index_change "
        "FROM evaluation_stability_trials WHERE evaluation_run_id = ? ORDER BY sample_id, method, trial_index",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[STABILITY_TRIALS], out_dir, STABILITY_TRIALS)


def export_stability_by_point(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        """
        SELECT s.sample_id, s.selection_reason, t.method,
               COUNT(*) AS n_trials,
               SUM(CASE WHEN t.changed_from_baseline THEN 1 ELSE 0 END) AS n_class_changes,
               AVG(CASE WHEN t.changed_from_baseline THEN 1.0 ELSE 0.0 END) AS class_change_rate,
               AVG(t.abs_index_change) AS mean_abs_index_change
        FROM evaluation_stability_trials t
        JOIN evaluation_stability_samples s ON s.evaluation_run_id = t.evaluation_run_id AND s.sample_id = t.sample_id
        WHERE t.evaluation_run_id = ?
        GROUP BY s.sample_id, s.selection_reason, t.method
        ORDER BY s.sample_id, t.method
        """,
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[STABILITY_BY_POINT], out_dir, STABILITY_BY_POINT)


def export_stability_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    from iaq_hfis.evaluation.multi_point_stability import wilson_ci

    df = con.execute(
        "SELECT sample_id, method, trial_index, trial_class, trial_index_value, changed_from_baseline, abs_index_change "
        "FROM evaluation_stability_trials WHERE evaluation_run_id = ?",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    rows = []
    for method, g in df.groupby("method"):
        n = len(g)
        n_changes = int(g["changed_from_baseline"].sum())
        ci = wilson_ci(n_changes, n)
        rows.append(
            {
                "method": method,
                "n_samples": g["sample_id"].nunique(),
                "n_trials_total": n,
                "n_class_changes": n_changes,
                "class_change_rate": n_changes / n if n else None,
                "class_change_rate_ci95_low": ci[0] if ci else None,
                "class_change_rate_ci95_high": ci[1] if ci else None,
                "mean_abs_index_change": float(g["abs_index_change"].mean()) if g["abs_index_change"].notna().any() else None,
                "median_abs_index_change": float(g["abs_index_change"].median()) if g["abs_index_change"].notna().any() else None,
                "p95_abs_index_change": float(g["abs_index_change"].quantile(0.95)) if g["abs_index_change"].notna().any() else None,
                "max_abs_index_change": float(g["abs_index_change"].max()) if g["abs_index_change"].notna().any() else None,
            }
        )
    return _write(pd.DataFrame(rows), COLUMNS[STABILITY_SUMMARY], out_dir, STABILITY_SUMMARY)


def _export_sensitivity_by_point(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str, varied_parameter: str, filename: str) -> Path | None:
    df = con.execute(
        "SELECT sample_id, computed_ts, stratum, reference_completeness_status, reference_index_class, reference_index_value, "
        "value, completeness_status, index_value, index_class "
        "FROM evaluation_sensitivity WHERE evaluation_run_id = ? AND varied_parameter = ? ORDER BY value, sample_id",
        [evaluation_run_id, varied_parameter],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[filename], out_dir, filename)


def export_sensitivity_window_by_point(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    return _export_sensitivity_by_point(con, out_dir, evaluation_run_id, "window_minutes", SENSITIVITY_WINDOW_BY_POINT)


def export_sensitivity_coverage_by_point(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    return _export_sensitivity_by_point(con, out_dir, evaluation_run_id, "coverage_threshold", SENSITIVITY_COVERAGE_BY_POINT)


def _export_sensitivity_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str, varied_parameter: str, filename: str) -> Path | None:
    from iaq_hfis.evaluation.multi_point_sensitivity import compute_sensitivity_summary

    rows = compute_sensitivity_summary(con, evaluation_run_id, varied_parameter)
    if not rows:
        return None
    df = pd.DataFrame(rows)
    return _write(df, COLUMNS[filename], out_dir, filename)


def export_sensitivity_window_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    return _export_sensitivity_summary(con, out_dir, evaluation_run_id, "window_minutes", SENSITIVITY_WINDOW_SUMMARY)


def export_sensitivity_coverage_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    return _export_sensitivity_summary(con, out_dir, evaluation_run_id, "coverage_threshold", SENSITIVITY_COVERAGE_SUMMARY)


def export_masking_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT method, severity_threshold, n_critical_events, n_masked, masking_rate FROM evaluation_masking WHERE evaluation_run_id = ? ORDER BY method",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[MASKING_SUMMARY], out_dir, MASKING_SUMMARY)


def export_reference_case_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT method, n, n_excluded, macro_f1, cohens_kappa FROM evaluation_reference_cases WHERE evaluation_run_id = ? ORDER BY method", [evaluation_run_id]
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[REFERENCE_CASE_SUMMARY], out_dir, REFERENCE_CASE_SUMMARY)


def export_outdoor_context_timeseries(con: duckdb.DuckDBPyConnection, out_dir: Path, pipeline_run_id: str, from_ts: datetime, to_ts: datetime) -> Path | None:
    df = con.execute(
        "SELECT computed_ts, outdoor_forecast_time, age_minutes, is_stale, pm2_5, pm10, temperature_2m "
        "FROM outdoor_context WHERE pipeline_run_id = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts",
        [pipeline_run_id, from_ts, to_ts],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[OUTDOOR_CONTEXT_TIMESERIES], out_dir, OUTDOOR_CONTEXT_TIMESERIES)


def export_continuity_grid(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT boundary_id, channel, boundary_value, grid_index, input_value, method, index_value, index_class "
        "FROM evaluation_continuity_grid WHERE evaluation_run_id = ? ORDER BY boundary_id, method, grid_index",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[CONTINUITY_GRID], out_dir, CONTINUITY_GRID)


def export_continuity_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT boundary_id, channel, method, max_adjacent_jump, mean_adjacent_jump, total_variation, n_class_transitions, "
        "class_transition_positions, index_range, monotonicity_violations, masked_by_favorable "
        "FROM evaluation_continuity_summary WHERE evaluation_run_id = ? ORDER BY boundary_id, method",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[CONTINUITY_SUMMARY], out_dir, CONTINUITY_SUMMARY)


def export_fault_injection_events(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT scenario_id, channel, fault_type, injected_at_index, duration_samples, description "
        "FROM fault_injection_events WHERE evaluation_run_id = ? ORDER BY scenario_id, channel, injected_at_index",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[FAULT_INJECTION_EVENTS], out_dir, FAULT_INJECTION_EVENTS)


def export_fault_detection_predictions(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT scenario_id, channel, sample_index, true_fault_type, predicted_reason_codes, stage2_state, usable "
        "FROM fault_detection_predictions WHERE evaluation_run_id = ? ORDER BY scenario_id, channel, sample_index",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[FAULT_DETECTION_PREDICTIONS], out_dir, FAULT_DETECTION_PREDICTIONS)


def export_fault_detection_metrics(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT reason_code, tp, fp, fn, precision, recall, f1, false_positive_rate, mean_detection_delay "
        "FROM fault_detection_metrics WHERE evaluation_run_id = ? ORDER BY reason_code",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[FAULT_DETECTION_METRICS], out_dir, FAULT_DETECTION_METRICS)


def export_hampel_calibration(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str) -> Path | None:
    df = con.execute(
        "SELECT dataset_split, window_size, mad_multiplier, fault_recall, genuine_event_preservation_rate, objective_score, selected "
        "FROM hampel_calibration WHERE evaluation_run_id = ? ORDER BY dataset_split, window_size, mad_multiplier",
        [evaluation_run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[HAMPEL_CALIBRATION], out_dir, HAMPEL_CALIBRATION)


def export_all(
    con: duckdb.DuckDBPyConnection,
    out_dir: Path,
    window_minutes: int,
    pipeline_run_id: str,
    evaluation_run_id: str | None,
    from_ts: datetime,
    to_ts: datetime,
) -> dict[str, Path | None]:
    """Writes every graph-ready CSV for one pipeline run (and, where
    applicable, its one selected evaluation run). Returns a dict of
    filename -> path written, with ``None`` for files that had nothing to
    export (explained in the caller's narrative/summary, never silently
    fabricated as an empty-but-present file)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        INDEX_TIMESERIES: export_index_timeseries(con, out_dir, pipeline_run_id, window_minutes, from_ts, to_ts),
        COMPONENT_SCORES_TIMESERIES: export_component_scores_timeseries(con, out_dir, pipeline_run_id, window_minutes, from_ts, to_ts),
        DATA_QUALITY_SUMMARY: export_data_quality_summary(con, out_dir, pipeline_run_id, window_minutes, from_ts, to_ts),
        REASON_CODE_FREQUENCY: export_reason_code_frequency(con, out_dir, pipeline_run_id, from_ts, to_ts),
        OUTDOOR_CONTEXT_TIMESERIES: export_outdoor_context_timeseries(con, out_dir, pipeline_run_id, from_ts, to_ts),
    }
    if evaluation_run_id is None:
        for name in (
            METHOD_COMPARISON, STABILITY_SAMPLES, STABILITY_TRIALS, STABILITY_BY_POINT, STABILITY_SUMMARY,
            SENSITIVITY_WINDOW_BY_POINT, SENSITIVITY_WINDOW_SUMMARY, SENSITIVITY_COVERAGE_BY_POINT, SENSITIVITY_COVERAGE_SUMMARY,
            MASKING_SUMMARY, REFERENCE_CASE_SUMMARY, CONTINUITY_GRID, CONTINUITY_SUMMARY,
            FAULT_INJECTION_EVENTS, FAULT_DETECTION_PREDICTIONS, FAULT_DETECTION_METRICS, HAMPEL_CALIBRATION,
        ):
            result[name] = None
        return result

    result.update(
        {
            METHOD_COMPARISON: export_method_comparison(con, out_dir, pipeline_run_id, evaluation_run_id, window_minutes, from_ts, to_ts),
            STABILITY_SAMPLES: export_stability_samples(con, out_dir, evaluation_run_id),
            STABILITY_TRIALS: export_stability_trials(con, out_dir, evaluation_run_id),
            STABILITY_BY_POINT: export_stability_by_point(con, out_dir, evaluation_run_id),
            STABILITY_SUMMARY: export_stability_summary(con, out_dir, evaluation_run_id),
            SENSITIVITY_WINDOW_BY_POINT: export_sensitivity_window_by_point(con, out_dir, evaluation_run_id),
            SENSITIVITY_WINDOW_SUMMARY: export_sensitivity_window_summary(con, out_dir, evaluation_run_id),
            SENSITIVITY_COVERAGE_BY_POINT: export_sensitivity_coverage_by_point(con, out_dir, evaluation_run_id),
            SENSITIVITY_COVERAGE_SUMMARY: export_sensitivity_coverage_summary(con, out_dir, evaluation_run_id),
            MASKING_SUMMARY: export_masking_summary(con, out_dir, evaluation_run_id),
            REFERENCE_CASE_SUMMARY: export_reference_case_summary(con, out_dir, evaluation_run_id),
            CONTINUITY_GRID: export_continuity_grid(con, out_dir, evaluation_run_id),
            CONTINUITY_SUMMARY: export_continuity_summary(con, out_dir, evaluation_run_id),
            FAULT_INJECTION_EVENTS: export_fault_injection_events(con, out_dir, evaluation_run_id),
            FAULT_DETECTION_PREDICTIONS: export_fault_detection_predictions(con, out_dir, evaluation_run_id),
            FAULT_DETECTION_METRICS: export_fault_detection_metrics(con, out_dir, evaluation_run_id),
            HAMPEL_CALIBRATION: export_hampel_calibration(con, out_dir, evaluation_run_id),
        }
    )
    return result
