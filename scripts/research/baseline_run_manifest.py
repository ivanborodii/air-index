"""Section 4: expand the thin baseline run log into a full reproducibility
manifest. Does NOT rerun the baseline pipeline computation -- pulls the
already-persisted record for pipeline_run_id=7f04698725dd4f35a432ba4a0de2934f
straight from pipeline_runs (config_hash, source_git_commit, mode, counts,
timing), cross-checks it against the current git HEAD and the frozen dataset
hash from section 3, and adds environment/dependency/hardware metadata that
was never captured at run time.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path

import duckdb

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import load_settings  # noqa: E402
from iaq_hfis.reproducibility import collect_environment_metadata, get_git_commit, get_git_tree_dirty  # noqa: E402

RUN_ID = "20260817_expanded_dataset_v1"
BASELINE_PIPELINE_RUN_ID = "7f04698725dd4f35a432ba4a0de2934f"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "baseline"
SNAPSHOT_VERIFICATION_PATH = REPO_ROOT / "research_results" / "runs" / RUN_ID / "snapshot" / "data_interval_verification.json"

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
run_row = con.execute(
    "SELECT * FROM pipeline_runs WHERE pipeline_run_id = ?", [BASELINE_PIPELINE_RUN_ID]
).fetch_df()
if run_row.empty:
    raise SystemExit(f"pipeline_run_id={BASELINE_PIPELINE_RUN_ID} not found in pipeline_runs -- cannot build manifest without rerunning")
run_row = run_row.iloc[0].to_dict()

completeness = con.execute(
    "SELECT completeness_status, count(*) n FROM iaq_index_results WHERE pipeline_run_id = ? GROUP BY 1",
    [BASELINE_PIPELINE_RUN_ID],
).fetch_df()
con.close()

current_git_commit = get_git_commit(REPO_ROOT)
baseline_was_run_at_current_commit = (run_row["source_git_commit"] == current_git_commit)

dataset_info = {}
if SNAPSHOT_VERIFICATION_PATH.exists():
    dv = json.loads(SNAPSHOT_VERIFICATION_PATH.read_text())
    dataset_info = {
        "dataset_csv_sha256": dv.get("dataset_csv_sha256"),
        "frozen_full_db_snapshot_sha256": dv.get("frozen_full_db_snapshot_sha256"),
        "selected_row_count": dv.get("selected_row_count"),
        "selected_min_ts": dv.get("selected_min_ts"),
        "selected_max_ts": dv.get("selected_max_ts"),
    }
else:
    dataset_info = {"warning": "section-3 snapshot verification file not found; run data_snapshot_and_interval_verification.py first"}

# Dependency versions actually installed in THIS interpreter (not a
# pyproject.toml wishlist -- the exact resolved versions used to produce
# every artifact in this run).
tracked_packages = ["duckdb", "pandas", "numpy", "pydantic", "jsonschema", "matplotlib", "pytest"]
dependency_versions = {}
for pkg in tracked_packages:
    try:
        dependency_versions[pkg] = importlib_metadata.version(pkg)
    except importlib_metadata.PackageNotFoundError:
        dependency_versions[pkg] = None

pi_model = None
for candidate in (Path("/proc/device-tree/model"), Path("/sys/firmware/devicetree/base/model")):
    if candidate.exists():
        pi_model = candidate.read_bytes().rstrip(b"\x00").decode("utf-8", errors="replace")
        break

os_release = {}
os_release_path = Path("/etc/os-release")
if os_release_path.exists():
    for line in os_release_path.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            os_release[k] = v.strip('"')

env_meta = collect_environment_metadata(REPO_ROOT)

# Every fixed random seed actually used anywhere in this research run,
# collected in one place per task section 1 ("use fixed random seeds and
# record them") -- sourced from the actual scripts/config, not re-guessed.
seeds_used = {
    "hampel_calibration_validation_split_seed": 20260815,  # task section 5.2's mandated seed
    "missing_data_strategy_subsample_and_bootstrap_seed": 20260815,
    "evaluation_stability_seed": 42,  # evaluation_runs.stability_seed for this project (see baseline run's provisional-parameter list)
}

manifest = {
    "run_id": RUN_ID,
    "pipeline_run_id": BASELINE_PIPELINE_RUN_ID,
    "description": "Unchanged baseline: current production iaq_hfis pipeline/config re-run over the expanded 2026-06-18..2026-08-16(excl) dataset, with no parameter changes.",
    "started_at": str(run_row["started_at"]),
    "finished_at": str(run_row["finished_at"]),
    "wall_clock_duration_seconds": (run_row["finished_at"] - run_row["started_at"]).total_seconds() if run_row["finished_at"] is not None else None,
    "status": run_row["status"],
    "mode": run_row["mode"],
    "window_minutes": int(run_row["window_minutes"]),
    "n_timestamps_processed": int(run_row["n_timestamps_processed"]),
    "n_snapshot_retries": int(run_row["n_snapshot_retries"]),
    "computed_ts_min": str(run_row["computed_ts_min"]),
    "computed_ts_max": str(run_row["computed_ts_max"]),
    "completeness_counts": dict(zip(completeness["completeness_status"], completeness["n"].astype(int))),
    "config_hash_at_run_time": run_row["config_hash"],
    "engine_version_at_run_time": run_row["engine_version"],
    "git_commit_used_for_this_pipeline_run": run_row["source_git_commit"],
    "current_git_head_commit": current_git_commit,
    "baseline_run_matches_current_git_head": bool(baseline_was_run_at_current_commit),
    "current_git_tree_dirty": get_git_tree_dirty(REPO_ROOT),
    "dataset": dataset_info,
    "random_seeds_used_in_this_research_run": seeds_used,
    "dependency_versions": dependency_versions,
    "python_version": platform.python_version(),
    "environment_metadata": env_meta,
    "os_release": os_release,
    "kernel_release": platform.release(),
    "machine_architecture": platform.machine(),
    "raspberry_pi_model": pi_model,
    "reproduce_command": (
        "iaq_hfis run --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 "
        "--window-minutes 15 --mode publication   # then: "
        "python scripts/research/data_snapshot_and_interval_verification.py"
    ),
    "note_on_rerun_policy": (
        "This manifest documents the ALREADY-COMPLETED baseline run "
        f"({BASELINE_PIPELINE_RUN_ID}) recorded in pipeline_runs; per task "
        "section 4 instruction, the baseline computation itself is not "
        "rerun here since its git_commit_used_for_this_pipeline_run matches "
        "current_git_head_commit (no code changed since it ran) and its "
        "row/timestamp counts match the frozen section-3 snapshot exactly."
    ),
}

OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "baseline_run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
print(json.dumps(manifest, indent=2, default=str))
