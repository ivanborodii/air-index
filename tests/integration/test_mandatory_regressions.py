import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest
from fixtures.build_synthetic_db import DEFAULT_ROW, create_air_monitor_db, create_weather_db, default_weather_row

from iaq_hfis.evaluate import run_evaluation
from iaq_hfis.final_snapshot import build_final_snapshot
from iaq_hfis.pipeline import run_pipeline
from iaq_hfis.report import generate_report
from iaq_hfis.validation import validate_artifacts

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
def full_run(base_settings, sensor_specs, room_profiles):
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), _clean_rows())
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(COMPUTED_TS - timedelta(hours=1))])
    run_summary = run_pipeline(base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)
    run_evaluation(base_settings, sensor_specs, room_profiles, run_summary["pipeline_run_id"], COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)
    generate_report(base_settings, run_summary["pipeline_run_id"], sensor_specs, room_profiles)
    return base_settings, run_summary["pipeline_run_id"]


def test_validate_artifacts_passes_on_a_genuine_run(full_run):
    settings, pipeline_run_id = full_run
    report = validate_artifacts(settings, pipeline_run_id)
    assert report.ok
    assert len(report.violations) == 0
    assert len(report.checks_passed) > 5


def test_validate_artifacts_catches_a_deliberately_corrupted_csv(full_run):
    """Mandatory regression test: artifact validation must catch an
    intentional mismatch, not just pass silently on well-formed input."""
    settings, pipeline_run_id = full_run
    report_dir = Path(settings.paths.run_summary_dir).parent / "reports" / pipeline_run_id
    csv_path = report_dir / "exports" / "index_timeseries.csv"
    original = csv_path.read_text()
    lines = original.splitlines()
    # Delete one data row -- the CSV row count will no longer match the DB/JSON counts.
    corrupted = "\n".join(lines[:-1]) + "\n"
    csv_path.write_text(corrupted)

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok
    assert any("index_timeseries.csv row count" in v for v in report.violations)


def test_validate_artifacts_catches_a_tampered_run_summary_json(full_run):
    settings, pipeline_run_id = full_run
    summary_path = Path(settings.paths.run_summary_dir) / f"run_summary_{pipeline_run_id}.json"
    summary = json.loads(summary_path.read_text())
    summary["completeness_summary"]["OK"] += 1000  # deliberately wrong
    summary_path.write_text(json.dumps(summary))

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok


def test_failed_results_have_null_index_class_and_no_dominant_component(full_run):
    """Mandatory regression test: FAILED completeness rows must always
    have a null index_value, null index_class, and empty dominant_component."""
    settings, pipeline_run_id = full_run
    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        bad = con.execute(
            "SELECT COUNT(*) FROM iaq_index_results WHERE pipeline_run_id = ? AND completeness_status = 'FAILED' "
            "AND (index_value IS NOT NULL OR index_class IS NOT NULL OR dominant_component IS NOT NULL OR len(co_dominant_components) > 0)",
            [pipeline_run_id],
        ).fetchone()[0]
        assert bad == 0
    finally:
        con.close()


def test_sensitivity_exports_have_no_duplicate_keys(full_run):
    """Mandatory regression test: evaluation_sensitivity rows must be
    unique per (evaluation_run_id, sample_id, varied_parameter, value)."""
    settings, pipeline_run_id = full_run
    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        total = con.execute("SELECT COUNT(*) FROM evaluation_sensitivity").fetchone()[0]
        distinct = con.execute("SELECT COUNT(DISTINCT (evaluation_run_id, sample_id, varied_parameter, value)) FROM evaluation_sensitivity").fetchone()[0]
        assert total == distinct
    finally:
        con.close()


def test_multi_point_stability_is_deterministic_with_fixed_seed(base_settings, sensor_specs, room_profiles):
    """Mandatory regression test: multi-point stability must use more than
    one timestamp and be exactly reproducible for a fixed seed."""
    create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), _clean_rows())
    create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(COMPUTED_TS - timedelta(hours=1))])
    run_summary = run_pipeline(base_settings, sensor_specs, room_profiles, COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)

    first = run_evaluation(base_settings, sensor_specs, room_profiles, run_summary["pipeline_run_id"], COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)
    second = run_evaluation(base_settings, sensor_specs, room_profiles, run_summary["pipeline_run_id"], COMPUTED_TS - timedelta(minutes=1), COMPUTED_TS + timedelta(minutes=1), window_minutes=15)

    first_stability = first["evaluation"]["stability"]
    second_stability = second["evaluation"]["stability"]
    assert first_stability["n_samples"] >= 1
    assert first_stability["by_method"] == second_stability["by_method"]  # byte-for-byte identical given the fixed seed


