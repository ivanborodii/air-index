"""Section 5 of the 2026-08-17 research task: expanded Hampel mad_multiplier
sweep (h = 1.0 .. 5.0, step 0.5) at the production window_size=11, computing
both the existing production objective (S_old, from
iaq_hfis.evaluation.fault_injection._objective) and a new objective
S_new = (F1_spike + P_event) / 2 for comparison.

This is a diagnostic/exploratory research script. It reuses the real,
already-shipped fault-injection benchmark (iaq_hfis.evaluation.fault_injection)
unmodified -- it does NOT alter config/iaq_hfis.yaml or any production
selection logic. Per task constraints: "Do not change the production fuzzy
model merely to obtain better results." Any recommendation this script
produces is reported, not applied.

Two independent split methodologies are computed and compared, since the
production benchmark's calibration/validation split is structural (disjoint
scenario_id suffixes with different deterministic scale/phase per variant,
see build_channel_scenarios), not a seeded random group split:

1. "structural" -- the existing production split (variant="calibration" vs
   variant="validation" scenario sets).
2. "seeded_group" -- a robustness cross-check: every generated scenario
   (across both variants) is pooled, grouped by scenario family (scenario_id
   with the _calibration/_validation suffix stripped, so no family straddles
   both groups), and assigned to a calibration/validation group via a
   deterministic 70/30 split using random.Random(20260815). This never mixes
   samples from the same family across groups, so there is no leakage within
   a split methodology.

Outputs (all under the run's hampel_sweep/ directory):
  hampel_threshold_sweep.csv       -- every (h, split_method, split) row
  hampel_calibration_results.csv   -- calibration-only view, both methods
  hampel_validation_results.csv    -- validation-only view, both methods
  hampel_selected_parameter.json   -- what each (method, objective) picks
  hampel_metric_definitions.md     -- exact formulas used
  hampel_pr_curve.png / .svg       -- single_spike precision/recall vs h
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import HampelConfig, load_settings, load_sensor_specs  # noqa: E402
from iaq_hfis.evaluation.fault_injection import (  # noqa: E402
    build_co2_scenarios,
    run_scenario,
    score_predictions,
    false_rejection_rate_for_genuine_events,
    _objective as s_old_objective,
)
from iaq_hfis.research_helpers import f1_of, s_new_objective, scenario_family  # noqa: E402

RUN_ID = "20260817_expanded_dataset_v1"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "hampel_sweep"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_SIZE = 11  # HAMPEL_SELECTION_WINDOW_SIZE, held fixed per task spec
H_GRID = [round(1.0 + 0.5 * i, 1) for i in range(9)]  # 1.0 .. 5.0 step 0.5
SEED = 20260815

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
sensor_specs = load_sensor_specs(REPO_ROOT / "config" / "sensor_specs.yaml")
cadence_seconds = settings.cadence.sample_cadence_seconds
schema_mapping = settings.schema_mapping
confirmation_cfg = settings.confirmation
pm_ordering_tolerance_pct = settings.confirmation.pm_cross_channel_tolerance_pct


def hampel_affected(variant: str):
    all_scenarios = build_co2_scenarios(cadence_seconds, variant=variant)
    return [s for s in all_scenarios if s.scenario_id.startswith(("co2_single_spike", "co2_genuine_rapid_event", "co2_persistent_real_change"))]


# --- Build the two split methodologies up front (scenario objects only; no metrics yet) ---
structural_calibration = hampel_affected("calibration")
structural_validation = hampel_affected("validation")

pooled = structural_calibration + structural_validation
families = sorted({scenario_family(s.scenario_id) for s in pooled})
rng = random.Random(SEED)
shuffled_families = list(families)
rng.shuffle(shuffled_families)
n_calib = round(0.7 * len(shuffled_families))
calib_families = set(shuffled_families[:n_calib])
valid_families = set(shuffled_families[n_calib:])
seeded_calibration = [s for s in pooled if scenario_family(s.scenario_id) in calib_families]
seeded_validation = [s for s in pooled if scenario_family(s.scenario_id) in valid_families]

split_methods = {
    "structural": {"calibration": structural_calibration, "validation": structural_validation},
    "seeded_group": {"calibration": seeded_calibration, "validation": seeded_validation},
}

split_method_notes = {
    "structural": "production benchmark's built-in split: disjoint scenario_ids, different deterministic scale/phase per variant (build_channel_scenarios).",
    "seeded_group": (
        f"robustness cross-check: {len(families)} scenario families pooled from both variants, "
        f"shuffled with random.Random(seed={SEED}), first {n_calib} families -> calibration "
        f"({sorted(calib_families)}), remaining {len(families) - n_calib} -> validation "
        f"({sorted(valid_families)}). No family appears in both groups."
    ),
}


rows = []
for method_name, groups in split_methods.items():
    for split_name, scenarios in groups.items():
        for h in H_GRID:
            hampel_cfg = HampelConfig(window_size=WINDOW_SIZE, mad_multiplier=h)
            predictions = [
                p for s in scenarios
                for p in run_scenario(s, schema_mapping, sensor_specs, hampel_cfg, confirmation_cfg, pm_ordering_tolerance_pct)
            ]
            metrics = {m.reason_code: m for m in score_predictions(predictions)}
            spike = metrics["single_spike"]
            preservation = 1.0 - fr if (fr := false_rejection_rate_for_genuine_events(predictions)) is not None else None
            s_old = s_old_objective(spike.recall, preservation, spike.false_positive_rate)
            f1_spike = f1_of(spike.precision, spike.recall)
            s_new = s_new_objective(f1_spike, preservation)
            rows.append(dict(
                split_method=method_name, dataset_split=split_name, window_size=WINDOW_SIZE, mad_multiplier=h,
                n_scenarios=len(scenarios), n_predictions=len(predictions),
                single_spike_precision=spike.precision, single_spike_recall=spike.recall,
                single_spike_f1=f1_spike, single_spike_fpr=spike.false_positive_rate,
                genuine_event_preservation_rate=preservation,
                s_old=s_old, s_new=s_new,
            ))

import csv

sweep_path = OUT_DIR / "hampel_threshold_sweep.csv"
fieldnames = list(rows[0].keys())
with open(sweep_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

for split_name, out_name in (("calibration", "hampel_calibration_results.csv"), ("validation", "hampel_validation_results.csv")):
    split_rows = [r for r in rows if r["dataset_split"] == split_name]
    with open(OUT_DIR / out_name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(split_rows)


def select_best(method_name: str, objective_key: str):
    """Mirrors select_hampel_multiplier's tie-break order (S, recall, preservation, fpr-ascending, h-ascending),
    but generalized to whichever objective column is requested, restricted to calibration rows of one split method."""
    candidates = [r for r in rows if r["split_method"] == method_name and r["dataset_split"] == "calibration"]

    def key(r):
        s = r[objective_key] if r[objective_key] is not None else float("-inf")
        recall = r["single_spike_recall"] if r["single_spike_recall"] is not None else float("-inf")
        preservation = r["genuine_event_preservation_rate"] if r["genuine_event_preservation_rate"] is not None else float("-inf")
        fpr = r["single_spike_fpr"] if r["single_spike_fpr"] is not None else float("inf")
        return (-s, -recall, -preservation, fpr, r["mad_multiplier"])

    best = min(candidates, key=key)
    return best


selection = {}
production_config_value = settings.hampel.mad_multiplier
for method_name in split_methods:
    for objective_key, objective_label in (("s_old", "S_old (production formula)"), ("s_new", "S_new = (F1_spike + P_event) / 2")):
        best = select_best(method_name, objective_key)
        selection[f"{method_name}__{objective_label}"] = {
            "selected_mad_multiplier": best["mad_multiplier"],
            "calibration_objective_value": best[objective_key],
            "calibration_single_spike_recall": best["single_spike_recall"],
            "calibration_single_spike_precision": best["single_spike_precision"],
            "calibration_genuine_event_preservation_rate": best["genuine_event_preservation_rate"],
        }

any_disagreement = len({v["selected_mad_multiplier"] for v in selection.values()}) > 1

# "value near 0.024" investigation: scan every computed metric across the full
# sweep for anything within 0.01 of 0.024, and report what it is (rather than
# assume/guess what the earlier reference meant).
near_0024 = []
for r in rows:
    for key in ("single_spike_precision", "single_spike_recall", "single_spike_f1", "single_spike_fpr", "genuine_event_preservation_rate", "s_old", "s_new"):
        v = r[key]
        if v is not None and abs(v - 0.024) < 0.01:
            near_0024.append({"split_method": r["split_method"], "dataset_split": r["dataset_split"], "mad_multiplier": r["mad_multiplier"], "metric": key, "value": v})

selected_summary = {
    "production_config_mad_multiplier": production_config_value,
    "window_size_held_fixed_at": WINDOW_SIZE,
    "h_grid": H_GRID,
    "seed": SEED,
    "selection_by_method_and_objective": selection,
    "any_disagreement_across_methods_or_objectives": any_disagreement,
    "recommendation": (
        "No production config change recommended by this script. Per task constraint "
        "('do not change the production fuzzy model merely to obtain better results'), "
        "this sweep is diagnostic only; any parameter change requires a separate, explicit, "
        "documented decision citing this artifact."
    ),
    "value_near_0_024_investigation": {
        "searched_within": 0.01,
        "matches_found": len(near_0024),
        "matches": near_0024,
    },
    "split_method_notes": split_method_notes,
}
(OUT_DIR / "hampel_selected_parameter.json").write_text(json.dumps(selected_summary, indent=2, default=str), encoding="utf-8")

definitions_md = f"""# Hampel threshold sweep -- metric definitions

