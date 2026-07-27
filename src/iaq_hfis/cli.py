"""Command-line entry points for iaq_hfis.

    python -m iaq_hfis.cli run --from ... --to ...
    python -m iaq_hfis.cli evaluate --from ... --to ... --run-id <id from 'run'>
    python -m iaq_hfis.cli report --run-id <id>
    python -m iaq_hfis.cli plot --run-id <id>
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from iaq_hfis.config import ConfigError, RoomProfilesConfig, SensorSpecs, Settings, load_room_profiles, load_sensor_specs, load_settings
from iaq_hfis.evaluate import run_evaluation
from iaq_hfis.pipeline import run_pipeline
from iaq_hfis.report import generate_plots, generate_report


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

    eval_p = sub.add_parser("evaluate", help="Run baselines + evaluation over an already-computed time range")
    _add_config_args(eval_p)
    _add_range_args(eval_p)
    eval_p.add_argument("--run-id", default=None, help="Merge results into an existing run's run_summary.json")

    report_p = sub.add_parser("report", help="Generate run_summary.md, run_narrative.md, CSVs, data dictionary, and plot_manifest.json for a run")
    _add_config_args(report_p)
    report_p.add_argument("--run-id", required=True)
    report_p.add_argument("--window-minutes", type=int, default=None)

    plot_p = sub.add_parser("plot", help="Render PNGs from an already-generated plot_manifest.json")
    _add_config_args(plot_p)
    plot_p.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    loaded = _load_config(args)
    if loaded is None:
        return 2
    settings, sensor_specs, room_profiles = loaded

    if args.command == "run":
        try:
            summary = run_pipeline(settings, sensor_specs, room_profiles, args.from_ts, args.to_ts, args.window_minutes)
        except ConfigError as exc:
            # e.g. a room/season combination with no configured profile -- a data-dependent
            # configuration gap, only discoverable once the pipeline reaches that instant.
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        print(f"Run {summary['run_id']}: {summary['status']}")
        print(f"  processed {summary['n_timestamps_processed']} timestamps over window={summary['window_minutes']}min")
        print(f"  completeness: {summary['completeness_summary']}")
        if summary["provisional_parameters_used"]:
            print(f"  provisional parameters engaged this run: {summary['provisional_parameters_used']}")
        return 0

    if args.command == "evaluate":
        try:
            summary = run_evaluation(settings, sensor_specs, room_profiles, args.from_ts, args.to_ts, args.window_minutes, run_id=args.run_id)
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        ev = summary["evaluation"]
        print(f"Evaluation {summary['run_id']}: {ev['n_computed_ts_evaluated']} computed_ts evaluated")
        for a in ev["agreement"]:
            print(f"  agreement {a['method_a']} vs {a['method_b']}: {a['percent_agreement']}, kappa={a['cohens_kappa']}")
        for m in ev["masking"]:
            print(f"  masking ({m['method']}, >= {m['severity_threshold']}): rate={m['masking_rate']} ({m['n_masked']}/{m['n_critical_events']})")
        for method, score in ev["ground_truth"].items():
            print(f"  ground truth {method}: macro_f1={score['macro_f1']}, kappa={score['cohens_kappa']} (n={score['n']})")
        print(f"  status proportions: {ev['status_proportions']}")
        return 0

    if args.command == "report":
        try:
            result = generate_report(settings, args.run_id, args.window_minutes)
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
        return 0

    if args.command == "plot":
        try:
            result = generate_plots(settings, args.run_id)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Plots written to {result['plots_dir']}")
        for name, path in result["rendered"].items():
            print(f"  {name}: {'written' if path else 'skipped (no data)'}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
