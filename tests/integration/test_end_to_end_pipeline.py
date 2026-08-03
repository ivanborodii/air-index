import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import jsonschema
import pytest
from fixtures.build_synthetic_db import DEFAULT_ROW, create_air_monitor_db, create_weather_db, default_weather_row

from iaq_hfis.config import TemperatureProfileNotDefinedError
from iaq_hfis.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_SUMMARY_SCHEMA = json.loads((REPO_ROOT / "config" / "run_summary.schema.json").read_text())

# A January instant so the manuscript's kitchen/cold_period profile (the
# only kitchen profile documented) applies without an override.
COMPUTED_TS = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
WINDOW_START = COMPUTED_TS - timedelta(minutes=15)


def _oscillate(base: float, amplitude: float, i: int) -> float:
    """Small non-repeating, non-spiky variation -- avoids both the stuck-value
    detector (never 5+ identical consecutive values) and the Hampel outlier
    detector (amplitude stays well inside a normal MAD-based threshold)."""
    return base + amplitude * (((i % 7) - 3) / 3.0)


def _clean_rows(n: int = 30, computed_ts: datetime = COMPUTED_TS, **nullify) -> list[dict]:
    """``n`` rows of otherwise-favourable, non-flat data ending at ``computed_ts``.
    Pass e.g. ``mass_pm2_5=True`` to null out a field across every row
    (simulating a fully unavailable channel)."""
    window_start = computed_ts - timedelta(minutes=15)
    rows = []
    for i in range(n):
        ts = window_start + timedelta(seconds=30 * (i + 1))
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
        for field in nullify:
            row[field] = None
        row["ts"] = ts
        row["measured_at"] = ts
        row["loaded_at"] = ts
        row["batch_id"] = f"batch-{i // 10}"
        row["row_in_batch"] = i % 10
        rows.append(row)
    return rows


@pytest.fixture
def run_and_inspect(base_settings, sensor_specs, room_profiles):
    def _run(rows, computed_ts: datetime = COMPUTED_TS, mode: str = "publication"):
        create_air_monitor_db(Path(base_settings.paths.air_monitor_db_path), rows)
        create_weather_db(Path(base_settings.paths.weather_db_path), [default_weather_row(computed_ts - timedelta(hours=1))])
        summary = run_pipeline(
            base_settings, sensor_specs, room_profiles, computed_ts - timedelta(minutes=1), computed_ts + timedelta(minutes=1), window_minutes=15, mode=mode
        )
        con = duckdb.connect(base_settings.paths.derived_db_path, read_only=True)
        result_row = con.execute(
            "SELECT completeness_status, index_value, index_class, missing_components FROM iaq_index_results WHERE computed_ts = ?", [computed_ts]
        ).fetchone()
        con.close()
        return summary, result_row

    return _run


def test_all_components_available_gives_ok(run_and_inspect):
    summary, (status, index_value, index_class, missing) = run_and_inspect(_clean_rows())
    assert status == "OK"
    assert missing == []
    assert index_value is not None
    assert index_class is not None
    assert summary["completeness_summary"]["OK"] >= 1


def test_one_missing_component_gives_partial(run_and_inspect):
    # Temperature AND humidity both null -> M unavailable, A and V still available -> PARTIAL
    summary, (status, index_value, index_class, missing) = run_and_inspect(_clean_rows(bme_temp_c=True, scd_temp_c=True, bme_humidity_pct=True, scd_humidity_pct=True))
    assert status == "PARTIAL"
    assert missing == ["M"]
    assert index_value is not None  # still computed from the remaining components
    assert index_class is not None


def test_two_missing_components_gives_failed(run_and_inspect):
    # PM (A) and temperature/humidity (M) both null -> only V (CO2) available -> FAILED
    summary, (status, index_value, index_class, missing) = run_and_inspect(
        _clean_rows(mass_pm2_5=True, mass_pm10=True, bme_temp_c=True, scd_temp_c=True, bme_humidity_pct=True, scd_humidity_pct=True)
    )
    assert status == "FAILED"
    assert set(missing) == {"A", "M"}
    assert index_value is None  # never a placeholder number
    assert index_class is None


