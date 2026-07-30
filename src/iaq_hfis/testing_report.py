"""Runs the full pytest suite and records a structured report -- total,
passed, failed, errors, skipped, wall time, and the exact environment it
ran in (Python version, DuckDB version, platform) -- required before any
'finalize'/publication step (task spec section 12: "do not proceed to
publishing if any required test fails").

A separate step from `iaq_hfis finalize` deliberately: the full suite takes
tens of minutes on a Raspberry Pi 5, so running it is a conscious,
explicit action (`iaq_hfis test-report`), not something silently triggered
by every finalize call. `finalize` then reads the already-generated
`test_report.json` rather than re-running the suite itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from iaq_hfis.reproducibility import collect_environment_metadata

TEST_REPORT_JSON = "test_report.json"
TEST_REPORT_MD = "test_report.md"


def run_full_test_suite(repo_root: Path, pytest_args: list[str] | None = None) -> dict:
    """Shells out to pytest with a JUnit-XML report, parses it for
    total/passed/failed/errors/skipped, and merges in environment metadata.
    Never raises on test failure -- the caller decides what to do with
    ``ok: False`` (per the "do not proceed to publishing" requirement).

    ``pytest_args``, if given, REPLACES the default ``tests/`` target
    entirely (e.g. a specific file/``-k`` expression for a quick check) --
    it does not append to the full suite."""
    junit_path = repo_root / ".pytest_junit_report.xml"
    targets = pytest_args if pytest_args else ["tests/"]
    args = [sys.executable, "-m", "pytest", f"--junit-xml={junit_path}", "-q"] + targets

    t0 = perf_counter()
    proc = subprocess.run(args, cwd=repo_root, capture_output=True, text=True)
    wall_seconds = perf_counter() - t0

    summary: dict = {
        "total": None,
        "passed": None,
        "failed": None,
        "errors": None,
        "skipped": None,
        "wall_seconds": wall_seconds,
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "environment": collect_environment_metadata(repo_root),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(args),
        "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-40:]),
    }

    if junit_path.is_file():
        try:
            root = ET.parse(junit_path).getroot()
            suite = root if root.tag == "testsuite" else root.find("testsuite")
            if suite is not None:
                total = int(suite.get("tests", 0))
                failed = int(suite.get("failures", 0))
                errors = int(suite.get("errors", 0))
                skipped = int(suite.get("skipped", 0))
                summary.update(
                    {"total": total, "failed": failed, "errors": errors, "skipped": skipped, "passed": total - failed - errors - skipped}
                )
        finally:
            junit_path.unlink(missing_ok=True)

    return summary


def build_test_report_markdown(summary: dict) -> str:
    env = summary.get("environment") or {}
    wall = summary.get("wall_seconds")
    lines = [
        "# Test Report",
        "",
        f"**Result: {'OK' if summary.get('ok') else 'FAILED'}**",
        "",
        f"- Total: {summary.get('total')}",
        f"- Passed: {summary.get('passed')}",
        f"- Failed: {summary.get('failed')}",
        f"- Errors: {summary.get('errors')}",
        f"- Skipped: {summary.get('skipped')}",
        f"- Wall time: {f'{wall:.1f}s' if wall is not None else 'not available'}",
        f"- Python version: {env.get('python_version')}",
        f"- DuckDB version: {env.get('duckdb_version')}",
        f"- Platform: {env.get('platform')}",
        f"- Git commit: {env.get('git_commit')}",
        f"- Generated at (UTC): {summary.get('generated_at_utc')}",
        "",
        "## Command",
        "",
        f"`{summary.get('command')}`",
        "",
    ]
    if not summary.get("ok"):
        lines += ["## Last output lines", "", "```", summary.get("stdout_tail") or "", "```", ""]
    return "\n".join(lines)


def write_test_report(summary: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / TEST_REPORT_JSON
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md_path = out_dir / TEST_REPORT_MD
    md_path.write_text(build_test_report_markdown(summary), encoding="utf-8")
    return json_path, md_path
