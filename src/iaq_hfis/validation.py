"""Cross-checks every generated artifact for one pipeline run against the
derived DuckDB and against each other, per the mandatory result-consistency
invariants: run_summary.json, run_summary.md, run_narrative.md, every
exported CSV, and plot_manifest.json must always agree, because they are
all built from one authoritative, run-scoped result model (see
:mod:`iaq_hfis.report`) rather than independently recomputed. Used by
``python -m iaq_hfis.cli validate-artifacts`` and by the publication
snapshot build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import jsonschema
import pandas as pd

from iaq_hfis.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_SUMMARY_SCHEMA_PATH = REPO_ROOT / "config" / "run_summary.schema.json"


class ArtifactValidationError(Exception):
    """Raised when validation cannot even be attempted (e.g. no
    run_summary.json for the given pipeline_run_id) -- distinct from a
    validation *failure*, which is reported in :class:`ArtifactValidationReport`."""


@dataclass
class ArtifactValidationReport:
    pipeline_run_id: str
    ok: bool
    checks_passed: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def messages(self) -> list[str]:
        lines = [f"Artifact validation for pipeline_run_id={self.pipeline_run_id}"]
        for c in self.checks_passed:
            lines.append(f"  PASS: {c}")
        for v in self.violations:
            lines.append(f"  FAIL: {v}")
        return lines


def _report_dir(settings: Settings, pipeline_run_id: str) -> Path:
    return Path(settings.paths.run_summary_dir).parent / "reports" / pipeline_run_id


def validate_artifacts(settings: Settings, pipeline_run_id: str) -> ArtifactValidationReport:
    passed: list[str] = []
    violations: list[str] = []

    summary_path = Path(settings.paths.run_summary_dir) / f"run_summary_{pipeline_run_id}.json"
    if not summary_path.is_file():
        raise ArtifactValidationError(f"no run_summary found for pipeline_run_id={pipeline_run_id} at {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    _check_schema(summary, passed, violations)
    _check_run_id_consistency(summary, pipeline_run_id, passed, violations)

    window_minutes = summary.get("window_minutes")
    report_dir = _report_dir(settings, pipeline_run_id)
    csv_dir = report_dir / "exports"

    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        db_count = _check_timestamp_counts(con, summary, pipeline_run_id, window_minutes, passed, violations)
        _check_failed_rows_are_null(con, pipeline_run_id, window_minutes, passed, violations)
        _check_index_timeseries_csv(csv_dir, summary, db_count, passed, violations)
        _check_narrative_and_summary_md(report_dir, summary, passed, violations)
        _check_agreement_and_masking(csv_dir, summary, passed, violations)
        _check_stability(csv_dir, summary, passed, violations)
        _check_plot_manifest(report_dir, csv_dir, passed, violations)
        _check_provisional_parameters_agree(report_dir, summary, passed, violations)
        _check_sensitivity_consistency(csv_dir, summary, passed, violations)
    finally:
        con.close()

    ok = len(violations) == 0
    return ArtifactValidationReport(pipeline_run_id=pipeline_run_id, ok=ok, checks_passed=passed, violations=violations)


def _check_schema(summary: dict, passed: list[str], violations: list[str]) -> None:
    if not RUN_SUMMARY_SCHEMA_PATH.is_file():
        violations.append(f"schema file not found at {RUN_SUMMARY_SCHEMA_PATH}")
        return
    schema = json.loads(RUN_SUMMARY_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=summary, schema=schema)
        passed.append("run_summary.json validates against config/run_summary.schema.json")
    except jsonschema.ValidationError as exc:
        violations.append(f"run_summary.json failed schema validation: {exc.message}")


def _check_run_id_consistency(summary: dict, pipeline_run_id: str, passed: list[str], violations: list[str]) -> None:
    if summary.get("pipeline_run_id") != pipeline_run_id:
        violations.append(f"run_summary.json pipeline_run_id={summary.get('pipeline_run_id')!r} does not match requested {pipeline_run_id!r}")
    else:
        passed.append("run_summary.json pipeline_run_id matches the requested pipeline_run_id")

    ev = summary.get("evaluation")
    if ev is not None:
        if ev.get("pipeline_run_id") != pipeline_run_id:
            violations.append(f"evaluation section pipeline_run_id={ev.get('pipeline_run_id')!r} does not match {pipeline_run_id!r}")
        elif ev.get("evaluation_run_id") != summary.get("selected_evaluation_run_id"):
            violations.append(
                f"evaluation section evaluation_run_id={ev.get('evaluation_run_id')!r} does not match "
                f"selected_evaluation_run_id={summary.get('selected_evaluation_run_id')!r}"
            )
        else:
            passed.append("evaluation section's pipeline_run_id/evaluation_run_id match the summary's own identifiers")


def _check_timestamp_counts(con, summary: dict, pipeline_run_id: str, window_minutes, passed: list[str], violations: list[str]) -> int:
    db_count = con.execute(
        "SELECT COUNT(*) FROM iaq_index_results WHERE pipeline_run_id = ? AND window_minutes = ?",
        [pipeline_run_id, window_minutes],
    ).fetchone()[0]
    if db_count == summary["n_timestamps_processed"]:
        passed.append(f"n_timestamps_processed ({summary['n_timestamps_processed']}) == persisted iaq_index_results count ({db_count})")
    else:
        violations.append(f"n_timestamps_processed ({summary['n_timestamps_processed']}) != persisted iaq_index_results count ({db_count})")

    cs = summary["completeness_summary"]
    total = cs["OK"] + cs["PARTIAL"] + cs["FAILED"]
    if total == summary["n_timestamps_processed"]:
        passed.append(f"completeness_summary sums to n_timestamps_processed ({total})")
    else:
        violations.append(f"completeness_summary sums to {total}, but n_timestamps_processed={summary['n_timestamps_processed']}")
    return db_count


def _check_failed_rows_are_null(con, pipeline_run_id: str, window_minutes, passed: list[str], violations: list[str]) -> None:
    bad = con.execute(
        "SELECT COUNT(*) FROM iaq_index_results WHERE pipeline_run_id = ? AND window_minutes = ? AND completeness_status = 'FAILED' "
        "AND (index_value IS NOT NULL OR index_class IS NOT NULL OR dominant_component IS NOT NULL OR len(co_dominant_components) > 0)",
        [pipeline_run_id, window_minutes],
    ).fetchone()[0]
    if bad == 0:
        passed.append("every FAILED row has a null index_value, null index_class, and no dominant_component")
    else:
        violations.append(f"{bad} FAILED row(s) have a non-null index_value/index_class or a non-empty dominant_component")


def _check_index_timeseries_csv(csv_dir: Path, summary: dict, db_count: int, passed: list[str], violations: list[str]) -> None:
    idx_csv = csv_dir / "index_timeseries.csv"
    if not idx_csv.is_file():
        violations.append(f"index_timeseries.csv not found at {idx_csv} -- run 'iaq_hfis report' first")
        return
    df = pd.read_csv(idx_csv)
    if len(df) == db_count:
        passed.append(f"index_timeseries.csv row count ({len(df)}) == persisted iaq_index_results count ({db_count})")
    else:
        violations.append(f"index_timeseries.csv row count ({len(df)}) != persisted iaq_index_results count ({db_count})")

    cs = summary["completeness_summary"]
    csv_counts = df["completeness_status"].value_counts().to_dict()
    mismatches = [status for status in ("OK", "PARTIAL", "FAILED") if csv_counts.get(status, 0) != cs[status]]
    if mismatches:
        violations.append(f"index_timeseries.csv status counts {csv_counts} disagree with run_summary.json completeness_summary {cs} for {mismatches}")
    else:
        passed.append("status counts agree between run_summary.json and index_timeseries.csv")


def _check_narrative_and_summary_md(report_dir: Path, summary: dict, passed: list[str], violations: list[str]) -> None:
    cs = summary["completeness_summary"]
    for label in ("run_summary.md", "run_narrative.md"):
        path = report_dir / label
        if not path.is_file():
            violations.append(f"{label} not found at {path} -- run 'iaq_hfis report' first")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [str(cs[k]) for k in ("OK", "PARTIAL", "FAILED") if str(cs[k]) not in text]
        if missing:
            violations.append(f"{label} does not contain all of the OK/PARTIAL/FAILED counts {cs}")
        else:
            passed.append(f"{label} contains the OK/PARTIAL/FAILED counts from run_summary.json")


def _check_agreement_and_masking(csv_dir: Path, summary: dict, passed: list[str], violations: list[str]) -> None:
    ev = summary.get("evaluation")
    mc_csv = csv_dir / "method_comparison.csv"
    if ev is None or not mc_csv.is_file():
        return
    mc = pd.read_csv(mc_csv)

    bad_agreement = [
        f"{a['method_a']} vs {a['method_b']}: n+n_excluded ({a['n'] + a['n_excluded']}) exceeds method_comparison.csv row count ({len(mc)})"
        for a in ev.get("agreement", [])
        if a["n"] + a["n_excluded"] > len(mc)
    ]
    if bad_agreement:
        violations.extend(f"agreement {m}" for m in bad_agreement)
    else:
        passed.append("agreement n+n_excluded reconciles with method_comparison.csv row count for every method pair")

    bad_masking = [f"{m['method']}: n_masked ({m['n_masked']}) exceeds n_critical_events ({m['n_critical_events']})" for m in ev.get("masking", []) if m["n_masked"] > m["n_critical_events"]]
    if bad_masking:
        violations.extend(f"masking {m}" for m in bad_masking)
    else:
        passed.append("masking n_masked <= n_critical_events for every method")


def _check_stability(csv_dir: Path, summary: dict, passed: list[str], violations: list[str]) -> None:
    ev = summary.get("evaluation")
    st_csv = csv_dir / "stability_trials.csv"
    if ev is None or ev.get("stability") is None or not st_csv.is_file():
        return
    trials = pd.read_csv(st_csv)
    by_method = ev["stability"].get("by_method") or {}
    for method, s in by_method.items():
        method_trials = trials[trials["method"] == method]
        if len(method_trials) == s["n_trials_total"]:
            passed.append(f"stability_trials.csv row count for {method} ({len(method_trials)}) == n_trials_total ({s['n_trials_total']})")
        else:
            violations.append(f"stability_trials.csv row count for {method} ({len(method_trials)}) != n_trials_total ({s['n_trials_total']})")

        if len(method_trials) > 0:
            reported_rate = s["class_change_rate"]
            actual_rate = float(method_trials["changed_from_baseline"].mean())
            if abs(actual_rate - reported_rate) < 1e-9:
                passed.append(f"stability class_change_rate for {method} reconciles with stability_trials.csv")
            else:
                violations.append(f"stability class_change_rate for {method} ({reported_rate}) != recomputed rate from stability_trials.csv ({actual_rate})")


def _check_plot_manifest(report_dir: Path, csv_dir: Path, passed: list[str], violations: list[str]) -> None:
    manifest_path = report_dir / "plot_manifest.json"
    if not manifest_path.is_file():
        violations.append(f"plot_manifest.json not found at {manifest_path} -- run 'iaq_hfis report' first")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bad_refs = []
    for entry in manifest:
        csv_path = csv_dir / entry["source_csv"]
        if not csv_path.is_file():
            continue  # legitimately skipped this run (nothing to export) -- not a manifest defect
        cols = set(pd.read_csv(csv_path, nrows=1).columns)
        wanted = [entry["x"]] + entry.get("y", []) + ([entry["group_by"]] if entry.get("group_by") else []) + list((entry.get("filter_equals") or {}).keys())
        missing = [c for c in wanted if c not in cols]
        if missing:
            bad_refs.append(f"plot '{entry['id']}' references missing column(s) {missing} in {entry['source_csv']}")
    if bad_refs:
        violations.extend(bad_refs)
    else:
        passed.append("every plot_manifest.json entry references columns that exist in its source CSV")


def _check_provisional_parameters_agree(report_dir: Path, summary: dict, passed: list[str], violations: list[str]) -> None:
    """Mandatory cross-artifact check: run_summary.json's top-level
    provisional_parameters_used, publication_readiness's copy of it,
    parameter_provenance.csv's engaged PROVISIONAL rows, run_summary.md,
    run_narrative.md, and article_results_summary.md (if present) must all
    report the exact same set of provisional parameters -- this is exactly
    the class of bug where run_summary.md said "None engaged" while
    publication_readiness said 16."""
    authoritative = sorted(summary.get("provisional_parameters_used") or [])
    n = len(authoritative)

    pr = summary.get("publication_readiness")
    if pr is not None:
        pr_list = sorted(pr.get("provisional_parameters_used") or [])
        if pr_list == authoritative:
            passed.append("publication_readiness.provisional_parameters_used matches run_summary.json's top-level provisional_parameters_used")
        else:
            violations.append(
                f"publication_readiness.provisional_parameters_used ({len(pr_list)}) != "
                f"run_summary.json top-level provisional_parameters_used ({n}): "
                f"only-in-publication_readiness={sorted(set(pr_list) - set(authoritative))}, "
                f"only-in-top-level={sorted(set(authoritative) - set(pr_list))}"
            )

    provenance_csv = report_dir / "parameter_provenance.csv"
    if provenance_csv.is_file():
        df = pd.read_csv(provenance_csv)
        engaged_provisional = sorted(df[(df["status"] == "PROVISIONAL") & (df["engaged"] == True)]["path"].tolist())  # noqa: E712
        if engaged_provisional == authoritative:
            passed.append("parameter_provenance.csv engaged PROVISIONAL rows match run_summary.json's provisional_parameters_used")
        else:
            violations.append(
                f"parameter_provenance.csv engaged PROVISIONAL rows ({len(engaged_provisional)}) != "
                f"run_summary.json provisional_parameters_used ({n}): "
                f"only-in-csv={sorted(set(engaged_provisional) - set(authoritative))}, "
                f"only-in-summary={sorted(set(authoritative) - set(engaged_provisional))}"
            )

    for label, filename in (("run_summary.md", "run_summary.md"), ("run_narrative.md", "run_narrative.md")):
        path = report_dir / filename
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if n == 0:
            if "none engaged this run" in text.lower() or "no provisional parameters were engaged" in text.lower():
                passed.append(f"{label} correctly states no provisional parameters were engaged (authoritative count is 0)")
            else:
                violations.append(f"{label} does not clearly state zero provisional parameters engaged, but the authoritative count is 0")
        else:
            if "none engaged this run" in text.lower() or "no provisional parameters were engaged" in text.lower():
                violations.append(f"{label} says no provisional parameters were engaged, but the authoritative count is {n}: {authoritative}")
                continue
            missing_from_text = [p for p in authoritative if p not in text]
            if missing_from_text:
                violations.append(f"{label} is missing {len(missing_from_text)} of {n} authoritative provisional parameter name(s): {missing_from_text}")
            else:
                passed.append(f"{label} names all {n} authoritative provisional parameters")

    article_path = report_dir / "article_results_summary.md"
    if article_path.is_file():
        text = article_path.read_text(encoding="utf-8")
        if n == 0:
            if "none engaged this run" in text.lower():
                passed.append("article_results_summary.md correctly states no provisional parameters were engaged")
            else:
                violations.append("article_results_summary.md does not clearly state zero provisional parameters engaged, but the authoritative count is 0")
        else:
            missing_from_text = [p for p in authoritative if p not in text]
            if missing_from_text:
                violations.append(f"article_results_summary.md is missing {len(missing_from_text)} of {n} authoritative provisional parameter name(s): {missing_from_text}")
            else:
                passed.append(f"article_results_summary.md names all {n} authoritative provisional parameters")


def _recompute_sensitivity_summary_from_by_point(by_point: pd.DataFrame) -> dict[float, dict]:
    """Independent re-implementation (deliberately not importing the
    production aggregation function) of the sensitivity summary formula,
    used only to cross-check that the persisted summary CSV was actually
    computed from the detailed by-point data it claims to summarize."""
    recomputed = {}
    for value, g in by_point.groupby("value"):
        n_eligible = len(g)
        evaluated = g[g["completeness_status"].notna()]
        n_evaluated = len(evaluated)
        class_transitions = int((evaluated["index_class"] != evaluated["reference_index_class"]).sum())
        valid = evaluated[evaluated["index_value"].notna() & evaluated["reference_index_value"].notna()]
        diffs = (valid["index_value"] - valid["reference_index_value"]).abs()
        recomputed[value] = {
            "n_eligible": n_eligible,
            "n_evaluated": n_evaluated,
            "n_class_transitions": class_transitions,
            "class_agreement_with_reference": (n_evaluated - class_transitions) / n_evaluated if n_evaluated else None,
            "mean_abs_index_diff": float(diffs.mean()) if len(diffs) else None,
        }
    return recomputed


def _check_sensitivity_consistency(csv_dir: Path, summary: dict, passed: list[str], violations: list[str]) -> None:
    """Mandatory check: every sensitivity summary row must recompute
    exactly (strict numeric tolerance) from its own detailed by-point CSV,
    contain no duplicate parameter settings, and agree with run_summary.json."""
    ev = summary.get("evaluation")
    if ev is None:
        return
    tol = 1e-6

    for varied_parameter, by_point_name, summary_name in (
        ("window_minutes", "sensitivity_window_by_point.csv", "sensitivity_window_summary.csv"),
        ("coverage_threshold", "sensitivity_coverage_by_point.csv", "sensitivity_coverage_summary.csv"),
    ):
        by_point_path = csv_dir / by_point_name
        summary_path = csv_dir / summary_name
        if not by_point_path.is_file() or not summary_path.is_file():
            continue

        by_point = pd.read_csv(by_point_path)
        summary_df = pd.read_csv(summary_path)

        dup = summary_df["value"].duplicated()
        if dup.any():
            violations.append(f"{summary_name} has duplicate 'value' rows: {summary_df.loc[dup, 'value'].tolist()}")
        else:
            passed.append(f"{summary_name} has no duplicate parameter settings")

        recomputed = _recompute_sensitivity_summary_from_by_point(by_point)
        mismatches = []
        for _, row in summary_df.iterrows():
            expected = recomputed.get(row["value"])
            if expected is None:
                mismatches.append(f"value={row['value']} present in {summary_name} but not in {by_point_name}")
                continue
            for key in ("n_eligible", "n_evaluated", "n_class_transitions"):
                if key in row and int(row[key]) != expected[key]:
                    mismatches.append(f"value={row['value']} {key}: summary={row[key]} recomputed={expected[key]}")
            for key in ("class_agreement_with_reference", "mean_abs_index_diff"):
                if key in row and expected[key] is not None and pd.notna(row[key]):
                    if abs(float(row[key]) - expected[key]) > tol:
                        mismatches.append(f"value={row['value']} {key}: summary={row[key]} recomputed={expected[key]}")
        if mismatches:
            violations.extend(f"{summary_name} disagrees with {by_point_name}: {m}" for m in mismatches)
        else:
            passed.append(f"{summary_name} recomputes exactly from {by_point_name} (tolerance {tol})")

        # Cross-check against run_summary.json's own copy of the same summary.
        json_rows = {r["value"]: r for r in (ev.get("sensitivity") or {}).get("by_parameter_value", []) if r["varied_parameter"] == varied_parameter}
        json_mismatches = []
        for _, row in summary_df.iterrows():
            j = json_rows.get(row["value"])
            if j is None:
                json_mismatches.append(f"value={row['value']} present in {summary_name} but not in run_summary.json")
                continue
            if int(j["n_class_transitions"]) != int(row["n_class_transitions"]):
                json_mismatches.append(f"value={row['value']} n_class_transitions: json={j['n_class_transitions']} csv={row['n_class_transitions']}")
        if json_mismatches:
            violations.extend(f"run_summary.json sensitivity disagrees with {summary_name}: {m}" for m in json_mismatches)
        else:
            passed.append(f"run_summary.json sensitivity ({varied_parameter}) agrees with {summary_name}")
