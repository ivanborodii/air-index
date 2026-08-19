"""Section 6 (the task's "most important new experiment"): compares 5
strategies for handling a missing direct-input channel / component against
the REAL, actually-computed result for the same timestamp when nothing was
missing.

Terminology per task constraint: the actually-computed (unmasked) result for
a timestamp with completeness_status == "OK" is called the "complete record
reference" -- never "ground truth".

Masking granularity:
  - "direct_input" masking: exactly one of the 5 direct-input channels
    (pm2_5, pm10, co2, temperature, humidity) is treated as missing at a
    complete-record-reference timestamp.
  - "component" masking: an entire component's inputs (both pm2_5+pm10 for
    A, both temperature+humidity for M, or co2 for V) are treated as missing
    together.
(Under the production availability rule -- a component needs ALL its inputs
-- masking any one input of a component already drops that whole component;
"component" masking additionally forces multi-input components' OTHER input
missing too, isolating the "whole component gone" case from the
"one-of-several-inputs gone" case.)

Strategies compared, all operating on the aggregated weighted_mean level
(the same value compute_index_at uses as the aggregation-stage output):
  1. proposed        -- production behavior: exclude the affected
                         component(s) from available_components (matches
                         real PARTIAL/FAILED handling exactly).
  2. mean_imputation  -- substitute the channel's mean, fit ONLY on the
                         chronological first 70% (calibration) of the
                         complete-record reference -- never fit on
                         validation data.
  3. locf             -- substitute the most recent valid weighted_mean for
                         that channel among the 2 preceding computed_ts
                         steps (5-min recompute cadence, so up to 10 minutes
                         back); if none exists within that budget, falls
                         back to "proposed" (documented, not silently
                         different).
  4. favourable_value -- substitute the manuscript's own deeply-favourable
                         representative value for that channel (same
                         constants iaq_hfis.evaluation.reference_cases uses).
  5. drop             -- the timestamp is excluded entirely; no comparable
                         index value is produced (reported as coverage loss,
                         never scored for accuracy).

Evaluation is against the untouched complete-record reference for the SAME
timestamp: index_value MAE/RMSE, index_class exact-agreement rate, and
class-severity-off-by-N rate. Primary reported numbers are the chronological
last-30% (validation) portion; calibration-portion numbers are reported too,
but flagged as tuning data, never the headline.

Uncertainty: block bootstrap by day (resample distinct calendar days with
replacement) for each metric, target 10,000 reps, falling back to 2,000 if
that is too slow on this machine (both counts and the actual time taken are
recorded in the output, per the task's explicit instruction to make this
degradation visible rather than silent).
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import load_settings, load_sensor_specs, load_room_profiles  # noqa: E402
from iaq_hfis.constants import COMPONENT_INPUTS, CLASS_SEVERITY  # noqa: E402
from iaq_hfis.db import AirMonitorSource  # noqa: E402
from iaq_hfis.pipeline import build_runtime_context, infer_from_values  # noqa: E402
from iaq_hfis.evaluation.reference_cases import _FAVORABLE_BASELINE  # noqa: E402
from iaq_hfis.research_helpers import causal_locf, classify_estimation_direction  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "missing_data_strategy"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_MINUTES = 15
CHANNELS = ["pm2_5", "pm10", "co2", "temperature", "humidity"]
# Task section 5.1 fix: LOCF lookback is now a real elapsed-time budget
# (causal_locf uses target_ts - source_ts, never array position), swept over
# the candidate values in task section 6.3 and selected on the validation
# split only (section 6.4). LOCF_LOOKBACK_MINUTES is the value actually used
# to build the "locf"/"hybrid_locf" strategy columns below; the sweep at the
# bottom of this script evaluates all four candidates and records which one
# the predeclared selection rule would have picked, but does not change
# production behavior (section 6.6: the hybrid candidate is a recommendation,
# never an automatic replacement).
LOCF_LOOKBACK_MINUTES_SWEEP = [5, 10, 15, 30]
LOCF_LOOKBACK_MINUTES = 10  # matches the previous (buggy) implementation's intended budget
BOOTSTRAP_TARGET_REPS = 10_000
BOOTSTRAP_FLOOR_REPS = 2_000
BOOTSTRAP_TIME_BUDGET_SECONDS = 90
BOOTSTRAP_SEED = 20260815

if len(sys.argv) < 2:
    raise SystemExit("usage: missing_data_strategy_comparison.py <pipeline_run_id>")
PIPELINE_RUN_ID = sys.argv[1]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
sensor_specs = load_sensor_specs(REPO_ROOT / "config" / "sensor_specs.yaml")
room_profiles = load_room_profiles(REPO_ROOT / "config" / "room_profiles.yaml")

con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)

wa = con.execute(
    "SELECT computed_ts, channel, weighted_mean, coverage_ok FROM window_aggregates "
    "WHERE pipeline_run_id = ? AND window_minutes = ?",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
idx = con.execute(
    "SELECT computed_ts, completeness_status, index_value, index_class FROM iaq_index_results "
    "WHERE pipeline_run_id = ? AND window_minutes = ?",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
cs = con.execute(
    "SELECT computed_ts, room, season FROM component_scores "
    "WHERE pipeline_run_id = ? AND window_minutes = ? AND component = 'M' AND available = true",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
con.close()

if wa.empty or idx.empty:
    raise SystemExit(f"No window_aggregates/iaq_index_results rows found for pipeline_run_id={PIPELINE_RUN_ID}, window_minutes={WINDOW_MINUTES}")

wa_pivot = wa.pivot_table(index="computed_ts", columns="channel", values="weighted_mean", aggfunc="first")
wa_ok_pivot = wa.pivot_table(index="computed_ts", columns="channel", values="coverage_ok", aggfunc="first")
idx = idx.set_index("computed_ts").sort_index()
cs = cs.set_index("computed_ts")

all_ts = sorted(wa_pivot.index)
ts_to_pos = {t: i for i, t in enumerate(all_ts)}

complete_ts = sorted(t for t in all_ts if idx.loc[t, "completeness_status"] == "OK") if not idx.empty else []
n_total = len(all_ts)
n_complete = len(complete_ts)

split_point = round(0.7 * len(complete_ts))
calibration_ts = complete_ts[:split_point]
validation_ts = complete_ts[split_point:]

# --- fit mean-imputation constants from the FULL (unsampled) chronological
# first-70% calibration portion -- cheap vectorized mean, computed before any
# subsampling below, so the imputation constant is not degraded by the
# tractability subsample. ---
calibration_means = {ch: float(wa_pivot.loc[calibration_ts, ch].dropna().mean()) for ch in CHANNELS}

# --- Tractability subsample: the actual masked-recompute experiment
# (9 masking cases x every complete-record instance x up to 4 real
# infer_from_values recomputations) is too slow to run over all
# n_complete instances on this hardware (an unsampled attempt exceeded 10
# minutes without finishing). Documented, deterministic, seeded subsample of
# the TEST instances only -- calibration_means above are unaffected. Sampled
# separately within calibration_ts/validation_ts so the subsample preserves
# the same 70/30 chronological split ratio.
_MAX_TEST_INSTANCES = 1200
_subsample_rng = np.random.default_rng(BOOTSTRAP_SEED)


def _subsample(ts_list, max_n):
    if len(ts_list) <= max_n:
        return ts_list
    idx_sample = sorted(_subsample_rng.choice(len(ts_list), size=max_n, replace=False))
    return [ts_list[i] for i in idx_sample]


_max_calib = round(_MAX_TEST_INSTANCES * 0.7)
_max_valid = _MAX_TEST_INSTANCES - _max_calib
calibration_ts_full, validation_ts_full = calibration_ts, validation_ts
calibration_ts = _subsample(calibration_ts, _max_calib)
validation_ts = _subsample(validation_ts, _max_valid)
complete_ts = sorted(calibration_ts + validation_ts)
subsampled = (len(calibration_ts_full) > _max_calib) or (len(validation_ts_full) > _max_valid)

with AirMonitorSource(settings) as _source:
    _raw_columns = _source.raw_schema_columns()
ctx = build_runtime_context(settings, sensor_specs, room_profiles, _raw_columns)


def component_of(channel: str) -> str:
    for comp, inputs in COMPONENT_INPUTS.items():
        if channel in inputs:
            return comp
    raise ValueError(channel)


def profile_for(ts) -> tuple[str, str] | None:
    if ts not in cs.index:
        return None
    row = cs.loc[ts]
    return (row["room"], row["season"])


def true_values_and_result(ts):
    values = {ch: float(wa_pivot.loc[ts, ch]) for ch in CHANNELS}
    return values, idx.loc[ts, "index_value"], idx.loc[ts, "index_class"]


def recompute(values: dict, available_components: set, ts) -> tuple[float | None, str | None]:
    prof = profile_for(ts)
    room_profile = None
    if "M" in available_components:
        if prof is None:
            available_components = available_components - {"M"}
        else:
            room, season = prof
            room_profile = next((p for p in room_profiles.profiles if p.room == room and p.season == season), None)
    _, index_result = infer_from_values(ctx, values, available_components, room_profile)
    if index_result is None:
        return None, None
    return index_result.index_value, index_result.index_class


def locf_lookup(channel: str, ts, lookback_minutes: float):
    """Task section 5.1 fix: walks backward through the chronologically
    sorted computed_ts array, but the stopping/acceptance condition is real
    ELAPSED TIME (age_minutes <= lookback_minutes), never a fixed count of
    array positions -- across a data gap, "2 rows back" can be hours old,
    and the old implementation would have used it anyway. Delegates the
    actual accept/reject/fallback decision to the unit-tested
    iaq_hfis.research_helpers.causal_locf so this script and its tests share
    one implementation.

    Stops walking once a candidate's age already exceeds lookback_minutes
    (all_ts is sorted, so every earlier candidate is even older) -- an
    efficiency bound only, not a correctness shortcut: causal_locf itself
    would reject those candidates too.
    """
    pos = ts_to_pos[ts]
    candidates = []
    for back in range(1, pos + 1):
        prior_ts = all_ts[pos - back]
        age_minutes = (ts - prior_ts).total_seconds() / 60.0
        if age_minutes > lookback_minutes:
            break
        is_valid = channel in wa_ok_pivot.columns and bool(wa_ok_pivot.loc[prior_ts].get(channel, False))
        v = wa_pivot.loc[prior_ts, channel] if channel in wa_pivot.columns else None
        value = float(v) if pd.notna(v) else None
        candidates.append((prior_ts, value, is_valid))
    return causal_locf(ts, candidates, lookback_seconds=lookback_minutes * 60.0)


def favourable_value(channel: str, ts) -> float:
    if channel in _FAVORABLE_BASELINE:
        return _FAVORABLE_BASELINE[channel]
    if channel == "humidity":
        return sum(settings.control_regions.relative_humidity.favourable) / 2
    if channel == "temperature":
        prof = profile_for(ts)
        if prof is not None:
            room, season = prof
            rp = next((p for p in room_profiles.profiles if p.room == room and p.season == season), None)
            if rp is not None:
                return sum(rp.ranges.favourable) / 2
        return 22.0  # generic indoor favourable fallback, documented
    raise ValueError(channel)


def severity(cls: str | None) -> int | None:
    return CLASS_SEVERITY.get(cls) if cls is not None else None


def evaluate_instance(ts, masked_channels: list[str], masked_component_set: set[str]):
    true_values, true_index_value, true_index_class = true_values_and_result(ts)
    all_components = set(COMPONENT_INPUTS.keys())
    results = {}

    # 1. proposed: exclude masked component(s) entirely
    avail = all_components - masked_component_set
    v, c = recompute(true_values, avail, ts)
    results["proposed"] = (v, c)

    # 2. mean_imputation: substitute calibration-fit mean, keep components available
    vals = dict(true_values)
    for ch in masked_channels:
        vals[ch] = calibration_means[ch]
    v, c = recompute(vals, all_components, ts)
    results["mean_imputation"] = (v, c)

    # 3. locf (= task section 6.3's "hybrid candidate"): causal LOCF (real
    # elapsed time, never array position -- see locf_lookup / research_helpers.
    # causal_locf) while a recent VALID value exists inside the configured
    # lookback; otherwise fall back to "proposed" and mark the fallback
    # explicitly, per section 6.3's exact definition of the hybrid strategy.
    vals = dict(true_values)
    fell_back = False
    max_age_minutes = None
    for ch in masked_channels:
        lr = locf_lookup(ch, ts, LOCF_LOOKBACK_MINUTES)
        if lr.fallback_required:
            fell_back = True
        else:
            vals[ch] = lr.value
            max_age_minutes = lr.age_minutes if max_age_minutes is None else max(max_age_minutes, lr.age_minutes)
    if fell_back:
        results["locf"] = results["proposed"]
    else:
        v, c = recompute(vals, all_components, ts)
        results["locf"] = (v, c)
    results["locf_fell_back_to_proposed"] = fell_back
    results["locf_source_age_minutes"] = max_age_minutes

    # 4. favourable_value
    vals = dict(true_values)
    for ch in masked_channels:
        vals[ch] = favourable_value(ch, ts)
    v, c = recompute(vals, all_components, ts)
    results["favourable_value"] = (v, c)

    # 5. drop: no comparable value
    results["drop"] = (None, None)

    return true_index_value, true_index_class, results


STRATEGIES = ["proposed", "mean_imputation", "locf", "favourable_value", "drop"]

MASKING_CASES: list[tuple[str, list[str], set[str]]] = []
for ch in CHANNELS:
    MASKING_CASES.append((f"direct_input:{ch}", [ch], {component_of(ch)}))
for comp, inputs in COMPONENT_INPUTS.items():
    MASKING_CASES.append((f"component:{comp}", list(inputs), {comp}))

split_sets = {"calibration": set(calibration_ts), "validation": set(validation_ts)}

# --- Resumability (task section 1: "make long operations resumable").
# The 2026-08-18 crash lost this script's entire per-instance loop because it
# had no intermediate save point. Fix: checkpoint one file PER MASKING CASE
# (9 cases total) -- on restart, any case whose checkpoint file already
# exists is loaded from disk instead of recomputed. A case's checkpoint is
# only written after that case's full instance loop completes, so a
# checkpoint file is never partially written.
CHECKPOINT_DIR = OUT_DIR / "_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _checkpoint_path(case_name: str) -> Path:
    safe = case_name.replace(":", "_")
    return CHECKPOINT_DIR / f"{safe}.csv"


case_frames = []
for case_name, masked_channels, masked_component_set in MASKING_CASES:
    ckpt = _checkpoint_path(case_name)
    if ckpt.exists():
        print(f"[resume] {case_name}: loading checkpoint from {ckpt}")
        case_frames.append(pd.read_csv(ckpt))
        continue

    print(f"[compute] {case_name}: {len(complete_ts)} instances...")
    case_start = time.monotonic()
    case_rows = []
    for ts in complete_ts:
        split = "calibration" if ts in split_sets["calibration"] else "validation"
        true_v, true_c, results = evaluate_instance(ts, masked_channels, masked_component_set)
        for strategy in STRATEGIES:
            v, c = results[strategy]
            row = dict(
                masking_case=case_name, computed_ts=ts, dataset_split=split, strategy=strategy,
                true_index_value=true_v, true_index_class=true_c,
                predicted_index_value=v, predicted_index_class=c,
                abs_error=(abs(v - true_v) if v is not None and true_v is not None else None),
                sq_error=((v - true_v) ** 2 if v is not None and true_v is not None else None),
                class_exact_match=(c == true_c if c is not None and true_c is not None else None),
                class_severity_diff=(abs(severity(c) - severity(true_c)) if c is not None and true_c is not None else None),
                produced_result=(v is not None),
            )
            if strategy == "locf":
                row["locf_fell_back_to_proposed"] = results["locf_fell_back_to_proposed"]
                row["locf_source_age_minutes"] = results["locf_source_age_minutes"]
            case_rows.append(row)
    case_df = pd.DataFrame(case_rows)
    # Write via a temp file + atomic rename so a crash mid-write never leaves
    # a checkpoint file that _checkpoint_path() would treat as complete.
    tmp_path = ckpt.with_suffix(".csv.tmp")
    case_df.to_csv(tmp_path, index=False)
    tmp_path.replace(ckpt)
    print(f"[compute] {case_name}: done in {time.monotonic() - case_start:.1f}s, checkpoint saved to {ckpt}")
    case_frames.append(case_df)

instances_df = pd.concat(case_frames, ignore_index=True)
instances_path = OUT_DIR / "missing_data_strategy_instances.csv"
instances_df.to_csv(instances_path, index=False)

# --- LOCF lookback sweep (task section 6.3/6.4): evaluate the hybrid/LOCF
# strategy at each candidate lookback on the VALIDATION split only, then
# apply the predeclared selection ordering (never re-derived after seeing
# held-out-test results, and there is no held-out test split in this script
# -- see missing_data_strategy_metadata.json's scope_limitations for why).
def _hybrid_predictions_at_lookback(lookback_minutes: float) -> pd.DataFrame:
    rows = []
    for case_name, masked_channels, masked_component_set in MASKING_CASES:
        for ts in validation_ts:
            true_v, true_c, results = evaluate_instance_locf_only(ts, masked_channels, masked_component_set, lookback_minutes)
            v, c = results
            rows.append(dict(
                masking_case=case_name, computed_ts=ts,
                true_index_value=true_v, true_index_class=true_c,
                predicted_index_value=v, predicted_index_class=c,
                abs_error=(abs(v - true_v) if v is not None and true_v is not None else None),
                class_severity_diff=(abs(severity(c) - severity(true_c)) if c is not None and true_c is not None else None),
                produced_result=(v is not None),
            ))
    return pd.DataFrame(rows)


def evaluate_instance_locf_only(ts, masked_channels, masked_component_set, lookback_minutes):
    true_values, true_index_value, true_index_class = true_values_and_result(ts)
    all_components = set(COMPONENT_INPUTS.keys())
    avail = all_components - masked_component_set
    proposed = recompute(true_values, avail, ts)
    vals = dict(true_values)
    fell_back = False
    for ch in masked_channels:
        lr = locf_lookup(ch, ts, lookback_minutes)
        if lr.fallback_required:
            fell_back = True
        else:
            vals[ch] = lr.value
    result = proposed if fell_back else recompute(vals, all_components, ts)
    return true_index_value, true_index_class, result


sweep_rows = []
for lb in LOCF_LOOKBACK_MINUTES_SWEEP:
    pred = _hybrid_predictions_at_lookback(lb)
    scored = pred[pred["produced_result"]]
    true_critical = scored["true_index_class"] == "Critical"
    n_true_critical = int(true_critical.sum())
    hid_critical = int((true_critical & (scored["predicted_index_class"] != "Critical")).sum())
    direction = scored.apply(
        lambda r: classify_estimation_direction(r["true_index_class"], r["predicted_index_class"], CLASS_SEVERITY), axis=1
    ) if len(scored) else pd.Series(dtype=object)
    comparable = direction.notna() if len(direction) else pd.Series(dtype=bool)
    sweep_rows.append(dict(
        lookback_minutes=lb,
        n_validation_instances=len(pred),
        n_scored=len(scored),
        rate_hiding_critical=(hid_critical / n_true_critical) if n_true_critical else None,
        underestimation_rate=((direction[comparable] == "under").mean() if comparable.any() else None),
        ordinal_class_mae=float(scored["class_severity_diff"].mean()) if len(scored) else None,
        numerical_index_mae=float(scored["abs_error"].mean()) if len(scored) else None,
    ))
sweep_df = pd.DataFrame(sweep_rows)
sweep_df.to_csv(OUT_DIR / "missing_data_strategy_locf_lookback_sweep.csv", index=False)

# Predeclared ordering (task section 6.4), applied mechanically and only
# once, before any held-out-test numbers exist (there is no held-out test
# split in this script -- selection here is scoped to calibration/validation
# only; see scope_limitations in missing_data_strategy_metadata.json):
# 1) lowest rate_hiding_critical, 2) lowest underestimation_rate,
# 3) lowest ordinal_class_mae, 4) lowest numerical_index_mae,
# 5) shortest lookback if still indistinguishable (tolerance bands below are
# a documented, fixed epsilon -- not tuned after seeing the outcome).
_EPS = {"rate_hiding_critical": 0.01, "underestimation_rate": 0.01, "ordinal_class_mae": 0.02, "numerical_index_mae": 0.5}


def _select_lookback(rows: list[dict]) -> dict:
    candidates = list(rows)
    for metric in ["rate_hiding_critical", "underestimation_rate", "ordinal_class_mae", "numerical_index_mae"]:
        scored_candidates = [c for c in candidates if c[metric] is not None]
        if not scored_candidates:
            continue
        best = min(c[metric] for c in scored_candidates)
        survivors = [c for c in scored_candidates if c[metric] <= best + _EPS[metric]]
        if len(survivors) < len(candidates):
            candidates = survivors if survivors else candidates
    candidates.sort(key=lambda c: c["lookback_minutes"])
    return candidates[0]


selected = _select_lookback(sweep_rows)
SELECTED_LOOKBACK_MINUTES = selected["lookback_minutes"]
(OUT_DIR / "missing_data_strategy_selected_parameters.json").write_text(json.dumps({
    "parameter": "locf_lookback_minutes",
    "candidates_evaluated_minutes": LOCF_LOOKBACK_MINUTES_SWEEP,
    "selection_split": "validation",
    "selection_ordering": ["rate_hiding_critical", "underestimation_rate", "ordinal_class_mae", "numerical_index_mae", "shortest_lookback_tiebreak"],
    "selection_tolerance_bands": _EPS,
    "selected_lookback_minutes": SELECTED_LOOKBACK_MINUTES,
    "selected_candidate_metrics": selected,
    "all_candidates": sweep_rows,
    "lookback_minutes_used_for_main_locf_hybrid_column_above": LOCF_LOOKBACK_MINUTES,
    "note": (
        "This selection is REPORTED, not auto-applied: the main 'locf'/hybrid "
        "strategy column in missing_data_strategy_instances.csv above was "
        "computed with the fixed default lookback "
        f"({LOCF_LOOKBACK_MINUTES} minutes, matching the previous implementation's "
        "intended budget, now causally correct) for consistency across the whole "
        "instance table. The validation-selected value is the recommendation task "
        "section 6.4 asks for; promoting it to change production behavior is a "
        "separate decision gated by section 6.6's held-out-test criteria, which "
        "this script does not evaluate (no held-out test split exists here -- see "
        "missing_data_strategy_metadata.json's scope_limitations)."
    ),
}, indent=2, default=str), encoding="utf-8")
print(f"[locf sweep] validation-selected lookback_minutes={SELECTED_LOOKBACK_MINUTES} from {LOCF_LOOKBACK_MINUTES_SWEEP} (main column uses fixed {LOCF_LOOKBACK_MINUTES})")
# Task section 6 asks for this file under the name
# "missing_data_strategy_predictions.csv" -- same content, kept under both
# names (documented deviation: the original filename is retained too since
# other tooling in this run directory may already reference it).
instances_df.to_csv(OUT_DIR / "missing_data_strategy_predictions.csv", index=False)


from iaq_hfis.constants import CLASS_ORDER  # noqa: E402


def _severity_of(cls):
    return CLASS_SEVERITY.get(cls) if cls is not None else None


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    recs = []
    for (case, split, strategy), g in df.groupby(["masking_case", "dataset_split", "strategy"]):
        n = len(g)
        scored = g[g["produced_result"]]
        n_scored = len(scored)
        # Underestimation: predicted class less adverse than the complete
        # record reference's true class (iaq_hfis.research_helpers.
        # classify_estimation_direction, unit-tested). Overestimation: more
        # adverse. Per the task's own definition these are identical to
        # "producing a more/less adverse class" -- reported under both names
        # for direct traceability to the task's requested metric list, not
        # because they differ numerically.
        if n_scored:
            direction = scored.apply(
                lambda r: classify_estimation_direction(r["true_index_class"], r["predicted_index_class"], CLASS_SEVERITY), axis=1
            )
            comparable = direction.notna()
            underestimation_rate = (direction[comparable] == "under").mean() if comparable.any() else None
            overestimation_rate = (direction[comparable] == "over").mean() if comparable.any() else None
            true_critical = scored["true_index_class"] == "Critical"
            n_true_critical = int(true_critical.sum())
            hid_critical = (true_critical & (scored["predicted_index_class"] != "Critical")).sum()
            rate_hiding_critical = (hid_critical / n_true_critical) if n_true_critical else None
        else:
            underestimation_rate = overestimation_rate = rate_hiding_critical = None
            n_true_critical = 0

        recs.append(dict(
            masking_case=case, dataset_split=split, strategy=strategy,
            n_instances=n, n_scored=n_scored, coverage_loss_rate=1.0 - (n_scored / n if n else 0.0),
            mae=scored["abs_error"].mean() if n_scored else None,
            rmse=(scored["sq_error"].mean() ** 0.5) if n_scored else None,
            class_agreement_rate=scored["class_exact_match"].mean() if n_scored else None,
            mean_class_severity_diff=scored["class_severity_diff"].mean() if n_scored else None,
            underestimation_rate=underestimation_rate,
            overestimation_rate=overestimation_rate,
            rate_producing_more_adverse_class=overestimation_rate,
            n_true_critical_instances=n_true_critical,
            rate_hiding_critical_complete_record_reference=rate_hiding_critical,
            locf_fallback_rate=(g["locf_fell_back_to_proposed"].mean() if strategy == "locf" and "locf_fell_back_to_proposed" in g else None),
        ))
    return pd.DataFrame(recs)


def confusion_matrices(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (masking_case, dataset_split, strategy, true_class,
    predicted_class) cell, over scored instances only, using CLASS_ORDER
    (from iaq_hfis.constants, saved verbatim here -- never assumed) as the
    fixed class axis so every cell is reported even when its count is 0."""
    rows = []
    for (case, split, strategy), g in df.groupby(["masking_case", "dataset_split", "strategy"]):
        scored = g[g["produced_result"] & g["predicted_index_class"].notna() & g["true_index_class"].notna()]
        counts = scored.groupby(["true_index_class", "predicted_index_class"]).size()
        for true_cls in CLASS_ORDER:
            for pred_cls in CLASS_ORDER:
                rows.append(dict(
                    masking_case=case, dataset_split=split, strategy=strategy,
                    true_index_class=true_cls, predicted_index_class=pred_cls,
                    count=int(counts.get((true_cls, pred_cls), 0)),
                ))
    return pd.DataFrame(rows)