Window size held fixed at {WINDOW_SIZE} (production `HAMPEL_SELECTION_WINDOW_SIZE`).
Multiplier `h` swept over {H_GRID}.

- **single_spike_precision / recall**: row-level precision/recall of the
  `single_spike` reason code against the fault-injection benchmark's known
  labels (`iaq_hfis.evaluation.fault_injection.score_predictions`).
- **single_spike_f1** (`F1_spike`): harmonic mean of the two above.
- **single_spike_fpr** (`FPR_spike`): false-positive rate of `single_spike`
  (real, non-fault samples incorrectly flagged as a spike).
- **genuine_event_preservation_rate** (`P_event`): `1 - false_rejection_rate`
  for samples labeled `genuine_event` (real, non-fault environmental
  changes) -- the fraction NOT discarded.
- **s_old** (production objective, unchanged):
  `S_old = (R_spike + P_event + (1 - FPR_spike)) / 3`
  (`iaq_hfis.evaluation.fault_injection._objective`).
- **s_new** (this task's requested alternative):
  `S_new = (F1_spike + P_event) / 2`

## Split methodologies

- **structural**: {split_method_notes['structural']}
- **seeded_group**: {split_method_notes['seeded_group']}

Selection procedure for each (split_method, objective) pair mirrors the
production `select_hampel_multiplier` tie-break order: highest objective,
then highest `single_spike_recall`, then highest `genuine_event_preservation_rate`,
then lowest `single_spike_fpr`, then smallest `h`. Always computed from the
**calibration** rows of that split method only; validation rows are reported
for context but never used in selection.
"""
(OUT_DIR / "hampel_metric_definitions.md").write_text(definitions_md, encoding="utf-8")

# --- PR-style plot: single_spike precision & recall vs h, one line per (split_method, dataset_split) ---
fig, ax = plt.subplots(figsize=(8, 5))
for method_name in split_methods:
    for split_name, style in (("calibration", "--"), ("validation", "-")):
        subset = sorted([r for r in rows if r["split_method"] == method_name and r["dataset_split"] == split_name], key=lambda r: r["mad_multiplier"])
        hs = [r["mad_multiplier"] for r in subset]
        precisions = [r["single_spike_precision"] for r in subset]
        recalls = [r["single_spike_recall"] for r in subset]
        ax.plot(hs, precisions, style, marker="o", label=f"precision ({method_name}/{split_name})", alpha=0.8)
        ax.plot(hs, recalls, style, marker="s", label=f"recall ({method_name}/{split_name})", alpha=0.8)
ax.set_xlabel("Hampel mad_multiplier (h)")
ax.set_ylabel("single_spike precision / recall")
ax.set_title("Hampel threshold sweep: single_spike precision & recall vs multiplier")
ax.legend(fontsize=7, ncol=2)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "hampel_pr_curve.png", dpi=150)
fig.savefig(OUT_DIR / "hampel_pr_curve.svg")
plt.close(fig)

print(f"Wrote sweep artifacts to {OUT_DIR}")
print(json.dumps(selected_summary, indent=2, default=str))
