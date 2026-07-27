"""Orchestrates Phase 2B: reads an existing ``run_summary_{run_id}.json``
(written by ``iaq_hfis run`` / ``iaq_hfis evaluate``) plus the derived
DuckDB, and writes every reporting artifact -- CSVs, data dictionary, plot
manifest, ``run_summary.md``, ``run_narrative.md``. A separate ``plot``
step then renders PNGs from the manifest.

Deliberately reads only already-persisted data (never recomputes) so every
artifact here is exactly as trustworthy as the run/evaluate steps that
produced its inputs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import duckdb

from iaq_hfis import plots
from iaq_hfis.config import Settings
from iaq_hfis.reporting import data_dictionary, exports, narrative, plot_manifest
from iaq_hfis.reporting import summary as summary_module


def _report_dir(settings: Settings, run_id: str) -> Path:
    return Path(settings.paths.run_summary_dir).parent / "reports" / run_id


def load_run_summary(settings: Settings, run_id: str) -> dict:
    summary_path = Path(settings.paths.run_summary_dir) / f"run_summary_{run_id}.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"no run_summary found for run_id={run_id} at {summary_path} -- run 'iaq_hfis run' first")
    return json.loads(summary_path.read_text(encoding="utf-8"))


def generate_report(settings: Settings, run_id: str, window_minutes: int | None = None) -> dict:
    """Writes every Phase 2B artifact for ``run_id`` into
    ``data/iaq_hfis/reports/{run_id}/``. Returns the paths written."""
    summary = load_run_summary(settings, run_id)
    window_minutes = window_minutes or summary.get("window_minutes") or settings.cadence.aggregation_window_minutes
    from_ts = datetime.fromisoformat(summary["computed_ts_range"][0])
    to_ts = datetime.fromisoformat(summary["computed_ts_range"][1])

    report_dir = _report_dir(settings, run_id)
    csv_dir = report_dir / "exports"

    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        csv_paths = exports.export_all(con, csv_dir, window_minutes, run_id, from_ts, to_ts)
    finally:
        con.close()

    dict_path = data_dictionary.write_data_dictionary(report_dir)
    manifest_path = plot_manifest.write_plot_manifest(report_dir)
    summary_md_path = summary_module.write_run_summary_markdown(summary, report_dir)
    narrative_path = narrative.write_run_narrative(summary, report_dir)

    return {
        "report_dir": str(report_dir),
        "csv_paths": {name: (str(path) if path else None) for name, path in csv_paths.items()},
        "data_dictionary": str(dict_path),
        "plot_manifest": str(manifest_path),
        "run_summary_md": str(summary_md_path),
        "run_narrative_md": str(narrative_path),
    }


def generate_plots(settings: Settings, run_id: str) -> dict:
    """Renders PNGs from an already-generated ``plot_manifest.json`` (run
    ``generate_report`` first)."""
    report_dir = _report_dir(settings, run_id)
    manifest_path = report_dir / plot_manifest.MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no plot_manifest.json for run_id={run_id} at {manifest_path} -- run 'iaq_hfis report --run-id {run_id}' first")

    csv_dir = report_dir / "exports"
    plots_dir = report_dir / "plots"
    rendered = plots.render_all(manifest_path, csv_dir, plots_dir)
    return {"plots_dir": str(plots_dir), "rendered": {name: (str(path) if path else None) for name, path in rendered.items()}}
