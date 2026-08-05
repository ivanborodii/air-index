"""Room/season temperature profile selection.

Three profiles are currently defined (cold_period/kitchen and
warm_period/general_residential from the manuscript's DBN citation, plus
warm_period/kitchen sourced to a substitute standard, DSTU B EN 15251:2011 —
see ``config/room_profiles.yaml`` for exact citations). Adding more
room/season combinations is config-only, but a missing combination must
fail loudly rather than silently falling back to an unrelated profile.
"""

from __future__ import annotations

from datetime import datetime

from iaq_hfis.config import ConfigError, ProfileSelectionConfig, RoomProfilesConfig, RoomTemperatureProfile, TemperatureProfileNotDefinedError


def select_season(at: datetime, season_month_ranges: dict[str, list[int]]) -> str:
    month = at.month
    for season, months in season_month_ranges.items():
        if month in months:
            return season
    raise ConfigError(f"no season configured for month {month} in season_month_ranges={season_month_ranges}")


def select_room_season(
    room_profiles: RoomProfilesConfig,
    at: datetime,
    profile_selection: ProfileSelectionConfig,
    room_override: str | None = None,
) -> RoomTemperatureProfile:
    room = room_override or profile_selection.room
    season = select_season(at, profile_selection.season_month_ranges)
    profile = room_profiles.find(room, season)
    if profile is None:
        available = [(p.room, p.season) for p in room_profiles.profiles]
        raise TemperatureProfileNotDefinedError(room, season, available)
    return profile
