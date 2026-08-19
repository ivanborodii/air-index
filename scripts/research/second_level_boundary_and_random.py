"""Task section 8.3/8.5: boundary-specific breakdown of the already-persisted
full 101^3 grid (evaluation_multi_component_grid), plus an independent
250,000-point deterministic random-continuous-triple check and the
attainable index range. Investigates the reviewer's specific claim that
"all observed disagreements appeared to occur when the maximum component
value was exactly 75."
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

from iaq_hfis.config import load_settings, load_sensor_specs, load_room_profiles  # noqa: E402
from iaq_hfis.db import AirMonitorSource  # noqa: E402
from iaq_hfis.pipeline import build_runtime_context  # noqa: E402
from iaq_hfis.evaluation.multi_component_grid import _hfis_from_component_scores  # noqa: E402
from iaq_hfis.baselines import fuzzy_component_max  # noqa: E402
from iaq_hfis.constants import OUTPUT_BOUNDARIES  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "second_level_equivalence"
OUT_DIR.mkdir(parents=True, exist_ok=True)

if len(sys.argv) < 2:
    raise SystemExit("usage: second_level_boundary_and_random.py <evaluation_run_id>")
EVALUATION_RUN_ID = sys.argv[1]
RANDOM_SEED = 20260815
N_RANDOM = 250_000
BOUNDARY_EPS = 1e-6

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
sensor_specs = load_sensor_specs(REPO_ROOT / "config" / "sensor_specs.yaml")
room_profiles = load_room_profiles(REPO_ROOT / "config" / "room_profiles.yaml")
with AirMonitorSource(settings) as _source:
    _raw_columns = _source.raw_schema_columns()
ctx = build_runtime_context(settings, sensor_specs, room_profiles, _raw_columns)

con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)


def _bucket_query(where_clause: str) -> dict:
    row = con.execute(
        f"""
        SELECT
            count(*) n,
            sum(CASE WHEN hfis_index_class = fuzzy_component_max_index_class THEN 1 ELSE 0 END) n_agree,
            avg(abs(hfis_index_value - fuzzy_component_max_index_value)) mean_abs_diff,
            median(abs(hfis_index_value - fuzzy_component_max_index_value)) median_abs_diff,
            min(abs(hfis_index_value - fuzzy_component_max_index_value)) min_abs_diff,
            quantile_cont(abs(hfis_index_value - fuzzy_component_max_index_value), 0.95) p95_abs_diff,
            quantile_cont(abs(hfis_index_value - fuzzy_component_max_index_value), 0.99) p99_abs_diff,
            max(abs(hfis_index_value - fuzzy_component_max_index_value)) max_abs_diff
        FROM evaluation_multi_component_grid
        WHERE evaluation_run_id = ? AND ({where_clause})
        """,
        [EVALUATION_RUN_ID],
    ).fetch_df().iloc[0]
    n = int(row["n"])
    return dict(
        n_points=n,
        n_class_agree=int(row["n_agree"]) if n else 0,
        class_agreement_rate=(float(row["n_agree"]) / n) if n else None,
        n_disagreements=(n - int(row["n_agree"])) if n else 0,
        mean_abs_diff=float(row["mean_abs_diff"]) if n else None,
        median_abs_diff=float(row["median_abs_diff"]) if n else None,
        min_abs_diff=float(row["min_abs_diff"]) if n else None,
        p95_abs_diff=float(row["p95_abs_diff"]) if n else None,
        p99_abs_diff=float(row["p99_abs_diff"]) if n else None,
        max_abs_diff=float(row["max_abs_diff"]) if n else None,
    )


buckets = {
    "all_grid_points": "1=1",
    "any_component_equals_25": "a = 25 OR v = 25 OR m = 25",
    "any_component_equals_50": "a = 50 OR v = 50 OR m = 50",
    "any_component_equals_75": "a = 75 OR v = 75 OR m = 75",
    "no_component_at_a_boundary": "a NOT IN (25,50,75) AND v NOT IN (25,50,75) AND m NOT IN (25,50,75)",
    "max_component_equals_75": "greatest(a,v,m) = 75",
    "max_component_immediately_below_75": "greatest(a,v,m) >= 74 AND greatest(a,v,m) < 75",
    "max_component_immediately_above_75": "greatest(a,v,m) > 75 AND greatest(a,v,m) <= 76",
}

boundary_rows = []
for label, clause in buckets.items():
    stats = _bucket_query(clause)
    stats["bucket"] = label
    boundary_rows.append(stats)
boundary_df = pd.DataFrame(boundary_rows)[["bucket", "n_points", "n_class_agree", "n_disagreements", "class_agreement_rate", "mean_abs_diff", "median_abs_diff", "min_abs_diff", "p95_abs_diff", "p99_abs_diff", "max_abs_diff"]]
boundary_df.to_csv(OUT_DIR / "second_level_boundary_summary.csv", index=False)

# All disagreements restricted to the "max==75" bucket vs elsewhere -- the
# reviewer's specific claim, checked directly.
disagree_at_75 = con.execute(
    "SELECT count(*) FROM evaluation_multi_component_grid WHERE evaluation_run_id = ? "
    "AND hfis_index_class != fuzzy_component_max_index_class AND greatest(a,v,m) = 75",
    [EVALUATION_RUN_ID],
).fetchone()[0]
disagree_total = con.execute(
    "SELECT count(*) FROM evaluation_multi_component_grid WHERE evaluation_run_id = ? "
    "AND hfis_index_class != fuzzy_component_max_index_class",
    [EVALUATION_RUN_ID],
).fetchone()[0]
disagree_not_at_75 = disagree_total - disagree_at_75

con.close()

# --- 250,000 deterministic random continuous (A, V, M) triples, excluding
# values within 1e-6 of a class boundary (25, 50, 75). ---
rng = np.random.default_rng(RANDOM_SEED)


def _draw_valid(n: int) -> np.ndarray:
    out = []
    while len(out) < n:
        batch = rng.uniform(0.0, 100.0, size=(n * 2, 3))
        for row in batch:
            if all(min(abs(x - b) for b in OUTPUT_BOUNDARIES) > BOUNDARY_EPS for x in row):
                out.append(row)
            if len(out) >= n:
                break
    return np.array(out[:n])


triples = _draw_valid(N_RANDOM)
diffs = np.empty(N_RANDOM)
classes_match = np.empty(N_RANDOM, dtype=bool)
counterexamples = []
for i, (a, v, m) in enumerate(triples):
    scores = {"A": float(a), "V": float(v), "M": float(m)}
    hfis_value, hfis_class = _hfis_from_component_scores(ctx, scores)
    cm = fuzzy_component_max(scores)
    diffs[i] = abs(hfis_value - cm.index_value)
    classes_match[i] = (hfis_class == cm.index_class)
    if not classes_match[i] and len(counterexamples) < 200:
        counterexamples.append(dict(
            a=float(a), v=float(v), m=float(m),
            hfis_index_value=hfis_value, hfis_index_class=hfis_class,
            fuzzy_component_max_index_value=cm.index_value, fuzzy_component_max_index_class=cm.index_class,
            abs_diff=float(abs(hfis_value - cm.index_value)),
            max_component=float(max(a, v, m)),
        ))

random_summary = {
    "n_points": N_RANDOM,
    "seed": RANDOM_SEED,
    "boundary_exclusion_eps": BOUNDARY_EPS,
    "n_class_agree": int(classes_match.sum()),
    "n_disagreements": int((~classes_match).sum()),
    "class_agreement_rate": float(classes_match.mean()),
    "mean_abs_diff": float(diffs.mean()),
    "median_abs_diff": float(np.median(diffs)),
    "min_abs_diff": float(diffs.min()),
    "p95_abs_diff": float(np.percentile(diffs, 95)),
    "p99_abs_diff": float(np.percentile(diffs, 99)),
    "max_abs_diff": float(diffs.max()),
    "n_disagreements_with_max_component_near_75_within_1": int(sum(1 for c in counterexamples if abs(c["max_component"] - 75) <= 1.0)),
    "n_counterexamples_saved": len(counterexamples),
}
pd.DataFrame([random_summary]).to_csv(OUT_DIR / "second_level_random_continuous_summary.csv", index=False)
pd.DataFrame(counterexamples).to_csv(OUT_DIR / "second_level_counterexamples.csv", index=False)

# --- attainable index range (task section 8.5) ---
con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
grid_range = con.execute(
    "SELECT min(hfis_index_value) lo, max(hfis_index_value) hi, count(*) n FROM evaluation_multi_component_grid WHERE evaluation_run_id = ?",
    [EVALUATION_RUN_ID],
).fetch_df().iloc[0]
con.close()

lo, hi = float(grid_range["lo"]), float(grid_range["hi"])
attainable = {
    "empirical_min_index_value_over_full_101_cubed_grid": lo,
    "empirical_max_index_value_over_full_101_cubed_grid": hi,
    "n_grid_points": int(grid_range["n"]),
    "zero_attained": bool(lo <= 1e-9),
    "hundred_attained": bool(hi >= 100.0 - 1e-9),
    "note": (
        "Centroid defuzzification over a bounded, non-degenerate output membership "
        "partition with shoulder classes at both ends generally cannot reach the "
        "extreme universe bounds 0/100 exactly, since even the most extreme input "
        "still distributes some membership mass short of the outer edge before "
        "defuzzification integrates it -- the empirical min/max above (from an "
        "exhaustive 101^3 grid, not a sample) is the actual attainable range under "
        "this rule base and membership configuration. Class boundaries (25, 50, 75) "
        "are attainable as OUTPUT values (a component's own crisp_score reaching a "
        "midpoint or boundary is fed straight through many rules) but the exact "
        "centroid of the DEFUZZIFIED index only coincides with a class boundary "
        "value for specific input configurations, not universally -- see "
        "second_level_boundary_summary.csv for the empirical near-boundary behavior."
    ),
}
(OUT_DIR / "attainable_index_range.json").write_text(json.dumps(attainable, indent=2, default=str), encoding="utf-8")

meta_addendum = {
    "reviewer_claim_check": {
        "claim": "All observed HFIS vs FUZZY_COMPONENT_MAX class disagreements occur when the maximum component value is exactly 75.",
        "n_disagreements_total_on_full_101_cubed_grid": int(disagree_total),
        "n_disagreements_with_max_component_exactly_75": int(disagree_at_75),
        "n_disagreements_with_max_component_NOT_exactly_75": int(disagree_not_at_75),
        "claim_supported": bool(disagree_not_at_75 == 0 and disagree_at_75 > 0),
    },
}
(OUT_DIR / "second_level_boundary_and_random_metadata.json").write_text(json.dumps(meta_addendum, indent=2, default=str), encoding="utf-8")

print(boundary_df.to_string())
print(json.dumps(random_summary, indent=2))
print(json.dumps(attainable, indent=2))
print(json.dumps(meta_addendum, indent=2))
