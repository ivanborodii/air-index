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
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from iaq_hfis import plots
from iaq_hfis.article_summary import write_article_summary
from iaq_hfis.config import RoomProfilesConfig, SensorSpecs, Settings
from iaq_hfis.provenance import apply_known_engagement, assess_publication_readiness, collect_parameter_provenance
from iaq_hfis.reporting import data_dictionary, exports, narrative, plot_manifest
from iaq_hfis.reporting import summary as summary_module
from iaq_hfis.reporting.provisional_assessment import PROVISIONAL_PARAMETER_ASSESSMENT_MD, build_provisional_parameter_assessment_markdown

PARAMETER_PROVENANCE_CSV = "parameter_provenance.csv"


def _report_dir(settings: Settings, pipeline_run_id: str) -> Path:
    return Path(settings.paths.run_summary_dir).parent / "reports" / pipeline_run_id


def load_run_summary(settings: Settings, pipeline_run_id: str) -> dict:
    summary_path = Path(settings.paths.run_summary_dir) / f"run_summary_{pipeline_run_id}.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"no run_summary found for pipeline_run_id={pipeline_run_id} at {summary_path} -- run 'iaq_hfis run' first")
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _write_run_summary(settings: Settings, pipeline_run_id: str, summary: dict) -> None:
    summary_path = Path(settings.paths.run_summary_dir) / f"run_summary_{pipeline_run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _write_parameter_provenance_csv(rows, report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / PARAMETER_PROVENANCE_CSV
    pd.DataFrame([r.as_dict() for r in rows]).to_csv(path, index=False)
    return path


def generate_report(settings: Settings, pipeline_run_id: str, sensor_specs: SensorSpecs, room_profiles: RoomProfilesConfig, window_minutes: int | None = None) -> dict:
    """Writes every reporting artifact for ``pipeline_run_id`` into
    ``data/iaq_hfis/reports/{pipeline_run_id}/``, scoped to exactly this
    pipeline run and its one ``selected_evaluation_run_id`` (if evaluation
    has been run). Returns the paths written.

    Also computes machine-readable parameter provenance and a
    publication_readiness assessment, persisting both back into
    ``run_summary_{pipeline_run_id}.json`` before rendering the
    Markdown/narrative from it -- the single authoritative result object
    every artifact here is generated from.
    """
    t0 = time.perf_counter()
    summary = load_run_summary(settings, pipeline_run_id)
    window_minutes = window_minutes or summary.get("window_minutes") or settings.cadence.aggregation_window_minutes
    from_ts = datetime.fromisoformat(summary["computed_ts_range"][0])
    to_ts = datetime.fromisoformat(summary["computed_ts_range"][1])
    evaluation_run_id = summary.get("selected_evaluation_run_id")

    # provisional_parameters_used was already decided authoritatively at 'run' time (pipeline.py);
    # here we only mark each catalog row's 'engaged' flag from that already-persisted list --
    # never re-derive engagement independently, which is exactly how run_summary.md/run_narrative.md
    # (reading this same top-level field) previously disagreed with publication_readiness.
    provenance = apply_known_engagement(collect_parameter_provenance(settings, sensor_specs, room_profiles), summary.get("provisional_parameters_used") or [])
    summary["publication_readiness"] = assess_publication_readiness(summary, provenance)
    _write_run_summary(settings, pipeline_run_id, summary)

    report_dir = _report_dir(settings, pipeline_run_id)
    csv_dir = report_dir / "exports"

    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        csv_paths = exports.export_all(con, csv_dir, window_minutes, pipeline_run_id, evaluation_run_id, from_ts, to_ts)
    finally:
        con.close()

    provenance_path = _write_parameter_provenance_csv(provenance, report_dir)
    dict_path = data_dictionary.write_data_dictionary(report_dir)
    manifest_path = plot_manifest.write_plot_manifest(report_dir)
    summary_md_path = summary_module.write_run_summary_markdown(summary, report_dir)
    narrative_path = narrative.write_run_narrative(summary, report_dir)
    article_md_path, article_json_path = write_article_summary(summary, report_dir)

    report_dir.mkdir(parents=True, exist_ok=True)
    assessment_path = report_dir / PROVISIONAL_PARAMETER_ASSESSMENT_MD
    assessment_path.write_text(build_provisional_parameter_assessment_markdown(provenance, summary), encoding="utf-8")

    return {
        "report_dir": str(report_dir),
        "csv_paths": {name: (str(path) if path else None) for name, path in csv_paths.items()},
        "parameter_provenance": str(provenance_path),
        "data_dictionary": str(dict_path),
        "plot_manifest": str(manifest_path),
        "run_summary_md": str(summary_md_path),
        "run_narrative_md": str(narrative_path),
        "article_results_summary": str(article_md_path),
        "article_metrics": str(article_json_path),
        "provisional_parameter_assessment": str(assessment_path),
        "generation_seconds": time.perf_counter() - t0,
    }


def generate_plots(settings: Settings, pipeline_run_id: str) -> dict:
    """Renders PNGs from an already-generated ``plot_manifest.json`` (run
    ``generate_report`` first)."""
    t0 = time.perf_counter()
    report_dir = _report_dir(settings, pipeline_run_id)
    manifest_path = report_dir / plot_manifest.MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no plot_manifest.json for pipeline_run_id={pipeline_run_id} at {manifest_path} -- run 'iaq_hfis report --pipeline-run-id {pipeline_run_id}' first")

    csv_dir = report_dir / "exports"
    plots_dir = report_dir / "plots"
    rendered = plots.render_all(manifest_path, csv_dir, plots_dir)
    return {"plots_dir": str(plots_dir), "rendered": {name: (str(path) if path else None) for name, path in rendered.items()}, "generation_seconds": time.perf_counter() - t0}
