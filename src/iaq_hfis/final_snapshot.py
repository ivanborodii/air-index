"""Builds the tracked, static publication snapshot at
``research_results/final/`` from one validated ``(pipeline_run_id,
evaluation_run_id)`` pair. Replaces the directory's contents atomically
(build into a temp dir, then swap) so a failed build never leaves a
partial/corrupt snapshot in place.

Never touches raw source databases or the live derived database beyond
reading from them; the tracked snapshot is a plain copy of already-
generated report artifacts plus a small `latest_run.json` index and the
`validate-artifacts` result.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from iaq_hfis.config import ConfigError, Settings
from iaq_hfis.provenance import fold_late_artifact_checks
from iaq_hfis.report import _report_dir, load_run_summary
from iaq_hfis.reporting.manuscript_readiness import (
    MANUSCRIPT_READINESS_JSON,
    MANUSCRIPT_READINESS_MD,
    build_manuscript_readiness_json,
    build_manuscript_readiness_markdown,
)
from iaq_hfis.testing_report import write_test_report
from iaq_hfis.validation import ArtifactValidationReport, check_same_commit_and_clean_tree, validate_artifacts, write_artifact_validation_report

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FINAL_SNAPSHOT_DIRNAME = "research_results/final"
EXPLORATORY_SNAPSHOT_DIRNAME = "research_results/exploratory"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_manifest(settings: Settings, staging: Path, summary: dict, pipeline_run_id: str, evaluation_run_id: str | None, generation_timestamp_utc: str) -> dict:
    """Machine-readable identity/integrity record for the snapshot: run IDs,
    timestamps, git commit, config hash, DB path/checksum, input date range,
    row counts, and a checksum of every artifact file in the snapshot --
    so a stale or tampered snapshot is mechanically detectable, not just
    trusted by convention."""
    performance = summary.get("performance") or {}
    environment = summary.get("environment") or {}

    db_paths = {
        "air_monitor_db_path": settings.paths.air_monitor_db_path,
        "weather_db_path": settings.paths.weather_db_path,
        "derived_db_path": settings.paths.derived_db_path,
    }
    databases = {}
    for name, rel_path in db_paths.items():
        abs_path = REPO_ROOT / rel_path
        databases[name] = {
            "path": rel_path,
            "sha256": _sha256_file(abs_path) if abs_path.is_file() else None,
            "size_bytes": abs_path.stat().st_size if abs_path.is_file() else None,
        }

    artifact_checksums = {}
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            artifact_checksums[str(path.relative_to(staging))] = _sha256_file(path)

    return {
        "pipeline_run_id": pipeline_run_id,
        "evaluation_run_id": evaluation_run_id,
        "generation_timestamp_utc": generation_timestamp_utc,
        "git_commit": environment.get("git_commit"),
        "config_hash": summary.get("config_hash"),
        "input_date_range_utc": summary.get("computed_ts_range"),
        "row_counts": {
            "source_raw_row_count": performance.get("source_raw_row_count"),
            "derived_row_counts": performance.get("derived_row_counts"),
        },
        "databases": databases,
        "artifact_checksums_sha256": artifact_checksums,
    }


def _write_readme(out_dir: Path, pipeline_run_id: str, evaluation_run_id: str | None, kind: str = "final") -> None:
    if kind == "exploratory":
        title = "Exploratory result snapshot -- NOT manuscript-final"
        function_ref = "build_exploratory_snapshot"
        scope_note = (
            "**This is an exploratory-mode run.** The microclimate (M) component was structurally omitted "
            "because no DBN-supported temperature profile exists for this run's room/season -- see "
            "`manuscript_readiness.md` for the exact blocker. This directory therefore reports an A/V-only "
            "(aerosol + ventilation) analysis and must never be presented as the manuscript's complete "
            "proposed method. It is kept OUTSIDE `research_results/final/` for exactly this reason."
        )
    else:
        title = "Final published result snapshot"
        function_ref = "build_final_snapshot"
        scope_note = ""
    text = f"""# {title}

This directory is a **tracked, static snapshot** of one validated
`(pipeline_run_id, evaluation_run_id)` pair's output -- not a live or
regenerable directory. It was produced by
`src/iaq_hfis/final_snapshot.py:{function_ref}` and replaced
atomically (never hand-edited).

{scope_note}

- pipeline_run_id: `{pipeline_run_id}`
- evaluation_run_id: `{evaluation_run_id}`

