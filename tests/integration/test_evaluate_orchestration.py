import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest
from fixtures.build_synthetic_db import DEFAULT_ROW, create_air_monitor_db, create_weather_db, default_weather_row

from iaq_hfis.evaluate import run_evaluation
from iaq_hfis.pipeline import run_pipeline

# A January instant so the manuscript's kitchen/cold_period profile applies without an override.
COMPUTED_TS = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
WINDOW_START = COMPUTED_TS - timedelta(minutes=15)

EVALUATION_TABLES = [
    "baseline_results",
    "evaluation_agreement",
    "evaluation_stability_samples",
    "evaluation_stability_trials",
    "evaluation_sensitivity",
    "evaluation_masking",
    "evaluation_reference_cases",
    "evaluation_continuity_grid",
    "evaluation_continuity_summary",
]


def _oscillate(base: float, amplitude: float, i: int) -> float:
    return base + amplitude * (((i % 7) - 3) / 3.0)


def _clean_rows(n: int = 30) -> list[dict]:
    rows = []
    for i in range(n):
        ts = WINDOW_START + timedelta(seconds=30 * (i + 1))
        row = dict(DEFAULT_ROW)
        row.update(
            {
                "co2_ppm": _oscillate(700.0, 5.0, i),
                "scd_temp_c": _oscillate(19.5, 0.1, i),
                "scd_humidity_pct": _oscillate(40.0, 0.5, i),
                "bme_temp_c": _oscillate(19.5, 0.1, i),
                "bme_humidity_pct": _oscillate(40.0, 0.5, i),
                "mass_pm1_0": _oscillate(3.0, 0.1, i),
                "mass_pm2_5": _oscillate(4.0, 0.1, i),
                "mass_pm4_0": _oscillate(4.5, 0.1, i),
                "mass_pm10": _oscillate(5.0, 0.1, i),
            }
        )
        row["ts"] = ts
        row["measured_at"] = ts
        row["loaded_at"] = ts
        row["batch_id"] = f"batch-{i // 10}"
        row["row_in_batch"] = i % 10
        rows.append(row)
    return rows


@pytest.fixture
def evaluated_run(base_settings, sensor_specs, room_profiles):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), _clean_rows())
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(COMPUTED_TS - timedelta(hours=1))])

    run_summary = run_pipeline(
        base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15
    )
    eval_summary = run_evaluation(
        base_settings,
        sensor_specs,
        room_profiles,
        run_summary["pipeline_run_id"],
        COMPUTED_TS - timedelta(minutes=1),
        COMPUTED_TS + timedelta(minutes=1),
        window_minutes=15,
    )
    return run_summary, eval_summary


def test_evaluation_merges_into_existing_run_summary(evaluated_run, base_settings):
    run_summary, eval_summary = evaluated_run
    assert eval_summary["pipeline_run_id"] == run_summary["pipeline_run_id"]
    assert "evaluation" in eval_summary
    assert eval_summary["selected_evaluation_run_id"] == eval_summary["evaluation"]["evaluation_run_id"]

    summary_path = Path(base_settings.paths.run_summary_dir) / f"run_summary_{run_summary['pipeline_run_id']}.json"
    on_disk = json.loads(summary_path.read_text())
    assert "evaluation" in on_disk
    assert on_disk["pipeline_run_id"] == run_summary["pipeline_run_id"]  # core fields preserved, not overwritten


def test_evaluation_tables_created_and_populated(evaluated_run, base_settings):
    con = duckdb.connect(base_settings.paths.derived_db_path, read_only=True)
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
    assert set(EVALUATION_TABLES) <= tables

    baseline_rows = con.execute("SELECT method, COUNT(*) FROM baseline_results GROUP BY 1").fetchall()
    con.close()
    methods = {r[0] for r in baseline_rows}
    assert methods == {"CRISP-MAX", "WEIGHTED-MEAN"}


