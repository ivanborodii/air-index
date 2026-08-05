"""Command-line entry points for iaq_hfis.

    python -m iaq_hfis.cli run --from ... --to ...
    python -m iaq_hfis.cli evaluate --from ... --to ... --pipeline-run-id <id from 'run'>
    python -m iaq_hfis.cli report --pipeline-run-id <id>
    python -m iaq_hfis.cli plot --pipeline-run-id <id>
    python -m iaq_hfis.cli validate-artifacts --pipeline-run-id <id>
    python -m iaq_hfis.cli rebuild-db --confirm
    python -m iaq_hfis.cli test-report
    python -m iaq_hfis.cli finalize --pipeline-run-id <id> [--test-report-json test_report.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from iaq_hfis.config import ConfigError, RoomProfilesConfig, SensorSpecs, Settings, load_room_profiles, load_sensor_specs, load_settings
from iaq_hfis.db import LegacySchemaError, rebuild_derived_database
from iaq_hfis.evaluate import run_evaluation
from iaq_hfis.final_snapshot import REPO_ROOT, build_exploratory_snapshot, build_final_snapshot
from iaq_hfis.pipeline import run_pipeline
from iaq_hfis.report import generate_plots, generate_report
from iaq_hfis.testing_report import run_full_test_suite, write_test_report
from iaq_hfis.validation import ArtifactValidationError, report_dir as validation_report_dir, validate_artifacts, write_artifact_validation_report


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _load_config(args: argparse.Namespace) -> tuple[Settings, SensorSpecs, RoomProfilesConfig] | None:
    try:
        return load_settings(args.config), load_sensor_specs(args.sensor_specs), load_room_profiles(args.room_profiles)
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return None


def _add_config_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default="config/iaq_hfis.yaml")
    p.add_argument("--sensor-specs", default="config/sensor_specs.yaml")
    p.add_argument("--room-profiles", default="config/room_profiles.yaml")
    p.add_argument("--verbose", action="store_true")


def _add_range_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--from", dest="from_ts", required=True, type=_parse_ts)
    p.add_argument("--to", dest="to_ts", required=True, type=_parse_ts)
    p.add_argument("--window-minutes", type=int, default=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iaq_hfis")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Compute the index over a time range and persist results")
    _add_config_args(run_p)
    _add_range_args(run_p)
    run_p.add_argument(
        "--mode", choices=["publication", "exploratory"], default="publication",
        help="publication (default, strict): a missing DBN temperature profile aborts the whole run. "
             "exploratory: the microclimate component is omitted (never fabricated) where no profile "
             "exists; the run is tagged exploratory and can never be finalized into research_results/final.",
    )

    eval_p = sub.add_parser("evaluate", help="Run the evaluation suite over an already-computed pipeline run")
    _add_config_args(eval_p)
    _add_range_args(eval_p)
    eval_p.add_argument("--pipeline-run-id", required=True, help="Which pipeline run's persisted results to evaluate (from 'run')")
    eval_p.add_argument(
        "--multi-component-grid-points", type=int, default=None, dest="multi_component_grid_points",
        help="Override evaluation.multi_component_grid_points_per_axis for this run only (e.g. 41 for the "
             "manuscript-validation task spec's own worked example, 41^3=68,921 combinations). Defaults to "
             "the configured value (modest, since this experiment re-runs on every evaluate call).",
    )

    report_p = sub.add_parser("report", help="Generate run_summary.md, run_narrative.md, CSVs, data dictionary, and plot_manifest.json for a run")
    _add_config_args(report_p)
    report_p.add_argument("--pipeline-run-id", required=True)
    report_p.add_argument("--window-minutes", type=int, default=None)

    plot_p = sub.add_parser("plot", help="Render PNGs from an already-generated plot_manifest.json")
    _add_config_args(plot_p)
    plot_p.add_argument("--pipeline-run-id", required=True)

    validate_p = sub.add_parser("validate-artifacts", help="Cross-check every generated artifact for one pipeline run against the derived DB")
    _add_config_args(validate_p)
    validate_p.add_argument("--pipeline-run-id", required=True)

    rebuild_p = sub.add_parser("rebuild-db", help="Delete and recreate the derived database with the current schema (never touches raw/weather source databases)")
    _add_config_args(rebuild_p)
    rebuild_p.add_argument("--confirm", action="store_true", help="Required: acknowledges this deletes the derived database file")

    finalize_p = sub.add_parser("finalize", help="Build the tracked research_results/final/ publication snapshot from a validated pipeline run")
    _add_config_args(finalize_p)
    finalize_p.add_argument("--pipeline-run-id", required=True)
    finalize_p.add_argument("--test-report-json", help="Path to a test_report.json from 'test-report' -- embedded in the snapshot; refuses to finalize if it says ok=false")
    finalize_p.add_argument(
        "--exploratory", action="store_true",
        help="Build research_results/exploratory/ instead of research_results/final/ -- required for mode=exploratory pipeline runs (never eligible for research_results/final).",
    )

    test_report_p = sub.add_parser("test-report", help="Run the full pytest suite and record total/passed/failed/skipped/time/environment (required before finalize)")
    test_report_p.add_argument("--verbose", action="store_true")
    test_report_p.add_argument("--out-dir", default=".", help="Directory to write test_report.json/.md into (default: repo root)")
    test_report_p.add_argument("--pytest-args", nargs=argparse.REMAINDER, default=[], help="Extra arguments passed through to pytest")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if args.command == "rebuild-db":
        settings, _, _ = _load_config(args) or (None, None, None)
        if settings is None:
            return 2
        if not args.confirm:
            print("Refusing to rebuild without --confirm. This deletes the derived database file "
                  f"({settings.paths.derived_db_path}) and recreates it empty with the current schema. "
                  "It never touches the raw air-monitor/weather source databases.", file=sys.stderr)
            return 2
        rebuild_derived_database(settings.paths.derived_db_path)
        print(f"Rebuilt derived database at {settings.paths.derived_db_path}")
        return 0

    if args.command == "test-report":
        summary = run_full_test_suite(REPO_ROOT, pytest_args=args.pytest_args)
        json_path, md_path = write_test_report(summary, Path(args.out_dir))
        print(f"Test report written to {json_path}, {md_path}")
        print(f"  total={summary.get('total')} passed={summary.get('passed')} failed={summary.get('failed')} "
              f"errors={summary.get('errors')} skipped={summary.get('skipped')} wall={summary.get('wall_seconds'):.1f}s")
        return 0 if summary.get("ok") else 1

    loaded = _load_config(args)
    if loaded is None:
        return 2
    settings, sensor_specs, room_profiles = loaded

    if args.command == "run":
        try:
            summary = run_pipeline(settings, sensor_specs, room_profiles, args.from_ts, args.to_ts, args.window_minutes, mode=args.mode)
        except ConfigError as exc:
            # e.g. a room/season combination with no configured profile -- a data-dependent
            # configuration gap, only discoverable once the pipeline reaches that instant.
            # In publication mode this includes TEMPERATURE_PROFILE_NOT_DEFINED, which
            # correctly aborts the whole run rather than producing a partial A/V/M/I result.
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except LegacySchemaError as exc:
            print(f"Schema error:\n{exc}", file=sys.stderr)
            return 2
        print(f"Run {summary['pipeline_run_id']} (mode={summary['mode']}): {summary['status']}")
        print(f"  processed {summary['n_timestamps_processed']} timestamps over window={summary['window_minutes']}min")
        print(f"  completeness: {summary['completeness_summary']}")
        if summary["provisional_parameters_used"]:
            print(f"  provisional parameters engaged this run: {summary['provisional_parameters_used']}")
        if args.mode == "exploratory":
            print("  NOTE: exploratory mode -- this run can never be promoted into research_results/final.")
        return 0

    if args.command == "evaluate":
        try:
            summary = run_evaluation(
                settings, sensor_specs, room_profiles, args.pipeline_run_id, args.from_ts, args.to_ts, args.window_minutes,
                multi_component_grid_points_per_axis=args.multi_component_grid_points,
            )
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except LegacySchemaError as exc:
            print(f"Schema error:\n{exc}", file=sys.stderr)
            return 2
        ev = summary["evaluation"]
        print(f"Evaluation {ev['evaluation_run_id']} (pipeline_run_id={ev['pipeline_run_id']}): {ev['n_computed_ts_evaluated']} computed_ts evaluated")
        for a in ev["agreement"]:
            print(f"  agreement {a['method_a']} vs {a['method_b']}: {a['percent_agreement']}, kappa={a['cohens_kappa']}")
        for m in ev["masking"]:
            print(f"  masking ({m['method']}, >= {m['severity_threshold']}): rate={m['masking_rate']} ({m['n_masked']}/{m['n_critical_events']})")
        for method, score in ev["reference_cases"].items():
            print(f"  reference-case consistency {method}: macro_f1={score['macro_f1']}, kappa={score['cohens_kappa']} (n={score['n']})")
        print(f"  status proportions: {ev['status_proportions']}")
        if ev["warnings"]:
            print(f"  warnings: {ev['warnings']}")
        return 0

    if args.command == "report":
        try:
            result = generate_report(settings, args.pipeline_run_id, sensor_specs, room_profiles, args.window_minutes)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Report written to {result['report_dir']}")
        for name, path in result["csv_paths"].items():
            print(f"  {name}: {'written' if path else 'skipped (nothing to export)'}")
        print(f"  run_summary.md: {result['run_summary_md']}")
        print(f"  run_narrative.md: {result['run_narrative_md']}")
        print(f"  data dictionary: {result['data_dictionary']}")
        print(f"  plot manifest: {result['plot_manifest']}")
        print(f"  parameter provenance: {result['parameter_provenance']}")
        print(f"  article results summary: {result['article_results_summary']}")
        print(f"  article metrics: {result['article_metrics']}")
        print(f"  provisional parameter assessment: {result['provisional_parameter_assessment']}")
        print(f"  parameter selection: {result['parameter_selection']}")
        print(f"  manuscript readiness: {result['manuscript_readiness_json']}")
        print(f"  publication claims matrix: {result['publication_claims_matrix_csv']}")
        print(f"  generated in {result['generation_seconds']:.1f}s")
        return 0

    if args.command == "plot":
        try:
            result = generate_plots(settings, args.pipeline_run_id)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Plots written to {result['plots_dir']}")
        for name, path in result["rendered"].items():
            print(f"  {name}: {'written' if path else 'skipped (no data)'}")
        print(f"  rendered in {result['generation_seconds']:.1f}s")
        return 0

    if args.command == "validate-artifacts":
        report = validate_artifacts(settings, args.pipeline_run_id)
        for line in report.messages:
            print(line)
        json_path, md_path = write_artifact_validation_report(report, validation_report_dir(settings, args.pipeline_run_id))
        print(f"  written: {json_path}, {md_path}")
        if report.ok:
            print(f"validate-artifacts: OK ({len(report.checks_passed)} checks passed)")
            return 0
        print(f"validate-artifacts: FAILED ({len(report.violations)} violation(s), {len(report.checks_passed)} passed)", file=sys.stderr)
        return 1

    if args.command == "finalize":
        test_report_summary = None
        if args.test_report_json:
            test_report_summary = json.loads(Path(args.test_report_json).read_text(encoding="utf-8"))
            if not test_report_summary.get("ok"):
                print(
                    f"finalize refused: {args.test_report_json} reports ok=false "
                    f"({test_report_summary.get('failed')} failed, {test_report_summary.get('errors')} error(s)) -- "
                    f"do not publish with failing tests. Fix and re-run 'iaq_hfis test-report' first.",
                    file=sys.stderr,
                )
                return 1
        try:
            builder = build_exploratory_snapshot if args.exploratory else build_final_snapshot
            result = builder(settings, args.pipeline_run_id, test_report_summary=test_report_summary)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ConfigError as exc:
            print(f"finalize refused:\n{exc}", file=sys.stderr)
            return 1
        print(f"Final snapshot written to {result['final_dir']}")
        vr = result["validation_report"]
        print(f"  artifact validation: {'OK' if vr.ok else 'FAILED'} ({len(vr.checks_passed)} passed, {len(vr.violations)} violations)")
        return 0 if vr.ok else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
