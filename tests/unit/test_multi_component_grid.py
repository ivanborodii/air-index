from datetime import datetime, timezone

from iaq_hfis import profiles
from iaq_hfis.evaluation.multi_component_grid import (
    METHODS,
    run_multi_component_grid,
    summarize_multi_component_grid,
    weighted_mean_masking_rate,
)
from iaq_hfis.pipeline import build_runtime_context

RAW_COLUMNS = {
    "ts", "co2_ppm", "scd_temp_c", "scd_humidity_pct", "bme_temp_c", "bme_humidity_pct",
    "mass_pm1_0", "mass_pm2_5", "mass_pm4_0", "mass_pm10", "number_pm0_5", "number_pm1_0",
    "number_pm2_5", "number_pm4_0", "number_pm10", "typical_size_um",
    "sensor_status", "scd41_status", "bme688_status", "sps30_status",
}


def _ctx(base_settings, sensor_specs, room_profiles):
    return build_runtime_context(base_settings, sensor_specs, room_profiles, RAW_COLUMNS)


def test_grid_row_count_matches_n_points_cubed(base_settings, sensor_specs, room_profiles):
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows = run_multi_component_grid(ctx, 5)
    assert len(rows) == 5**3


def test_grid_default_axis_matches_spec_worked_example(base_settings, sensor_specs, room_profiles):
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows = run_multi_component_grid(ctx, 41)
    assert len(rows) == 68_921


def test_all_four_corners_agree_on_class(base_settings, sensor_specs, room_profiles):
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows = run_multi_component_grid(ctx, 3)  # {0, 50, 100}
    all_favorable = next(r for r in rows if r.a == 0.0 and r.v == 0.0 and r.m == 0.0)
    assert all_favorable.hfis_index_class == "Favourable"
    assert all_favorable.fuzzy_component_max_index_class == "Favourable"
    assert all_favorable.crisp_class_max_index_class == "Favourable"
    assert all_favorable.weighted_mean_index_class == "Favourable"

    all_critical = next(r for r in rows if r.a == 100.0 and r.v == 100.0 and r.m == 100.0)
    for cls in (
        all_critical.hfis_index_class, all_critical.fuzzy_component_max_index_class,
        all_critical.crisp_class_max_index_class, all_critical.weighted_mean_index_class,
    ):
        assert cls == "Critical"


def test_hfis_not_numerically_equivalent_to_fuzzy_component_max(base_settings, sensor_specs, room_profiles):
    # Regression guard for the finding in docs/hfis_vs_crispmax_audit.md
    # section 2: once more than one component carries signal, PROPOSED_HFIS
    # must diverge numerically from FUZZY_COMPONENT_MAX on a non-trivial
    # fraction of the grid (it may still agree at extremes/single-signal
    # points, so this checks the aggregate, not every point).
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows = run_multi_component_grid(ctx, 11)
    summaries = summarize_multi_component_grid(rows)
    hfis_vs_fuzzy = next(s for s in summaries if {s.method_a, s.method_b} == {"PROPOSED_HFIS", "FUZZY_COMPONENT_MAX"})
    assert hfis_vs_fuzzy.mean_abs_diff > 1.0
    assert hfis_vs_fuzzy.n_class_disagreements == 0  # class-level agreement was 100% in the audit's coarse sample too


def test_summary_covers_all_six_pairs(base_settings, sensor_specs, room_profiles):
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows = run_multi_component_grid(ctx, 3)
    summaries = summarize_multi_component_grid(rows)
    pairs = {frozenset((s.method_a, s.method_b)) for s in summaries}
    assert len(pairs) == 6
    assert len(METHODS) == 4


def test_weighted_mean_masking_rate_is_high_on_the_grid(base_settings, sensor_specs, room_profiles):
    # One component pinned Critical with the other two Favourable should be
    # masked by WEIGHTED_MEAN's arithmetic mean far more often than not.
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows = run_multi_component_grid(ctx, 5)
    masking = weighted_mean_masking_rate(rows)
    assert masking["n_critical_events"] > 0
    assert masking["masking_rate"] > 0.5


def test_grid_is_deterministic(base_settings, sensor_specs, room_profiles):
    ctx = _ctx(base_settings, sensor_specs, room_profiles)
    rows_a = run_multi_component_grid(ctx, 5)
    rows_b = run_multi_component_grid(ctx, 5)
    assert rows_a == rows_b
