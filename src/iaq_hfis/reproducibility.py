"""Environment/reproducibility metadata collected once per run and merged
into ``run_summary.json``: package version, interpreter/library versions,
platform/CPU info, git commit (when available), and the rule-generation
algorithm version.

``git_commit`` is ``None`` when ``repo_root`` is not inside a git working
tree (e.g. `git rev-parse` fails) rather than raising.
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


def get_git_tree_dirty(repo_root: Path) -> bool | None:
    """``True`` if the working tree has uncommitted changes (tracked or
    untracked), ``False`` if clean, ``None`` if git status could not be
    determined (e.g. not a git working tree)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(repo_root), capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return len(result.stdout.strip()) > 0


def collect_environment_metadata(repo_root: Path | None = None) -> dict:
    return {
        "iaq_hfis_version": __version__,
        "python_version": platform.python_version(),
        "duckdb_version": duckdb.__version__,
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "git_commit": get_git_commit(repo_root) if repo_root is not None else None,
        "git_tree_dirty": get_git_tree_dirty(repo_root) if repo_root is not None else None,
        "rule_generation_version": RULE_GENERATION_VERSION,
    }
