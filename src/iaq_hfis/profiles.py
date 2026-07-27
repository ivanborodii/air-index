"""Room/season temperature profile selection.

Only two profiles are given numerically in the manuscript
(cold_period/kitchen, warm_period/general_residential — see
``config/room_profiles.yaml``). Adding more room/season combinations is
config-only, but a missing combination must fail loudly rather than
silently falling back to an unrelated profile.
"""

from __future__ import annotations

from datetime import datetime

from iaq_hfis.config import ConfigError, ProfileSelectionConfig, RoomProfilesConfig, RoomTemperatureProfile


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
        raise ConfigError(
            f"no room profile configured for (room='{room}', season='{season}'); "
            f"available profiles: {available}"
        )
    return profile
