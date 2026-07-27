"""Graph-ready CSV exports from the derived DuckDB.

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
STABILITY_TRIALS = "stability_trials.csv"
SENSITIVITY_WINDOW = "sensitivity_window.csv"
SENSITIVITY_COVERAGE = "sensitivity_coverage.csv"
MASKING_SUMMARY = "masking_summary.csv"
GROUND_TRUTH_SUMMARY = "ground_truth_summary.csv"
OUTDOOR_CONTEXT_TIMESERIES = "outdoor_context_timeseries.csv"

COLUMNS: dict[str, list[ColumnSpec]] = {
    INDEX_TIMESERIES: [
        ColumnSpec("computed_ts", "datetime", "UTC timestamp", "Instant the index was computed for (end of the rolling window)."),
        ColumnSpec("window_minutes", "int", "minutes", "Aggregation window size used for this row."),
        ColumnSpec("completeness_status", "str", "-", "OK | PARTIAL | FAILED."),
        ColumnSpec("index_value", "float", "0-100", "Defuzzified PROPOSED-HFIS index value; null if FAILED."),
        ColumnSpec("index_class", "str", "-", "Favorable | Acceptable | Degraded | Critical; null if FAILED."),
        ColumnSpec("dominant_component", "str", "-", "Semicolon-joined component(s) most responsible for the activated rules (A/V/M); ties preserved."),
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
    STABILITY_TRIALS: [
        ColumnSpec("trial_index", "int", "-", "0-based perturbation trial number."),
        ColumnSpec("trial_class", "str", "-", "Index class recomputed after perturbing every available channel within its declared uncertainty."),
        ColumnSpec("changed_from_baseline", "bool", "-", "Whether this trial's class differs from the unperturbed baseline class."),
    ],
    SENSITIVITY_WINDOW: [
        ColumnSpec("value", "int", "minutes", "Window size tested (manuscript-specified: 5, 15, 30, 60)."),
        ColumnSpec("completeness_status", "str", "-", "OK | PARTIAL | FAILED at this window size."),
        ColumnSpec("index_value", "float", "0-100", "Index value at this window size; null if FAILED."),
        ColumnSpec("index_class", "str", "-", "Index class at this window size; null if FAILED."),
    ],
    SENSITIVITY_COVERAGE: [
        ColumnSpec("value", "float", "0-1", "Coverage threshold tested (manuscript-specified: 0.70, 0.80, 0.90)."),
        ColumnSpec("completeness_status", "str", "-", "OK | PARTIAL | FAILED at this threshold."),
        ColumnSpec("index_value", "float", "0-100", "Index value at this threshold; null if FAILED."),
        ColumnSpec("index_class", "str", "-", "Index class at this threshold; null if FAILED."),
    ],
    MASKING_SUMMARY: [
        ColumnSpec("method", "str", "-", "CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("severity_threshold", "str", "-", "Severity a component must reach to count as 'hidden' if the baseline doesn't also reach it."),
        ColumnSpec("n_critical_events", "int", "count", "Computed_ts where at least one component reached severity_threshold."),
        ColumnSpec("n_masked", "int", "count", "Of those, how many the baseline's aggregated class did not also reach."),
        ColumnSpec("masking_rate", "float", "0-1", "n_masked / n_critical_events; null if n_critical_events is 0 (nothing to mask, not a fabricated 0)."),
    ],
    GROUND_TRUTH_SUMMARY: [
        ColumnSpec("method", "str", "-", "PROPOSED-HFIS | CRISP-MAX | WEIGHTED-MEAN."),
        ColumnSpec("n", "int", "count", "Synthetic boundary-adjacent vectors scored."),
        ColumnSpec("n_excluded", "int", "count", "Vectors excluded for lack of a predicted class (e.g. FAILED)."),
        ColumnSpec("macro_f1", "float", "0-1", "Unweighted mean per-class F1 against the synthetic ground truth."),
        ColumnSpec("cohens_kappa", "float", "-1 to 1", "Cohen's kappa against the synthetic ground truth."),
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


def export_index_timeseries(con: duckdb.DuckDBPyConnection, out_dir: Path, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        "SELECT computed_ts, window_minutes, completeness_status, index_value, index_class, dominant_component, n_rules_fired "
        "FROM iaq_index_results WHERE window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts",
        [window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[INDEX_TIMESERIES], out_dir, INDEX_TIMESERIES)


def export_component_scores_timeseries(con: duckdb.DuckDBPyConnection, out_dir: Path, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        "SELECT computed_ts, window_minutes, component, available, crisp_score, "
        "membership_favorable, membership_acceptable, membership_degraded, membership_critical, room, season "
        "FROM component_scores WHERE window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts, component",
        [window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[COMPONENT_SCORES_TIMESERIES], out_dir, COMPONENT_SCORES_TIMESERIES)


def export_method_comparison(con: duckdb.DuckDBPyConnection, out_dir: Path, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
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
        LEFT JOIN baseline_results cm ON cm.computed_ts = p.computed_ts AND cm.window_minutes = p.window_minutes AND cm.method = 'CRISP-MAX'
        LEFT JOIN baseline_results wm ON wm.computed_ts = p.computed_ts AND wm.window_minutes = p.window_minutes AND wm.method = 'WEIGHTED-MEAN'
        WHERE p.window_minutes = ? AND p.computed_ts > ? AND p.computed_ts <= ?
        ORDER BY p.computed_ts
        """,
        [window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[METHOD_COMPARISON], out_dir, METHOD_COMPARISON)


