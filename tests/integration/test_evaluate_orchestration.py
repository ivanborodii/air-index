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
    "evaluation_stability",
    "evaluation_sensitivity",
    "evaluation_masking",
    "evaluation_ground_truth",
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
        COMPUTED_TS - timedelta(minutes=1),
        COMPUTED_TS + timedelta(minutes=1),
        window_minutes=15,
        run_id=run_summary["run_id"],
    )
    return run_summary, eval_summary


def test_evaluation_merges_into_existing_run_summary(evaluated_run, base_settings):
    run_summary, eval_summary = evaluated_run
    assert eval_summary["run_id"] == run_summary["run_id"]
    assert "evaluation" in eval_summary

    summary_path = Path(base_settings.paths.run_summary_dir) / f"run_summary_{run_summary['run_id']}.json"
    on_disk = json.loads(summary_path.read_text())
    assert "evaluation" in on_disk
    assert on_disk["run_id"] == run_summary["run_id"]  # core fields preserved, not overwritten


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


def test_ground_truth_scored_for_all_three_methods(evaluated_run):
    _, eval_summary = evaluated_run
    gt = eval_summary["evaluation"]["ground_truth"]
    assert set(gt.keys()) == {"PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"}
    for method, score in gt.items():
        assert score["n"] > 0
        assert score["macro_f1"] is not None


def test_sensitivity_sweep_covers_configured_windows_and_thresholds(evaluated_run, base_settings):
    _, eval_summary = evaluated_run
    sens = eval_summary["evaluation"]["sensitivity"]
    windows = {s["value"] for s in sens if s["varied_parameter"] == "window_minutes"}
    thresholds = {s["value"] for s in sens if s["varied_parameter"] == "coverage_threshold"}
    assert windows == set(base_settings.evaluation.sensitivity_window_minutes)
    assert thresholds == set(base_settings.evaluation.sensitivity_coverage_thresholds)


def test_status_proportions_match_run_completeness_summary(evaluated_run):
    run_summary, eval_summary = evaluated_run
    props = eval_summary["evaluation"]["status_proportions"]
    n_total = run_summary["n_timestamps_processed"]
    assert props["n_total"] == n_total
    if n_total > 0:
        assert abs((props["OK"] or 0) + (props["PARTIAL"] or 0) + (props["FAILED"] or 0) - 1.0) < 1e-9