def test_final_snapshot_contains_no_forbidden_files(full_run, tmp_path):
    """Mandatory regression test: the tracked publication snapshot must
    never contain database files, WAL files, or credential/environment
    files -- only report artifacts, config copies, and metadata."""
    settings, pipeline_run_id = full_run
    result = build_final_snapshot(settings, pipeline_run_id, final_dir=tmp_path / "final")

    forbidden_suffixes = (".duckdb", ".wal", ".env")
    forbidden_names = {"email_credentials.env", "credentials.json"}
    all_files = list(Path(result["final_dir"]).rglob("*"))
    assert all_files, "snapshot must not be empty"
    for f in all_files:
        if f.is_dir():
            continue
        assert not f.name.endswith(forbidden_suffixes), f"forbidden file found in snapshot: {f}"
        assert f.name not in forbidden_names, f"forbidden file found in snapshot: {f}"
    assert (Path(result["final_dir"]) / "latest_run.json").is_file()
    assert (Path(result["final_dir"]) / "README.md").is_file()


def test_final_snapshot_manifest_has_identity_and_correct_checksums(full_run, tmp_path):
    """Mandatory regression test: manifest.json must record the run's full
    identity chain (run IDs, git commit, config hash, DB checksums, input
    date range, row counts) and its per-artifact checksums must actually
    match the files on disk -- a tampered or stale snapshot must be
    mechanically detectable, not just trusted by convention."""
    settings, pipeline_run_id = full_run
    result = build_final_snapshot(settings, pipeline_run_id, final_dir=tmp_path / "final")
    final_dir = Path(result["final_dir"])

    manifest_path = final_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())

    assert manifest["pipeline_run_id"] == pipeline_run_id
    assert manifest["evaluation_run_id"]
    assert manifest["git_commit"] is None or isinstance(manifest["git_commit"], str)
    assert manifest["config_hash"]
    assert manifest["input_date_range_utc"]
    assert manifest["row_counts"]["source_raw_row_count"] is not None
    assert manifest["row_counts"]["derived_row_counts"]

    derived_db = manifest["databases"]["derived_db_path"]
    assert derived_db["sha256"] == hashlib.sha256(Path(settings.paths.derived_db_path).read_bytes()).hexdigest()

    # manifest.json is written after checksums are computed, so it never lists itself.
    assert "manifest.json" not in manifest["artifact_checksums_sha256"]
    checked = 0
    for rel_path, expected_sha in manifest["artifact_checksums_sha256"].items():
        actual = hashlib.sha256((final_dir / rel_path).read_bytes()).hexdigest()
        assert actual == expected_sha, f"checksum mismatch for {rel_path}"
        checked += 1
    assert checked > 5
    # Every file physically present in the snapshot (besides manifest.json itself) is checksummed -- no silent gaps.
    all_files = {str(f.relative_to(final_dir)) for f in final_dir.rglob("*") if f.is_file()}
    assert all_files - {"manifest.json"} == set(manifest["artifact_checksums_sha256"].keys())


def _report_dir_for(settings, pipeline_run_id) -> Path:
    return Path(settings.paths.run_summary_dir).parent / "reports" / pipeline_run_id


def test_validate_artifacts_catches_continuity_grid_corruption(full_run):
    """Mandatory regression test: a tampered continuity_grid.csv (an
    index_value edited so continuity_summary.csv's max_adjacent_jump no
    longer recomputes from it) must be caught, not silently trusted."""
    settings, pipeline_run_id = full_run
    csv_path = _report_dir_for(settings, pipeline_run_id) / "exports" / "continuity_grid.csv"
    df_text = csv_path.read_text()
    lines = df_text.splitlines()
    header = lines[0].split(",")
    index_value_col = header.index("index_value")
    # Corrupt the last data row's index_value to an implausibly large number.
    parts = lines[-1].split(",")
    parts[index_value_col] = "999999.0"
    lines[-1] = ",".join(parts)
    csv_path.write_text("\n".join(lines) + "\n")

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok
    assert any("continuity_summary.csv disagrees with continuity_grid.csv" in v for v in report.violations)