def test_cold_period_kitchen_default_config_is_provisional_param_free(run_and_inspect):
    # provisional_parameters_used is the single authoritative catalog
    # (iaq_hfis.provenance.engaged_provisional_paths), which always includes
    # every config-level PROVISIONAL parameter (e.g. Hampel filter settings).
    # kitchen/cold_period is not itself a provisional room profile in the
    # current config, so no room_profiles.* path should appear.
    winter_ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    summary, row = run_and_inspect(_clean_rows(computed_ts=winter_ts), computed_ts=winter_ts)
    assert row[0] == "OK"
    assert summary["mode"] == "publication"
    assert summary["provisional_parameters_used"]  # config-level PROVISIONAL params are always engaged
    assert not any(p.startswith("room_profiles.") for p in summary["provisional_parameters_used"])


def test_publication_mode_blocks_warm_period_kitchen_run(run_and_inspect):
    # DBN Table D.4 has no room-specific value for a standalone kitchen in
    # the warm period. Publication mode (the default) must abort the entire
    # run rather than silently substituting or omitting the microclimate
    # component for a "full" A/V/M/I result.
    summer_ts = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(TemperatureProfileNotDefinedError) as exc_info:
        run_and_inspect(_clean_rows(computed_ts=summer_ts), computed_ts=summer_ts)
    err = exc_info.value
    assert err.requested_room == "kitchen"
    assert err.requested_season == "warm_period"


def test_exploratory_mode_omits_microclimate_for_warm_period_kitchen(run_and_inspect):
    # Exploratory mode never fabricates the microclimate component: with no
    # DBN profile for kitchen/warm_period, M is structurally omitted (like a
    # genuinely missing component), and A/V still produce a PARTIAL result.
    summer_ts = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    summary, (status, index_value, index_class, missing) = run_and_inspect(
        _clean_rows(computed_ts=summer_ts), computed_ts=summer_ts, mode="exploratory"
    )
    assert summary["mode"] == "exploratory"
    assert status == "PARTIAL"
    assert missing == ["M"]
    assert index_value is not None
    assert index_class is not None


def test_provisional_room_profile_usage_is_tracked_in_run_summary(run_and_inspect, room_profiles, base_settings):
    # Exercises the tracking mechanism itself (pipeline.py:
    # RuntimeContext.provisional_profiles_used, surfaced through
    # provenance.engaged_provisional_paths) independent of which real
    # profiles happen to be provisional today. The engaged entry is reported
    # by its actual provenance path (room_profiles.<room>/<season>.transition_width),
    # not the raw internal event string -- that path is what parameter_provenance.csv
    # and every other artifact key off of. Uses general_residential/warm_period
    # (a real, currently-non-provisional profile) rather than the now-removed
    # kitchen/warm_period, temporarily marking it provisional for this test.
    summer_ts = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    base_settings.profile_selection.room = "general_residential"
    profile = room_profiles.find("general_residential", "warm_period")
    profile.provisional = True

    summary, row = run_and_inspect(_clean_rows(computed_ts=summer_ts), computed_ts=summer_ts)
    assert row[0] == "OK"
    assert "room_profiles.general_residential/warm_period.transition_width" in summary["provisional_parameters_used"]


def test_run_summary_json_validates_against_schema(run_and_inspect):
    summary, _ = run_and_inspect(_clean_rows())
    jsonschema.validate(instance=summary, schema=RUN_SUMMARY_SCHEMA)


def test_run_summary_file_is_written_and_matches_returned_summary(run_and_inspect, base_settings):
    summary, _ = run_and_inspect(_clean_rows())
    summary_dir = Path(base_settings.paths.run_summary_dir)
    files = list(summary_dir.glob("run_summary_*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert on_disk == summary
