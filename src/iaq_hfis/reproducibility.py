"""Environment/reproducibility metadata collected once per run and merged
into ``run_summary.json``: package version, interpreter/library versions,
platform/CPU info, git commit (when available), and the rule-generation
algorithm version.

This repository has no ``.git`` directory (verified: `git status` reports
"not a git repository") — ``git_commit`` is reported as ``None`` rather
than raising, matching the task spec's "record ... Git commit when
available".
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import duckdb

from iaq_hfis import __version__
from iaq_hfis.rules import RULE_GENERATION_VERSION


def get_git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def collect_environment_metadata(repo_root: Path | None = None) -> dict:
    return {
        "iaq_hfis_version": __version__,
        "python_version": platform.python_version(),
        "duckdb_version": duckdb.__version__,
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "git_commit": get_git_commit(repo_root) if repo_root is not None else None,
        "rule_generation_version": RULE_GENERATION_VERSION,
    }
