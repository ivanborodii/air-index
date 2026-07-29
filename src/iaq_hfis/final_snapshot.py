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

from iaq_hfis.config import Settings
from iaq_hfis.report import _report_dir, load_run_summary
from iaq_hfis.validation import validate_artifacts, write_artifact_validation_report

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FINAL_SNAPSHOT_DIRNAME = "research_results/final"


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


def _write_readme(out_dir: Path, pipeline_run_id: str, evaluation_run_id: str | None) -> None:
    text = f"""# Final published result snapshot

This directory is a **tracked, static snapshot** of one validated
`(pipeline_run_id, evaluation_run_id)` pair's output -- not a live or
regenerable directory. It was produced by
`src/iaq_hfis/final_snapshot.py:build_final_snapshot` and replaced
atomically (never hand-edited).

- pipeline_run_id: `{pipeline_run_id}`
- evaluation_run_id: `{evaluation_run_id}`

See `latest_run.json` for the full identity chain (config hash, git
commit, generation timestamp, publication-readiness status) and
`docs/result_reproducibility.md` (repo root) for how to reproduce it.

`run_narrative.md` and `article_results_summary.md` are software-generated
drafts -- review and rewrite before including any text in a publication.

If you change config or code, this snapshot goes stale. Regenerate it via
the final-run procedure; do not edit these files directly.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def build_final_snapshot(
    settings: Settings,
    pipeline_run_id: str,
    test_report_text: str | None = None,
    final_dir: Path | None = None,
) -> dict:
    """Copies every validated artifact for ``pipeline_run_id`` into
    ``final_dir`` (defaults to ``<repo root>/research_results/final``),
    plus ``latest_run.json`` and (if given) a ``test_report.txt``. Returns
    the validate-artifacts report used.

    ``final_dir`` is overridable specifically so tests never touch the
    real repository's tracked publication snapshot.
    """
    summary = load_run_summary(settings, pipeline_run_id)
    evaluation_run_id = summary.get("selected_evaluation_run_id")
    report_dir = _report_dir(settings, pipeline_run_id)
    if not report_dir.is_dir():
        raise FileNotFoundError(f"no report directory for pipeline_run_id={pipeline_run_id} at {report_dir} -- run 'iaq_hfis report' first")

    validation_report = validate_artifacts(settings, pipeline_run_id)
    if summary.get("publication_readiness") is not None:
        summary["publication_readiness"]["artifact_validation"] = {
            "ok": validation_report.ok,
            "n_checks_passed": len(validation_report.checks_passed),
            "n_violations": len(validation_report.violations),
        }
        if test_report_text is not None:
            summary["publication_readiness"]["tests_executed"] = {"summary": test_report_text.strip().splitlines()[-1] if test_report_text.strip() else None}

    final_dir = final_dir or (REPO_ROOT / FINAL_SNAPSHOT_DIRNAME)
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

        if test_report_text is not None:
            (staging / "test_report.txt").write_text(test_report_text, encoding="utf-8")

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
            "publication_readiness": summary.get("publication_readiness"),
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
                "artifact_validation_json": "artifact_validation.json",
                "artifact_validation_md": "artifact_validation.md",
                "exports_dir": "exports/",
                "plots_dir": "plots/",
            },
        }
        from datetime import datetime, timezone

        latest_run["result_generation_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        (staging / "latest_run.json").write_text(json.dumps(latest_run, indent=2), encoding="utf-8")

        _write_readme(staging, pipeline_run_id, evaluation_run_id)

        manifest = _build_manifest(settings, staging, summary, pipeline_run_id, evaluation_run_id, latest_run["result_generation_timestamp_utc"])
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if final_dir.exists():
            shutil.rmtree(final_dir)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(final_dir))

    return {"final_dir": str(final_dir), "validation_report": validation_report, "latest_run": latest_run}
