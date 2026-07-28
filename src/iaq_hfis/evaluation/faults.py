"""Completeness-status proportions and data-quality reason-code frequency
over an evaluation period, read from the derived DuckDB
(:class:`iaq_hfis.db.DerivedResultsWriter`'s ``iaq_index_results`` and
``observation_quality`` tables).

Per the task's evaluation requirements: unavailable metrics (e.g. a period
with zero recorded index results) must be explained, never reported as a
fabricated 0.0.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

import duckdb


@dataclass(frozen=True)
class StatusProportions:
    n_total: int
    ok: float | None
    partial: float | None
    failed: float | None


@dataclass(frozen=True)
class ReasonCodeFrequency:
    n_total_quality_rows: int
    counts: dict[str, int] = field(default_factory=dict)


def compute_status_proportions(con: duckdb.DuckDBPyConnection, pipeline_run_id: str, window_minutes: int, from_ts: datetime, to_ts: datetime) -> StatusProportions:
    rows = con.execute(
        "SELECT completeness_status, COUNT(*) FROM iaq_index_results "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? GROUP BY 1",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    counts = dict(rows)
    n_total = sum(counts.values())
    if n_total == 0:
        return StatusProportions(n_total=0, ok=None, partial=None, failed=None)
    return StatusProportions(
        n_total=n_total,
        ok=counts.get("OK", 0) / n_total,
        partial=counts.get("PARTIAL", 0) / n_total,
        failed=counts.get("FAILED", 0) / n_total,
    )


def compute_reason_code_frequency(con: duckdb.DuckDBPyConnection, pipeline_run_id: str, from_ts: datetime, to_ts: datetime, channel: str | None = None) -> ReasonCodeFrequency:
    clauses = ["pipeline_run_id = ?", "ts > ?", "ts <= ?"]
    params: list = [pipeline_run_id, from_ts, to_ts]
    if channel:
        clauses.append("channel = ?")
        params.append(channel)
    where = " WHERE " + " AND ".join(clauses)

    n_total = con.execute(f"SELECT COUNT(*) FROM observation_quality{where}", params).fetchone()[0]
    if n_total == 0:
        return ReasonCodeFrequency(n_total_quality_rows=0, counts={})

    rows = con.execute(f"SELECT UNNEST(reason_codes) AS reason FROM observation_quality{where}", params).fetchall()
    counts = Counter(r[0] for r in rows)
    return ReasonCodeFrequency(n_total_quality_rows=n_total, counts=dict(counts))