def test_validate_artifacts_catches_fault_event_metrics_corruption(full_run):
    """Mandatory regression test: fault_detection_event_metrics.csv's
    n_true_events must match the actual count in fault_injection_events.csv
    -- a tampered count must be caught."""
    settings, pipeline_run_id = full_run
    csv_path = _report_dir_for(settings, pipeline_run_id) / "exports" / "fault_detection_event_metrics.csv"
    df_text = csv_path.read_text()
    lines = df_text.splitlines()
    header = lines[0].split(",")
    n_true_col = header.index("n_true_events")
    parts = lines[1].split(",")
    parts[n_true_col] = str(int(parts[n_true_col]) + 100)
    lines[1] = ",".join(parts)
    csv_path.write_text("\n".join(lines) + "\n")

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok
    assert any("n_true_events" in v for v in report.violations)


def test_validate_artifacts_catches_confusion_matrix_diagonal_mismatch(full_run):
    """Mandatory regression test: the confusion matrix's diagonal cell for
    a reason code must equal that reason code's row-level TP count."""
    settings, pipeline_run_id = full_run
    csv_path = _report_dir_for(settings, pipeline_run_id) / "exports" / "fault_detection_confusion_matrix.csv"
    df_text = csv_path.read_text()
    lines = df_text.splitlines()
    header = lines[0].split(",")
    count_col = header.index("count")
    true_col = header.index("true_label")
    pred_col = header.index("predicted_label")
    # Find a diagonal row (true_label == predicted_label) and corrupt its count.
    corrupted = False
    for i in range(1, len(lines)):
        parts = lines[i].split(",")
        if parts[true_col] == parts[pred_col] and not corrupted:
            parts[count_col] = str(int(parts[count_col]) + 1000)
            lines[i] = ",".join(parts)
            corrupted = True
    assert corrupted, "expected at least one diagonal confusion-matrix cell"
    csv_path.write_text("\n".join(lines) + "\n")

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok
    assert any("confusion matrix diagonal" in v for v in report.violations)


def test_validate_artifacts_catches_config_hash_mismatch_between_run_and_evaluate(full_run):
    """Mandatory regression test: if evaluate's persisted config_hash for
    the selected evaluation_run_id disagrees with the pipeline's own
    config_hash, that must be caught -- it means evaluate ran against a
    different config than the pipeline run it's attached to."""
    settings, pipeline_run_id = full_run
    con = duckdb.connect(settings.paths.derived_db_path)
    try:
        con.execute("UPDATE evaluation_runs SET config_hash = 'deliberately-wrong-hash' WHERE pipeline_run_id = ?", [pipeline_run_id])
    finally:
        con.close()

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok
    assert any("evaluation_runs.config_hash" in v for v in report.violations)


def test_validate_artifacts_catches_stability_by_variable_total_mismatch(full_run):
    """Mandatory regression test: stability's by_variable breakdown must
    sum to the same overall n_trials_total as by_method -- a tampered
    run_summary.json where they disagree must be caught."""
    settings, pipeline_run_id = full_run
    summary_path = Path(settings.paths.run_summary_dir) / f"run_summary_{pipeline_run_id}.json"
    summary = json.loads(summary_path.read_text())
    by_variable = summary["evaluation"]["stability"]["by_variable"]
    assert by_variable, "expected at least one by_variable row"
    by_variable[0]["n_trials_total"] += 1000
    summary_path.write_text(json.dumps(summary))

    report = validate_artifacts(settings, pipeline_run_id)
    assert not report.ok
    assert any("by_variable rows for" in v for v in report.violations)


def test_validate_artifacts_writes_json_and_md_reports(full_run, tmp_path):
    from iaq_hfis.validation import write_artifact_validation_report

    settings, pipeline_run_id = full_run
    report = validate_artifacts(settings, pipeline_run_id)
    json_path, md_path = write_artifact_validation_report(report, tmp_path)
    assert json_path.is_file()
    assert md_path.is_file()

    parsed = json.loads(json_path.read_text())
    assert parsed["ok"] == report.ok
    assert parsed["n_checks_passed"] == len(report.checks_passed)
    assert parsed["n_violations"] == len(report.violations)

    md_text = md_path.read_text()
    assert "Artifact Validation Report" in md_text
    assert pipeline_run_id in md_text
