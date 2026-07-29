"""Expected time-slot grid for the rolling-window aggregation.

The grid is defined purely by arithmetic on ``computed_ts`` (the instant the
index is being computed for) — it never depends on which raw timestamps
actually exist, so it is deterministic and reproducible independent of
sensor jitter or gaps.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def expected_slots(computed_ts: datetime, window_minutes: int, cadence_seconds: int) -> list[datetime]:
    """The right-aligned window (computed_ts - window, computed_ts] as a list
    of expected sample instants, spaced ``cadence_seconds`` apart and
    anchored at ``computed_ts`` (not an absolute epoch).

    A 15-minute window at 30 s cadence yields exactly 30 slots.
    """
    if window_minutes <= 0 or cadence_seconds <= 0:
        raise ValueError("window_minutes and cadence_seconds must be positive")
    n_slots = (window_minutes * 60) // cadence_seconds
    step = timedelta(seconds=cadence_seconds)
    # slots at computed_ts, computed_ts - step, ..., computed_ts - (n_slots-1)*step
    return [computed_ts - i * step for i in range(n_slots - 1, -1, -1)]


def align_computed_timestamps(
    range_start: datetime, range_end: datetime, recompute_interval_minutes: int
) -> list[datetime]:
    """Deterministic, floor-aligned recompute instants in ``(range_start, range_end]``.

    Alignment is to interval boundaries (minute % interval == 0, second=0,
    microsecond=0) so the same [range_start, range_end] always yields the
    same set of computed_ts values regardless of when the pipeline happens
    to run.
    """
    if recompute_interval_minutes <= 0:
        raise ValueError("recompute_interval_minutes must be positive")
    interval = timedelta(minutes=recompute_interval_minutes)

    floor_start = range_start.replace(second=0, microsecond=0)
    excess_minutes = floor_start.minute % recompute_interval_minutes
    floor_start -= timedelta(minutes=excess_minutes)
    if floor_start <= range_start:
        floor_start += interval

    out = []
    t = floor_start
    while t <= range_end:
        out.append(t)
        t += interval
    return out


def match_actual_to_slots(
    expected: list[datetime], actual: pd.Series, tolerance_seconds: float
) -> dict[datetime, datetime | None]:
    """Match each expected slot to the nearest actual timestamp within tolerance.

    Each actual timestamp is used by at most one expected slot: matching is
    greedy nearest-first (globally, by absolute time difference), with ties
    broken by the earliest actual timestamp, so a duplicate/near-duplicate
    raw row is never double-counted across two expected slots.
    """
    actual_sorted = sorted(pd.to_datetime(actual).tolist())
    candidates: list[tuple[float, datetime, datetime]] = []
    tol = timedelta(seconds=tolerance_seconds)
    for slot in expected:
        lo, hi = slot - tol, slot + tol
        for ts in actual_sorted:
            if lo <= ts <= hi:
                diff = abs((ts - slot).total_seconds())
                candidates.append((diff, slot, ts))

    candidates.sort(key=lambda c: (c[0], c[2]))

    result: dict[datetime, datetime | None] = {slot: None for slot in expected}
    used_actual: set[datetime] = set()
    for _diff, slot, ts in candidates:
        if result[slot] is not None or ts in used_actual:
            continue
        result[slot] = ts
        used_actual.add(ts)
    return result


def align_columns_to_slots(raw_df: pd.DataFrame, matched_slots: dict[datetime, datetime | None], columns: list[str]) -> pd.DataFrame:
    """Reindex selected ``raw_df`` columns onto the expected-slot grid, using
    ``matched_slots`` (from :func:`match_actual_to_slots`) — unmatched slots
    get NaN rows. Used to bring auxiliary/secondary raw columns (PM1/PM4,
    the duplicate T/RH channel, ...) onto the same per-slot index as a
    channel's own quality dataframe for cross-channel confirmation checks.
    """
    indexed = raw_df.set_index("ts")
    rows = []
    for actual_ts in matched_slots.values():
        if actual_ts is None:
            rows.append({c: float("nan") for c in columns})
            continue
        record = indexed.loc[actual_ts]
        if isinstance(record, pd.DataFrame):
            record = record.iloc[0]
        rows.append({c: record.get(c) for c in columns})
    return pd.DataFrame(rows, index=list(matched_slots.keys()))
