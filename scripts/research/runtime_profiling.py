"""Section 12: per-stage runtime/resource profiling, HFIS vs
FUZZY_COMPONENT_MAX, over up to 2000 real complete-record-reference
timestamps from the expanded dataset. 1 warmup rep (discarded) + 5 timed
reps, per the task's exact protocol.

Stages measured (all on the same real weighted_means, same profile):
  stage1_membership_and_component_inference -- shared prerequisite for
      every method (membership degrees + first-level Mamdani inference per
      component); duplicated here read-only from
      iaq_hfis.pipeline.infer_from_values's own loop, NOT modifying
      production code.
  stage2_hfis_second_level  -- ctx.engine.infer_index (PROPOSED_HFIS only)
  stage2_fuzzy_component_max -- iaq_hfis.baselines.fuzzy_component_max
"""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path

import duckdb
import numpy as np

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis import membership  # noqa: E402
from iaq_hfis.baselines import fuzzy_component_max  # noqa: E402
from iaq_hfis.config import load_settings, load_sensor_specs, load_room_profiles  # noqa: E402
from iaq_hfis.db import AirMonitorSource  # noqa: E402
from iaq_hfis.pipeline import build_runtime_context  # noqa: E402

RUN_ID = "20260817_expanded_dataset_v1"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "runtime_profiling"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOW_MINUTES = 15
MAX_TIMESTAMPS = 2000
N_WARMUP = 1
N_REPS = 5
SEED = 20260815

if len(sys.argv) < 2:
    raise SystemExit("usage: runtime_profiling.py <pipeline_run_id>")
PIPELINE_RUN_ID = sys.argv[1]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
sensor_specs = load_sensor_specs(REPO_ROOT / "config" / "sensor_specs.yaml")
room_profiles = load_room_profiles(REPO_ROOT / "config" / "room_profiles.yaml")

con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
wa = con.execute(
    "SELECT computed_ts, channel, weighted_mean FROM window_aggregates WHERE pipeline_run_id = ? AND window_minutes = ?",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
idx = con.execute(
    "SELECT computed_ts FROM iaq_index_results WHERE pipeline_run_id = ? AND window_minutes = ? AND completeness_status = 'OK'",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
cs = con.execute(
    "SELECT computed_ts, room, season FROM component_scores WHERE pipeline_run_id = ? AND window_minutes = ? AND component = 'M' AND available = true",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
con.close()

wa_pivot = wa.pivot_table(index="computed_ts", columns="channel", values="weighted_mean", aggfunc="first")
cs_idx = cs.set_index("computed_ts")
ok_ts = sorted(idx["computed_ts"])

rng = np.random.default_rng(SEED)
if len(ok_ts) > MAX_TIMESTAMPS:
    chosen = sorted(rng.choice(len(ok_ts), size=MAX_TIMESTAMPS, replace=False))
    ok_ts = [ok_ts[i] for i in chosen]

with AirMonitorSource(settings) as _source:
    _raw_columns = _source.raw_schema_columns()
ctx = build_runtime_context(settings, sensor_specs, room_profiles, _raw_columns)

instances = []
for ts in ok_ts:
    if ts not in cs_idx.index:
        continue
    room, season = cs_idx.loc[ts, "room"], cs_idx.loc[ts, "season"]
    profile = next((p for p in room_profiles.profiles if p.room == room and p.season == season), None)
    if profile is None:
        continue
    values = {ch: float(wa_pivot.loc[ts, ch]) for ch in ("pm2_5", "pm10", "co2", "temperature", "humidity")}
    instances.append((ts, values, profile))

from iaq_hfis.constants import COMPONENT_INPUTS


def stage1(values, profile):
    component_results = {}
    for component, inputs in COMPONENT_INPUTS.items():
        input_memberships = {}
        for ch in inputs:
            shapes = ctx.temperature_shapes_by_profile[(profile.room, profile.season)] if ch == "temperature" else ctx.static_shapes["relative_humidity" if ch == "humidity" else ch]
            input_memberships[ch] = membership.evaluate_memberships(values[ch], shapes)
        component_results[component] = ctx.engine.infer_component(component, input_memberships)
    return component_results


def stage2_hfis(component_results):
    component_degrees = {c: r.class_degrees for c, r in component_results.items()}
    component_crisp_scores = {c: r.crisp_score for c, r in component_results.items()}
    return ctx.engine.infer_index(component_degrees, set(component_results.keys()), component_crisp_scores, ctx.settings.membership.dominant_component_tie_tolerance)


def stage2_fcm(component_results):
    scores = {c: r.crisp_score for c, r in component_results.items()}
    return fuzzy_component_max(scores)


def time_stage(fn, n_reps):
    times = []
    for _ in range(n_reps):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return times


def run_full_pass(method: str):
    for ts, values, profile in instances:
        component_results = stage1(values, profile)
        if method == "hfis":
            stage2_hfis(component_results)
        else:
            stage2_fcm(component_results)


results = {}
for method in ("hfis", "fuzzy_component_max"):
    for _ in range(N_WARMUP):
        run_full_pass(method)
    rep_times = []
    peak_mem_bytes = []
    for _ in range(N_REPS):
        tracemalloc.start()
        t0 = time.perf_counter()
        run_full_pass(method)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rep_times.append(elapsed)
        peak_mem_bytes.append(peak)
    results[method] = {
        "n_timestamps": len(instances),
        "rep_seconds": rep_times,
        "mean_seconds": float(np.mean(rep_times)),
        "median_seconds": float(np.median(rep_times)),
        "std_seconds": float(np.std(rep_times)),
        "seconds_per_timestamp_mean": float(np.mean(rep_times)) / len(instances) if instances else None,
        "peak_memory_bytes_per_rep": peak_mem_bytes,
        "peak_memory_bytes_mean": float(np.mean(peak_mem_bytes)),
    }

# stage-level split (stage1 shared, stage2 per-method), 1 warmup + 5 reps each, on same instance set
stage_results = {}
component_results_cache = [stage1(values, profile) for _, values, profile in instances]  # warmup + reuse
stage1_times = time_stage(lambda: [stage1(values, profile) for _, values, profile in instances], N_REPS)
stage2_hfis_times = time_stage(lambda: [stage2_hfis(cr) for cr in component_results_cache], N_REPS)
stage2_fcm_times = time_stage(lambda: [stage2_fcm(cr) for cr in component_results_cache], N_REPS)
stage_results = {
    "stage1_membership_and_component_inference": {"rep_seconds": stage1_times, "mean_seconds": float(np.mean(stage1_times))},
    "stage2_hfis_second_level": {"rep_seconds": stage2_hfis_times, "mean_seconds": float(np.mean(stage2_hfis_times))},
    "stage2_fuzzy_component_max": {"rep_seconds": stage2_fcm_times, "mean_seconds": float(np.mean(stage2_fcm_times))},
}

report = {
    "pipeline_run_id": PIPELINE_RUN_ID,
    "n_timestamps_profiled": len(instances),
    "n_warmup_reps": N_WARMUP,
    "n_timed_reps": N_REPS,
    "seed": SEED,
    "full_pass_by_method": results,
    "stage_level_timing": stage_results,
    "note": "Timed on the actual development/production machine this script ran on; not a controlled benchmark environment. seconds_per_timestamp figures are indicative, not hardware-independent.",
}
(OUT_DIR / "runtime_profiling_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print(f"Wrote artifacts to {OUT_DIR}")
print(json.dumps(report, indent=2, default=str))
