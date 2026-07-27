"""``run_summary.md``: a human-readable Markdown rendering of
``run_summary_{run_id}.json``. Pure formatting -- every number here already
exists in the JSON; this module invents nothing.
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
    "Baseline Comparison",
    "Masking",
    "Ground-Truth Scoring",
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
    lines: list[str] = [f"# iaq_hfis Run Summary", "", f"Run ID: `{summary['run_id']}`", ""]

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

    lines += [f"## {SECTIONS[3]}", ""]
    provisional = summary.get("provisional_parameters_used") or []
    if provisional:
        lines += [f"- {p}" for p in provisional]
    else:
        lines.append("None engaged this run.")
    lines.append("")

    ev = summary.get("evaluation")
    if ev is None:
        for section in SECTIONS[4:]:
            lines += [f"## {section}", "", "Not computed for this run_id -- run `iaq_hfis evaluate --run-id <id>` first.", ""]
        return "\n".join(lines)

    lines += [f"## {SECTIONS[4]} (agreement, unlabeled real data)", ""]
    for a in ev.get("agreement", []):
        lines.append(
            f"- {a['method_a']} vs {a['method_b']}: {_fmt(a['percent_agreement'])} agreement, "
            f"Cohen's kappa={_fmt(a['cohens_kappa'])} (n={a['n']}, excluded={a['n_excluded']})"
        )
    if not ev.get("agreement"):
        lines.append("No agreement results (no computed_ts evaluated).")
    lines.append("")

    lines += [f"## {SECTIONS[5]}", ""]
    for m in ev.get("masking", []):
        lines.append(f"- {m['method']} (>= {m['severity_threshold']}): rate={_fmt(m['masking_rate'])} ({m['n_masked']}/{m['n_critical_events']} events)")
    if not ev.get("masking"):
        lines.append("No masking results.")
    lines.append("")

    lines += [f"## {SECTIONS[6]}", ""]
    for method, score in (ev.get("ground_truth") or {}).items():
        lines.append(f"- {method}: macro-F1={_fmt(score['macro_f1'])}, Cohen's kappa={_fmt(score['cohens_kappa'])} (n={score['n']}, excluded={score['n_excluded']})")
    lines.append("")

    lines += [f"## {SECTIONS[7]}", ""]
    stability = ev.get("stability")
    if stability is None:
        lines.append("Not sampled this run (no computed_ts with available components).")
    else:
        lines += [
            f"- Sampled at: {stability['computed_ts']}",
            f"- Seed: {stability['seed']} (fixed, reproducible)",
            f"- Trials: {stability['n_trials']}",
            f"- Baseline class: {stability['baseline_class']}",
            f"- Class-change rate: {_fmt(stability['class_change_rate'])}",
        ]
    lines.append("")

    lines += [f"## {SECTIONS[8]}", ""]
    for s in ev.get("sensitivity", []):
        lines.append(f"- {s['varied_parameter']}={s['value']}: status={s['completeness_status']}, index={_fmt(s['index_value'])} ({s['index_class']})")
    if not ev.get("sensitivity"):
        lines.append("No sensitivity results.")
    lines.append("")

    lines += [f"## {SECTIONS[9]}", ""]
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
