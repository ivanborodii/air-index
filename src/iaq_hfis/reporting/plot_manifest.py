"""``plot_manifest.json``: one entry per recommended figure, each naming a
source CSV and the exact columns it plots. Validated against
:data:`iaq_hfis.reporting.exports.COLUMNS` at build time -- a plot can never
reference a file or column that doesn't exist in the export registry.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from iaq_hfis.reporting import exports

MANIFEST_FILENAME = "plot_manifest.json"


@dataclass(frozen=True)
class PlotSpec:
    id: str
    title: str
    source_csv: str
    plot_type: str  # line | scatter | bar | histogram
    x: str
    y: list[str] = field(default_factory=list)
    group_by: str | None = None
    description: str = ""
    filter_equals: dict[str, str] | None = None  # e.g. {"context": "favourable"} -- restrict to one slice before plotting


PLOTS: list[PlotSpec] = [
    PlotSpec(
        id="index_timeseries",
        title="IAQ Index Over Time",
        source_csv=exports.INDEX_TIMESERIES,
        plot_type="line",
        x="computed_ts",
        y=["index_value"],
        description="PROPOSED_HFIS index value over the computed range. Shade/annotate the 25/50/75 class boundaries.",
    ),
    PlotSpec(
        id="method_comparison",
        title="PROPOSED_HFIS vs FUZZY_COMPONENT_MAX vs CRISP_CLASS_MAX vs WEIGHTED_MEAN",
        source_csv=exports.METHOD_COMPARISON,
        plot_type="line",
        x="computed_ts",
        y=["proposed_index_value", "crisp_max_index_value", "crisp_class_max_index_value", "weighted_mean_index_value"],
        description="Four index series over the same computed_ts range -- shows where methods diverge.",
    ),
    PlotSpec(
        id="component_scores",
        title="Component Crisp Scores Over Time",
        source_csv=exports.COMPONENT_SCORES_TIMESERIES,
        plot_type="line",
        x="computed_ts",
        y=["crisp_score"],
        group_by="component",
        description="One line per component (A/V/M), grouped by the 'component' column.",
    ),
    PlotSpec(
        id="coverage_over_time",
        title="Channel Coverage Ratio Over Time",
        source_csv=exports.DATA_QUALITY_SUMMARY,
        plot_type="line",
        x="computed_ts",
        y=["coverage_ratio"],
        group_by="channel",
        description="Coverage ratio per direct-input channel, grouped by 'channel'; overlay the configured min_ratio threshold.",
    ),
    PlotSpec(
        id="reason_code_frequency",
        title="Data-Quality Reason Code Frequency",
        source_csv=exports.REASON_CODE_FREQUENCY,
        plot_type="bar",
        x="reason_code",
        y=["count"],
        description="Which fault categories (stuck value, single spike, ...) drove data unavailability.",
    ),
    PlotSpec(
        id="stability_trials",
        title="Stability: Trial Outcomes by Method",
        source_csv=exports.STABILITY_TRIALS,
        plot_type="histogram",
        x="trial_class",
        group_by="method",
        description="Count of perturbation trials landing in each class, one series per method, across every sampled point.",
    ),
    PlotSpec(
        id="stability_summary",
        title="Stability: Class-Change Rate by Method",
        source_csv=exports.STABILITY_SUMMARY,
        plot_type="bar",
        x="method",
        y=["class_change_rate"],
        description="Aggregate class-change rate under perturbation, one bar per method, across all sampled points.",
    ),
    PlotSpec(
        id="sensitivity_window_summary",
        title="Sensitivity to Window Duration",
        source_csv=exports.SENSITIVITY_WINDOW_SUMMARY,
        plot_type="line",
        x="value",
        y=["mean_abs_index_diff", "p95_abs_index_diff"],
        description="Mean and 95th-percentile absolute index difference from the 15-minute reference, at each window size, aggregated across all sampled points.",
    ),
    PlotSpec(
        id="sensitivity_coverage_summary",
        title="Sensitivity to Coverage Threshold",
        source_csv=exports.SENSITIVITY_COVERAGE_SUMMARY,
        plot_type="line",
        x="value",
        y=["mean_abs_index_diff", "p95_abs_index_diff"],
        description="Mean and 95th-percentile absolute index difference from the reference coverage threshold, aggregated across all sampled points.",
    ),
    PlotSpec(
        id="masking_rate",
        title="Masking Rate: FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN",
        source_csv=exports.MASKING_SUMMARY,
        plot_type="bar",
        x="method",
        y=["masking_rate"],
        description="Fraction of critical-component events hidden by each baseline's aggregation.",
    ),
    PlotSpec(
        id="reference_case_scores",
        title="Reference-Case Consistency (Macro-F1) by Method",
        source_csv=exports.REFERENCE_CASE_SUMMARY,
        plot_type="bar",
        x="method",
        y=["macro_f1"],
        description="Macro-F1 consistency with the predefined synthetic boundary-adjacent reference cases, one bar per method -- NOT an empirical accuracy estimate.",
    ),
    PlotSpec(
        id="continuity_curves",
        title="HFIS vs FUZZY_COMPONENT_MAX: Index Value Across a Boundary Grid (favourable context)",
        source_csv=exports.CONTINUITY_GRID,
        plot_type="line",
        x="input_value",
        y=["index_value"],
        group_by="method",
        filter_equals={"context": "favourable"},
        description="Index value across a dense input grid straddling one control-region boundary, one line per method, restricted to the favourable other-components context for readability (see continuity_grid.csv for the acceptable/degraded contexts too); render one figure per boundary_id.",
    ),
    PlotSpec(
        id="continuity_summary",
        title="Boundary Continuity: Maximum Adjacent Jump by Method (favourable context)",
        source_csv=exports.CONTINUITY_SUMMARY,
        plot_type="bar",
        x="boundary_id",
        y=["max_adjacent_jump"],
        group_by="method",
        filter_equals={"context": "favourable"},
        description="Largest single-step index change across each boundary's grid, grouped by method, restricted to the favourable other-components context for readability -- smaller is smoother.",
    ),
    PlotSpec(
        id="fault_detection_metrics",
        title="Fault-Injection Detection Performance by Reason Code (validation split)",
        source_csv=exports.FAULT_DETECTION_METRICS,
        plot_type="bar",
        x="reason_code",
        y=["precision", "recall", "f1"],
        filter_equals={"dataset_split": "validation"},
        description="Row-level labeled precision/recall/F1 for each data-quality reason code, validation split only (disjoint from calibration -- no parameter was tuned against these numbers), from the deterministic fault-injection benchmark (not unlabeled real data).",
    ),
    PlotSpec(
        id="multi_component_grid_summary",
        title="Multi-Component Grid: Mean Absolute Score Difference by Method Pair",
        source_csv=exports.MULTI_COMPONENT_GRID_SUMMARY,
        plot_type="bar",
        x="method_a",
        y=["mean_abs_diff", "p95_abs_diff"],
        group_by="method_b",
        description="Mean and p95 |method_a - method_b| across the independent (A, V, M) grid (default 41^3 = 68,921 combinations) -- the aggregate score-difference distribution between every pair of methods, not just at boundaries.",
    ),
]


def validate_plots(plots: list[PlotSpec]) -> None:
    for p in plots:
        if p.source_csv not in exports.COLUMNS:
            raise ValueError(f"plot '{p.id}': unknown source_csv '{p.source_csv}' (not in exports.COLUMNS)")
        valid_columns = {c.name for c in exports.COLUMNS[p.source_csv]}
        if p.x not in valid_columns:
            raise ValueError(f"plot '{p.id}': x column '{p.x}' not found in {p.source_csv}")
        for y in p.y:
            if y not in valid_columns:
                raise ValueError(f"plot '{p.id}': y column '{y}' not found in {p.source_csv}")
        if p.group_by is not None and p.group_by not in valid_columns:
            raise ValueError(f"plot '{p.id}': group_by column '{p.group_by}' not found in {p.source_csv}")
        for col in (p.filter_equals or {}):
            if col not in valid_columns:
                raise ValueError(f"plot '{p.id}': filter_equals column '{col}' not found in {p.source_csv}")


def build_plot_manifest() -> list[dict]:
    validate_plots(PLOTS)
    return [asdict(p) for p in PLOTS]


def write_plot_manifest(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MANIFEST_FILENAME
    path.write_text(json.dumps(build_plot_manifest(), indent=2), encoding="utf-8")
    return path
