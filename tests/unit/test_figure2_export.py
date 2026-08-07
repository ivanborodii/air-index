from pathlib import Path

import duckdb
import pytest

from iaq_hfis.reporting.figure2_export import (
    PreferredScenario,
    build_figure2_dataframe,
    select_scenario,
    validate_export,
    write_figure2_export,
)

SCHEMA_SQL = (Path(__file__).resolve().parent.parent.parent / "src" / "iaq_hfis" / "sql" / "create_tables.sql").read_text(encoding="utf-8")

METHODS = ("PROPOSED_HFIS", "FUZZY_COMPONENT_MAX", "CRISP_CLASS_MAX", "WEIGHTED_MEAN")

SCENARIOS = (
    PreferredScenario(panel="a", component="Aerosol", channel="pm2_5", boundary_id="pm2_5_breakpoint0", context="favourable"),
    PreferredScenario(panel="b", component="Ventilation", channel="co2", boundary_id="co2_breakpoint0", context="favourable"),
    PreferredScenario(panel="c", component="Microclimate", channel="humidity", boundary_id="humidity_favorable_low_edge_all_seasons", context="favourable"),
)

EVAL_RUN_ID = "eval-test-1"
PIPELINE_RUN_ID = "pipe-test-1"
N_POINTS = 5


def _grid_row(boundary_id, channel, context, boundary_value, grid_index, input_value, method, index_value, index_class):
    return [EVAL_RUN_ID, PIPELINE_RUN_ID, boundary_id, channel, context, boundary_value, grid_index, input_value, method, index_value, index_class]


def _linear_curve(boundary_value: float, span: float, n: int, slope: float, jump_at: int | None = None, jump_size: float = 0.0):
    """Deterministic synthetic score curve: linear ramp, class flips halfway,
    optional single hard jump (to emulate CRISP_CLASS_MAX-style discontinuity)."""
    xs = [boundary_value - span + (2 * span * i) / (n - 1) for i in range(n)]
    values = [10.0 + slope * i for i in range(n)]
    if jump_at is not None:
        for i in range(jump_at, n):
            values[i] += jump_size
    classes = ["Favourable"] * (n // 2) + ["Acceptable"] * (n - n // 2)
    return xs, values, classes


def _populate(con: duckdb.DuckDBPyConnection, scenarios=SCENARIOS, methods=METHODS, n_points=N_POINTS, mismatch_grid=False, break_index_range=False) -> None:
    con.execute(SCHEMA_SQL)
    boundary_values = {"pm2_5": 15.0, "co2": 800.0, "humidity": 30.0}
    for scenario in scenarios:
        bv = boundary_values[scenario.channel]
        for method in methods:
            slope = 0.5 if method == "PROPOSED_HFIS" else 5.0
            jump_at = n_points // 2
            jump_size = 1.0 if method == "PROPOSED_HFIS" else 20.0
            xs, values, classes = _linear_curve(bv, 5.0, n_points, slope, jump_at=jump_at, jump_size=jump_size)
            if mismatch_grid and method != "PROPOSED_HFIS":
                xs = [x + 100.0 for x in xs]  # deliberately different grid for non-proposed methods
            if break_index_range and method == "CRISP_CLASS_MAX":
                values[0] = 999.0  # out of [0, 100]
            for i, (x, v, c) in enumerate(zip(xs, values, classes)):
                con.execute(
                    "INSERT INTO evaluation_continuity_grid "
                    "(evaluation_run_id, pipeline_run_id, boundary_id, channel, context, boundary_value, grid_index, input_value, method, index_value, index_class) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _grid_row(scenario.boundary_id, scenario.channel, scenario.context, bv, i, x, method, v, c),
                )
            jumps = [abs(b - a) for a, b in zip(values, values[1:])]
            transitions = sum(1 for a, b in zip(classes, classes[1:]) if a != b)
            con.execute(
                "INSERT INTO evaluation_continuity_summary "
                "(evaluation_run_id, pipeline_run_id, boundary_id, channel, context, method, max_adjacent_jump, mean_adjacent_jump, "
                "median_adjacent_jump, p95_adjacent_jump, total_variation, local_lipschitz_ratio, n_class_transitions, "
                "class_transition_positions, index_range, monotonicity_violations, masked_by_favorable, area_between_curves_vs_crisp_max) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    EVAL_RUN_ID, PIPELINE_RUN_ID, scenario.boundary_id, scenario.channel, scenario.context, method,
                    max(jumps), sum(jumps) / len(jumps), None, None, sum(jumps), None, transitions, "", max(values) - min(values), 0, False, None,
                ],
            )


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


