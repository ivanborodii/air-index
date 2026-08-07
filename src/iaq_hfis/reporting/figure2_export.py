"""Figure 2 (manuscript): PROPOSED_HFIS vs CRISP_CLASS_MAX behavior near
representative direct-input control boundaries, one panel per first-level
component (A/V/M).

Every point in the exported CSV is read directly from
``evaluation_continuity_grid`` -- the already-persisted, point-level output
of the deterministic boundary-continuity experiment
(:mod:`iaq_hfis.evaluation.continuity`). Nothing here recomputes, fabricates,
interpolates, or reconstructs a score from aggregate metrics
(max_adjacent_jump, mean_adjacent_jump, etc.); those aggregates are only used
afterward, in :func:`validate_export`, as an independent cross-check that the
exported points reconcile with ``evaluation_continuity_summary``.

Scenario selection is deterministic and pre-declared (:data:`PREFERRED_SCENARIOS`),
never chosen after inspecting which boundary makes one method look better.
If a preferred boundary_id no longer exists for a given (channel, context),
:func:`select_scenario` falls back to a documented, deterministic rule (see
its docstring) and records that a fallback occurred.

This is a standalone, targeted addition to the tracked
``research_results/final/`` snapshot -- not part of the routine
``iaq_hfis report`` export set (see ``scripts/export_figure2_boundary_curves.py``).
Regenerating ``research_results/final/`` via ``iaq_hfis finalize`` replaces
that directory atomically and does not know about this file; re-run the
script afterward to restore it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb
import pandas as pd

from iaq_hfis.evaluation.continuity import MONOTONIC_CHANNELS

FIGURE2_CSV_FILENAME = "figure2_boundary_curves.csv"
FIGURE2_METADATA_FILENAME = "figure2_boundary_curves_metadata.json"

#: Internal repository method identifiers -> manuscript-facing labels.
#: Only these two methods belong in Figure 2 (never WEIGHTED_MEAN or
#: FUZZY_COMPONENT_MAX, which illustrate a different point in the manuscript).
METHOD_LABELS: dict[str, str] = {
    "PROPOSED_HFIS": "PROPOSED-HFIS",
    "CRISP_CLASS_MAX": "CRISP-CLASS-MAX",
}
REQUIRED_METHODS: tuple[str, ...] = tuple(METHOD_LABELS.keys())

#: Real-world units for the channels Figure 2 can plot, matching
#: config/iaq_hfis.yaml's control_regions comments and the convention
#: already used in output_data_dictionary.csv (plain ASCII "ug/m3", not "µg/m³").
CHANNEL_UNITS: dict[str, str] = {
    "pm2_5": "ug/m3",
    "pm10": "ug/m3",
    "co2": "ppm",
    "humidity": "%",
    "temperature": "degC",
}


@dataclass(frozen=True)
class PreferredScenario:
    panel: str
    component: str
    channel: str
    boundary_id: str
    context: str


#: One representative boundary per first-level component (A/V/M), same
#: favourable background context for all three, in the same order Figure 2's
#: panels (a)/(b)/(c) are described in the manuscript. Do not add, remove, or
#: reorder entries to chase a particular visual result -- see module docstring.
PREFERRED_SCENARIOS: tuple[PreferredScenario, ...] = (
    PreferredScenario(panel="a", component="Aerosol", channel="pm2_5", boundary_id="pm2_5_breakpoint0", context="favourable"),
    PreferredScenario(panel="b", component="Ventilation", channel="co2", boundary_id="co2_breakpoint0", context="favourable"),
    PreferredScenario(panel="c", component="Microclimate", channel="humidity", boundary_id="humidity_favorable_low_edge_all_seasons", context="favourable"),
)

CSV_COLUMNS: list[str] = [
    "panel", "component", "channel", "boundary_id", "context", "boundary_value", "boundary_unit",
    "grid_point", "input_value", "distance_from_boundary", "method", "integrated_index", "output_class",
]


@dataclass(frozen=True)
class ResolvedScenario:
    panel: str
    component: str
    channel: str
    context: str
    preferred_boundary_id: str
    resolved_boundary_id: str
    boundary_value: float
    selection_note: str


def _available_boundaries(con: duckdb.DuckDBPyConnection, evaluation_run_id: str, channel: str, context: str) -> list[tuple[str, float]]:
    rows = con.execute(
        "SELECT DISTINCT boundary_id, boundary_value FROM evaluation_continuity_grid "
        "WHERE evaluation_run_id = ? AND channel = ? AND context = ?",
        [evaluation_run_id, channel, context],
    ).fetchall()
    return [(bid, float(bv)) for bid, bv in rows]


def select_scenario(con: duckdb.DuckDBPyConnection, evaluation_run_id: str, scenario: PreferredScenario) -> ResolvedScenario:
    """Resolves ``scenario`` against what's actually in ``evaluation_continuity_grid``
    for this ``evaluation_run_id``. Uses the exact preferred boundary_id if it
    exists. Otherwise falls back to a deterministic, documented rule -- never a
    choice made after looking at which boundary would flatter one method:

    - monotonic channels (pm2_5, pm10, co2): the boundary with the smallest
      boundary_value among those available for (channel, context) -- i.e. the
      first/lowest breakpoint, matching how ``breakpoint0`` is already named;
    - two-sided channels (humidity, temperature): among boundary_ids
      containing "favor"/"favour" (matching this scenario's favourable
      context) AND "low" (the lower/control edge, not the upper one), the one
      with the smallest boundary_value; if none contain "low", the smallest
      boundary_value among the "favor"/"favour" ones; if none of those exist
      either, the smallest boundary_value overall.
    """
    available = _available_boundaries(con, evaluation_run_id, scenario.channel, scenario.context)
    if not available:
        raise ValueError(
            f"No boundaries found for channel={scenario.channel!r} context={scenario.context!r} "
            f"in evaluation_run_id={evaluation_run_id!r} -- cannot select a scenario for panel {scenario.panel!r}."
        )
    ids = {bid for bid, _ in available}

    if scenario.boundary_id in ids:
        resolved_id = scenario.boundary_id
        note = "preferred_id_matched"
    elif scenario.channel in MONOTONIC_CHANNELS:
        resolved_id = min(available, key=lambda t: t[1])[0]
        note = f"preferred_id_missing; fallback=lowest_breakpoint_for_monotonic_channel (preferred was {scenario.boundary_id!r})"
    else:
        favor_low = [t for t in available if ("favor" in t[0] or "favour" in t[0]) and "low" in t[0]]
        pool = favor_low or [t for t in available if "favor" in t[0] or "favour" in t[0]] or available
        resolved_id = min(pool, key=lambda t: t[1])[0]
        note = f"preferred_id_missing; fallback=first_favourable_lower_control_boundary (preferred was {scenario.boundary_id!r})"

    boundary_value = dict(available)[resolved_id]
    return ResolvedScenario(
        panel=scenario.panel, component=scenario.component, channel=scenario.channel, context=scenario.context,
        preferred_boundary_id=scenario.boundary_id, resolved_boundary_id=resolved_id,
        boundary_value=boundary_value, selection_note=note,
    )


def _fetch_grid_rows(con: duckdb.DuckDBPyConnection, evaluation_run_id: str, scenario: ResolvedScenario) -> pd.DataFrame:
    df = con.execute(
        "SELECT grid_index, input_value, method, index_value, index_class FROM evaluation_continuity_grid "
        "WHERE evaluation_run_id = ? AND boundary_id = ? AND context = ? AND method IN (?, ?) "
        "ORDER BY method, grid_index",
        [evaluation_run_id, scenario.resolved_boundary_id, scenario.context, *REQUIRED_METHODS],
    ).df()
    return df


def build_figure2_dataframe(con: duckdb.DuckDBPyConnection, evaluation_run_id: str, scenarios: list[ResolvedScenario]) -> pd.DataFrame:
    rows: list[dict] = []
    for scenario in scenarios:
        grid = _fetch_grid_rows(con, evaluation_run_id, scenario)
        present_methods = set(grid["method"].unique())
        missing = set(REQUIRED_METHODS) - present_methods
        if missing:
            raise ValueError(
                f"boundary_id={scenario.resolved_boundary_id!r} context={scenario.context!r} is missing "
                f"required method(s) {sorted(missing)} in evaluation_continuity_grid -- refusing to fabricate them."
            )
        for method in REQUIRED_METHODS:
            method_rows = grid[grid["method"] == method].sort_values("grid_index")
            for _, r in method_rows.iterrows():
                index_class = r["index_class"]
                rows.append(
                    {
                        "panel": scenario.panel,
                        "component": scenario.component,
                        "channel": scenario.channel,
                        "boundary_id": scenario.resolved_boundary_id,
                        "context": scenario.context,
                        "boundary_value": scenario.boundary_value,
                        "boundary_unit": CHANNEL_UNITS[scenario.channel],
                        "grid_point": int(r["grid_index"]) + 1,
                        "input_value": float(r["input_value"]),
                        "distance_from_boundary": float(r["input_value"]) - scenario.boundary_value,
                        "method": METHOD_LABELS[method],
                        "integrated_index": None if pd.isna(r["index_value"]) else float(r["index_value"]),
                        "output_class": None if index_class is None or (isinstance(index_class, float) and pd.isna(index_class)) else str(index_class).upper(),
                    }
                )
    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    return df


def _recompute_continuity_metrics(values: list[float | None], classes: list[str | None], channel: str) -> dict:
    """Mirrors iaq_hfis.evaluation.continuity.summarize_boundary's per-method
    metric computation exactly, over the exported point-level values -- used
    only to cross-check against the already-persisted
    evaluation_continuity_summary row, never to produce the CSV itself."""
    defined = [v for v in values if v is not None]
    jumps = [abs(b - a) for a, b in zip(values, values[1:]) if a is not None and b is not None]
    transitions = [
        i for i in range(len(classes) - 1)
        if classes[i] is not None and classes[i + 1] is not None and classes[i] != classes[i + 1]
    ]
    monotonicity_violations = 0
    if channel in MONOTONIC_CHANNELS:
        monotonicity_violations = sum(1 for a, b in zip(values, values[1:]) if a is not None and b is not None and b < a - 1e-9)
    return {
        "max_adjacent_jump": max(jumps) if jumps else None,
        "mean_adjacent_jump": (sum(jumps) / len(jumps)) if jumps else None,
        "n_class_transitions": len(transitions),
        "monotonicity_violations": monotonicity_violations,
        "n_points": len(defined),
    }


def validate_export(con: duckdb.DuckDBPyConnection, evaluation_run_id: str, df: pd.DataFrame, scenarios: list[ResolvedScenario], expected_grid_points: int) -> list[dict]:
    """Runs the eight required checks and returns a list of
    ``{"name": ..., "passed": bool, "detail": ...}`` records. Never mutates
    ``df``; raises nothing itself -- callers decide what a failed check means."""
    checks: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    # 1. input_value monotonically ordered within each panel and method.
    ok = True
    for (panel, method), g in df.groupby(["panel", "method"]):
        vals = g.sort_values("grid_point")["input_value"].tolist()
        if vals != sorted(vals):
            ok = False
    record("input_value_monotonic_per_panel_and_method", ok, "input_value strictly non-decreasing in grid_point order, per (panel, method).")

    # 2. Both methods have exactly the same input grid within each panel.
    ok = True
    for panel, g in df.groupby("panel"):
        grids = [tuple(g[g["method"] == METHOD_LABELS[m]].sort_values("grid_point")["input_value"]) for m in REQUIRED_METHODS]
        if len(set(grids)) != 1:
            ok = False
    record("same_input_grid_across_methods_per_panel", ok, "Both methods share an identical input_value sequence within each panel.")

    # 3. All valid integrated_index values lie within [0, 100].
    defined = df["integrated_index"].dropna()
    ok = bool(((defined >= 0) & (defined <= 100)).all())
    record("integrated_index_in_0_100", ok, f"{len(defined)} defined integrated_index values checked, all in [0, 100]: {ok}.")

    # 4. boundary_value is constant inside a panel.
    ok = bool((df.groupby("panel")["boundary_value"].nunique() == 1).all())
    record("boundary_value_constant_per_panel", ok, "Exactly one distinct boundary_value per panel.")

    # 5. Exactly three scenarios/components are present.
    n_panels = df["panel"].nunique()
    ok = n_panels == 3 and set(df["panel"].unique()) == {"a", "b", "c"}
    record("exactly_three_scenarios", ok, f"panels present: {sorted(df['panel'].unique())}.")

    # 6. Only the two required methods are present.
    methods_present = set(df["method"].unique())
    ok = methods_present == set(METHOD_LABELS.values())
    record("only_required_methods_present", ok, f"methods present: {sorted(methods_present)}.")

    # 7. Each panel contains the expected number of points per method.
    ok = True
    counts = {}
    for (panel, method), g in df.groupby(["panel", "method"]):
        counts[(panel, method)] = len(g)
        if len(g) != expected_grid_points:
            ok = False
    record("expected_points_per_panel_and_method", ok, f"expected {expected_grid_points} points/panel/method; counts={counts}.")

    # 8. Recalculated continuity metrics agree with evaluation_continuity_summary.
    ok = True
    detail_parts = []
    for scenario in scenarios:
        for method_internal in REQUIRED_METHODS:
            method_label = METHOD_LABELS[method_internal]
            g = df[(df["panel"] == scenario.panel) & (df["method"] == method_label)].sort_values("grid_point")
            recomputed = _recompute_continuity_metrics(
                g["integrated_index"].where(g["integrated_index"].notna(), None).tolist(),
                g["output_class"].where(g["output_class"].notna(), None).tolist(),
                scenario.channel,
            )
            row = con.execute(
                "SELECT max_adjacent_jump, mean_adjacent_jump, n_class_transitions, monotonicity_violations "
                "FROM evaluation_continuity_summary WHERE evaluation_run_id = ? AND boundary_id = ? AND context = ? AND method = ?",
                [evaluation_run_id, scenario.resolved_boundary_id, scenario.context, method_internal],
            ).fetchone()
            if row is None:
                ok = False
                detail_parts.append(f"{scenario.resolved_boundary_id}/{method_internal}: no evaluation_continuity_summary row found")
                continue
            ref_max_jump, ref_mean_jump, ref_transitions, ref_mono = row
            tol = 1e-6
            matches = (
                (ref_max_jump is None) == (recomputed["max_adjacent_jump"] is None)
                and (ref_max_jump is None or abs(ref_max_jump - recomputed["max_adjacent_jump"]) < tol)
                and (ref_mean_jump is None) == (recomputed["mean_adjacent_jump"] is None)
                and (ref_mean_jump is None or abs(ref_mean_jump - recomputed["mean_adjacent_jump"]) < tol)
                and ref_transitions == recomputed["n_class_transitions"]
                and ref_mono == recomputed["monotonicity_violations"]
            )
            if not matches:
                ok = False
            detail_parts.append(
                f"{scenario.resolved_boundary_id}/{method_internal}: recomputed={recomputed}, "
                f"summary=(max_jump={ref_max_jump}, mean_jump={ref_mean_jump}, transitions={ref_transitions}, mono={ref_mono}), match={matches}"
            )
    record("recomputed_metrics_match_continuity_summary", ok, "; ".join(detail_parts))

    return checks


def export_figure2_boundary_curves(con: duckdb.DuckDBPyConnection, out_dir: Path, evaluation_run_id: str | None) -> Path | None:
    """Routine-export-convention entry point (mirrors every ``export_*``
    function in :mod:`iaq_hfis.reporting.exports`, and is wired into
    ``export_all()`` there): writes just the CSV, no metadata JSON, no
    validation, returning ``None`` if there's nothing to export for this
    run -- e.g. no continuity data yet, or none of Figure 2's three
    channels/boundaries were swept -- exactly like every other export
    returning ``None`` for "nothing to export," never a crash of the whole
    report. For the metadata JSON + validation (used to actually publish
    Figure 2), see :func:`write_figure2_export` /
    ``scripts/export_figure2_boundary_curves.py``.
    """
    if evaluation_run_id is None:
        return None
    try:
        resolved = [select_scenario(con, evaluation_run_id, s) for s in PREFERRED_SCENARIOS]
        df = build_figure2_dataframe(con, evaluation_run_id, resolved)
    except ValueError:
        return None
    if df.empty:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FIGURE2_CSV_FILENAME
    df.to_csv(path, index=False)
    return path


def write_figure2_export(
    con: duckdb.DuckDBPyConnection,
    out_dir: Path,
    evaluation_run_id: str,
    pipeline_run_id: str,
    git_commit: str | None,
    config_hash: str | None,
    expected_grid_points: int,
    scenarios: tuple[PreferredScenario, ...] = PREFERRED_SCENARIOS,
) -> dict:
    """Resolves scenarios, builds and writes the CSV, validates it, and
    writes the metadata JSON. Returns the metadata dict (also what's written
    to disk). Raises ValueError if any required method/scenario is missing
    (never silently drops a point or fabricates one)."""
    resolved = [select_scenario(con, evaluation_run_id, s) for s in scenarios]
    df = build_figure2_dataframe(con, evaluation_run_id, resolved)

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / FIGURE2_CSV_FILENAME
    df.to_csv(csv_path, index=False)

    checks = validate_export(con, evaluation_run_id, df, resolved, expected_grid_points)
    all_passed = all(c["passed"] for c in checks)

    metadata = {
        "figure": "Figure 2",
        "purpose": (
            "Illustrate PROPOSED_HFIS vs CRISP_CLASS_MAX behavior near representative direct-input "
            "control boundaries for the three first-level IAQ components: (a) PM2.5 -> Aerosol, "
            "(b) CO2 -> Ventilation, (c) Relative humidity -> Microclimate."
        ),
        "selection_rule": (
            "One deterministic, pre-declared boundary per component, all under the same favourable "
            "background context, using the exact boundary_id from the previous publication run if it "
            "still exists; otherwise the first favourable lower/control boundary for that channel "
            "(lowest breakpoint for monotonic channels; lowest 'favor*low*' edge for two-sided channels). "
            "No scenario was chosen or changed based on which one produced the largest difference between methods."
        ),
        "pipeline_run_id": pipeline_run_id,
        "evaluation_run_id": evaluation_run_id,
        "git_commit": git_commit,
        "config_hash": config_hash,
        "grid_points_per_boundary": expected_grid_points,
        "selected_scenarios": [asdict(s) for s in resolved],
        "methods": list(METHOD_LABELS.values()),
        "csv_path": str(Path("research_results") / "final" / "exports" / FIGURE2_CSV_FILENAME),
        "validation": {
            "row_count": len(df),
            "passed": all_passed,
            "checks": checks,
        },
    }

    metadata_path = out_dir / FIGURE2_METADATA_FILENAME
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata
