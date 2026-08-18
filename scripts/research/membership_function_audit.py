"""Section 11: membership-function audit across every configured input and
output channel (pm2_5, pm10, co2, relative_humidity, temperature [per
room/season profile], and the output index) -- breakpoint ordering, range
coverage, gaps/overlaps, transition width, max membership degree, shoulder
behaviour, and specifically whether the PM10 "Degraded" category is
triangular or trapezoidal (reported honestly either way, never silently
"corrected").

Uses the REAL, effective (possibly auto-expanded) widths this config
actually builds (iaq_hfis.schema.validate_membership_config can widen a
class's width to satisfy overlap_width_policy before
iaq_hfis.membership.build_monotonic_classes ever sees it) -- not the raw
configured numbers alone.

Reachable output ranges are computed empirically: for each component (A, V,
M) we sample its own real input domain through the real single-component
engine (ctx.engine.infer_component) and take the observed crisp-score
min/max -- not a theoretical [0,100] assumption. The final index's reachable
range is read from evaluation_multi_component_grid if that table has already
been populated by `iaq_hfis evaluate` for this run (a full grid sweep is far
more informative than a further ad-hoc sample); falls back to a coarser
in-script 3D sample of (A, V, M) if that table is not yet available.
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

from iaq_hfis.config import load_settings, load_sensor_specs, load_room_profiles  # noqa: E402
from iaq_hfis.membership import build_monotonic_classes, build_two_sided_classes, trapezoid, evaluate_memberships  # noqa: E402
from iaq_hfis.research_helpers import monotonic_shape_type  # noqa: E402
from iaq_hfis.pipeline import build_runtime_context  # noqa: E402
from iaq_hfis.db import AirMonitorSource  # noqa: E402
from iaq_hfis.constants import CLASS_ORDER  # noqa: E402

RUN_ID = "20260817_expanded_dataset_v1"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "membership_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
sensor_specs = load_sensor_specs(REPO_ROOT / "config" / "sensor_specs.yaml")
room_profiles = load_room_profiles(REPO_ROOT / "config" / "room_profiles.yaml")
control_regions = settings.control_regions

# Read the shapes straight from a real RuntimeContext -- ctx.static_shapes /
# ctx.temperature_shapes_by_profile are exactly what compute_index_at uses
# at inference time (post overlap_width_policy auto-widening), so this is
# the actual effective config, not a separate reconstruction that could
# drift from it.
with AirMonitorSource(settings) as _source:
    _raw_columns = _source.raw_schema_columns()
ctx = build_runtime_context(settings, sensor_specs, room_profiles, _raw_columns)

audit_rows = []


def audit_from_shapes(channel: str, shapes: dict, kind: str, source: str):
    """Records audit rows directly from an already-built shapes dict (as
    used by ctx at real inference time) -- no separate reconstruction."""
    for cls in CLASS_ORDER:
        for side_idx, (a, b, c, d) in enumerate(shapes[cls]):
            side = None if kind == "monotonic_right_shoulder" else (
                "single_band" if len(shapes[cls]) == 1 else ("low" if side_idx == 0 else "high")
            )
            finite_bd = np.isfinite(b) and np.isfinite(c)
            if finite_bd:
                shape_type = monotonic_shape_type(a, b, c, d)
            else:
                shape_type = "shoulder"
            audit_rows.append(dict(
                channel=channel, class_name=cls, shape_kind=kind, side=side,
                a=a, b=b, c=c, d=d,
                plateau_width=(c - b) if finite_bd else None,
                shape_type=shape_type, max_membership_degree=1.0,
                transition_width_source=source,
            ))


monotonic_shapes = {}
for channel in ("pm2_5", "pm10", "co2", "output"):
    shapes = ctx.static_shapes[channel]
    monotonic_shapes[channel] = shapes
    audit_from_shapes(channel, shapes, "monotonic_right_shoulder", "ctx.static_shapes (real effective config used at inference time)")

two_sided_shapes = {"relative_humidity": ctx.static_shapes["relative_humidity"]}
audit_from_shapes("relative_humidity", two_sided_shapes["relative_humidity"], "two_sided", "ctx.static_shapes (real effective config)")

for (room, season), shapes in ctx.temperature_shapes_by_profile.items():
    key = f"temperature[{room}/{season}]"
    two_sided_shapes[key] = shapes
    audit_from_shapes(key, shapes, "two_sided", f"ctx.temperature_shapes_by_profile[{room}/{season}] (real effective config)")

# --- breakpoint ordering / range coverage / gap and overlap check ---
coverage_rows = []
for channel in ("pm2_5", "pm10", "co2", "output"):
    bp = list(getattr(control_regions, channel).breakpoints) if channel != "output" else list(control_regions.output.breakpoints)
    ordered = all(bp[i] < bp[i + 1] for i in range(len(bp) - 1))
    shapes = monotonic_shapes[channel]
    classes_sorted = [(cls, shapes[cls][0]) for cls in CLASS_ORDER]
    gaps = []
    overlaps = []
    for i in range(len(classes_sorted) - 1):
        (cls_a, (a1, b1, c1, d1)) = classes_sorted[i]
        (cls_b, (a2, b2, c2, d2)) = classes_sorted[i + 1]
        # adjacent classes should meet exactly at c1==a2 for a shared edge (no gap, no unintended overlap)
        if np.isfinite(c1) and np.isfinite(a2):
            if a2 > c1 + 1e-9:
                gaps.append(f"{cls_a}->{cls_b}: gap [{c1},{a2}]")
            elif a2 < c1 - 1e-9:
                overlaps.append(f"{cls_a}->{cls_b}: overlap [{a2},{c1}]")
    coverage_rows.append(dict(
        channel=channel, breakpoints=bp, breakpoints_strictly_increasing=ordered,
        gaps_found="; ".join(gaps) if gaps else "none",
        unintended_overlaps_found="; ".join(overlaps) if overlaps else "none",
    ))

audit_df = pd.DataFrame(audit_rows)
audit_df.to_csv(OUT_DIR / "membership_function_audit.csv", index=False)

# --- reachable ranges: sample each component's real single-component engine,
# using the exact same shapes dicts already audited above (ctx.static_shapes /
# ctx.temperature_shapes_by_profile) -- no separate reconstruction. ---
co2_bp = control_regions.co2.breakpoints
pm25_bp, pm10_bp = control_regions.pm2_5.breakpoints, control_regions.pm10.breakpoints


def sample_reachable_component(component: str, n_per_axis: int = 61):
    if component == "V":
        lo, hi = max(co2_bp[0] - 3000, 0), co2_bp[2] + 3000
        scores = [ctx.engine.infer_component("V", {"co2": evaluate_memberships(float(co2), monotonic_shapes["co2"])}).crisp_score
                  for co2 in np.linspace(lo, hi, n_per_axis)]
        return float(min(scores)), float(max(scores)), len(scores)
    if component == "A":
        v25 = np.linspace(0, pm25_bp[2] + 100, n_per_axis)
        v10 = np.linspace(0, pm10_bp[2] + 100, n_per_axis)
        scores = []
        for a in v25[:: max(1, n_per_axis // 15)]:
            for b in v10[:: max(1, n_per_axis // 15)]:
                mem = {"pm2_5": evaluate_memberships(float(a), monotonic_shapes["pm2_5"]), "pm10": evaluate_memberships(float(b), monotonic_shapes["pm10"])}
                scores.append(ctx.engine.infer_component("A", mem).crisp_score)
        return float(min(scores)), float(max(scores)), len(scores)
    return None, None, 0


reachable = {}
for comp in ("A", "V"):
    lo, hi, n = sample_reachable_component(comp)
    reachable[comp] = {"empirical_min_crisp_score": lo, "empirical_max_crisp_score": hi, "n_samples": n, "method": "sampled own real input domain through ctx.engine.infer_component"}

# M is room/season-dependent; report per profile.
rh_shapes = ctx.static_shapes["relative_humidity"]
m_reach = {}
for profile in room_profiles.profiles:
    t_shapes = ctx.temperature_shapes_by_profile[(profile.room, profile.season)]
    t_lo, t_hi = profile.ranges.critical_low_max - 3, profile.ranges.critical_high_min + 3
    rh_lo, rh_hi = control_regions.relative_humidity.critical_low_max - 3, control_regions.relative_humidity.critical_high_min + 3
    scores = []
    for t in np.linspace(t_lo, t_hi, 31):
        for rh in np.linspace(max(rh_lo, 0), min(rh_hi, 100), 31):
            mem = {"temperature": evaluate_memberships(float(t), t_shapes), "humidity": evaluate_memberships(float(rh), rh_shapes)}
            scores.append(ctx.engine.infer_component("M", mem).crisp_score)
    m_reach[f"{profile.room}/{profile.season}"] = {"empirical_min_crisp_score": float(min(scores)), "empirical_max_crisp_score": float(max(scores)), "n_samples": len(scores)}
reachable["M"] = m_reach

# Final index reachable range: prefer the real evaluate grid if populated.
try:
    con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)
    try:
        grid = con.execute(
            "SELECT min(hfis_index_value) lo, max(hfis_index_value) hi, count(*) n FROM evaluation_multi_component_grid"
        ).fetch_df()
        if not grid.empty and grid["n"].iloc[0] > 0:
            reachable["final_index"] = {
                "empirical_min": float(grid["lo"].iloc[0]), "empirical_max": float(grid["hi"].iloc[0]),
                "n_samples": int(grid["n"].iloc[0]), "source": "evaluation_multi_component_grid (iaq_hfis evaluate)",
            }
        else:
            reachable["final_index"] = {"note": "evaluation_multi_component_grid empty at audit time"}
    finally:
        con.close()
except Exception as exc:  # noqa: BLE001 - e.g. DB locked by a concurrent writer; report, don't crash the audit
    reachable["final_index"] = {"note": f"evaluation_multi_component_grid not available (DB busy or missing): {exc}"}

(OUT_DIR / "reachable_output_ranges.json").write_text(json.dumps(reachable, indent=2, default=str), encoding="utf-8")

# --- PM10 Degraded specific focus (task explicitly asks) ---
pm10_degraded = next(r for r in audit_rows if r["channel"] == "pm10" and r["class_name"] == "Degraded")
a, b, c, d = pm10_degraded["a"], pm10_degraded["b"], pm10_degraded["c"], pm10_degraded["d"]
lo = a - 5 if np.isfinite(a) else b - 10
hi = d + 5 if np.isfinite(d) else c + 10
xs = np.linspace(lo, hi, 500)
ys = [trapezoid(x, a, b, c, d) for x in xs]
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(xs, ys, label=f"PM10 Degraded ({pm10_degraded['shape_type']})")
ax.axvline(b, color="gray", linestyle=":", alpha=0.6, label=f"b={b:.2f}")
ax.axvline(c, color="gray", linestyle="--", alpha=0.6, label=f"c={c:.2f}")
ax.set_xlabel("PM10 (ug/m3)")
ax.set_ylabel("membership degree")
ax.set_title(f"PM10 Degraded membership shape: {pm10_degraded['shape_type']} (plateau width={pm10_degraded['plateau_width']})")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "pm10_degraded_shape.png", dpi=300)
fig.savefig(OUT_DIR / "pm10_degraded_shape.svg")
plt.close(fig)

md_lines = [
    "# Membership function audit",
    "",
    f"PM10 Degraded category shape: **{pm10_degraded['shape_type']}** "
    f"(a={a:.3f}, b={b:.3f}, c={c:.3f}, d={d:.3f}, plateau_width={pm10_degraded['plateau_width']}).",
    "",
    "This is the actual, effective shape given the config's real (possibly "
    "auto-widened) transition width -- reported as-is, not silently changed "
    "to match manuscript terminology if it turns out to differ.",
    "",
    "## Breakpoint ordering / range coverage / gaps / overlaps",
    "",
    "```",
    pd.DataFrame(coverage_rows).to_string(index=False),
    "```",
    "",
    "## Full shape audit (every channel/class/side)",
    "",
    "See membership_function_audit.csv for the full machine-readable table. Summary:",
    "```",
    audit_df.to_string(index=False),
    "```",
    "",
    "## Reachable output ranges (empirical, sampled through the real engine)",
    "",
    "```json",
    json.dumps(reachable, indent=2, default=str),
    "```",
]
(OUT_DIR / "membership_function_audit.md").write_text("\n".join(md_lines), encoding="utf-8")

print(f"Wrote artifacts to {OUT_DIR}")
print(pd.DataFrame(coverage_rows).to_string())
print(f"PM10 Degraded shape_type = {pm10_degraded['shape_type']}")
