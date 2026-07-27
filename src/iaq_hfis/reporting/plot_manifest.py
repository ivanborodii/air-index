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


PLOTS: list[PlotSpec] = [
    PlotSpec(
        id="index_timeseries",
        title="IAQ Index Over Time",
        source_csv=exports.INDEX_TIMESERIES,
        plot_type="line",
        x="computed_ts",
        y=["index_value"],
        description="PROPOSED-HFIS index value over the computed range. Shade/annotate the 25/50/75 class boundaries.",
    ),
    PlotSpec(
        id="method_comparison",
        title="PROPOSED-HFIS vs CRISP-MAX vs WEIGHTED-MEAN",
        source_csv=exports.METHOD_COMPARISON,
        plot_type="line",
        x="computed_ts",
        y=["proposed_index_value", "crisp_max_index_value", "weighted_mean_index_value"],
        description="Three index series over the same computed_ts range -- shows where methods diverge.",
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
        title="Stability: Class Outcomes Under Perturbation",
        source_csv=exports.STABILITY_TRIALS,
        plot_type="histogram",
        x="trial_class",
        description="Count of perturbation trials landing in each class; compare against the baseline_class from run_summary.json.",
    ),
    PlotSpec(
        id="sensitivity_window",
        title="Sensitivity to Window Duration",
        source_csv=exports.SENSITIVITY_WINDOW,
        plot_type="line",
        x="value",
        y=["index_value"],
        description="Index value at each manuscript-specified window size (5/15/30/60 min).",
    ),
    PlotSpec(
        id="sensitivity_coverage",
        title="Sensitivity to Coverage Threshold",
        source_csv=exports.SENSITIVITY_COVERAGE,
        plot_type="line",
        x="value",
        y=["index_value"],
        description="Index value at each manuscript-specified coverage threshold (0.70/0.80/0.90).",
    ),
    PlotSpec(
        id="masking_rate",
        title="Masking Rate: CRISP-MAX vs WEIGHTED-MEAN",
        source_csv=exports.MASKING_SUMMARY,
        plot_type="bar",
        x="method",
        y=["masking_rate"],
        description="Fraction of critical-component events hidden by each baseline's aggregation.",
    ),
    PlotSpec(
        id="ground_truth_scores",
        title="Ground-Truth Macro-F1 by Method",
        source_csv=exports.GROUND_TRUTH_SUMMARY,
        plot_type="bar",
        x="method",
        y=["macro_f1"],
        description="Macro-F1 against the synthetic boundary-adjacent ground truth, one bar per method.",
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


def build_plot_manifest() -> list[dict]:
    validate_plots(PLOTS)
    return [asdict(p) for p in PLOTS]


def write_plot_manifest(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MANIFEST_FILENAME
    path.write_text(json.dumps(build_plot_manifest(), indent=2), encoding="utf-8")
    return path
