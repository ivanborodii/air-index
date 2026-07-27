from datetime import datetime, timezone

import pytest

from iaq_hfis.config import ConfigError
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


def test_kitchen_warm_period_reuses_general_residential_by_author_decision(base_settings, room_profiles):
    # Author decision (2026-07-24): DBN has no kitchen-specific warm-period value,
    # so the kitchen is treated as falling under general residential requirements
    # for the warm period -- a confirmed methodological choice, not a guess.
    profile = select_room_season(room_profiles, datetime(2026, 7, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    assert (profile.room, profile.season) == ("kitchen", "warm_period")
    assert profile.provisional is False
    general_residential = room_profiles.find("general_residential", "warm_period")
    assert profile.ranges == general_residential.ranges


def test_select_room_season_room_override(base_settings, room_profiles):
    profile = select_room_season(room_profiles, datetime(2026, 7, 15, tzinfo=timezone.utc), base_settings.profile_selection, room_override="general_residential")
    assert (profile.room, profile.season) == ("general_residential", "warm_period")