See `latest_run.json` for the full identity chain (config hash, git
commit, generation timestamp, readiness status) and
`docs/reproducibility.md` (repo root) for how to reproduce it.

`run_narrative.md` and `article_results_summary.md` are software-generated
drafts -- review and rewrite before including any text in a publication.

If you change config or code, this snapshot goes stale. Regenerate it via
the final-run procedure; do not edit these files directly.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def build_final_snapshot(
    settings: Settings,
    pipeline_run_id: str,
    test_report_summary: dict | None = None,
    final_dir: Path | None = None,
) -> dict:
    """Copies every validated artifact for ``pipeline_run_id`` into
    ``final_dir`` (defaults to ``<repo root>/research_results/final``),
    plus ``latest_run.json`` and (if given) ``test_report.json``/``.md``
    (the structured dict from :func:`iaq_hfis.testing_report.run_full_test_suite`
    -- total/passed/failed/skipped/wall-time/environment). Returns the
    validate-artifacts report used.

    Refuses (raises :class:`ConfigError`) if ``pipeline_run_id`` was computed
    in ``mode='exploratory'`` -- an exploratory run can never be promoted
    into ``research_results/final``; use :func:`build_exploratory_snapshot`
    for those (targets ``research_results/exploratory`` instead).

    ``final_dir`` is overridable specifically so tests never touch the
    real repository's tracked publication snapshot.
    """
    summary = load_run_summary(settings, pipeline_run_id)
    if summary.get("mode") == "exploratory":
        raise ConfigError(
            f"pipeline_run_id={pipeline_run_id} was computed in mode='exploratory' (a required DBN "
            "temperature profile was missing for at least one computed_ts, so the microclimate "
            "component was structurally omitted). Exploratory runs can never be promoted into "
            "research_results/final -- use build_exploratory_snapshot() / see "
            "research_results/exploratory instead, or run 'iaq_hfis run --mode publication' with an "
            "eligible room/season."
        )
    return _build_snapshot(settings, pipeline_run_id, summary, test_report_summary, final_dir or (REPO_ROOT / FINAL_SNAPSHOT_DIRNAME), kind="final")


def build_exploratory_snapshot(
    settings: Settings,
    pipeline_run_id: str,
    test_report_summary: dict | None = None,
    final_dir: Path | None = None,
) -> dict:
    """Like :func:`build_final_snapshot`, but for ``mode='exploratory'`` runs
    only, targeting ``research_results/exploratory`` (never
    ``research_results/final`` -- an exploratory run's microclimate
    component was structurally omitted and must never be presented as the
    manuscript's complete proposed method).
    """
    summary = load_run_summary(settings, pipeline_run_id)
    if summary.get("mode") != "exploratory":
        raise ConfigError(
            f"pipeline_run_id={pipeline_run_id} was computed in mode='{summary.get('mode')}', not 'exploratory'. "
            "build_exploratory_snapshot is only for exploratory-mode runs -- use build_final_snapshot for a "
            "publication-mode run."
        )
    return _build_snapshot(settings, pipeline_run_id, summary, test_report_summary, final_dir or (REPO_ROOT / EXPLORATORY_SNAPSHOT_DIRNAME), kind="exploratory")