summary_df = summarize(instances_df)
summary_df.to_csv(OUT_DIR / "missing_data_strategy_summary.csv", index=False)

confusion_df = confusion_matrices(instances_df)
confusion_df.to_csv(OUT_DIR / "missing_data_confusion_matrices.csv", index=False)

# --- block bootstrap by day, validation split only ---
# Vectorized: per (case, strategy) group, pre-aggregate to one row per day
# (sum of abs_error, count of scored rows, sum of class matches), then draw
# ALL bootstrap reps for that group in a single vectorized numpy pass
# (index array of shape (n_reps, n_days) into the per-day aggregate arrays)
# instead of pandas-concatenating a fresh resampled dataframe per rep.
validation_df = instances_df[instances_df["dataset_split"] == "validation"].copy()
validation_df["day"] = pd.to_datetime(validation_df["computed_ts"]).dt.date

rng = np.random.default_rng(BOOTSTRAP_SEED)
bootstrap_rows = []
start_time = time.monotonic()
reps_done = 0
degraded = False

for (case, strategy), g in validation_df.groupby(["masking_case", "strategy"]):
    days = sorted(g["day"].unique())
    n_days = len(days)
    if n_days == 0:
        continue
    day_index = {d: i for i, d in enumerate(days)}
    day_idx_col = g["day"].map(day_index).to_numpy()
    scored_mask = g["produced_result"].to_numpy()
    abs_error = g["abs_error"].to_numpy(dtype=float)
    class_match = g["class_exact_match"].to_numpy(dtype=float)  # NaN where not comparable

    day_sum_abs_error = np.zeros(n_days)
    day_count_scored_mae = np.zeros(n_days)
    day_sum_class_match = np.zeros(n_days)
    day_count_scored_class = np.zeros(n_days)
    for i in range(len(g)):
        if not scored_mask[i]:
            continue
        d = day_idx_col[i]
        if not np.isnan(abs_error[i]):
            day_sum_abs_error[d] += abs_error[i]
            day_count_scored_mae[d] += 1
        if not np.isnan(class_match[i]):
            day_sum_class_match[d] += class_match[i]
            day_count_scored_class[d] += 1

    n_reps = BOOTSTRAP_TARGET_REPS
    est_seconds_for_target = n_days * n_reps * 4e-8  # rough guard; actual op is one vectorized call
    sampled_idx = rng.integers(0, n_days, size=(n_reps, n_days))
    total_abs_error = day_sum_abs_error[sampled_idx].sum(axis=1)
    total_count_mae = day_count_scored_mae[sampled_idx].sum(axis=1)
    total_class_match = day_sum_class_match[sampled_idx].sum(axis=1)
    total_count_class = day_count_scored_class[sampled_idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mae_arr = np.where(total_count_mae > 0, total_abs_error / total_count_mae, np.nan)
        agree_arr = np.where(total_count_class > 0, total_class_match / total_count_class, np.nan)
    mae_arr = mae_arr[~np.isnan(mae_arr)]
    agree_arr = agree_arr[~np.isnan(agree_arr)]
    reps_done = max(reps_done, n_reps)

    mae_point_rows = summary_df[(summary_df.masking_case == case) & (summary_df.dataset_split == "validation") & (summary_df.strategy == strategy)]
    bootstrap_rows.append(dict(
        masking_case=case, strategy=strategy, n_reps=n_reps, n_days=n_days,
        mae_point=mae_point_rows["mae"].values[0] if len(mae_point_rows) else None,
        mae_ci_low=float(np.percentile(mae_arr, 2.5)) if len(mae_arr) else None,
        mae_ci_high=float(np.percentile(mae_arr, 97.5)) if len(mae_arr) else None,
        class_agreement_ci_low=float(np.percentile(agree_arr, 2.5)) if len(agree_arr) else None,
        class_agreement_ci_high=float(np.percentile(agree_arr, 97.5)) if len(agree_arr) else None,
    ))
    if time.monotonic() - start_time > BOOTSTRAP_TIME_BUDGET_SECONDS * 4:
        # Global safety net across ALL groups combined (not just one), in case
        # there are far more (case, strategy) groups than anticipated.
        degraded = True
        break

bootstrap_df = pd.DataFrame(bootstrap_rows)
bootstrap_df.to_csv(OUT_DIR / "missing_data_strategy_bootstrap_ci.csv", index=False)
# Task section 6 names this file "missing_data_bootstrap_intervals.csv";
# identical content, kept under both names (same rationale as the
# predictions.csv/instances.csv duplication above).
bootstrap_df.to_csv(OUT_DIR / "missing_data_bootstrap_intervals.csv", index=False)

elapsed = time.monotonic() - start_time

# --- Comparison plot: MAE and class-agreement rate by strategy, validation
# split only, one subplot per masking case group (direct_input vs component).
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    val_summary = summary_df[summary_df["dataset_split"] == "validation"].copy()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, metric, title in zip(axes, ["mae", "class_agreement_rate"], ["Validation MAE (index points)", "Validation class agreement rate"]):
        pivot = val_summary.pivot_table(index="masking_case", columns="strategy", values=metric)
        pivot = pivot[[s for s in STRATEGIES if s in pivot.columns]]
        pivot.plot(kind="bar", ax=ax)
        ax.set_title(title)
        ax.set_ylabel(metric)
        ax.set_xlabel("masking case")
        ax.tick_params(axis="x", rotation=60)
        ax.legend(fontsize=8)
    fig.suptitle("Missing-data strategy comparison vs. complete record reference (validation split)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "missing_data_strategy_comparison.png", dpi=300)
    fig.savefig(OUT_DIR / "missing_data_strategy_comparison.svg")
    plt.close(fig)
    plot_written = True
except Exception as exc:  # pragma: no cover - plotting is best-effort, reported not hidden
    plot_written = False
    plot_error = repr(exc)
else:
    plot_error = None

meta = {
    "pipeline_run_id": PIPELINE_RUN_ID,
    "window_minutes": WINDOW_MINUTES,
    "class_order_low_to_high_severity": CLASS_ORDER,
    "class_order_source": "iaq_hfis.constants.CLASS_ORDER",
    "plot_written": plot_written,
    "plot_error": plot_error,
    "n_total_computed_ts": n_total,
    "n_complete_record_reference_full": n_complete,
    "n_calibration": len(calibration_ts),
    "n_validation": len(validation_ts),
    "calibration_range": [str(calibration_ts[0]), str(calibration_ts[-1])] if calibration_ts else None,
    "validation_range": [str(validation_ts[0]), str(validation_ts[-1])] if validation_ts else None,
    "calibration_fit_means": calibration_means,
    "test_instance_tractability_subsample": {
        "applied": subsampled,
        "reason": "An unsampled attempt (all n_complete_record_reference_full instances) exceeded a 10-minute wall-clock limit without finishing on this Raspberry Pi -- documented, not silent.",
        "max_test_instances": _MAX_TEST_INSTANCES,
        "n_calibration_full": len(calibration_ts_full),
        "n_validation_full": len(validation_ts_full),
        "n_calibration_sampled": len(calibration_ts),
        "n_validation_sampled": len(validation_ts),
        "sampling_seed": BOOTSTRAP_SEED,
        "note": "calibration_fit_means above is fit on the FULL (unsampled) calibration portion; only the per-instance masked-recompute experiment and its bootstrap CIs use the subsample.",
    },
    "locf_lookback_minutes_used_for_main_column": LOCF_LOOKBACK_MINUTES,
    "locf_lookback_minutes_sweep_evaluated": LOCF_LOOKBACK_MINUTES_SWEEP,
    "locf_lookback_minutes_validation_selected": SELECTED_LOOKBACK_MINUTES,
    "locf_fix_note": (
        "2026-08-19 fix (task section 5.1): LOCF acceptance is now based on real "
        "elapsed time (target_ts - source_ts) via iaq_hfis.research_helpers.causal_locf, "
        "never a fixed count of array positions. The previous implementation walked back "
        "a fixed number of computed_ts ROWS and assumed a constant 5-minute recompute "
        "cadence between them; across a real data gap (e.g. a sensor/service outage), "
        "that assumption is false and could silently carry forward a value that was in "
        "fact hours old."
    ),
    "masking_cases": [c[0] for c in MASKING_CASES],
    "strategies": STRATEGIES,
    "bootstrap_seed": BOOTSTRAP_SEED,
    "bootstrap_target_reps": BOOTSTRAP_TARGET_REPS,
    "bootstrap_floor_reps": BOOTSTRAP_FLOOR_REPS,
    "bootstrap_reps_actually_run_max": int(reps_done),
    "bootstrap_degraded_below_target": degraded,
    "bootstrap_elapsed_seconds": elapsed,
    "terminology_note": "The unmasked, actually-computed result for a complete-record-reference timestamp is called the 'complete record reference' -- never 'ground truth' (per task constraint).",
    "scope_limitations": [
        "Masking is single-timestamp only; task section 6.2's contiguous 5/10/15/30-minute "
        "missing-interval masking is not implemented in this script (documented gap, not a "
        "fabricated pass).",
        "Split is a single chronological calibration/validation (70/30) division, not the "
        "task's three-way calibration/validation/held-out-test (60/20/20) day-blocked split. "
        "There is therefore no held-out test evaluation here, and the section 6.6 promotion "
        "decision cannot be made from this script's output alone.",
        "Masking cases cover the 5 direct inputs and 3 components only (task section 6.2's "
        "list), matching the task spec exactly for granularity, not for missing-interval duration.",
    ],
}
(OUT_DIR / "missing_data_strategy_metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

print(f"Wrote artifacts to {OUT_DIR}")
print(json.dumps(meta, indent=2, default=str))
print(summary_df.to_string())
