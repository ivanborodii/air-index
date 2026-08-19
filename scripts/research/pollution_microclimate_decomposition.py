"""Section 7: pollution (A, V) vs microclimate (M) decomposition of the final
index over the expanded dataset. Purely descriptive/correlational -- no
causal claim is made anywhere below; findings are phrased as "dominant
component" / "associated input", never "cause".

Uses the real, already-persisted component_scores and iaq_index_results for
one pipeline run, restricted to completeness_status == "OK" timestamps
(every component genuinely available -- no imputed/substituted value).

The "pollution oriented index" is not a hand-rolled max() shortcut: it is
computed by feeding the SAME real (A, V) crisp scores through the SAME
production 2nd-level engine used everywhere else in this codebase
(iaq_hfis.pipeline.infer_from_values with available_components={"A","V"}) --
identical machinery to how a real PARTIAL run handles "M unavailable", just
invoked here for research purposes rather than because M was actually
missing at that timestamp.
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

from iaq_hfis import membership  # noqa: E402
from iaq_hfis.config import load_settings, load_sensor_specs, load_room_profiles  # noqa: E402
from iaq_hfis.constants import CLASS_SEVERITY, CLASS_ORDER  # noqa: E402
from iaq_hfis.db import AirMonitorSource  # noqa: E402
from iaq_hfis.pipeline import build_runtime_context, infer_from_values  # noqa: E402
from iaq_hfis.fuzzy_engine import classify_output  # noqa: E402
from iaq_hfis.research_helpers import has_dominance_tie, most_adverse_direct_input as _rank_by_membership  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "pollution_microclimate"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOW_MINUTES = 15

if len(sys.argv) < 2:
    raise SystemExit("usage: pollution_microclimate_decomposition.py <pipeline_run_id>")
PIPELINE_RUN_ID = sys.argv[1]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
sensor_specs = load_sensor_specs(REPO_ROOT / "config" / "sensor_specs.yaml")
room_profiles = load_room_profiles(REPO_ROOT / "config" / "room_profiles.yaml")

con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
idx = con.execute(
    "SELECT computed_ts, completeness_status, index_value, index_class, dominant_component, co_dominant_components "
    "FROM iaq_index_results WHERE pipeline_run_id = ? AND window_minutes = ? AND completeness_status = 'OK'",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
cs = con.execute(
    "SELECT computed_ts, component, crisp_score, room, season FROM component_scores "
    "WHERE pipeline_run_id = ? AND window_minutes = ? AND available = true",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
wa = con.execute(
    "SELECT computed_ts, channel, weighted_mean FROM window_aggregates WHERE pipeline_run_id = ? AND window_minutes = ?",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
con.close()

if idx.empty:
    raise SystemExit(f"No OK-completeness rows for pipeline_run_id={PIPELINE_RUN_ID}")

cs_pivot = cs.pivot_table(index="computed_ts", columns="component", values="crisp_score", aggfunc="first")
wa_pivot = wa.pivot_table(index="computed_ts", columns="channel", values="weighted_mean", aggfunc="first")
m_profile = cs[cs["component"] == "M"].set_index("computed_ts")[["room", "season"]]

df = idx.set_index("computed_ts").join(cs_pivot, how="inner")
df = df.join(wa_pivot, how="left")
df = df.join(m_profile, how="left")
df["hour_of_day"] = pd.to_datetime(df.index).hour
df["day"] = pd.to_datetime(df.index).date

with AirMonitorSource(settings) as _source:
    _raw_columns = _source.raw_schema_columns()
ctx = build_runtime_context(settings, sensor_specs, room_profiles, _raw_columns)


def pollution_oriented(row):
    """Real 2nd-level inference fed only the raw (pm2_5, pm10, co2) direct
    inputs -- identical code path a genuine PARTIAL "M unavailable" run
    would use (infer_from_values recomputes A/V's own membership degrees
    and crisp scores from these raw values, then runs the real engine)."""
    if pd.isna(row.get("pm2_5")) or pd.isna(row.get("pm10")) or pd.isna(row.get("co2")):
        return None, None
    values = {"pm2_5": row["pm2_5"], "pm10": row["pm10"], "co2": row["co2"]}
    _, res = infer_from_values(ctx, values, {"A", "V"}, None)
    return (res.index_value, res.index_class) if res is not None else (None, None)


pollution_results = [pollution_oriented(row) for _, row in df.iterrows()]
df["pollution_index_value"] = [r[0] for r in pollution_results]
df["pollution_index_class"] = [r[1] for r in pollution_results]

CATEGORY_MAP = {"A": "pollution", "V": "pollution", "M": "microclimate"}


def categorize(row):
    dom = row["dominant_component"]
    co = row["co_dominant_components"] if isinstance(row["co_dominant_components"], (list, np.ndarray)) else []
    cats = {CATEGORY_MAP.get(dom)} | {CATEGORY_MAP.get(c) for c in co}
    cats.discard(None)
    if len(cats) > 1:
        return "tie_pollution_microclimate"
    if cats:
        return next(iter(cats))
    return "none"


df["dominance_category"] = df.apply(categorize, axis=1)
# Fix for task section 5.2: a tie exists only when MORE THAN ONE DISTINCT
# component remains co-dominant. co_dominant_components always contains at
# least the dominant component itself (fuzzy_engine.determine_dominance sets
# dominant = co_dominant[0]), so the old `len(c) > 0` check flagged a tie on
# essentially every row. len(set(...)) > 1 is the correct condition.
df["has_tie"] = df["co_dominant_components"].apply(
    lambda c: has_dominance_tie(list(c)) if isinstance(c, (list, np.ndarray)) else False
)

DIRECT_INPUTS = {"A": ["pm2_5", "pm10"], "V": ["co2"], "M": ["temperature", "humidity"]}


def _shapes_for_channel(channel: str, row) -> dict | None:
    if channel == "temperature":
        room, season = row.get("room"), row.get("season")
        if pd.isna(room) or pd.isna(season):
            return None
        key = (room, season)
        return ctx.temperature_shapes_by_profile.get(key)
    return ctx.static_shapes["relative_humidity" if channel == "humidity" else channel]


def most_adverse_direct_input(row):
    """Among the direct inputs of the dominant component, report which one
    is most adverse -- an associated input, not a claimed cause. Ties
    reported explicitly.

    Fix for task section 5.3: the previous implementation ranked channels by
    percentile rank within the dataset, which silently fails for two-sided
    channels (temperature, humidity) since both a very low and a very high
    value can be adverse but only one direction can hold the top percentile
    rank. This now uses the real fuzzy membership definitions (the same
    shapes the production pipeline evaluates) and class severity: rank by
    each channel's most adverse ACTIVE class first, then by membership
    degree in that class if severities tie.
    """
    dom = row["dominant_component"]
    inputs = DIRECT_INPUTS.get(dom, [])
    if len(inputs) < 2:
        return inputs[0] if inputs else None, False
    channel_degrees = {}
    for ch in inputs:
        v = row.get(ch)
        if pd.isna(v):
            continue
        shapes = _shapes_for_channel(ch, row)
        if shapes is None:
            continue
        channel_degrees[ch] = membership.evaluate_memberships(float(v), shapes)
    if len(channel_degrees) < len(inputs):
        return None, False
    return _rank_by_membership(channel_degrees, CLASS_SEVERITY)


assoc = df.apply(most_adverse_direct_input, axis=1, result_type="expand")
df["associated_direct_input"], df["associated_direct_input_tie"] = assoc[0], assoc[1]

# --- 1. class distributions ---
def class_dist(series):
    counts = series.value_counts()
    return {cls: int(counts.get(cls, 0)) for cls in CLASS_ORDER}


current_dist = class_dist(df["index_class"])
pollution_dist = class_dist(df["pollution_index_class"].dropna())
microclimate_class = df["M"].apply(classify_output)
microclimate_dist = class_dist(microclimate_class)

n = len(df)
summary = {
    "n_observations_ok_completeness": n,
    "current_integrated_index_class_distribution": current_dist,
    "current_integrated_index_critical_count": current_dist["Critical"],
    "current_integrated_index_critical_share": current_dist["Critical"] / n,
    "pollution_oriented_index_class_distribution": pollution_dist,
    "pollution_oriented_index_critical_count": pollution_dist["Critical"],
    "pollution_oriented_index_critical_share": pollution_dist["Critical"] / n,
    "microclimate_component_class_distribution": microclimate_dist,
    "microclimate_component_critical_count": microclimate_dist["Critical"],
    "microclimate_component_critical_share": microclimate_dist["Critical"] / n,
    "n_current_critical_remaining_critical_under_pollution_oriented": int(
        ((df["index_class"] == "Critical") & (df["pollution_index_class"] == "Critical")).sum()
    ),
    "n_current_critical_total": int((df["index_class"] == "Critical").sum()),
    "share_current_critical_remaining_critical_under_pollution_oriented": (
        float(((df["index_class"] == "Critical") & (df["pollution_index_class"] == "Critical")).sum() / current_dist["Critical"])
        if current_dist["Critical"] else None
    ),
    "dominance_category_counts": df["dominance_category"].value_counts().to_dict(),
    "n_ties_any_co_dominant_component": int(df["has_tie"].sum()),
    "tie_rate": float(df["has_tie"].mean()),
    "pearson_r_index_value_vs_pollution_score": float(df["index_value"].corr(df[["A", "V"]].max(axis=1))),
    "pearson_r_index_value_vs_microclimate_score": float(df["index_value"].corr(df["M"])),
    "class_order_low_to_high_severity": CLASS_ORDER,
    "causality_note": "All findings above are descriptive associations over this deployment's real data, not causal claims. 'Dominant'/'associated' language only.",
}
(OUT_DIR / "pollution_microclimate_summary.csv").write_text(
    pd.Series(summary, dtype=object).apply(lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v).to_csv(header=["value"]),
    encoding="utf-8",
)
(OUT_DIR / "pollution_microclimate_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

# --- 2. critical driver summary: among CRITICAL current-index timestamps,
# what was the dominant component and associated direct input? ---
critical_df = df[df["index_class"] == "Critical"].copy()
driver_summary = (
    critical_df.groupby(["dominant_component", "associated_direct_input"], dropna=False)
    .size().rename("n_timestamps").reset_index()
)
driver_summary["share_of_critical"] = driver_summary["n_timestamps"] / max(len(critical_df), 1)
driver_summary.to_csv(OUT_DIR / "critical_driver_summary.csv", index=False)

by_day = (
    critical_df.groupby("day").agg(
        n_critical=("index_class", "size"),
        n_dominant_A=("dominant_component", lambda s: (s == "A").sum()),
        n_dominant_V=("dominant_component", lambda s: (s == "V").sum()),
        n_dominant_M=("dominant_component", lambda s: (s == "M").sum()),
        n_ties=("has_tie", "sum"),
    ).reset_index()
)
by_day.to_csv(OUT_DIR / "critical_driver_by_day.csv", index=False)

by_hour = (
    critical_df.groupby("hour_of_day").agg(
        n_critical=("index_class", "size"),
        n_dominant_A=("dominant_component", lambda s: (s == "A").sum()),
        n_dominant_V=("dominant_component", lambda s: (s == "V").sum()),
        n_dominant_M=("dominant_component", lambda s: (s == "M").sum()),
        n_ties=("has_tie", "sum"),
    ).reindex(range(24), fill_value=0).rename_axis("hour_of_day").reset_index()
)
by_hour.to_csv(OUT_DIR / "critical_driver_by_hour.csv", index=False)

# --- 3. warm-period persistence: does M stay adverse (Degraded/Critical)
# across a run of consecutive computed_ts, i.e. persistent rather than a
# one-off spike? Reported per season using the same room/season profile
# join component_scores already carries for M. ---
df2 = df.join(m_profile, how="left", rsuffix="_prof")
df2 = df2.sort_index()
df2["m_adverse"] = microclimate_class.reindex(df2.index).isin(["Degraded", "Critical"])
df2["m_adverse_run_id"] = (df2["m_adverse"] != df2["m_adverse"].shift()).cumsum()
run_lengths = df2[df2["m_adverse"]].groupby(["season", "m_adverse_run_id"]).size()
persistence_by_season = run_lengths.groupby("season").agg(["count", "mean", "max"]).rename(
    columns={"count": "n_adverse_runs", "mean": "mean_run_length_timestamps", "max": "max_run_length_timestamps"}
).reset_index() if not run_lengths.empty else pd.DataFrame(columns=["season", "n_adverse_runs", "mean_run_length_timestamps", "max_run_length_timestamps"])
persistence_by_season.to_csv(OUT_DIR / "microclimate_persistence_by_season.csv", index=False)

# --- plot: class distribution comparison ---
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(CLASS_ORDER))
width = 0.25
ax.bar(x - width, [current_dist[c] for c in CLASS_ORDER], width, label="Current integrated index")
ax.bar(x, [pollution_dist[c] for c in CLASS_ORDER], width, label="Pollution-oriented (A,V only)")
ax.bar(x + width, [microclimate_dist[c] for c in CLASS_ORDER], width, label="Microclimate component (M)")
ax.set_xticks(x)
ax.set_xticklabels(CLASS_ORDER)
ax.set_ylabel("n_timestamps (completeness_status=OK)")
ax.set_title("Class distribution: current index vs pollution-oriented index vs microclimate component")
ax.legend()
fig.tight_layout()
fig.savefig(OUT_DIR / "index_class_distribution_comparison.png", dpi=300)
fig.savefig(OUT_DIR / "index_class_distribution_comparison.svg")
plt.close(fig)

print(f"Wrote artifacts to {OUT_DIR}")
print(json.dumps(summary, indent=2, default=str))