def _build_snapshot(
    settings: Settings,
    pipeline_run_id: str,
    summary: dict,
    test_report_summary: dict | None,
    final_dir: Path,
    kind: str,
) -> dict:
    evaluation_run_id = summary.get("selected_evaluation_run_id")
    report_dir = _report_dir(settings, pipeline_run_id)
    if not report_dir.is_dir():
        raise FileNotFoundError(f"no report directory for pipeline_run_id={pipeline_run_id} at {report_dir} -- run 'iaq_hfis report' first")

    validation_report = validate_artifacts(settings, pipeline_run_id)
    same_commit_passed: list[str] = []
    same_commit_violations: list[str] = []
    check_same_commit_and_clean_tree(summary, same_commit_passed, same_commit_violations)
    validation_report = ArtifactValidationReport(
        pipeline_run_id=pipeline_run_id,
        ok=validation_report.ok and not same_commit_violations,
        checks_passed=validation_report.checks_passed + same_commit_passed,
        violations=validation_report.violations + same_commit_violations,
    )
    artifact_validation_dict = {
        "ok": validation_report.ok,
        "n_checks_passed": len(validation_report.checks_passed),
        "n_violations": len(validation_report.violations),
    }
    tests_executed_dict = (
        {
            "ok": test_report_summary.get("ok"),
            "total": test_report_summary.get("total"),
            "passed": test_report_summary.get("passed"),
            "failed": test_report_summary.get("failed"),
            "skipped": test_report_summary.get("skipped"),
        }
        if test_report_summary is not None
        else None
    )
    if summary.get("readiness") is not None:
        summary["readiness"] = fold_late_artifact_checks(summary["readiness"], artifact_validation_dict, tests_executed_dict)

    with tempfile.TemporaryDirectory(prefix="iaq_hfis_final_snapshot_") as tmp:
        staging = Path(tmp) / "final"
        shutil.copytree(report_dir, staging)

        (staging / "effective_config").mkdir(exist_ok=True)
        shutil.copy2(REPO_ROOT / "config" / "iaq_hfis.yaml", staging / "effective_config" / "iaq_hfis.yaml")
        shutil.copy2(REPO_ROOT / "config" / "sensor_specs.yaml", staging / "effective_config" / "sensor_specs.yaml")
        shutil.copy2(REPO_ROOT / "config" / "room_profiles.yaml", staging / "effective_config" / "room_profiles.yaml")

        artifact_validation_text = "\n".join(validation_report.messages) + f"\n\nRESULT: {'OK' if validation_report.ok else 'FAILED'}\n"
        (staging / "artifact_validation_report.txt").write_text(artifact_validation_text, encoding="utf-8")
        write_artifact_validation_report(validation_report, staging)

        if test_report_summary is not None:
            write_test_report(test_report_summary, staging)

        if summary.get("readiness") is not None:
            (staging / MANUSCRIPT_READINESS_JSON).write_text(build_manuscript_readiness_json(summary["readiness"]), encoding="utf-8")
            (staging / MANUSCRIPT_READINESS_MD).write_text(build_manuscript_readiness_markdown(summary["readiness"]), encoding="utf-8")

        summary_snapshot_path = staging / f"run_summary_{pipeline_run_id}.json"
        summary_snapshot_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        # Also under the conventional name expected by spec 12.2.
        (staging / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        latest_run = {
            "pipeline_run_id": pipeline_run_id,
            "evaluation_run_id": evaluation_run_id,
            "source_time_range": summary["computed_ts_range"],
            "window_minutes": summary["window_minutes"],
            "coverage_min_ratio": settings.coverage.min_ratio,
            "config_hash": summary["config_hash"],
            "git_commit": (summary.get("environment") or {}).get("git_commit"),
            "result_generation_timestamp_utc": None,
            "readiness": summary.get("readiness"),
            "artifact_validation": {
                "ok": validation_report.ok,
                "n_checks_passed": len(validation_report.checks_passed),
                "n_violations": len(validation_report.violations),
            },
            "paths": {
                "run_summary_md": "run_summary.md",
                "run_narrative_md": "run_narrative.md",
                "article_results_summary": "article_results_summary.md",
                "article_metrics": "article_metrics.json",
                "plot_manifest": "plot_manifest.json",
                "provisional_parameter_assessment": "provisional_parameter_assessment.md",
                "parameter_selection": "parameter_selection.json",
                "manuscript_readiness_json": "manuscript_readiness.json",
                "manuscript_readiness_md": "manuscript_readiness.md",
                "publication_claims_matrix_csv": "publication_claims_matrix.csv",
                "publication_claims_matrix_md": "publication_claims_matrix.md",
                "artifact_validation_json": "artifact_validation.json",
                "artifact_validation_md": "artifact_validation.md",
                "test_report_json": "test_report.json",
                "test_report_md": "test_report.md",
                "exports_dir": "exports/",
                "plots_dir": "plots/",
            },
        }
        from datetime import datetime, timezone

        latest_run["result_generation_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        (staging / "latest_run.json").write_text(json.dumps(latest_run, indent=2), encoding="utf-8")

        _write_readme(staging, pipeline_run_id, evaluation_run_id, kind=kind)

        manifest = _build_manifest(settings, staging, summary, pipeline_run_id, evaluation_run_id, latest_run["result_generation_timestamp_utc"])
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if final_dir.exists():
            shutil.rmtree(final_dir)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(final_dir))

    return {"final_dir": str(final_dir), "validation_report": validation_report, "latest_run": latest_run}
