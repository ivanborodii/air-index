"""Read-only access to the live air-monitor databases, and a writer for
iaq_hfis's own derived-results database.

``air_monitor.duckdb`` is held open read-write for the entire lifetime of
the separate, continuously-running collection service
(``air-monitor/scripts/run_pipeline.py``), so a second process cannot open
it ``read_only=True`` while that service runs (DuckDB allows either one
read-write connection, or N read-only connections — never both at once).
This module reuses the snapshot technique already established in
``air-monitor/scripts/send_daily_report.py``: copy the ``.duckdb`` (+
``.wal``) file with a plain filesystem read (``shutil.copy2``, which does
not contend with DuckDB's connection-level lock) and open the copy
read-only. ``weather.duckdb`` is written only briefly, once an hour, by a
cron job, so it is opened read-only directly with a short retry.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

import duckdb
import pandas as pd

from iaq_hfis.config import Settings

logger = logging.getLogger(__name__)

#: Run-isolated schema: every run-dependent table carries pipeline_run_id
#: (and, for evaluation tables, evaluation_run_id). Version 1 (pre-isolation)
#: rows must never be silently reinterpreted as version 2 rows -- see
#: LegacySchemaError below and iaq_hfis.cli's rebuild-db command.
#: Version 3: evaluation_continuity_grid/evaluation_continuity_summary gained
#: a `context` column (favorable/acceptable/degraded) and new summary metrics
#: (median/p95 adjacent jump, local_lipschitz_ratio, area_between_curves_vs_crisp_max).
#: Version 4: iaq_index_results.dominant_component changed from VARCHAR[] to a
#: single VARCHAR (the deterministic priority-hierarchy result), plus new
#: co_dominant_components/worst_component_class/largest_component_score/
#: dominance_reason columns -- see fuzzy_engine.determine_dominance.
#: Version 5: fault_injection_events/fault_detection_predictions/
#: fault_detection_metrics gained a dataset_split column (calibration |
#: validation); fault_detection_metrics gained tn/specificity; two new
#: tables (fault_detection_event_metrics, fault_detection_confusion_matrix).
#: Version 6: pipeline_runs gained a mode column (publication | exploratory)
#: -- see profiles.select_room_season / TEMPERATURE_PROFILE_NOT_DEFINED.
#: Version 7: new CRISP_CLASS_MAX baseline (genuinely hard/discontinuous,
#: spec section 6.2) added alongside FUZZY_COMPONENT_MAX (renamed from
#: CRISP-MAX), PROPOSED_HFIS, WEIGHTED_MEAN (renamed from WEIGHTED-MEAN);
#: evaluation_stability_samples gained baseline_class_crisp_class_max /
#: baseline_index_crisp_class_max columns.
#: Version 8: new evaluation_multi_component_grid /
#: evaluation_multi_component_grid_summary tables (spec section 7.2).
SCHEMA_VERSION = 8

#: Tables whose presence with a pre-isolation column set indicates a legacy
#: (schema version 1) derived database.
_RUN_ISOLATED_TABLES = (
    "observation_quality",
    "window_aggregates",
    "outdoor_context",
    "component_scores",
    "iaq_index_results",
    "baseline_results",
)


class SnapshotError(Exception):
    """Raised when a consistent point-in-time snapshot could not be taken
    after exhausting retries. Callers should treat this as a skip-this-cycle
    condition, not a fatal error."""


class LegacySchemaError(Exception):
    """Raised when the derived database file already exists with a
    pre-run-isolation schema (no pipeline_run_id column on the
    run-dependent tables). Legacy rows are never silently reinterpreted as
    run-isolated rows -- the derived database is fully reproducible from
    config + raw source data, so the safe fix is always to rebuild it, never
    to guess at a migration.
    """


def make_snapshot(source_db_path: Path, snapshot_dir: Path, max_retries: int = 3, retry_delay_s: float = 2.0) -> tuple[Path, int]:
    """Copy ``source_db_path`` (+ its .wal, if present) to a uniquely-named
    file under ``snapshot_dir`` and verify it opens.

    The source is actively written by another process, so the copy is
    best-effort consistent: we record (mtime, size) before and after the
    copy and retry if either changed mid-copy (torn read), and separately
    verify the copy actually opens in DuckDB before returning it.

    Returns ``(snapshot_path, retry_count)`` — retry_count is included in
    the run's reproducibility metadata.
    """
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    wal_path = Path(str(source_db_path) + ".wal")

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        run_id = uuid.uuid4().hex[:12]
        dest = snapshot_dir / f"snapshot_{run_id}.duckdb"
        dest_wal = Path(str(dest) + ".wal")
        try:
            before = _stat_signature(source_db_path, wal_path)
            shutil.copy2(source_db_path, dest)
            if wal_path.exists():
                shutil.copy2(wal_path, dest_wal)
            after = _stat_signature(source_db_path, wal_path)
            if before != after:
                raise SnapshotError("source file changed during copy (torn read)")

            probe = duckdb.connect(str(dest), read_only=True)
            probe.execute("SELECT 1").fetchone()
            probe.close()
            return dest, attempt - 1
        except Exception as exc:  # noqa: BLE001 - broad on purpose, this is a best-effort retry loop
            last_error = exc
            dest.unlink(missing_ok=True)
            dest_wal.unlink(missing_ok=True)
            logger.warning("snapshot attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_delay_s)

    raise SnapshotError(f"could not take a consistent snapshot of {source_db_path} after {max_retries} attempts") from last_error


def _stat_signature(*paths: Path) -> tuple:
    sig = []
    for p in paths:
        if p.exists():
            st = p.stat()
            sig.append((st.st_mtime_ns, st.st_size))
        else:
            sig.append(None)
    return tuple(sig)


class AirMonitorSource:
    """Context manager exposing read-only access to a point-in-time
    snapshot of ``raw_observations`` and, via ``ATTACH``, the (separately
    read-only opened) ``weather_observations`` table.

    Both underlying database files belong to the air-monitor project and
    are never modified.
    """

    def __init__(self, settings: Settings, retain_snapshot: bool = False) -> None:
        self._settings = settings
        self._retain_snapshot = retain_snapshot
        self._snapshot_path: Path | None = None
        self._con: duckdb.DuckDBPyConnection | None = None
        self.snapshot_retry_count: int = 0

    def __enter__(self) -> "AirMonitorSource":
        snapshot_dir = Path(self._settings.paths.snapshot_dir)
        source_db = Path(self._settings.paths.air_monitor_db_path)
        self._snapshot_path, self.snapshot_retry_count = make_snapshot(source_db, snapshot_dir)
        self._con = duckdb.connect(str(self._snapshot_path), read_only=True)
        weather_db = Path(self._settings.paths.weather_db_path)
        self._con.execute(f"ATTACH '{weather_db}' AS wx (READ_ONLY)")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._con is not None:
            self._con.close()
        if self._snapshot_path is not None and not self._retain_snapshot:
            self._snapshot_path.unlink(missing_ok=True)
            Path(str(self._snapshot_path) + ".wal").unlink(missing_ok=True)

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            raise RuntimeError("AirMonitorSource used outside a 'with' block")
        return self._con

    def raw_schema_columns(self) -> set[str]:
        rows = self.connection.execute("DESCRIBE raw_observations").fetchall()
        return {r[0] for r in rows}

    def fetch_raw_window(self, start: datetime, end: datetime) -> pd.DataFrame:
        """All raw_observations rows with ``start < ts <= end``, ordered by ts."""
        return self.connection.execute(
            "SELECT * FROM raw_observations WHERE ts > ? AND ts <= ? ORDER BY ts",
            [start, end],
        ).df()

    def fetch_outdoor_asof(self, computed_ts: datetime) -> dict | None:
        """The latest ``weather_observations`` row with
        ``forecast_time <= computed_ts`` (ASOF join — never a future row).
        Returns None if no such row exists (e.g. computed_ts predates all
        weather data).
        """
        row = self.connection.execute(
            """
            SELECT w.*
            FROM (SELECT CAST(? AS TIMESTAMPTZ) AS computed_ts) g
            ASOF LEFT JOIN wx.weather_observations w
            ON g.computed_ts >= w.forecast_time
            """,
            [computed_ts],
        ).fetchdf()
        if row.empty or pd.isna(row.iloc[0].get("forecast_time")):
            return None
        return row.iloc[0].to_dict()


def _existing_table_columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str] | None:
    """Returns the column names of ``table`` if it already exists in
    ``con``'s database, or ``None`` if it does not exist yet."""
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
    ).fetchall()
    if not rows:
        return None
    return {r[0] for r in rows}


