#!/usr/bin/env python3
"""scripts/plot_iaq_hfis_results.py

Thin wrapper around `python -m iaq_hfis.cli plot` for readers who prefer a
plain Python entry point over the CLI module syntax. Requires a report to
already exist for the given run_id (run `iaq_hfis report --run-id <id>`
first, or use scripts/run_iaq_hfis.sh for the full pipeline).

Usage:
    python scripts/plot_iaq_hfis_results.py --run-id <run_id> \\
        [--config config/iaq_hfis.yaml]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import ConfigError, load_settings  # noqa: E402
from iaq_hfis.report import generate_plots  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", default="config/iaq_hfis.yaml")
    args = parser.parse_args()

    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 2

    try:
        result = generate_plots(settings, args.run_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Plots written to {result['plots_dir']}")
    for name, path in result["rendered"].items():
        print(f"  {name}: {'written' if path else 'skipped (no data)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
