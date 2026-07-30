"""Renders PNGs from ``plot_manifest.json`` and the exported CSVs.

Reads only from the CSVs already written by
:mod:`iaq_hfis.reporting.exports` -- never recomputes from the database --
so a plot is only ever as trustworthy as its already-validated export.
Headless (``Agg`` backend), matching the existing pattern in
``air-monitor/scripts/send_daily_report.py``.

A plot whose source CSV is missing (the export legitimately had nothing to
write -- e.g. no masking events this run) is SKIPPED with a logged,
explained reason, never rendered as a misleading empty chart.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)


def _plot_line_or_scatter(ax, df: pd.DataFrame, spec: dict) -> None:
    kind = "line" if spec["plot_type"] == "line" else None
    if spec["group_by"]:
        for key, group in df.groupby(spec["group_by"]):
            group = group.sort_values(spec["x"])
            for y in spec["y"]:
                ax.plot(group[spec["x"]], group[y], label=f"{key}", marker="o" if spec["plot_type"] == "scatter" else None)
    else:
        df = df.sort_values(spec["x"])
        for y in spec["y"]:
            ax.plot(df[spec["x"]], df[y], label=y, marker="o" if spec["plot_type"] == "scatter" else None)
    ax.legend()


def _plot_bar(ax, df: pd.DataFrame, spec: dict) -> None:
    x = df[spec["x"]].astype(str)
    width = 0.8 / max(len(spec["y"]), 1)
    for i, y in enumerate(spec["y"]):
        offsets = [xi + i * width for xi in range(len(x))]
        ax.bar(offsets, df[y], width=width, label=y)
    ax.set_xticks(range(len(x)))
    ax.set_xticklabels(x, rotation=30, ha="right")
    ax.legend()


def _plot_histogram(ax, df: pd.DataFrame, spec: dict) -> None:
    if spec.get("group_by"):
        categories = sorted(df[spec["x"]].dropna().unique().tolist(), key=str)
        width = 0.8 / max(df[spec["group_by"]].nunique(), 1)
        for i, (key, group) in enumerate(df.groupby(spec["group_by"])):
            counts = group[spec["x"]].value_counts().reindex(categories, fill_value=0)
            offsets = [xi + i * width for xi in range(len(categories))]
            ax.bar(offsets, counts.values, width=width, label=str(key))
        ax.set_xticks(range(len(categories)))
        ax.set_xticklabels([str(c) for c in categories], rotation=30, ha="right")
        ax.legend()
    else:
        counts = df[spec["x"]].value_counts().sort_index()
        ax.bar(counts.index.astype(str), counts.values)


def render_plot(spec: dict, csv_dir: Path, out_dir: Path) -> Path | None:
    csv_path = csv_dir / spec["source_csv"]
    if not csv_path.is_file():
        logger.info("skipping plot '%s': source CSV %s was not exported this run (nothing to show)", spec["id"], spec["source_csv"])
        return None

    df = pd.read_csv(csv_path)
    if df.empty:
        logger.info("skipping plot '%s': %s has no rows this run", spec["id"], spec["source_csv"])
        return None

    if spec.get("filter_equals"):
        for col, value in spec["filter_equals"].items():
            df = df[df[col] == value]
        if df.empty:
            logger.info("skipping plot '%s': no rows match filter %s in %s", spec["id"], spec["filter_equals"], spec["source_csv"])
            return None

    if spec["y"] and all(df[y].isna().all() for y in spec["y"]):
        # e.g. masking_rate is null for every row when n_critical_events=0 this run --
        # a bar/line chart of all-NaN values renders as a misleading "all zero" chart,
        # not an honest "not applicable" one, so skip it with a clear reason instead.
        logger.info("skipping plot '%s': %s has rows but every y-column (%s) is null this run -- nothing to show, not zero", spec["id"], spec["source_csv"], spec["y"])
        return None

    if spec["x"].endswith("_ts") or spec["x"].endswith("_time"):
        df[spec["x"]] = pd.to_datetime(df[spec["x"]])

    fig, ax = plt.subplots(figsize=(9, 5))
    try:
        if spec["plot_type"] in ("line", "scatter"):
            _plot_line_or_scatter(ax, df, spec)
        elif spec["plot_type"] == "bar":
            _plot_bar(ax, df, spec)
        elif spec["plot_type"] == "histogram":
            _plot_histogram(ax, df, spec)
        else:
            raise ValueError(f"unknown plot_type '{spec['plot_type']}' for plot '{spec['id']}'")

        ax.set_title(spec["title"])
        ax.set_xlabel(spec["x"])
        if spec["plot_type"] in ("line", "scatter") and pd.api.types.is_datetime64_any_dtype(df[spec["x"]]):
            fig.autofmt_xdate(rotation=30)
        fig.tight_layout()

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{spec['id']}.png"
        fig.savefig(out_path, dpi=120)
        return out_path
    finally:
        plt.close(fig)


def render_all(manifest_path: Path, csv_dir: Path, out_dir: Path) -> dict[str, Path | None]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {spec["id"]: render_plot(spec, csv_dir, out_dir) for spec in manifest}
