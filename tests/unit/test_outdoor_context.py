from datetime import datetime, timedelta, timezone

from iaq_hfis.outdoor_context import _USED_OUTDOOR_FIELDS, compute_outdoor_trend_signs, fetch_outdoor_context

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


def test_carbon_monoxide_never_among_used_outdoor_fields():
    assert "carbon_monoxide" not in _USED_OUTDOOR_FIELDS


def test_trend_sign_rising():
    current = {"pm2_5": 20.0, "temperature_2m": 25.0}
    previous = {"pm2_5": 10.0, "temperature_2m": 25.0}
    signs = compute_outdoor_trend_signs(current, previous)
    assert signs["pm2_5"] == 1
    assert signs["temperature"] == 0


def test_trend_sign_falling():
    current = {"pm2_5": 5.0}
    previous = {"pm2_5": 10.0}
    signs = compute_outdoor_trend_signs(current, previous)
    assert signs["pm2_5"] == -1


def test_trend_sign_none_when_data_missing():
    signs = compute_outdoor_trend_signs(None, {"pm2_5": 10.0})
    assert all(v is None for v in signs.values())


class _FakeSource:
    def __init__(self, responses: dict):
        self._responses = responses

    def fetch_outdoor_asof(self, ts):
        return self._responses.get(ts)


def test_stale_outdoor_context_is_flagged():
    old_forecast = NOW - timedelta(hours=5)
    source = _FakeSource({NOW: {"forecast_time": old_forecast, "pm2_5": 5.0, "pm10": 8.0, "temperature_2m": 20.0, "relative_humidity_2m": 50.0}})
    ctx = fetch_outdoor_context(source, NOW, max_age_minutes=90.0)
    assert ctx["is_stale"] is True


def test_fresh_outdoor_context_not_flagged():
    recent_forecast = NOW - timedelta(minutes=10)
    source = _FakeSource({NOW: {"forecast_time": recent_forecast, "pm2_5": 5.0, "pm10": 8.0, "temperature_2m": 20.0, "relative_humidity_2m": 50.0}})
    ctx = fetch_outdoor_context(source, NOW, max_age_minutes=90.0)
    assert ctx["is_stale"] is False
    assert ctx["age_minutes"] == 10.0


def test_no_outdoor_data_is_stale():
    source = _FakeSource({})
    ctx = fetch_outdoor_context(source, NOW, max_age_minutes=90.0)
    assert ctx["is_stale"] is True
    assert ctx["forecast_time"] is None
