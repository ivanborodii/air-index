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


def report_dir(settings: Settings, pipeline_run_id: str) -> Path:
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
    run_report_dir = report_dir(settings, pipeline_run_id)
    csv_dir = run_report_dir / "exports"

    con = duckdb.connect(settings.paths.derived_db_path, read_only=True)
    try:
        db_count = _check_timestamp_counts(con, summary, pipeline_run_id, window_minutes, passed, violations)
        _check_failed_rows_are_null(con, pipeline_run_id, window_minutes, passed, violations)
        _check_index_timeseries_csv(csv_dir, summary, db_count, passed, violations)
        _check_narrative_and_summary_md(run_report_dir, summary, passed, violations)
        _check_agreement_and_masking(csv_dir, summary, passed, violations)
        _check_stability(csv_dir, summary, passed, violations)
        _check_stability_dimension_consistency(csv_dir, summary, passed, violations)
        _check_plot_manifest(run_report_dir, csv_dir, passed, violations)
        _check_plot_artifacts(run_report_dir, csv_dir, passed, violations)
        _check_provisional_parameters_agree(run_report_dir, summary, passed, violations)
        _check_sensitivity_consistency(csv_dir, summary, passed, violations)
        _check_continuity_consistency(csv_dir, settings, passed, violations)
        _check_fault_injection_consistency(csv_dir, passed, violations)
        _check_config_hash_consistency(con, summary, passed, violations)
        _check_publication_claims_matrix(run_report_dir, passed, violations)
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
    provisional_parameters_used, readiness's copy of it,
    parameter_provenance.csv's engaged provisional-like rows, run_summary.md,
    run_narrative.md, and article_results_summary.md (if present) must all
    report the exact same set of provisional parameters -- this is exactly
    the class of bug where run_summary.md said "None engaged" while
    the readiness assessment said 16."""
    authoritative = sorted(summary.get("provisional_parameters_used") or [])
    n = len(authoritative)

    readiness = summary.get("readiness")
    if readiness is not None:
        pr_list = sorted(readiness.get("provisional_parameters_used") or [])
        if pr_list == authoritative:
            passed.append("readiness.provisional_parameters_used matches run_summary.json's top-level provisional_parameters_used")
        else:
            violations.append(
                f"readiness.provisional_parameters_used ({len(pr_list)}) != "
                f"run_summary.json top-level provisional_parameters_used ({n}): "
                f"only-in-readiness={sorted(set(pr_list) - set(authoritative))}, "
                f"only-in-top-level={sorted(set(authoritative) - set(pr_list))}"
            )

    provenance_csv = report_dir / "parameter_provenance.csv"
    if provenance_csv.is_file():
        from iaq_hfis.provenance import PROVISIONAL_LIKE_STATUSES

        df = pd.read_csv(provenance_csv)
        engaged_provisional = sorted(df[(df["status"].isin(PROVISIONAL_LIKE_STATUSES)) & (df["engaged"] == True)]["path"].tolist())  # noqa: E712
        if engaged_provisional == authoritative:
            passed.append("parameter_provenance.csv engaged provisional-like rows match run_summary.json's provisional_parameters_used")
        else:
            violations.append(
                f"parameter_provenance.csv engaged provisional-like rows ({len(engaged_provisional)}) != "
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
        # pandas/numpy NaN != NaN is True (unlike Python's None != None), which would
        # wrongly count two simultaneously-FAILED (index_class both null) rows as a class
        # transition -- exclude the both-null case explicitly, matching the production
        # aggregation's Python-level None comparison semantics exactly.
        idx_class, ref_class = evaluated["index_class"], evaluated["reference_index_class"]
        both_null = idx_class.isna() & ref_class.isna()
        class_transitions = int(((idx_class != ref_class) & ~both_null).sum())
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


def _check_stability_dimension_consistency(csv_dir: Path, summary: dict, passed: list[str], violations: list[str]) -> None:
    """Every stability aggregation dimension (by_variable, by_original_class)
    must sum to the SAME overall n_trials_total as by_method for that
    method -- they are all computed from the same persisted trial rows
    (:func:`iaq_hfis.evaluation.multi_point_stability._aggregate_stability_rows`),
    just grouped differently, so their totals can never legitimately
    diverge."""
    ev = summary.get("evaluation")
    if ev is None:
        return
    stability = ev.get("stability")
    if not stability:
        return
    by_method = stability.get("by_method") or {}
    by_variable = stability.get("by_variable") or []
    by_original_class = stability.get("by_original_class") or []
    if not by_variable and not by_original_class:
        return

    for method, s in by_method.items():
        for dimension_name, rows in (("by_variable", by_variable), ("by_original_class", by_original_class)):
            if not rows:
                continue
            dimension_total = sum(r["n_trials_total"] for r in rows if r["method"] == method)
            if dimension_total == s["n_trials_total"]:
                passed.append(f"stability {dimension_name} rows for {method} sum to overall n_trials_total ({dimension_total})")
            else:
                violations.append(
                    f"stability {dimension_name} rows for {method} sum to {dimension_total}, but overall n_trials_total is {s['n_trials_total']}"
                )


def _check_plot_artifacts(report_dir: Path, csv_dir: Path, passed: list[str], violations: list[str]) -> None:
    """If plots have been rendered (``iaq_hfis plot``), every PNG must
    correspond to a real plot_manifest.json entry (no stale/orphaned PNGs
    left over from a previous config, e.g. after a plot was renamed or
    removed) and its declared source CSV must still exist."""
    plots_dir = report_dir / "plots"
    manifest_path = report_dir / "plot_manifest.json"
    if not plots_dir.is_dir() or not any(plots_dir.glob("*.png")):
        return
    if not manifest_path.is_file():
        violations.append(f"plots/ directory exists at {plots_dir} but plot_manifest.json is missing -- cannot verify which plots are current")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = {entry["id"] for entry in manifest}
    manifest_by_id = {entry["id"]: entry for entry in manifest}

    orphans = [p.name for p in plots_dir.glob("*.png") if p.stem not in manifest_ids]
    if orphans:
        violations.append(f"plots/ contains PNG(s) with no matching plot_manifest.json entry (stale from a previous config?): {sorted(orphans)}")
    else:
        passed.append("every PNG in plots/ corresponds to a current plot_manifest.json entry")

    missing_csv = []
    for png in plots_dir.glob("*.png"):
        entry = manifest_by_id.get(png.stem)
        if entry and not (csv_dir / entry["source_csv"]).is_file():
            missing_csv.append(f"{png.name} declares source_csv={entry['source_csv']!r}, which no longer exists in exports/")
    if missing_csv:
        violations.extend(missing_csv)
    elif any(plots_dir.glob("*.png")):
        passed.append("every rendered plot's declared source_csv still exists in exports/")


def _check_continuity_consistency(csv_dir: Path, settings, passed: list[str], violations: list[str]) -> None:
    """Threshold coverage (every manuscript-configured PM2.5/PM10/CO2
    breakpoint must appear in continuity_grid.csv; temperature/humidity
    must be covered at all) plus recomputing continuity_summary.csv's
    max_adjacent_jump directly from continuity_grid.csv, and confirming the
    grid itself is dense (contiguous grid_index) and monotonic (input_value
    strictly increasing with grid_index) for every (boundary, context,
    method) -- a non-monotonic or sparse grid would silently invalidate the
    Lipschitz-ratio and area-between-curves metrics computed from it."""
    grid_path = csv_dir / "continuity_grid.csv"
    summary_path = csv_dir / "continuity_summary.csv"
    if not grid_path.is_file() or not summary_path.is_file():
        return
    grid = pd.read_csv(grid_path)
    summary_df = pd.read_csv(summary_path)

    for channel, breakpoints in (
        ("pm2_5", settings.control_regions.pm2_5.breakpoints),
        ("pm10", settings.control_regions.pm10.breakpoints),
        ("co2", settings.control_regions.co2.breakpoints),
    ):
        channel_values = grid.loc[grid["channel"] == channel, "boundary_value"].tolist()
        missing = [bp for bp in breakpoints if not any(abs(bp - v) < 1e-6 for v in channel_values)]
        if missing:
            violations.append(f"continuity_grid.csv is missing manuscript breakpoint(s) {missing} for channel={channel}")
        else:
            passed.append(f"continuity_grid.csv covers every manuscript-configured breakpoint for channel={channel}")
    two_sided_missing = [channel for channel in ("temperature", "humidity") if (grid["channel"] == channel).sum() == 0]
    if two_sided_missing:
        violations.append(f"continuity_grid.csv has no boundaries at all for channel(s): {two_sided_missing}")
    else:
        passed.append("continuity_grid.csv covers both two-sided channels (temperature, humidity)")

    jump_mismatches = []
    grid_shape_violations = []
    for (bid, ctx, method), g in grid.sort_values("grid_index").groupby(["boundary_id", "context", "method"]):
        indices = g["grid_index"].tolist()
        if indices != list(range(len(indices))):
            grid_shape_violations.append(f"{bid}/{ctx}/{method}: grid_index is not contiguous from 0 ({indices[:5]}...)")
        inputs = g["input_value"].tolist()
        if inputs != sorted(inputs):
            grid_shape_violations.append(f"{bid}/{ctx}/{method}: input_value is not monotonically increasing with grid_index")

        values = g["index_value"].tolist()
        jumps = [abs(b - a) for a, b in zip(values, values[1:]) if pd.notna(a) and pd.notna(b)]
        if not jumps:
            continue
        recomputed_max = max(jumps)
        row = summary_df[(summary_df["boundary_id"] == bid) & (summary_df["context"] == ctx) & (summary_df["method"] == method)]
        if row.empty:
            jump_mismatches.append(f"{bid}/{ctx}/{method}: no matching row in continuity_summary.csv")
            continue
        reported_max = row.iloc[0]["max_adjacent_jump"]
        if pd.notna(reported_max) and abs(float(reported_max) - recomputed_max) > 1e-6:
            jump_mismatches.append(f"{bid}/{ctx}/{method}: max_adjacent_jump summary={reported_max} recomputed={recomputed_max}")

    if grid_shape_violations:
        violations.extend(grid_shape_violations[:20])
    else:
        passed.append("continuity_grid.csv is dense (contiguous grid_index) and monotonic (input_value) for every boundary/context/method")

    if jump_mismatches:
        violations.extend(f"continuity_summary.csv disagrees with continuity_grid.csv: {m}" for m in jump_mismatches[:20])
    else:
        passed.append("continuity_summary.csv's max_adjacent_jump recomputes exactly from continuity_grid.csv")


def _check_fault_injection_consistency(csv_dir: Path, passed: list[str], violations: list[str]) -> None:
    """Calibration/validation non-overlap (no scenario_id shared between
    the two splits -- the no-leakage guarantee); event-level n_true_events
    matches the actual count in fault_injection_events.csv; one-to-one
    matching sanity (tp+fn == n_true_events, tp+fp == n_predicted_events --
    an event-level TP can never exceed the number of true events injected,
    the core "no double-counting" guarantee); and the confusion matrix's
    diagonal exactly equals the row-level TP count for every reason code."""
    events_path = csv_dir / "fault_injection_events.csv"
    if not events_path.is_file():
        return
    events = pd.read_csv(events_path)

    calibration_ids = set(events.loc[events["dataset_split"] == "calibration", "scenario_id"])
    validation_ids = set(events.loc[events["dataset_split"] == "validation", "scenario_id"])
    overlap = calibration_ids & validation_ids
    if overlap:
        violations.append(f"fault_injection_events.csv has scenario_id(s) present in BOTH calibration and validation splits (data leakage): {sorted(overlap)}")
    else:
        passed.append("fault_injection_events.csv's calibration and validation splits share no scenario_id (no data leakage)")

    event_metrics_path = csv_dir / "fault_detection_event_metrics.csv"
    if event_metrics_path.is_file():
        event_metrics = pd.read_csv(event_metrics_path)
        mismatches = []
        for _, row in event_metrics.iterrows():
            actual_n_true = int(((events["dataset_split"] == row["dataset_split"]) & (events["fault_type"] == row["reason_code"])).sum())
            if actual_n_true != row["n_true_events"]:
                mismatches.append(f"{row['dataset_split']}/{row['reason_code']}: n_true_events={row['n_true_events']} but {actual_n_true} actual event(s) in fault_injection_events.csv")
            if row["tp"] + row["fn"] != row["n_true_events"]:
                mismatches.append(f"{row['dataset_split']}/{row['reason_code']}: tp+fn ({row['tp'] + row['fn']}) != n_true_events ({row['n_true_events']})")
            if row["tp"] + row["fp"] != row["n_predicted_events"]:
                mismatches.append(f"{row['dataset_split']}/{row['reason_code']}: tp+fp ({row['tp'] + row['fp']}) != n_predicted_events ({row['n_predicted_events']})")
        if mismatches:
            violations.extend(mismatches)
        else:
            passed.append("fault_detection_event_metrics.csv's n_true_events matches fault_injection_events.csv, and tp/fp/fn are internally consistent (one-to-one matching)")

    confusion_path = csv_dir / "fault_detection_confusion_matrix.csv"
    row_metrics_path = csv_dir / "fault_detection_metrics.csv"
    if confusion_path.is_file() and row_metrics_path.is_file():
        confusion = pd.read_csv(confusion_path)
        row_metrics = pd.read_csv(row_metrics_path)
        mismatches = []
        for _, row in row_metrics.iterrows():
            diag = confusion[
                (confusion["dataset_split"] == row["dataset_split"])
                & (confusion["true_label"] == row["reason_code"])
                & (confusion["predicted_label"] == row["reason_code"])
            ]
            diag_count = int(diag["count"].sum())
            if diag_count != row["tp"]:
                mismatches.append(f"{row['dataset_split']}/{row['reason_code']}: confusion matrix diagonal ({diag_count}) != row-level tp ({row['tp']})")
        if mismatches:
            violations.extend(mismatches)
        else:
            passed.append("fault_detection_confusion_matrix.csv's diagonal matches fault_detection_metrics.csv's row-level tp for every reason code")


def _check_config_hash_consistency(con, summary: dict, passed: list[str], violations: list[str]) -> None:
    """The evaluation actually persisted for this run's selected
    evaluation_run_id must have been computed against the SAME config as
    the pipeline run itself -- catches evaluate being run after a config
    change without re-running the pipeline."""
    evaluation_run_id = summary.get("selected_evaluation_run_id")
    if evaluation_run_id is None:
        return
    row = con.execute("SELECT config_hash FROM evaluation_runs WHERE evaluation_run_id = ?", [evaluation_run_id]).fetchone()
    if row is None:
        violations.append(f"no evaluation_runs row found for evaluation_run_id={evaluation_run_id}")
        return
    evaluation_config_hash = row[0]
    pipeline_config_hash = summary.get("config_hash")
    if evaluation_config_hash == pipeline_config_hash:
        passed.append("evaluation_runs.config_hash matches run_summary.json's pipeline config_hash (evaluate was run against the same config as run)")
    else:
        violations.append(
            f"evaluation_runs.config_hash ({evaluation_config_hash}) != run_summary.json's config_hash ({pipeline_config_hash}) -- "
            f"evaluate may have been run after a config change without re-running the pipeline"
        )


def check_same_commit_and_clean_tree(summary: dict, passed: list[str], violations: list[str]) -> None:
    """Spec section 11's same-commit invariant: the final scientific result
    set must be generated and tested from the same code state. Compares the
    CURRENT git commit/tree-dirty status (evaluated live, at validation
    time) against the commit recorded in run_summary.json's environment
    block at run-time -- catches code being edited after 'iaq_hfis run' but
    before 'iaq_hfis finalize', which would make the tracked snapshot
    describe code that no longer matches what's on disk.

    Deliberately NOT part of :func:`validate_artifacts`'s general check
    list: a development sandbox routinely has uncommitted changes, and
    `iaq_hfis validate-artifacts` is used throughout development, not just
    at finalize time. Only :func:`iaq_hfis.final_snapshot.build_final_snapshot`
    calls this -- the one place a dirty tree or commit drift is genuinely
    disqualifying.
    """
    from iaq_hfis.reproducibility import get_git_commit, get_git_tree_dirty

    recorded_commit = (summary.get("environment") or {}).get("git_commit")
    current_commit = get_git_commit(REPO_ROOT)
    if current_commit is None or recorded_commit is None:
        violations.append("git commit could not be determined for the current tree or the recorded run -- same-commit invariant cannot be verified")
        return
    if current_commit != recorded_commit:
        violations.append(
            f"current git commit ({current_commit}) != commit recorded when this run was computed ({recorded_commit}) -- "
            "code has changed since 'iaq_hfis run'; re-run the pipeline before finalizing"
        )
    else:
        passed.append("current git commit matches the commit recorded when this run was computed (same-commit invariant holds)")

    tree_dirty = get_git_tree_dirty(REPO_ROOT)
    if tree_dirty is None:
        violations.append("working tree clean/dirty status could not be determined -- same-commit invariant cannot be verified")
    elif tree_dirty:
        violations.append("working tree has uncommitted changes -- a final publication snapshot must be built from a clean, committed tree")
    else:
        passed.append("working tree is clean (no uncommitted changes)")


_VALID_CLAIM_STATUSES = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "BLOCKED"}


def _check_publication_claims_matrix(report_dir: Path, passed: list[str], violations: list[str]) -> None:
    """publication_claims_matrix.csv must exist, cover all 9 minimum claims
    (spec section 13), and every status must be one of the 4 allowed
    values -- never left blank or set to something ad hoc."""
    csv_path = report_dir / "publication_claims_matrix.csv"
    if not csv_path.is_file():
        violations.append("publication_claims_matrix.csv is missing")
        return
    df = pd.read_csv(csv_path)
    if len(df) < 9:
        violations.append(f"publication_claims_matrix.csv has only {len(df)} claim(s), fewer than the required minimum of 9")
        return
    bad_status = df[~df["status"].isin(_VALID_CLAIM_STATUSES)]
    if not bad_status.empty:
        violations.append(f"publication_claims_matrix.csv has invalid status value(s): {sorted(bad_status['status'].unique().tolist())}")
        return
    passed.append(f"publication_claims_matrix.csv covers {len(df)} claims, all with a valid status")


def write_artifact_validation_report(report: ArtifactValidationReport, out_dir: Path) -> tuple[Path, Path]:
    """Writes ``artifact_validation.json`` (machine-readable) and
    ``artifact_validation.md`` (human-readable) for one validation report --
    the two required output formats, alongside the plain-text rendering
    already embedded in the final publication snapshot."""
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "artifact_validation.json"
    json_path.write_text(
        json.dumps(
            {
                "pipeline_run_id": report.pipeline_run_id,
                "ok": report.ok,
                "n_checks_passed": len(report.checks_passed),
                "n_violations": len(report.violations),
                "checks_passed": report.checks_passed,
                "violations": report.violations,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    md_lines = [
        "# Artifact Validation Report",
        "",
        f"pipeline_run_id: `{report.pipeline_run_id}`",
        "",
        f"**Result: {'OK' if report.ok else 'FAILED'}** -- {len(report.checks_passed)} passed, {len(report.violations)} violation(s)",
        "",
    ]
    if report.violations:
        md_lines += ["## Violations", ""]
        md_lines += [f"- {v}" for v in report.violations]
        md_lines.append("")
    md_lines += ["## Checks passed", ""]
    md_lines += [f"- {c}" for c in report.checks_passed]
    md_path = out_dir / "artifact_validation.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return json_path, md_path
