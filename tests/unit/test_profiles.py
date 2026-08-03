from datetime import datetime, timezone

import pytest

from iaq_hfis.config import ConfigError, TemperatureProfileNotDefinedError
from iaq_hfis.profiles import select_room_season, select_season


def test_select_season_cold_period(base_settings):
    season = select_season(datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection.season_month_ranges)
    assert season == "cold_period"


def test_select_season_warm_period(base_settings):
    season = select_season(datetime(2026, 7, 15, tzinfo=timezone.utc), base_settings.profile_selection.season_month_ranges)
    assert season == "warm_period"


def test_select_room_season_returns_correct_profile(base_settings, room_profiles):
    profile = select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    assert (profile.room, profile.season) == ("kitchen", "cold_period")


def test_select_room_season_fails_loudly_for_missing_combo(base_settings, room_profiles):
    # general_residential/cold_period is genuinely absent from room_profiles.yaml
    with pytest.raises(ConfigError) as exc_info:
        select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection, room_override="general_residential")
    msg = str(exc_info.value)
    assert "general_residential" in msg and "cold_period" in msg
    assert "kitchen" in msg  # lists the available profiles, doesn't just say "not found"


def test_kitchen_warm_period_raises_temperature_profile_not_defined(base_settings, room_profiles):
    # DBN Table D.4 has a literal dash for the standalone-kitchen row in the
    # warm-period column -- no room-specific value is defined. The system must
    # fail loudly with a structured error rather than silently reusing
    # general_residential/warm_period's numbers for a different room.
    with pytest.raises(TemperatureProfileNotDefinedError) as exc_info:
        select_room_season(room_profiles, datetime(2026, 7, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    err = exc_info.value
    assert err.requested_room == "kitchen"
    assert err.requested_season == "warm_period"
    assert ("kitchen", "cold_period") in err.available_profiles
    assert ("general_residential", "warm_period") in err.available_profiles
    assert "TEMPERATURE_PROFILE_NOT_DEFINED" in str(err)
    assert "DBN" in err.dbn_source


def test_select_room_season_room_override(base_settings, room_profiles):
    profile = select_room_season(room_profiles, datetime(2026, 7, 15, tzinfo=timezone.utc), base_settings.profile_selection, room_override="general_residential")
    assert (profile.room, profile.season) == ("general_residential", "warm_period")
