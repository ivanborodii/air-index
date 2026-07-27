from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from iaq_hfis.config import ChannelMapEntry
from iaq_hfis.constants import QualityState
from iaq_hfis.quality.hard_checks import run_hard_checks
from iaq_hfis.quality.soft_checks import run_soft_checks

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
N = 20


def _slots():
    return [NOW + timedelta(seconds=30 * i) for i in range(N)]


def _matched(slots):
    return {s: s for s in slots}


def test_persistent_multichannel_pm_event_is_confirmed(sensor_specs, base_settings):
    slots = _slots()
    pm2_5 = [4.0] * 10 + [30.0] * 5 + [4.0] * 5  # sustained jump, corroborated by pm1 below
    pm1 = [3.0] * 10 + [22.0] * 5 + [3.0] * 5  # aux channel moves the same direction
    df = pd.DataFrame(
        {
            "ts": slots,
            "mass_pm2_5": pm2_5,
            "mass_pm1_0": pm1,
            "mass_pm4_0": pm2_5,
            "mass_pm10": [v * 1.1 for v in pm2_5],
            "number_pm2_5": [8.0] * N,
            "typical_size_um": [0.5] * N,
            "sps30_status": ["ok"] * N,
        }
    )
    matched = _matched(slots)
    channel_map = ChannelMapEntry(canonical_name="pm2_5", source_column="mass_pm2_5", device_status_column="sps30_status")
    stage1 = run_hard_checks(df, matched, "pm2_5", channel_map, sensor_specs, base_settings.device_status_state_map, pm_ordering_tolerance_pct=50.0)
    stage2 = run_soft_checks(stage1, "pm2_5", channel_map, df, outdoor_trend_sign=None, hampel_cfg=base_settings.hampel, confirmation_cfg=base_settings.confirmation)

    confirmed_rows = stage2[(stage2["ts"] >= slots[10]) & (stage2["ts"] <= slots[14])]
    assert confirmed_rows["usable"].any(), "a persistent, cross-corroborated PM event should become usable"


def test_isolated_unconfirmed_spike_stays_unusable(sensor_specs, base_settings):
    slots = _slots()
    # Small isolated spike (stays within PM1<=PM2.5<=PM4<=PM10 ordering tolerance,
    # so it only trips the Hampel/soft-check path, not the stage-1 ordering check).
    pm2_5 = [4.0] * 10 + [4.3] + [4.0] * (N - 11)
    df = pd.DataFrame(
        {
            "ts": slots,
            "mass_pm2_5": pm2_5,
            "mass_pm1_0": [3.0] * N,  # aux channel does NOT move
            "mass_pm4_0": [4.5] * N,
            "mass_pm10": [5.0] * N,
            "number_pm2_5": [8.0] * N,
            "typical_size_um": [0.5] * N,
            "sps30_status": ["ok"] * N,
        }
    )
    matched = _matched(slots)
    channel_map = ChannelMapEntry(canonical_name="pm2_5", source_column="mass_pm2_5", device_status_column="sps30_status")
    stage1 = run_hard_checks(df, matched, "pm2_5", channel_map, sensor_specs, base_settings.device_status_state_map, pm_ordering_tolerance_pct=50.0)
    stage2 = run_soft_checks(stage1, "pm2_5", channel_map, df, outdoor_trend_sign=None, hampel_cfg=base_settings.hampel, confirmation_cfg=base_settings.confirmation)

    spike_row = stage2[stage2["ts"] == slots[10]].iloc[0]
    assert spike_row["stage2_state"] == QualityState.SUSPECT.value
    assert spike_row["usable"] == False  # noqa: E712 -- isolated, uncorroborated spike never becomes usable


def test_stuck_value_detected_in_soft_checks(sensor_specs, base_settings):
    slots = _slots()
    co2 = [700.0, 705.0, 710.0] + [800.0] * 10 + [712.0, 715.0, 720.0, 718.0, 716.0, 714.0, 713.0]
    df = pd.DataFrame({"ts": slots, "co2_ppm": co2, "scd41_status": ["ok"] * N})
    matched = _matched(slots)
    channel_map = ChannelMapEntry(canonical_name="co2", source_column="co2_ppm", device_status_column="scd41_status")
    stage1 = run_hard_checks(df, matched, "co2", channel_map, sensor_specs, base_settings.device_status_state_map)
    stage2 = run_soft_checks(stage1, "co2", channel_map, df, outdoor_trend_sign=None, hampel_cfg=base_settings.hampel, confirmation_cfg=base_settings.confirmation)

    stuck_rows = stage2[(stage2["ts"] >= slots[3]) & (stage2["ts"] <= slots[12])]
    assert any("stuck_value" in codes for codes in stuck_rows["reason_codes"])


def test_raw_values_never_overwritten(sensor_specs, base_settings):
    slots = _slots()
    co2 = [700.0 + i for i in range(N)]
    df = pd.DataFrame({"ts": slots, "co2_ppm": co2, "scd41_status": ["ok"] * N})
    matched = _matched(slots)
    channel_map = ChannelMapEntry(canonical_name="co2", source_column="co2_ppm", device_status_column="scd41_status")
    stage1 = run_hard_checks(df, matched, "co2", channel_map, sensor_specs, base_settings.device_status_state_map)
    stage2 = run_soft_checks(stage1, "co2", channel_map, df, outdoor_trend_sign=None, hampel_cfg=base_settings.hampel, confirmation_cfg=base_settings.confirmation)

    assert list(stage2["raw_value"]) == pytest.approx(co2)