def export_data_quality_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, window_minutes: int, from_ts: datetime, to_ts: datetime) -> Path:
    df = con.execute(
        "SELECT computed_ts, window_minutes, channel, n_expected, n_usable, coverage_ratio, coverage_ok, weighted_mean "
        "FROM window_aggregates WHERE window_minutes = ? AND computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts, channel",
        [window_minutes, from_ts, to_ts],
    ).df()
    return _write(df, COLUMNS[DATA_QUALITY_SUMMARY], out_dir, DATA_QUALITY_SUMMARY)


def export_reason_code_frequency(con: duckdb.DuckDBPyConnection, out_dir: Path, from_ts: datetime, to_ts: datetime) -> Path | None:
    from iaq_hfis.evaluation.faults import compute_reason_code_frequency

    freq = compute_reason_code_frequency(con, from_ts, to_ts)
    if freq.n_total_quality_rows == 0:
        return None
    df = pd.DataFrame({"reason_code": list(freq.counts.keys()), "count": list(freq.counts.values())})
    return _write(df, COLUMNS[REASON_CODE_FREQUENCY], out_dir, REASON_CODE_FREQUENCY)


def export_stability_trials(con: duckdb.DuckDBPyConnection, out_dir: Path, run_id: str) -> Path | None:
    row = con.execute("SELECT baseline_class, trial_classes FROM evaluation_stability WHERE run_id = ?", [run_id]).fetchone()
    if row is None:
        return None
    baseline_class, trial_classes = row
    df = pd.DataFrame(
        {
            "trial_index": range(len(trial_classes)),
            "trial_class": trial_classes,
            "changed_from_baseline": [tc != baseline_class for tc in trial_classes],
        }
    )
    return _write(df, COLUMNS[STABILITY_TRIALS], out_dir, STABILITY_TRIALS)


def _export_sensitivity(con: duckdb.DuckDBPyConnection, out_dir: Path, run_id: str, varied_parameter: str, filename: str) -> Path | None:
    df = con.execute(
        "SELECT value, completeness_status, index_value, index_class FROM evaluation_sensitivity "
        "WHERE run_id = ? AND varied_parameter = ? ORDER BY value",
        [run_id, varied_parameter],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[filename], out_dir, filename)


def export_sensitivity_window(con: duckdb.DuckDBPyConnection, out_dir: Path, run_id: str) -> Path | None:
    return _export_sensitivity(con, out_dir, run_id, "window_minutes", SENSITIVITY_WINDOW)


def export_sensitivity_coverage(con: duckdb.DuckDBPyConnection, out_dir: Path, run_id: str) -> Path | None:
    return _export_sensitivity(con, out_dir, run_id, "coverage_threshold", SENSITIVITY_COVERAGE)


def export_masking_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, run_id: str) -> Path | None:
    df = con.execute(
        "SELECT method, severity_threshold, n_critical_events, n_masked, masking_rate FROM evaluation_masking WHERE run_id = ? ORDER BY method",
        [run_id],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[MASKING_SUMMARY], out_dir, MASKING_SUMMARY)


def export_ground_truth_summary(con: duckdb.DuckDBPyConnection, out_dir: Path, run_id: str) -> Path | None:
    df = con.execute(
        "SELECT method, n, n_excluded, macro_f1, cohens_kappa FROM evaluation_ground_truth WHERE run_id = ? ORDER BY method", [run_id]
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[GROUND_TRUTH_SUMMARY], out_dir, GROUND_TRUTH_SUMMARY)


def export_outdoor_context_timeseries(con: duckdb.DuckDBPyConnection, out_dir: Path, from_ts: datetime, to_ts: datetime) -> Path | None:
    df = con.execute(
        "SELECT computed_ts, outdoor_forecast_time, age_minutes, is_stale, pm2_5, pm10, temperature_2m "
        "FROM outdoor_context WHERE computed_ts > ? AND computed_ts <= ? ORDER BY computed_ts",
        [from_ts, to_ts],
    ).df()
    if df.empty:
        return None
    return _write(df, COLUMNS[OUTDOOR_CONTEXT_TIMESERIES], out_dir, OUTDOOR_CONTEXT_TIMESERIES)


def export_all(con: duckdb.DuckDBPyConnection, out_dir: Path, window_minutes: int, run_id: str, from_ts: datetime, to_ts: datetime) -> dict[str, Path | None]:
    """Writes every graph-ready CSV for one run. Returns a dict of
    filename -> path written, with ``None`` for files that had nothing to
    export (explained in the caller's narrative/summary, never silently
    fabricated as an empty-but-present file)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        INDEX_TIMESERIES: export_index_timeseries(con, out_dir, window_minutes, from_ts, to_ts),
        COMPONENT_SCORES_TIMESERIES: export_component_scores_timeseries(con, out_dir, window_minutes, from_ts, to_ts),
        METHOD_COMPARISON: export_method_comparison(con, out_dir, window_minutes, from_ts, to_ts),
        DATA_QUALITY_SUMMARY: export_data_quality_summary(con, out_dir, window_minutes, from_ts, to_ts),
        REASON_CODE_FREQUENCY: export_reason_code_frequency(con, out_dir, from_ts, to_ts),
        STABILITY_TRIALS: export_stability_trials(con, out_dir, run_id),
        SENSITIVITY_WINDOW: export_sensitivity_window(con, out_dir, run_id),
        SENSITIVITY_COVERAGE: export_sensitivity_coverage(con, out_dir, run_id),
        MASKING_SUMMARY: export_masking_summary(con, out_dir, run_id),
        GROUND_TRUTH_SUMMARY: export_ground_truth_summary(con, out_dir, run_id),
        OUTDOOR_CONTEXT_TIMESERIES: export_outdoor_context_timeseries(con, out_dir, from_ts, to_ts),
    }