def _detect_legacy_schema(con: duckdb.DuckDBPyConnection, db_path: Path) -> None:
    """Raises :class:`LegacySchemaError` if any run-isolated table already
    exists in ``con`` without a ``pipeline_run_id`` column -- i.e. this
    derived database predates run isolation (schema version 1)."""
    for table in _RUN_ISOLATED_TABLES:
        columns = _existing_table_columns(con, table)
        if columns is not None and "pipeline_run_id" not in columns:
            raise LegacySchemaError(
                f"'{db_path}' contains table '{table}' without a pipeline_run_id column -- "
                f"this is a pre-run-isolation (schema version 1) derived database. "
                f"The derived database is fully reproducible from config + raw source data, "
                f"so the safe fix is to rebuild it: "
                f"`python -m iaq_hfis.cli rebuild-db --config <path> --confirm`. "
                f"This only deletes the derived database file (never the raw air-monitor/weather source databases)."
            )


def rebuild_derived_database(db_path: str) -> None:
    """Deletes the derived database file (+ its .wal, if present) and
    recreates it fresh with the current (run-isolated) schema. Only ever
    touches ``paths.derived_db_path`` -- never air_monitor.duckdb or
    weather.duckdb, which this module only ever opens read-only.
    """
    path = Path(db_path)
    wal = Path(str(path) + ".wal")
    path.unlink(missing_ok=True)
    wal.unlink(missing_ok=True)
    writer = DerivedResultsWriter(db_path)
    writer.close()


