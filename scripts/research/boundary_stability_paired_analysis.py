"""Section 9 supplement: paired statistical tests on top of the production
multi-point stability trials (iaq_hfis.evaluation.multi_point_stability,
already run and persisted by `iaq_hfis evaluate`).

Reuses the exact persisted evaluation_stability_trials / _samples rows --
never recomputes independently. Trials are genuinely paired across methods:
run_multi_point_stability perturbs each input ONCE per trial_index and
scores every method against that SAME perturbed input, so
(sample_id, trial_index) is a valid pairing key.

Adds three things the production stability module does not compute:

1. Active/inactive scenario classification: "active" = selection_reason
   'boundary_adjacent' (constructed to sit near a control-region boundary,
   where instability is structurally expected); "inactive" =
   'random_comparison'. This reuses the existing field rather than inventing
   a new classification rule.

2. Paired sign test (exact McNemar, two-sided) between PROPOSED_HFIS and
   each baseline method, on the paired binary "changed_from_baseline"
   outcome at matching (sample_id, trial_index).

3. Paired cluster bootstrap CI (resampling sample_id, not individual
   trials, since trials within one sample are not independent) for the
   difference in class_change_rate between PROPOSED_HFIS and each baseline.

4. Class-flapping rate: within one (sample_id, method)'s ordered trial
   sequence, the fraction of consecutive trial-to-trial class changes
   (oscillation), separate from changed_from_baseline (which only compares
   each trial to the ORIGINAL baseline, not to the previous trial).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))
from iaq_hfis.config import load_settings  # noqa: E402
from iaq_hfis.research_helpers import mcnemar_exact  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "boundary_stability_paired"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SEED = 20260815
N_BOOTSTRAP = 10_000

if len(sys.argv) < 2:
    raise SystemExit("usage: boundary_stability_paired_analysis.py <evaluation_run_id>")
EVALUATION_RUN_ID = sys.argv[1]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
trials = con.execute(
    "SELECT sample_id, method, trial_index, trial_class, changed_from_baseline FROM evaluation_stability_trials WHERE evaluation_run_id = ?",
    [EVALUATION_RUN_ID],
).fetch_df()
samples = con.execute(
    "SELECT sample_id, selection_reason, boundary_channel FROM evaluation_stability_samples WHERE evaluation_run_id = ?",
    [EVALUATION_RUN_ID],
).fetch_df()
con.close()

if trials.empty:
    raise SystemExit(f"No evaluation_stability_trials rows for evaluation_run_id={EVALUATION_RUN_ID}")

trials = trials.merge(samples, on="sample_id", how="left")
trials["scenario_activity"] = trials["selection_reason"].map({"boundary_adjacent": "active", "random_comparison": "inactive"})

METHODS = sorted(trials["method"].unique())
PRIMARY = "PROPOSED_HFIS"
OTHERS = [m for m in METHODS if m != PRIMARY]

# --- 1. active/inactive summary (per method) ---
activity_summary = (
    trials.groupby(["method", "scenario_activity"])["changed_from_baseline"]
    .agg(["mean", "count"])
    .reset_index()
    .rename(columns={"mean": "class_change_rate", "count": "n_trials"})
)
activity_summary.to_csv(OUT_DIR / "stability_activity_summary.csv", index=False)


pivoted = trials.pivot_table(index=["sample_id", "trial_index"], columns="method", values="changed_from_baseline", aggfunc="first")

sign_test_rows = []
for other in OTHERS:
    paired = pivoted[[PRIMARY, other]].dropna()
    b = int(((paired[PRIMARY] == True) & (paired[other] == False)).sum())  # noqa: E712
    c = int(((paired[PRIMARY] == False) & (paired[other] == True)).sum())  # noqa: E712
    p = mcnemar_exact(b, c)
    sign_test_rows.append(dict(
        method_a=PRIMARY, method_b=other, n_paired_trials=len(paired),
        n_a_changed_b_not=b, n_b_changed_a_not=c, mcnemar_p_value=p,
        n_a_changed=int(paired[PRIMARY].sum()), n_b_changed=int(paired[other].sum()),
    ))
sign_test_df = pd.DataFrame(sign_test_rows)
sign_test_df.to_csv(OUT_DIR / "stability_paired_sign_test.csv", index=False)

# --- 3. paired cluster bootstrap CI (resample sample_id) ---
# Vectorized (same pattern as missing_data_strategy_comparison.py's per-day
# bootstrap): pre-aggregate to one (changed_count, total_count) pair per
# sample_id/method, then draw ALL N_BOOTSTRAP resamples in one indexed numpy
# pass instead of a Python-level loop per rep per sample_id -- the original
# nested-loop version had no checkpointing and no bound on wall-clock time,
# which is exactly the kind of long unresumable operation task section 1
# warns against. This version finishes in well under a second regardless of
# N_BOOTSTRAP, so no checkpoint file is needed here (kept simple rather than
# adding checkpoint machinery to something that no longer needs it).
CHECKPOINT_PATH = OUT_DIR / "stability_paired_bootstrap_ci.csv"
rng = np.random.default_rng(SEED)
sample_ids = sorted(trials["sample_id"].unique())
n_samples = len(sample_ids)
sample_index = {sid: i for i, sid in enumerate(sample_ids)}

per_sample_changed = {}
per_sample_total = {}
for method in METHODS:
    changed = np.zeros(n_samples)
    total = np.zeros(n_samples)
    for sid, g in trials[trials.method == method].groupby("sample_id"):
        i = sample_index[sid]
        changed[i] = g["changed_from_baseline"].sum()
        total[i] = len(g)
    per_sample_changed[method] = changed
    per_sample_total[method] = total

resample_idx = rng.integers(0, n_samples, size=(N_BOOTSTRAP, n_samples))

bootstrap_rows = []
for other in OTHERS:
    a_changed = per_sample_changed[PRIMARY][resample_idx].sum(axis=1)
    a_total = per_sample_total[PRIMARY][resample_idx].sum(axis=1)
    b_changed = per_sample_changed[other][resample_idx].sum(axis=1)
    b_total = per_sample_total[other][resample_idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate_a = np.where(a_total > 0, a_changed / a_total, np.nan)
        rate_b = np.where(b_total > 0, b_changed / b_total, np.nan)
    diffs = rate_a - rate_b
    diffs = diffs[~np.isnan(diffs)]
    point_a = trials[trials.method == PRIMARY]["changed_from_baseline"].mean()
    point_b = trials[trials.method == other]["changed_from_baseline"].mean()
    bootstrap_rows.append(dict(
        method_a=PRIMARY, method_b=other, n_reps=N_BOOTSTRAP,
        point_diff=float(point_a - point_b),
        ci_low=float(np.percentile(diffs, 2.5)) if len(diffs) else None,
        ci_high=float(np.percentile(diffs, 97.5)) if len(diffs) else None,
    ))
bootstrap_df = pd.DataFrame(bootstrap_rows)
bootstrap_df.to_csv(CHECKPOINT_PATH, index=False)

# --- 4. class-flapping rate ---
flap_rows = []
for (sid, method), g in trials.groupby(["sample_id", "method"]):
    g = g.sort_values("trial_index")
    classes = g["trial_class"].tolist()
    n_transitions = sum(1 for i in range(1, len(classes)) if classes[i] != classes[i - 1])
    flap_rows.append(dict(
        sample_id=sid, method=method, n_trials=len(classes),
        n_transitions=n_transitions,
        flapping_rate=(n_transitions / (len(classes) - 1)) if len(classes) > 1 else None,
    ))
flap_df = pd.DataFrame(flap_rows)
flap_df.to_csv(OUT_DIR / "stability_class_flapping_by_point.csv", index=False)
flap_summary = flap_df.groupby("method")["flapping_rate"].agg(["mean", "median", "std", "count"]).reset_index()
flap_summary.to_csv(OUT_DIR / "stability_class_flapping_summary.csv", index=False)

meta = {
    "evaluation_run_id": EVALUATION_RUN_ID,
    "methods": METHODS,
    "primary_method": PRIMARY,
    "n_samples": len(sample_ids),
    "n_trials_total": len(trials),
    "bootstrap_seed": SEED,
    "bootstrap_reps": N_BOOTSTRAP,
    "note": "Pairing key is (sample_id, trial_index): run_multi_point_stability perturbs inputs once per trial_index and scores all methods against that same perturbed input, so this pairing is exact, not approximate.",
}
(OUT_DIR / "boundary_stability_paired_metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

print(f"Wrote artifacts to {OUT_DIR}")
print(sign_test_df.to_string())
print(bootstrap_df.to_string())
print(flap_summary.to_string())
