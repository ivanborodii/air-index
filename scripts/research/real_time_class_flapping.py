"""Task sections 5.4 / 9.3: REAL chronological class-flapping analysis.

Replaces the previous "class flapping" artifact
(stability_class_flapping_by_point.csv, in boundary_stability_paired_analysis.py),
which counted transitions across an ARBITRARY PERTURBATION-TRIAL ORDER at a
single fixed sample point -- trial_index has no relationship whatsoever to
real elapsed sensor time, so that number was never a temporal flapping rate.

This script instead uses the REAL chronological computed_ts series (every
persisted timestamp, all four methods: PROPOSED_HFIS from iaq_index_results,
FUZZY_COMPONENT_MAX / CRISP_CLASS_MAX / WEIGHTED_MEAN from baseline_results,
already computed by `iaq_hfis evaluate`). Two real timestamps are only
treated as "consecutive" (able to form a transition, a dwell-time run, or
part of an A-B-A reversal triple) when the elapsed time between them is
<= MAX_GAP_MINUTES -- a genuine multi-hour pipeline outage never counts as
one continuous run, regardless of how close the two rows are in array
position (iaq_hfis.research_helpers.is_chronologically_consecutive).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import load_settings  # noqa: E402
from iaq_hfis.constants import CLASS_ORDER  # noqa: E402
from iaq_hfis.research_helpers import (  # noqa: E402
    classify_class_transition,
    is_aba_reversal,
    is_chronologically_consecutive,
)

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "real_time_class_flapping"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOW_MINUTES = 15
MAX_GAP_MINUTES = 10.0
SEED = 20260815
N_BOOTSTRAP = 10_000
PRIMARY = "PROPOSED_HFIS"

if len(sys.argv) < 3:
    raise SystemExit("usage: real_time_class_flapping.py <pipeline_run_id> <evaluation_run_id>")
PIPELINE_RUN_ID = sys.argv[1]
EVALUATION_RUN_ID = sys.argv[2]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)

hfis = con.execute(
    "SELECT computed_ts, index_class AS trial_class, completeness_status FROM iaq_index_results "
    "WHERE pipeline_run_id = ? AND window_minutes = ?",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
hfis["method"] = PRIMARY

baselines = con.execute(
    """
    SELECT b.computed_ts, b.method, b.index_class AS trial_class, i.completeness_status
    FROM baseline_results b
    JOIN iaq_index_results i
      ON i.pipeline_run_id = b.pipeline_run_id AND i.computed_ts = b.computed_ts AND i.window_minutes = b.window_minutes
    WHERE b.pipeline_run_id = ? AND b.evaluation_run_id = ? AND b.window_minutes = ?
    """,
    [PIPELINE_RUN_ID, EVALUATION_RUN_ID, WINDOW_MINUTES],
).fetch_df()
con.close()

if hfis.empty:
    raise SystemExit(f"No iaq_index_results rows for pipeline_run_id={PIPELINE_RUN_ID}, window_minutes={WINDOW_MINUTES}")
if baselines.empty:
    raise SystemExit(f"No baseline_results rows for evaluation_run_id={EVALUATION_RUN_ID} -- run 'iaq_hfis evaluate' first")

df = pd.concat([hfis[["computed_ts", "method", "trial_class", "completeness_status"]], baselines], ignore_index=True)
df = df.dropna(subset=["trial_class"]).copy()
df["computed_ts"] = pd.to_datetime(df["computed_ts"], utc=True)
df["day"] = df["computed_ts"].dt.date
METHODS = sorted(df["method"].unique())


def compute_transitions(sub: pd.DataFrame) -> pd.DataFrame:
    """One row per consecutive-in-position pair; `consecutive` (real elapsed
    time <= MAX_GAP_MINUTES) gates whether it is scored as a transition at
    all -- a pair across a gap is recorded (for transparency) but excluded
    from every transition/reversal/dwell count."""
    sub = sub.sort_values("computed_ts").reset_index(drop=True)
    ts, cls = sub["computed_ts"].tolist(), sub["trial_class"].tolist()
    rows = []
    for i in range(1, len(sub)):
        consecutive = is_chronologically_consecutive(ts[i - 1], ts[i], MAX_GAP_MINUTES)
        gap_minutes = (ts[i] - ts[i - 1]).total_seconds() / 60.0
        ttype = classify_class_transition(cls[i - 1], cls[i], CLASS_ORDER) if consecutive else "gap_excluded"
        rows.append(dict(computed_ts=ts[i], gap_minutes=gap_minutes, consecutive=consecutive, transition_type=ttype))
    return pd.DataFrame(rows)


def compute_reversals(sub: pd.DataFrame) -> pd.DataFrame:
    """A-B-A reversal opportunities: three chronologically-consecutive VALID
    updates (both adjoining gaps <= MAX_GAP_MINUTES)."""
    sub = sub.sort_values("computed_ts").reset_index(drop=True)
    ts, cls = sub["computed_ts"].tolist(), sub["trial_class"].tolist()
    rows = []
    for i in range(2, len(sub)):
        c1 = is_chronologically_consecutive(ts[i - 2], ts[i - 1], MAX_GAP_MINUTES)
        c2 = is_chronologically_consecutive(ts[i - 1], ts[i], MAX_GAP_MINUTES)
        if c1 and c2:
            rows.append(dict(computed_ts=ts[i], is_reversal=is_aba_reversal(cls[i - 2], cls[i - 1], cls[i])))
    return pd.DataFrame(rows)


def compute_dwell_times(sub: pd.DataFrame) -> pd.DataFrame:
    """A 'run' is a maximal chronologically-consecutive (gap <= MAX_GAP_MINUTES
    at every internal step) sequence of updates sharing the same class. A
    run broken by a large gap ends there -- continuity across an outage is
    never assumed. dwell_minutes = last_ts - first_ts of the run (0 for a
    length-1 run: the true dwell duration is unknown beyond the single
    observed instant, reported as 0 rather than guessed)."""
    sub = sub.sort_values("computed_ts").reset_index(drop=True)
    ts, cls = sub["computed_ts"].tolist(), sub["trial_class"].tolist()
    runs = []
    run_start = run_end = ts[0]
    run_class = cls[0]
    n_updates = 1
    for i in range(1, len(sub)):
        consecutive = is_chronologically_consecutive(ts[i - 1], ts[i], MAX_GAP_MINUTES)
        if consecutive and cls[i] == run_class:
            run_end = ts[i]
            n_updates += 1
        else:
            runs.append(dict(class_=run_class, dwell_minutes=(run_end - run_start).total_seconds() / 60.0, n_updates=n_updates))
            run_start = run_end = ts[i]
            run_class = cls[i]
            n_updates = 1
    runs.append(dict(class_=run_class, dwell_minutes=(run_end - run_start).total_seconds() / 60.0, n_updates=n_updates))
    return pd.DataFrame(runs)


summary_rows: list[dict] = []
transition_rows: list[pd.DataFrame] = []
by_day_all: list[pd.DataFrame] = []

for method in METHODS:
    g_all = df[df["method"] == method]
    for scope_name, scope_df in [("all", g_all), ("completeness_ok_only", g_all[g_all["completeness_status"] == "OK"])]:
        if len(scope_df) < 2:
            continue
        trans = compute_transitions(scope_df)
        trans["method"], trans["scope"] = method, scope_name
        transition_rows.append(trans)

        rev = compute_reversals(scope_df)
        dwell = compute_dwell_times(scope_df)

        n_valid_updates = len(scope_df)
        n_days = scope_df["day"].nunique()
        n_consecutive_pairs = int(trans["consecutive"].sum())
        n_transitions = int(trans["transition_type"].isin(["adjacent", "nonadjacent"]).sum())
        n_adjacent = int((trans["transition_type"] == "adjacent").sum())
        n_nonadjacent = int((trans["transition_type"] == "nonadjacent").sum())
        n_reversal_opportunities = len(rev)
        n_reversals = int(rev["is_reversal"].sum()) if len(rev) else 0
        dwell_minutes = dwell["dwell_minutes"].to_numpy() if len(dwell) else np.array([])

        summary_rows.append(dict(
            method=method, scope=scope_name,
            n_valid_updates=n_valid_updates, n_days=n_days,
            n_consecutive_pairs=n_consecutive_pairs, n_gap_excluded_pairs=int((~trans["consecutive"]).sum()),
            n_class_transitions=n_transitions,
            transitions_per_day=(n_transitions / n_days) if n_days else None,
            transitions_per_100_valid_updates=(n_transitions / n_valid_updates * 100.0) if n_valid_updates else None,
            n_adjacent_transitions=n_adjacent, n_nonadjacent_transitions=n_nonadjacent,
            n_aba_reversal_opportunities=n_reversal_opportunities, n_aba_reversals=n_reversals,
            reversals_per_day=(n_reversals / n_days) if n_days else None,
            n_dwell_runs=len(dwell),
            median_dwell_minutes=float(np.median(dwell_minutes)) if len(dwell_minutes) else None,
            p5_dwell_minutes=float(np.percentile(dwell_minutes, 5)) if len(dwell_minutes) else None,
            p95_dwell_minutes=float(np.percentile(dwell_minutes, 95)) if len(dwell_minutes) else None,
        ))

        if scope_name == "all":
            t2 = trans.copy()
            t2["day"] = pd.to_datetime(t2["computed_ts"]).dt.date
            byday = t2.groupby("day").apply(
                lambda d: pd.Series({
                    "n_transitions": int(d["transition_type"].isin(["adjacent", "nonadjacent"]).sum()),
                    "n_consecutive_pairs": int(d["consecutive"].sum()),
                }),
                include_groups=False,
            ).reset_index()
            byday["method"] = method
            by_day_all.append(byday)

transitions_df = pd.concat(transition_rows, ignore_index=True)
transitions_df.to_csv(OUT_DIR / "real_time_class_flapping.csv", index=False)

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv(OUT_DIR / "real_time_class_flapping_summary.csv", index=False)

byday_df = pd.concat(by_day_all, ignore_index=True) if by_day_all else pd.DataFrame(columns=["day", "n_transitions", "n_consecutive_pairs", "method"])
byday_df.to_csv(OUT_DIR / "real_time_class_flapping_by_day.csv", index=False)

# --- paired day-level block bootstrap: PROPOSED_HFIS vs each baseline on
# transitions-per-day (days are the resampling unit -- the correct block
# here, since transitions within one day are not independent observations). ---
bootstrap_rows = []
if not byday_df.empty and PRIMARY in byday_df["method"].unique():
    pivot_days = byday_df.pivot_table(index="day", columns="method", values="n_transitions", fill_value=0)
    days_arr = pivot_days.index.to_numpy()
    n_days = len(days_arr)
    rng = np.random.default_rng(SEED)
    resample_idx = rng.integers(0, n_days, size=(N_BOOTSTRAP, n_days))
    primary_vals = pivot_days[PRIMARY].to_numpy(dtype=float)
    for other in [m for m in pivot_days.columns if m != PRIMARY]:
        other_vals = pivot_days[other].to_numpy(dtype=float)
        a_mean = primary_vals[resample_idx].mean(axis=1)
        b_mean = other_vals[resample_idx].mean(axis=1)
        diffs = a_mean - b_mean
        bootstrap_rows.append(dict(
            method_a=PRIMARY, method_b=other, n_days=n_days, n_reps=N_BOOTSTRAP,
            point_diff_transitions_per_day=float(primary_vals.mean() - other_vals.mean()),
            ci_low=float(np.percentile(diffs, 2.5)), ci_high=float(np.percentile(diffs, 97.5)),
            significant_at_95=bool(np.percentile(diffs, 2.5) > 0 or np.percentile(diffs, 97.5) < 0),
        ))
bootstrap_df = pd.DataFrame(bootstrap_rows)
bootstrap_df.to_csv(OUT_DIR / "real_time_class_flapping_bootstrap_ci.csv", index=False)

# --- publication figure: transitions/day and reversals/day per method (scope=all) ---
plot_df = summary_df[summary_df["scope"] == "all"].set_index("method")
fig, axes = plt.subplots(1, 2, figsize=(11, 5))
axes[0].bar(plot_df.index, plot_df["transitions_per_day"])
axes[0].set_ylabel("Class transitions per day")
axes[0].tick_params(axis="x", rotation=30)
axes[1].bar(plot_df.index, plot_df["reversals_per_day"])
axes[1].set_ylabel("A-B-A reversals per day")
axes[1].tick_params(axis="x", rotation=30)
fig.suptitle("Real chronological class-flapping rate by method (full period, MAX_GAP_MINUTES=10)")
fig.tight_layout()
fig.savefig(OUT_DIR / "real_time_class_flapping.png", dpi=300)
fig.savefig(OUT_DIR / "real_time_class_flapping.svg")
plt.close(fig)

meta = {
    "pipeline_run_id": PIPELINE_RUN_ID,
    "evaluation_run_id": EVALUATION_RUN_ID,
    "window_minutes": WINDOW_MINUTES,
    "max_gap_minutes": MAX_GAP_MINUTES,
    "methods": METHODS,
    "primary_method": PRIMARY,
    "bootstrap_seed": SEED,
    "bootstrap_reps": N_BOOTSTRAP,
    "fix_note": (
        "2026-08-19 (task section 5.4): replaces the arbitrary-perturbation-trial-order "
        "'flapping rate' previously computed in boundary_stability_paired_analysis.py "
        "(stability_class_flapping_by_point.csv) with the REAL chronological "
        "computed_ts series for all four methods. Two updates are only 'consecutive' "
        "when their real elapsed time gap is <= max_gap_minutes; a gap-spanning pair "
        "is recorded (for transparency) but excluded from every transition/reversal/"
        "dwell-time count, so a multi-hour pipeline outage is never silently treated "
        "as continuous coverage."
    ),
}
(OUT_DIR / "real_time_class_flapping_metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

print(f"Wrote artifacts to {OUT_DIR}")
print(summary_df.to_string())
print(bootstrap_df.to_string())