def test_build_figure2_dataframe_has_three_scenarios_and_two_methods(con):
    _populate(con)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    assert set(df["panel"].unique()) == {"a", "b", "c"}
    assert set(df["method"].unique()) == {"PROPOSED-HFIS", "CRISP-CLASS-MAX"}
    assert len(df) == 3 * N_POINTS * 2


def test_only_required_methods_exported_even_though_four_exist(con):
    _populate(con, methods=METHODS)  # table has all 4 methods
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    assert set(df["method"].unique()) == {"PROPOSED-HFIS", "CRISP-CLASS-MAX"}


def test_schema_matches_required_column_order(con):
    _populate(con)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    assert list(df.columns) == [
        "panel", "component", "channel", "boundary_id", "context", "boundary_value", "boundary_unit",
        "grid_point", "input_value", "distance_from_boundary", "method", "integrated_index", "output_class",
    ]
    assert df["grid_point"].min() == 1  # 1-based, not 0-based grid_index


def test_missing_required_method_raises_instead_of_fabricating(con):
    _populate(con, methods=("PROPOSED_HFIS",))  # CRISP_CLASS_MAX absent
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    with pytest.raises(ValueError, match="CRISP_CLASS_MAX"):
        build_figure2_dataframe(con, EVAL_RUN_ID, resolved)


def test_deterministic_output(con):
    _populate(con)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df1 = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    df2 = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    assert df1.equals(df2)


def test_validate_export_detects_score_out_of_range(con):
    _populate(con, break_index_range=True)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    checks = validate_export(con, EVAL_RUN_ID, df, resolved, N_POINTS)
    by_name = {c["name"]: c for c in checks}
    assert by_name["integrated_index_in_0_100"]["passed"] is False


def test_validate_export_detects_mismatched_grids_between_methods(con):
    _populate(con, mismatch_grid=True)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    checks = validate_export(con, EVAL_RUN_ID, df, resolved, N_POINTS)
    by_name = {c["name"]: c for c in checks}
    assert by_name["same_input_grid_across_methods_per_panel"]["passed"] is False


def test_validate_export_passes_on_consistent_data(con):
    _populate(con)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    checks = validate_export(con, EVAL_RUN_ID, df, resolved, N_POINTS)
    assert all(c["passed"] for c in checks), checks


def test_recomputed_metrics_match_the_persisted_summary_row(con):
    _populate(con)
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    checks = validate_export(con, EVAL_RUN_ID, df, resolved, N_POINTS)
    by_name = {c["name"]: c for c in checks}
    assert by_name["recomputed_metrics_match_continuity_summary"]["passed"] is True


def test_recomputed_metrics_detects_a_planted_mismatch(con):
    _populate(con)
    # Corrupt the persisted summary so it no longer matches the point-level data.
    con.execute(
        "UPDATE evaluation_continuity_summary SET max_adjacent_jump = 12345.0 "
        "WHERE evaluation_run_id = ? AND boundary_id = 'pm2_5_breakpoint0' AND method = 'PROPOSED_HFIS'",
        [EVAL_RUN_ID],
    )
    resolved = [select_scenario(con, EVAL_RUN_ID, s) for s in SCENARIOS]
    df = build_figure2_dataframe(con, EVAL_RUN_ID, resolved)
    checks = validate_export(con, EVAL_RUN_ID, df, resolved, N_POINTS)
    by_name = {c["name"]: c for c in checks}
    assert by_name["recomputed_metrics_match_continuity_summary"]["passed"] is False


def test_select_scenario_uses_preferred_id_when_present(con):
    _populate(con)
    resolved = select_scenario(con, EVAL_RUN_ID, SCENARIOS[0])
    assert resolved.resolved_boundary_id == "pm2_5_breakpoint0"
    assert resolved.selection_note == "preferred_id_matched"


