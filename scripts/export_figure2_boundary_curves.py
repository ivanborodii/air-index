#!/usr/bin/env python3
"""scripts/export_figure2_boundary_curves.py

Builds the manuscript's Figure 2 dataset -- PROPOSED_HFIS vs CRISP_CLASS_MAX
near one representative favourable-context control boundary per first-level
component (PM2.5->Aerosol, CO2->Ventilation, humidity->Microclimate) --
entirely from point-level rows already persisted by the boundary-continuity
experiment (``evaluation_continuity_grid`` in the derived DuckDB). Never
recomputes, interpolates, or reconstructs a score from aggregate metrics.

Writes, by default, into research_results/final/exports/:
    figure2_boundary_curves.csv
    figure2_boundary_curves_metadata.json

By default reads pipeline_run_id/evaluation_run_id/git_commit/config_hash
from research_results/final/manifest.json (the already-finalized, tracked
publication snapshot) so this always describes the real run that produced
it -- pass --evaluation-run-id etc. explicitly to target a different run.

This is a standalone addition to the tracked research_results/final/
snapshot, not part of the routine `iaq_hfis report` export set. Re-running
`iaq_hfis finalize` replaces research_results/final/ atomically and does not
know about this file -- re-run this script afterward to restore it.

Usage:
    python scripts/export_figure2_boundary_curves.py
    python scripts/export_figure2_boundary_curves.py --evaluation-run-id <id> --pipeline-run-id <id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import duckdb  # noqa: E402

from iaq_hfis.config import ConfigError, load_settings  # noqa: E402
from iaq_hfis.reporting.figure2_export import write_figure2_export  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "research_results" / "final" / "manifest.json"
DEFAULT_OUT_DIR = REPO_ROOT / "research_results" / "final" / "exports"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config/iaq_hfis.yaml")
    parser.add_argument("--pipeline-run-id", default=None, help="Default: read from research_results/final/manifest.json")
    parser.add_argument("--evaluation-run-id", default=None, help="Default: read from research_results/final/manifest.json")
    parser.add_argument("--git-commit", default=None, help="Default: read from research_results/final/manifest.json")
    parser.add_argument("--config-hash", default=None, help="Default: read from research_results/final/manifest.json")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    pipeline_run_id, evaluation_run_id, git_commit, config_hash = args.pipeline_run_id, args.evaluation_run_id, args.git_commit, args.config_hash
    if None in (pipeline_run_id, evaluation_run_id, git_commit, config_hash):
        if not DEFAULT_MANIFEST.is_file():
            print(f"No --pipeline-run-id/--evaluation-run-id/--git-commit/--config-hash given and {DEFAULT_MANIFEST} does not exist.", file=sys.stderr)
            return 2
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        pipeline_run_id = pipeline_run_id or manifest["pipeline_run_id"]
        evaluation_run_id = evaluation_run_id or manifest["evaluation_run_id"]
        git_commit = git_commit or manifest["git_commit"]
        config_hash = config_hash or manifest["config_hash"]

    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 2

    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        metadata = write_figure2_export(
            con=con,
            out_dir=Path(args.out_dir),
            evaluation_run_id=evaluation_run_id,
            pipeline_run_id=pipeline_run_id,
            git_commit=git_commit,
            config_hash=config_hash,
            expected_grid_points=settings.evaluation.continuity_grid_points,
        )
    except ValueError as exc:
        print(f"Figure 2 export failed:\n{exc}", file=sys.stderr)
        return 1
    finally:
        con.close()

    print(f"figure2_boundary_curves.csv: {metadata['validation']['row_count']} rows -> {Path(args.out_dir) / 'figure2_boundary_curves.csv'}")
    print(f"figure2_boundary_curves_metadata.json -> {Path(args.out_dir) / 'figure2_boundary_curves_metadata.json'}")
    print(f"validation passed: {metadata['validation']['passed']}")
    for check in metadata["validation"]["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"  {status}: {check['name']}")
    for s in metadata["selected_scenarios"]:
        print(f"  panel {s['panel']} ({s['component']}/{s['channel']}): boundary_id={s['resolved_boundary_id']} boundary_value={s['boundary_value']} [{s['selection_note']}]")

    return 0 if metadata["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