def test_evaluation_never_references_raw_tables(base_settings):
    from iaq_hfis.db import DerivedResultsWriter

    writer = DerivedResultsWriter(base_settings.paths.derived_db_path)
    tables = {r[0] for r in writer.connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
    writer.close()
    assert "raw_observations" not in tables
    assert "weather_observations" not in tables


def test_agreement_results_present_for_every_method_pair(evaluated_run):
    _, eval_summary = evaluated_run
    pairs = {(a["method_a"], a["method_b"]) for a in eval_summary["evaluation"]["agreement"]}
    assert pairs == {("CRISP-MAX", "PROPOSED-HFIS"), ("CRISP-MAX", "WEIGHTED-MEAN"), ("PROPOSED-HFIS", "WEIGHTED-MEAN")}


def test_reference_cases_scored_for_all_three_methods(evaluated_run):
    _, eval_summary = evaluated_run
    rc = eval_summary["evaluation"]["reference_cases"]
    assert set(rc.keys()) == {"PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"}
    for method, score in rc.items():
        assert score["n"] > 0
        assert score["macro_f1"] is not None


def test_sensitivity_sweep_covers_configured_windows_and_thresholds(evaluated_run, base_settings):
    _, eval_summary = evaluated_run
    sens = eval_summary["evaluation"]["sensitivity"]
    by_value = sens["by_parameter_value"]
    windows = {row["value"] for row in by_value if row["varied_parameter"] == "window_minutes"}
    thresholds = {row["value"] for row in by_value if row["varied_parameter"] == "coverage_threshold"}
    assert windows == set(base_settings.evaluation.sensitivity_window_minutes)
    assert thresholds == set(base_settings.evaluation.sensitivity_coverage_thresholds)
    assert sens["n_sample_points"] >= 1


def test_status_proportions_match_run_completeness_summary(evaluated_run):
    run_summary, eval_summary = evaluated_run
    props = eval_summary["evaluation"]["status_proportions"]
    n_total = run_summary["n_timestamps_processed"]
    assert props["n_total"] == n_total
    if n_total > 0:
        assert abs((props["OK"] or 0) + (props["PARTIAL"] or 0) + (props["FAILED"] or 0) - 1.0) < 1e-9


def test_two_evaluation_runs_do_not_mix_rows(base_settings, sensor_specs, room_profiles):
    """Mandatory regression test: two evaluation executions for the same
    pipeline run must each get their own evaluation_run_id and never mix
    rows, even when run back to back over the identical range."""
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), _clean_rows())
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(COMPUTED_TS - timedelta(hours=1))])

    run_summary = run_pipeline(
        base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15
    )
    first = run_evaluation(
        base_settings, sensor_specs, room_profiles, run_summary["pipeline_run_id"],
        COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15,
    )
    second = run_evaluation(
        base_settings, sensor_specs, room_profiles, run_summary["pipeline_run_id"],
        COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15,
    )

    first_id = first["evaluation"]["evaluation_run_id"]
    second_id = second["evaluation"]["evaluation_run_id"]
    assert first_id != second_id

    con = duckdb.connect(base_settings.paths.derived_db_path, read_only=True)
    try:
        first_rows = con.execute("SELECT COUNT(*) FROM baseline_results WHERE evaluation_run_id = ?", [first_id]).fetchone()[0]
        second_rows = con.execute("SELECT COUNT(*) FROM baseline_results WHERE evaluation_run_id = ?", [second_id]).fetchone()[0]
        assert first_rows > 0
        assert second_rows > 0
        assert first_rows == second_rows  # same underlying data, independently (re)computed, not merged

        # The run_summary.json now points at only the most recent (second) evaluation run.
        summary_path = Path(base_settings.paths.run_summary_dir) / f"run_summary_{run_summary['pipeline_run_id']}.json"
        on_disk = json.loads(summary_path.read_text())
        assert on_disk["selected_evaluation_run_id"] == second_id
    finally:
        con.close()


def test_continuity_experiment_covers_every_boundary_and_method(evaluated_run, base_settings, room_profiles):
    _, eval_summary = evaluated_run
    continuity = eval_summary["evaluation"]["continuity"]
    n_profiles = len(room_profiles.profiles)
    assert continuity["n_boundaries"] == 3 + 3 + 3 + 6 + 6 * n_profiles  # pm2_5/pm10/co2 breakpoints + humidity edges + temperature edges PER room/season profile
    assert continuity["n_contexts"] == 3
    assert set(continuity["contexts"]) == {"favorable", "acceptable", "degraded"}
    rows = continuity["by_boundary_method"]
    methods_present = {r["method"] for r in rows}
    assert methods_present == {"PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"}
    assert all(r["max_adjacent_jump"] is not None for r in rows)
    smoothness = continuity["smoothness_comparison"]
    assert smoothness["n_boundary_context_pairs_compared"] == continuity["n_boundaries"] * continuity["n_contexts"]
    assert smoothness["conclusion"]

    con = duckdb.connect(base_settings.paths.derived_db_path, read_only=True)
    try:
        evaluation_run_id = eval_summary["evaluation"]["evaluation_run_id"]
        grid_rows = con.execute("SELECT COUNT(*) FROM evaluation_continuity_grid WHERE evaluation_run_id = ?", [evaluation_run_id]).fetchone()[0]
        summary_rows = con.execute("SELECT COUNT(*) FROM evaluation_continuity_summary WHERE evaluation_run_id = ?", [evaluation_run_id]).fetchone()[0]
        assert grid_rows == continuity["n_boundaries"] * continuity["n_contexts"] * 3 * base_settings.evaluation.continuity_grid_points
        assert summary_rows == continuity["n_boundaries"] * continuity["n_contexts"] * 3
    finally:
        con.close()
