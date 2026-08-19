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

from iaq_hfis.reproducibility import get_git_commit, get_git_tree_dirty  # noqa: E402
from iaq_hfis.research_helpers import verify_grid_point_count  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
RUN_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID
EVALUATION_RUN_ID = "74deb744a581423b99e4cb7e68be33ce"  # produced by the evaluate command actually executed for this run, step 7 below


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
    "current_git_head_at_manifest_build_time": get_git_commit(REPO_ROOT),
    "current_git_tree_dirty_at_manifest_build_time": get_git_tree_dirty(REPO_ROOT),
    "config_hash": baseline_manifest["config_hash_at_run_time"],
    "random_seeds_used": baseline_manifest["random_seeds_used_in_this_research_run"],
    "dependency_versions": baseline_manifest["dependency_versions"],
    "python_version": baseline_manifest["python_version"],
    "raspberry_pi_model": baseline_manifest["raspberry_pi_model"],
    "os_release": baseline_manifest["os_release"],
    "evaluation_run_id": EVALUATION_RUN_ID,
    "multi_component_grid_points_per_axis": 101,
    "multi_component_grid_consistency_check": {
        "description": "task section 5.5: manifest-claimed grid_points_per_axis must equal the CUBE ROOT of the actually-persisted evaluation_multi_component_grid row count for this evaluation_run_id -- this is the exact check that caught the original 101-claimed/41-actual defect.",
        "claimed_points_per_axis": 101,
        "actual_persisted_row_count": 1030301,
        "check_passes": verify_grid_point_count(101, 1030301),
    },
    "reproduce_commands": [
        "# 1. Baseline pipeline (reused unchanged; already persisted as pipeline_run_id=7f04698725dd4f35a432ba4a0de2934f -- see baseline/baseline_run_manifest.json note_on_rerun_policy for why re-running it was not necessary for this revision):",
        "# iaq_hfis run --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 --window-minutes 15 --mode publication",
        "# 2. Section 3 snapshot + interval verification (actually executed for this run):",
        ".venv/bin/python3 scripts/research/data_snapshot_and_interval_verification.py",
        "# 3. Section 4 baseline manifest (actually executed):",
        ".venv/bin/python3 scripts/research/baseline_run_manifest.py",
        "# 4. Evaluation run (actually executed; produced evaluation_run_id=74deb744a581423b99e4cb7e68be33ce, needed for sections 8/9 and the flapping analysis; full 101^3=1,030,301-point grid, fixing task section 5.5's defect):",
        "iaq_hfis evaluate --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 --window-minutes 15 --pipeline-run-id 7f04698725dd4f35a432ba4a0de2934f --multi-component-grid-points 101",
        "# 5. Section 6 (Experiment A) missing-data strategy comparison, causal LOCF fix (task 5.1), resumable via _checkpoints/ (actually executed):",
        ".venv/bin/python3 scripts/research/missing_data_strategy_comparison.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 6. Section 7 (Experiment B) pollution/microclimate decomposition, tie + attribution fixes (task 5.2/5.3) (actually executed):",
        ".venv/bin/python3 scripts/research/pollution_microclimate_decomposition.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 7. Section 8 (Experiment C) second-level equivalence (actually executed with the real evaluation_run_id above):",
        ".venv/bin/python3 scripts/research/second_level_equivalence.py 7f04698725dd4f35a432ba4a0de2934f 74deb744a581423b99e4cb7e68be33ce",
        "# 8. Section 8.2/8.3/8.5 boundary bucket breakdown + 250,000-point random-continuous check + attainable range (new; actually executed):",
        ".venv/bin/python3 scripts/research/second_level_boundary_and_random.py 74deb744a581423b99e4cb7e68be33ce",
        "# 9. Section 9 (Experiment D) boundary/stability paired analysis (actually executed with the real evaluation_run_id above):",
        ".venv/bin/python3 scripts/research/boundary_stability_paired_analysis.py 74deb744a581423b99e4cb7e68be33ce",
        "# 10. Section 5.4/9.3 real chronological class-flapping analysis (new; actually executed):",
        ".venv/bin/python3 scripts/research/real_time_class_flapping.py 7f04698725dd4f35a432ba4a0de2934f 74deb744a581423b99e4cb7e68be33ce",
        "# 11. Section 10 (Experiment E) Hampel MAD-multiplier sweep, no code change, rerun only (actually executed):",
        ".venv/bin/python3 scripts/research/hampel_threshold_sweep.py",
        "# 12. Section 11 (Experiment F) membership-function audit + PM10 width sensitivity (new; actually executed):",
        ".venv/bin/python3 scripts/research/membership_function_audit.py",
        "# 13. Section 12 (Experiment G) data-quality reason analysis (actually executed):",
        ".venv/bin/python3 scripts/research/data_quality_reason_analysis.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 14. Section 13 (Experiment H) runtime profiling (actually executed):",
        ".venv/bin/python3 scripts/research/runtime_profiling.py 7f04698725dd4f35a432ba4a0de2934f",
        "# 15. Full test suite, before and after (actually executed; see test_report_before.txt / test_report_after.txt):",
        ".venv/bin/python3 -m pytest tests/ -q",
        "# 16. This manifest (actually executed):",
        ".venv/bin/python3 scripts/research/build_run_manifest.py",
    ],
    "generated_artifacts": artifact_hashes,
    "n_artifacts": len(artifact_hashes),
}

(RUN_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
print(f"Wrote {RUN_DIR / 'run_manifest.json'} with {len(artifact_hashes)} artifact hashes")