def test_select_scenario_falls_back_for_monotonic_channel_to_lowest_breakpoint(con):
    con.execute(SCHEMA_SQL)
    for bid, bv in (("pm2_5_breakpoint1", 25.0), ("pm2_5_breakpoint2", 50.0)):
        con.execute(
            "INSERT INTO evaluation_continuity_grid "
            "(evaluation_run_id, pipeline_run_id, boundary_id, channel, context, boundary_value, grid_index, input_value, method, index_value, index_class) "
            "VALUES (?, ?, ?, 'pm2_5', 'favourable', ?, 0, ?, 'PROPOSED_HFIS', 10.0, 'Favourable')",
            [EVAL_RUN_ID, PIPELINE_RUN_ID, bid, bv, bv],
        )
    scenario = PreferredScenario(panel="a", component="Aerosol", channel="pm2_5", boundary_id="pm2_5_breakpoint0", context="favourable")
    resolved = select_scenario(con, EVAL_RUN_ID, scenario)
    assert resolved.resolved_boundary_id == "pm2_5_breakpoint1"  # the lowest of what's actually available (25.0 < 50.0)
    assert "fallback" in resolved.selection_note


def test_select_scenario_falls_back_for_two_sided_channel_to_favourable_low_edge(con):
    con.execute(SCHEMA_SQL)
    for bid, bv in (
        ("humidity_favorable_high_edge_all_seasons", 50.0),
        ("humidity_acceptable_low_edge_all_seasons", 25.0),  # lower boundary_value, but not a favourable edge
    ):
        con.execute(
            "INSERT INTO evaluation_continuity_grid "
            "(evaluation_run_id, pipeline_run_id, boundary_id, channel, context, boundary_value, grid_index, input_value, method, index_value, index_class) "
            "VALUES (?, ?, ?, 'humidity', 'favourable', ?, 0, ?, 'PROPOSED_HFIS', 10.0, 'Favourable')",
            [EVAL_RUN_ID, PIPELINE_RUN_ID, bid, bv, bv],
        )
    scenario = PreferredScenario(panel="c", component="Microclimate", channel="humidity", boundary_id="humidity_favorable_low_edge_all_seasons", context="favourable")
    resolved = select_scenario(con, EVAL_RUN_ID, scenario)
    # must pick the favourable-labeled edge (50.0), not the numerically lower but non-favourable acceptable edge (25.0)
    assert resolved.resolved_boundary_id == "humidity_favorable_high_edge_all_seasons"
    assert "fallback" in resolved.selection_note


def test_select_scenario_raises_when_nothing_available(con):
    con.execute(SCHEMA_SQL)
    scenario = PreferredScenario(panel="a", component="Aerosol", channel="pm2_5", boundary_id="pm2_5_breakpoint0", context="favourable")
    with pytest.raises(ValueError, match="No boundaries found"):
        select_scenario(con, EVAL_RUN_ID, scenario)


def test_write_figure2_export_writes_csv_and_metadata(con, tmp_path):
    _populate(con)
    metadata = write_figure2_export(
        con=con, out_dir=tmp_path, evaluation_run_id=EVAL_RUN_ID, pipeline_run_id=PIPELINE_RUN_ID,
        git_commit="abc123", config_hash="hash123", expected_grid_points=N_POINTS, scenarios=SCENARIOS,
    )
    csv_path = tmp_path / "figure2_boundary_curves.csv"
    metadata_path = tmp_path / "figure2_boundary_curves_metadata.json"
    assert csv_path.is_file()
    assert metadata_path.is_file()
    assert metadata["validation"]["row_count"] == 3 * N_POINTS * 2
    assert metadata["validation"]["passed"] is True
    assert metadata["pipeline_run_id"] == PIPELINE_RUN_ID
    assert metadata["evaluation_run_id"] == EVAL_RUN_ID
    assert metadata["methods"] == ["PROPOSED-HFIS", "CRISP-CLASS-MAX"]
    with csv_path.open() as f:
        first_line = f.readline().strip()
    assert first_line == "panel,component,channel,boundary_id,context,boundary_value,boundary_unit,grid_point,input_value,distance_from_boundary,method,integrated_index,output_class"
