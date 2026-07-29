"""``run_summary.md``: a human-readable Markdown rendering of
``run_summary_{pipeline_run_id}.json``. Pure formatting -- every number here
already exists in the JSON; this module invents nothing.
"""

from __future__ import annotations

from pathlib import Path

RUN_SUMMARY_MD = "run_summary.md"

#: Section headers this module always emits, in order -- also the anchor
#: strings the corresponding test checks for ("run_summary.md contains all
#: mandatory sections").
SECTIONS = [
    "Run Metadata",
    "Environment",
    "Completeness Summary",
    "Provisional Parameters Used",
    "Publication Readiness",
    "Baseline Comparison",
    "Masking",
    "Reference-Case Consistency",
    "Stability",
    "Sensitivity",
    "Fault / Reason-Code Frequency",
]


def _fmt(value) -> str:
    if value is None:
        return "not available"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def build_run_summary_markdown(summary: dict) -> str:
    lines: list[str] = ["# iaq_hfis Run Summary", "", f"Pipeline run ID: `{summary['pipeline_run_id']}`", ""]

    lines += [f"## {SECTIONS[0]}", ""]
    lines += [
        f"- Status: **{summary['status']}**",
        f"- Started: {summary['started_at']}",
        f"- Finished: {summary['finished_at']}",
        f"- Computed range: {summary['computed_ts_range'][0]} to {summary['computed_ts_range'][1]}",
        f"- Window: {summary['window_minutes']} minutes",
        f"- Timestamps processed: {summary['n_timestamps_processed']}",
        f"- Snapshot retries: {summary['n_snapshot_retries']}",
        f"- Config hash: `{summary['config_hash']}`",
        f"- Engine version: {summary['engine_version']}",
        f"- Selected evaluation run ID: {_fmt(summary.get('selected_evaluation_run_id'))}",
        "",
    ]

    lines += [f"## {SECTIONS[1]}", ""]
    env = summary.get("environment") or {}
    for key, value in env.items():
        lines.append(f"- {key}: {_fmt(value)}")
    lines.append("")

    lines += [f"## {SECTIONS[2]}", ""]
    cs = summary["completeness_summary"]
    lines += [f"- OK: {cs['OK']}", f"- PARTIAL: {cs['PARTIAL']}", f"- FAILED: {cs['FAILED']}", ""]
    dcf = summary.get("dominant_component_frequency") or {}
    if dcf:
        lines.append("Dominant-component frequency (OK/PARTIAL computed_ts only):")
        for component in sorted(dcf):
            lines.append(f"- {component}: {dcf[component]}")
        lines.append("")

    lines += [f"## {SECTIONS[3]}", ""]
    provisional = summary.get("provisional_parameters_used") or []
    if provisional:
        lines += [f"- {p}" for p in provisional]
    else:
        lines.append("None engaged this run.")
    lines.append("")

    lines += [f"## {SECTIONS[4]}", ""]
    pr = summary.get("publication_readiness")
    if pr is None:
        lines.append("Not assessed for this run -- run `iaq_hfis validate-artifacts` and regenerate the report.")
    else:
        lines.append(f"- Ready: **{pr.get('ready')}**")
        for issue in pr.get("blocking_issues") or []:
            lines.append(f"- Blocking: {issue}")
        for warning in pr.get("warnings") or []:
            lines.append(f"- Warning: {warning}")
    lines.append("")

    ev = summary.get("evaluation")
    if ev is None:
        for section in SECTIONS[5:]:
            lines += [f"## {section}", "", "Not computed for this pipeline_run_id -- run `iaq_hfis evaluate --pipeline-run-id <id>` first.", ""]
        return "\n".join(lines)

    lines += [f"## {SECTIONS[5]} (agreement, unlabeled real data)", ""]
    for a in ev.get("agreement", []):
        lines.append(
            f"- {a['method_a']} vs {a['method_b']}: {_fmt(a['percent_agreement'])} agreement, "
            f"Cohen's kappa={_fmt(a['cohens_kappa'])} (n={a['n']}, excluded={a['n_excluded']})"
        )
    if not ev.get("agreement"):
        lines.append("No agreement results (no computed_ts evaluated).")
    lines.append("")

    lines += [f"## {SECTIONS[6]}", ""]
    for m in ev.get("masking", []):
        lines.append(f"- {m['method']} (>= {m['severity_threshold']}): rate={_fmt(m['masking_rate'])} ({m['n_masked']}/{m['n_critical_events']} events)")
    if not ev.get("masking"):
        lines.append("No masking results.")
    lines.append("")

    lines += [f"## {SECTIONS[7]}", ""]
    lines.append("Consistency with predefined synthetic boundary-adjacent labels -- NOT an empirical accuracy estimate.")
    for method, score in (ev.get("reference_cases") or {}).items():
        lines.append(f"- {method}: macro-F1={_fmt(score['macro_f1'])}, Cohen's kappa={_fmt(score['cohens_kappa'])} (n={score['n']}, excluded={score['n_excluded']})")
    lines.append("")

    lines += [f"## {SECTIONS[8]}", ""]
    stability = ev.get("stability")
    if stability is None:
        lines.append("Not sampled this run (no eligible computed_ts with available components).")
    else:
        lines += [
            f"- Sample points: {stability['n_samples']} (boundary-adjacent + random-comparison)",
            f"- Seed: {stability['seed']} (fixed, reproducible)",
            f"- Trials per sample: {stability['n_trials_per_sample']}",
        ]
        for method, s in (stability.get("by_method") or {}).items():
            ci = s.get("class_change_rate_ci95")
            ci_text = f" (95% CI [{_fmt(ci[0])}, {_fmt(ci[1])}])" if ci else ""
            lines.append(
                f"- {method}: class_change_rate={_fmt(s['class_change_rate'])}{ci_text}, "
                f"mean|Δindex|={_fmt(s['mean_abs_index_change'])}, p95|Δindex|={_fmt(s['p95_abs_index_change'])}, "
                f"max|Δindex|={_fmt(s['max_abs_index_change'])}"
            )
    lines.append("")

    lines += [f"## {SECTIONS[9]}", ""]
    sensitivity = ev.get("sensitivity")
    if not sensitivity or not sensitivity.get("n_sample_points"):
        lines.append("No sensitivity results.")
    else:
        lines.append(f"- Sample points: {sensitivity['n_sample_points']}")
        lines.append(f"- Strata: {', '.join(sensitivity.get('strata') or [])}")
        for row in sensitivity.get("by_parameter_value") or []:
            lines.append(
                f"  - {row['varied_parameter']}={row['value']}: class_agreement={_fmt(row['class_agreement_with_reference'])}, "
                f"mean|Δindex|={_fmt(row['mean_abs_index_diff'])}, n={row['n_samples']}"
            )
    lines.append("")

    lines += [f"## {SECTIONS[10]}", ""]
    props = ev.get("status_proportions") or {}
    lines.append(f"- Status proportions (n={props.get('n_total')}): OK={_fmt(props.get('OK'))}, PARTIAL={_fmt(props.get('PARTIAL'))}, FAILED={_fmt(props.get('FAILED'))}")
    freq = ev.get("reason_code_frequency") or {}
    counts = freq.get("counts") or {}
    if counts:
        for code, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {code}: {count}")
    else:
        lines.append("- No data-quality reason codes recorded.")
    lines.append("")

    return "\n".join(lines)


def write_run_summary_markdown(summary: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RUN_SUMMARY_MD
    path.write_text(build_run_summary_markdown(summary), encoding="utf-8")
    return path
