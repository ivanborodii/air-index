"""Section 8: does the second fuzzy level (the real 2-level Mamdani engine,
PROPOSED_HFIS) change the final class versus a direct maximum of the
component results (FUZZY_COMPONENT_MAX)?

Two genuinely separate claims, kept separate throughout:

1. RULE-LEVEL property (proven, not sampled): every one of the 64 real
   index-level rules in iaq_hfis.rules.build_rule_base().index_rules has a
   consequent equal to the max-severity antecedent, by construction
   (generate_component_rules always takes max(combo, key=severity)). Since
   there are only 64 rules (4^3, a finite Cartesian product), checking every
   single one IS a complete proof by exhaustion, not an empirical sample.

2. AGGREGATE numerical behaviour (empirical, both on the real dataset and on
   a synthetic grid): whether PROPOSED_HFIS's Mamdani centroid output
   actually equals FUZZY_COMPONENT_MAX's hard max in practice. When two or
   more components have graded (partial) membership in adjacent classes,
   multiple rules fire simultaneously and Mamdani centroid defuzzification
   blends them -- this can differ numerically from a single-rule hard max
   EVEN THOUGH property (1) holds for every individual rule. Property (1)
   does not imply numerical equivalence of the two methods' aggregate
   output; this script does not claim it does.

Real-timestamp data comes from iaq_index_results (PROPOSED_HFIS) joined to
baseline_results (FUZZY_COMPONENT_MAX), both already persisted by
`iaq_hfis evaluate --pipeline-run-id ...`. Grid data comes from
evaluation_multi_component_grid (already persisted by the same command with
--multi-component-grid-points).
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))

from iaq_hfis.config import load_settings  # noqa: E402
from iaq_hfis.constants import CLASS_SEVERITY  # noqa: E402
from iaq_hfis.rules import build_rule_base  # noqa: E402

RUN_ID = "20260817_expanded_dataset_v1"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "second_level_equivalence"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOW_MINUTES = 15
GRID_CSV_SAMPLE_SEED = 20260815
GRID_CSV_SAMPLE_MAX_ROWS = 50_000

if len(sys.argv) < 3:
    raise SystemExit("usage: second_level_equivalence.py <pipeline_run_id> <evaluation_run_id>")
PIPELINE_RUN_ID = sys.argv[1]
EVALUATION_RUN_ID = sys.argv[2]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")

# --- 1. Rule-level audit: exhaustive, not sampled (only 64 rules exist) ---
rule_base = build_rule_base()
rule_audit_rows = []
n_index_rules = len(rule_base.index_rules)
n_correct = 0
for rule in rule_base.index_rules:
    antecedent_classes = [cls for _, cls in rule.antecedents]
    worst = max(antecedent_classes, key=lambda c: CLASS_SEVERITY[c])
    matches = rule.consequent_class == worst
    n_correct += int(matches)
    rule_audit_rows.append(dict(
        antecedents=dict(rule.antecedents), consequent_class=rule.consequent_class,
        expected_worst_of_antecedents=worst, matches_worst_of_property=matches,
    ))
all_index_rules_are_worst_of = (n_correct == n_index_rules)

md_lines = [
    "# Second-level rule audit",
    "",
    f"Index-level (2nd fuzzy level) rule base has {n_index_rules} rules "
    f"(iaq_hfis.rules.build_rule_base().index_rules, a full 4^3 Cartesian "
    f"product over {{A,V,M}} x CLASS_ORDER).",
    "",
    f"**Exhaustive check (all {n_index_rules} rules, not a sample): "
    f"{n_correct}/{n_index_rules} rules assign the consequent class equal to "
    f"the most adverse (max-severity) antecedent class.** "
    f"{'This is a complete proof by exhaustion for this finite rule set.' if all_index_rules_are_worst_of else 'COUNTEREXAMPLE FOUND -- see rows below where matches_worst_of_property=False.'}",
    "",
    "## Important distinction (do not conflate these two claims)",
    "",
    "1. The rule-level property above (every individual rule's consequent is "
    "the worst-of its antecedents) is proven by exhaustive enumeration.",
    "2. This does NOT by itself prove the AGGREGATE Mamdani engine output "
    "(PROPOSED_HFIS, which fires potentially several rules at once when "
    "inputs have graded/partial membership in more than one class, then "
    "combines them via max-OR and centroid defuzzification) is numerically "
    "identical to FUZZY_COMPONENT_MAX (a hard max of crisp component "
    "scores). See second_level_equivalence_real.csv / _grid.csv / "
    "_summary.json for the actual empirical numerical comparison -- those "
    "results, not this rule audit, are what determine whether the two "
    "methods agree in practice.",
    "",
    "## All rules (machine-readable copy also at second_level_rule_audit.csv)",
]
pd.DataFrame(rule_audit_rows).to_csv(OUT_DIR / "second_level_rule_audit.csv", index=False)
(OUT_DIR / "second_level_rule_audit.md").write_text("\n".join(md_lines) + "\n\n```\n" + pd.DataFrame(rule_audit_rows).to_string() + "\n```\n", encoding="utf-8")

# --- 2a. Real-timestamp comparison ---
con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
real = con.execute(
    """
    SELECT i.computed_ts, i.index_value AS hfis_index_value, i.index_class AS hfis_index_class,
           b.index_value AS fcm_index_value, b.index_class AS fcm_index_class
    FROM iaq_index_results i
    JOIN baseline_results b
      ON b.pipeline_run_id = i.pipeline_run_id AND b.computed_ts = i.computed_ts AND b.window_minutes = i.window_minutes
    WHERE i.pipeline_run_id = ? AND i.window_minutes = ? AND i.completeness_status = 'OK'
      AND b.evaluation_run_id = ? AND b.method = 'FUZZY_COMPONENT_MAX'
    ORDER BY i.computed_ts
    """,
    [PIPELINE_RUN_ID, WINDOW_MINUTES, EVALUATION_RUN_ID],
).fetch_df()

if real.empty:
    raise SystemExit(
        f"No joined iaq_index_results/baseline_results rows for pipeline_run_id={PIPELINE_RUN_ID}, "
        f"evaluation_run_id={EVALUATION_RUN_ID} -- run 'iaq_hfis evaluate --pipeline-run-id ...' first"
    )

real["signed_diff"] = real["hfis_index_value"] - real["fcm_index_value"]
real["abs_diff"] = real["signed_diff"].abs()
real["class_match"] = real["hfis_index_class"] == real["fcm_index_class"]
real.to_csv(OUT_DIR / "second_level_equivalence_real.csv", index=False)


def diff_stats(df: pd.DataFrame, value_col: str = "signed_diff") -> dict:
    d = df[value_col].dropna()
    ad = d.abs()
    return {
        "n": int(len(d)),
        "mean_signed_diff": float(d.mean()) if len(d) else None,
        "median_signed_diff": float(d.median()) if len(d) else None,
        "median_abs_diff": float(ad.median()) if len(d) else None,
        "mean_abs_diff": float(ad.mean()) if len(d) else None,
        "max_abs_diff": float(ad.max()) if len(d) else None,
        "p50_abs_diff": float(np.percentile(ad, 50)) if len(d) else None,
        "p90_abs_diff": float(np.percentile(ad, 90)) if len(d) else None,
        "p95_abs_diff": float(np.percentile(ad, 95)) if len(d) else None,
        "p99_abs_diff": float(np.percentile(ad, 99)) if len(d) else None,
        "n_hfis_lower": int((d < 0).sum()),
        "n_hfis_higher": int((d > 0).sum()),
        "n_exact_equal": int((d == 0).sum()),
    }


real_stats = diff_stats(real)
real_stats["n_class_disagreements"] = int((~real["class_match"]).sum())
real_stats["class_agreement_rate"] = float(real["class_match"].mean())

# --- 2b. Grid comparison (full-table SQL aggregation -- avoids materializing
# potentially >1M rows in pandas just for summary stats) ---
grid_summary_row = con.execute(
    """
    SELECT
        count(*) n,
        avg(hfis_index_value - fuzzy_component_max_index_value) mean_signed_diff,
        median(hfis_index_value - fuzzy_component_max_index_value) median_signed_diff,
        avg(abs(hfis_index_value - fuzzy_component_max_index_value)) mean_abs_diff,
        median(abs(hfis_index_value - fuzzy_component_max_index_value)) median_abs_diff,
        max(abs(hfis_index_value - fuzzy_component_max_index_value)) max_abs_diff,
        quantile_cont(abs(hfis_index_value - fuzzy_component_max_index_value), 0.90) p90_abs_diff,
        quantile_cont(abs(hfis_index_value - fuzzy_component_max_index_value), 0.95) p95_abs_diff,
        quantile_cont(abs(hfis_index_value - fuzzy_component_max_index_value), 0.99) p99_abs_diff,
        sum(CASE WHEN hfis_index_value < fuzzy_component_max_index_value THEN 1 ELSE 0 END) n_hfis_lower,
        sum(CASE WHEN hfis_index_value > fuzzy_component_max_index_value THEN 1 ELSE 0 END) n_hfis_higher,
        sum(CASE WHEN hfis_index_value = fuzzy_component_max_index_value THEN 1 ELSE 0 END) n_exact_equal,
        sum(CASE WHEN hfis_index_class = fuzzy_component_max_index_class THEN 1 ELSE 0 END) n_class_agree,
        sum(CASE WHEN hfis_index_class != fuzzy_component_max_index_class THEN 1 ELSE 0 END) n_class_disagree
    FROM evaluation_multi_component_grid
    WHERE evaluation_run_id = ?
    """,
    [EVALUATION_RUN_ID],
).fetch_df()

if grid_summary_row["n"].iloc[0] == 0:
    grid_stats = {"note": "evaluation_multi_component_grid is empty for this DB -- was --multi-component-grid-points used with 'iaq_hfis evaluate'?"}
    n_points_per_axis_used = None
else:
    row = grid_summary_row.iloc[0]
    n = int(row["n"])
    grid_stats = {
        "n": n,
        "mean_signed_diff": float(row["mean_signed_diff"]),
        "median_signed_diff": float(row["median_signed_diff"]),
        "mean_abs_diff": float(row["mean_abs_diff"]),
        "median_abs_diff": float(row["median_abs_diff"]),
        "max_abs_diff": float(row["max_abs_diff"]),
        "p90_abs_diff": float(row["p90_abs_diff"]),
        "p95_abs_diff": float(row["p95_abs_diff"]),
        "p99_abs_diff": float(row["p99_abs_diff"]),
        "n_hfis_lower": int(row["n_hfis_lower"]),
        "n_hfis_higher": int(row["n_hfis_higher"]),
        "n_exact_equal": int(row["n_exact_equal"]),
        "n_class_agree": int(row["n_class_agree"]),
        "n_class_disagree": int(row["n_class_disagree"]),
        "class_agreement_rate": float(row["n_class_agree"] / n),
    }
    n_points_per_axis_used = round(n ** (1 / 3))

    # Deterministic sample for the CSV deliverable (full grid may be >1M rows;
    # summary stats above are already computed from the FULL table via SQL).
    _base_query = f"SELECT * FROM evaluation_multi_component_grid WHERE evaluation_run_id = '{EVALUATION_RUN_ID}'"
    grid_sample = con.execute(
        f"{_base_query} USING SAMPLE {min(GRID_CSV_SAMPLE_MAX_ROWS, n)} (reservoir, {GRID_CSV_SAMPLE_SEED})"
        if n > GRID_CSV_SAMPLE_MAX_ROWS else _base_query
    ).fetch_df()
    grid_sample.to_csv(OUT_DIR / "second_level_equivalence_grid.csv", index=False)

con.close()

summary = {
    "pipeline_run_id": PIPELINE_RUN_ID,
    "evaluation_run_id": EVALUATION_RUN_ID,
    "rule_level_audit": {
        "n_index_rules": n_index_rules,
        "n_rules_matching_worst_of_property": n_correct,
        "all_rules_are_worst_of_max_severity": all_index_rules_are_worst_of,
        "proof_type": "exhaustive enumeration of all rules (complete, not sampled)",
    },
    "real_timestamps": real_stats,
    "synthetic_grid": grid_stats,
    "grid_n_points_per_axis": n_points_per_axis_used,
    "grid_csv_is_a_deterministic_sample": (grid_stats.get("n", 0) > GRID_CSV_SAMPLE_MAX_ROWS) if isinstance(grid_stats, dict) else None,
    "grid_csv_sample_size": min(GRID_CSV_SAMPLE_MAX_ROWS, grid_stats.get("n", 0)) if isinstance(grid_stats, dict) and "n" in grid_stats else None,
    "interpretation_note": (
        "Rule-level worst-of property (proven exhaustively) does NOT imply the "
        "two methods' aggregate numerical output is identical -- see "
        "real_timestamps/synthetic_grid class_agreement_rate and diff stats "
        "for the actual empirical answer. If class_agreement_rate is high but "
        "not 1.0, or if numerical diffs are nonzero even where classes agree, "
        "both are reported honestly, not smoothed over."
    ),
}
(OUT_DIR / "second_level_equivalence_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

print(f"Wrote artifacts to {OUT_DIR}")
print(json.dumps(summary, indent=2, default=str))
