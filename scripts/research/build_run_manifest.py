"""Section 14: assemble run_manifest.json for
research_results/runs/20260817_expanded_dataset_v1/ -- run identifier, UTC
data interval, row counts, dataset SHA256, git commit, config hash, seeds,
reproduce command, dependency versions, every generated artifact path, and
a SHA256 of each final artifact. Run this LAST, after every experiment
script above has produced its outputs.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

RUN_ID = "20260817_expanded_dataset_v1"
RUN_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


baseline_manifest = json.loads((RUN_DIR / "baseline" / "baseline_run_manifest.json").read_text())
dataset_report = json.loads((RUN_DIR / "snapshot" / "data_interval_verification.json").read_text())

EXCLUDE_DIRS = {"_checkpoints"}
EXCLUDE_SUFFIXES = {".duckdb", ".wal"}
EXCLUDE_NAMES = {"raw_observations_2026-06-18_to_2026-08-16.csv"}  # raw data export, hashed separately, not re-listed per-file

artifact_hashes = {}
for path in sorted(RUN_DIR.rglob("*")):
    if path.is_dir():
        continue
    if any(part in EXCLUDE_DIRS for part in path.relative_to(RUN_DIR).parts):
        continue
    if path.suffix in EXCLUDE_SUFFIXES or path.name in EXCLUDE_NAMES:
        continue
    if path.name == "run_manifest.json":
        continue
    rel = str(path.relative_to(RUN_DIR))
    artifact_hashes[rel] = {"sha256": sha256_of(path), "size_bytes": path.stat().st_size}

manifest = {
    "run_id": RUN_ID,
    "utc_data_interval": {
        "start_inclusive": "2026-06-18T00:00:00+00:00",
        "end_exclusive": "2026-08-16T00:00:00+00:00",
    },
    "selected_row_count": dataset_report["selected_row_count"],
    "selected_unique_ts_count": dataset_report["selected_unique_ts_count"],
    "dataset_csv_sha256": dataset_report["dataset_csv_sha256"],
    "frozen_full_db_snapshot_sha256": dataset_report["frozen_full_db_snapshot_sha256"],
    "git_commit_used_for_baseline_pipeline_run": baseline_manifest["git_commit_used_for_this_pipeline_run"],
    "current_git_head_at_manifest_build_time": None,  # filled by build_run_manifest's caller after this script via `git rev-parse HEAD`; left explicit here since this script itself does not commit anything
    "config_hash": baseline_manifest["config_hash_at_run_time"],
    "random_seeds_used": baseline_manifest["random_seeds_used_in_this_research_run"],
    "dependency_versions": baseline_manifest["dependency_versions"],
    "python_version": baseline_manifest["python_version"],
    "raspberry_pi_model": baseline_manifest["raspberry_pi_model"],
    "os_release": baseline_manifest["os_release"],
    "reproduce_commands": [
        "# 1. Baseline pipeline (already persisted as pipeline_run_id=7f04698725dd4f35a432ba4a0de2934f; do not rerun unless git HEAD differs from git_commit_used_for_baseline_pipeline_run above):",
        "iaq_hfis run --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 --window-minutes 15 --mode publication",
        "# 2. Section 3 snapshot + interval verification:",
        "python scripts/research/data_snapshot_and_interval_verification.py",
        "# 3. Section 4 baseline manifest:",
        "python scripts/research/baseline_run_manifest.py",
        "# 4. Section 5 Hampel sweep:",
        "python scripts/research/hampel_threshold_sweep.py",
        "# 5. Section 6 missing-data strategy comparison (resumable via _checkpoints/):",
        "python scripts/research/missing_data_strategy_comparison.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 6. Section 7 pollution/microclimate decomposition:",
        "python scripts/research/pollution_microclimate_decomposition.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 7. Evaluation run (needed for sections 8, 9):",
        "python -m iaq_hfis.cli evaluate --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 --window-minutes 15 --pipeline-run-id 7f04698725dd4f35a432ba4a0de2934f --multi-component-grid-points 101",
        "# 8. Section 8 second-level equivalence (needs the evaluation_run_id printed by step 7):",
        "python scripts/research/second_level_equivalence.py 7f04698725dd4f35a432ba4a0de2934f <EVALUATION_RUN_ID>",
        "# 9. Section 9 boundary/stability paired analysis (same evaluation_run_id):",
        "python scripts/research/boundary_stability_paired_analysis.py <EVALUATION_RUN_ID>",
        "# 10. Section 10 data-quality reason analysis:",
        "python scripts/research/data_quality_reason_analysis.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 11. Section 11 membership-function audit:",
        "python scripts/research/membership_function_audit.py",
        "# 12. Section 12 runtime profiling:",
        "python scripts/research/runtime_profiling.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 13. Tests:",
        "python -m pytest tests/ -q",
        "# 14. This manifest:",
        "python scripts/research/build_run_manifest.py",
    ],
    "generated_artifacts": artifact_hashes,
    "n_artifacts": len(artifact_hashes),
}

(RUN_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
print(f"Wrote {RUN_DIR / 'run_manifest.json'} with {len(artifact_hashes)} artifact hashes")
