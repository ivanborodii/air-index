import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fixtures.build_synthetic_db import DEFAULT_ROW, create_air_monitor_db, create_weather_db, default_weather_row

from iaq_hfis.evaluate import run_evaluation
from iaq_hfis.pipeline import run_pipeline
from iaq_hfis.report import generate_plots, generate_report
from iaq_hfis.reporting.exports import COLUMNS

COMPUTED_TS = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
WINDOW_START = COMPUTED_TS - timedelta(minutes=15)


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
def reported_run(base_settings, sensor_specs, room_profiles):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), _clean_rows())
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(COMPUTED_TS - timedelta(hours=1))])

    run_summary = run_pipeline(base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)
    run_evaluation(base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15, run_id=run_summary["run_id"])
    report_result = generate_report(base_settings, run_summary["run_id"])
    return base_settings, run_summary["run_id"], report_result


def test_report_raises_clear_error_for_unknown_run_id(base_settings, sensor_specs, room_profiles):
    with pytest.raises(FileNotFoundError, match="run 'iaq_hfis run' first"):
        generate_report(base_settings, "does-not-exist")


def test_report_writes_every_csv(reported_run):
    _, _, result = reported_run
    for filename in COLUMNS:
        assert filename in result["csv_paths"]


def test_report_writes_markdown_and_json_artifacts(reported_run):
    _, _, result = reported_run
    assert Path(result["run_summary_md"]).is_file()
    assert Path(result["run_narrative_md"]).is_file()
    assert Path(result["data_dictionary"]).is_file()
    assert Path(result["plot_manifest"]).is_file()


def test_data_dictionary_matches_registry(reported_run):
    _, _, result = reported_run
    df = pd.read_csv(result["data_dictionary"])
    assert set(df["file"].unique()) == set(COLUMNS.keys())


def test_plot_manifest_is_valid_json_list(reported_run):
    _, _, result = reported_run
    manifest = json.loads(Path(result["plot_manifest"]).read_text())
    assert isinstance(manifest, list) and len(manifest) > 0


def test_narrative_traceable_to_actual_run_summary_json(reported_run, base_settings):
    _, run_id, _ = reported_run
    summary_path = Path(base_settings.paths.run_summary_dir) / f"run_summary_{run_id}.json"
    summary = json.loads(summary_path.read_text())
    narrative_path = Path(base_settings.paths.run_summary_dir).parent / "reports" / run_id / "run_narrative.md"
    narrative = narrative_path.read_text()

    assert run_id in narrative
    cs = summary["completeness_summary"]
    assert str(cs["OK"]) in narrative
    ev = summary["evaluation"]
    for method, score in ev["ground_truth"].items():
        assert f"{score['macro_f1']:.3f}" in narrative


def test_plot_raises_clear_error_before_report(base_settings, sensor_specs, room_profiles):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), _clean_rows())
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(COMPUTED_TS - timedelta(hours=1))])
    run_summary = run_pipeline(base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)
    with pytest.raises(FileNotFoundError, match="run 'iaq_hfis report"):
        generate_plots(base_settings, run_summary["run_id"])


def test_plot_renders_pngs_after_report(reported_run):
    settings, run_id, _ = reported_run
    plot_result = generate_plots(settings, run_id)
    rendered_paths = [p for p in plot_result["rendered"].values() if p is not None]
    assert len(rendered_paths) > 0
    for path in rendered_paths:
        assert Path(path).is_file()
        assert Path(path).suffix == ".png"