class DerivedResultsWriter:
    """Single persistent read-write connection to iaq_hfis's own derived
    database (never air_monitor.duckdb / weather.duckdb), mirroring the
    connection-lifetime pattern of ``air-monitor/storage/duckdb_client.py``.

    Detects a legacy (pre-run-isolation) schema on an existing database file
    and fails loudly with :class:`LegacySchemaError` rather than silently
    reinterpreting old rows as run-isolated. On a fresh or already
    up-to-date database, stamps/verifies ``schema_version``.
    """

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(path), read_only=False)
        _detect_legacy_schema(self._con, path)
        schema_sql = (Path(__file__).parent / "sql" / "create_tables.sql").read_text(encoding="utf-8")
        self._con.execute(schema_sql)
        self._ensure_schema_version(path)

    def _ensure_schema_version(self, path: Path) -> None:
        row = self._con.execute("SELECT max(version) FROM schema_version").fetchone()
        current = row[0] if row else None
        if current is None:
            self._con.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", [SCHEMA_VERSION, datetime.now(timezone.utc)])
        elif current != SCHEMA_VERSION:
            raise LegacySchemaError(
                f"'{path}' has schema_version={current}, but this code expects schema_version={SCHEMA_VERSION}. "
                f"Rebuild the derived database: `python -m iaq_hfis.cli rebuild-db --config <path> --confirm`."
            )

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        return self._con

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "DerivedResultsWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
