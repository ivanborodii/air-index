"""``article_results_summary.md`` and ``article_metrics.json``: a
factual, validated-metrics-only summary structured for manual adaptation
into the manuscript. Generated only from fields already present in
``run_summary_{pipeline_run_id}.json`` -- the same single authoritative
result object every other report artifact reads from. No new computation,
no publication claims beyond what the numbers themselves support.
"""

from __future__ import annotations

import json
from pathlib import Path

ARTICLE_SUMMARY_MD = "article_results_summary.md"
ARTICLE_METRICS_JSON = "article_metrics.json"


def _pct(value) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) else "not available"


def _num(value, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "not available"


def build_article_metrics(summary: dict) -> dict:
    """A flattened, machine-readable subset of run_summary.json intended
    for direct citation in the manuscript's Results section (exact values,
    no prose)."""
    ev = summary.get("evaluation") or {}
    cs = summary["completeness_summary"]
    total = cs["OK"] + cs["PARTIAL"] + cs["FAILED"]
    return {
        "pipeline_run_id": summary["pipeline_run_id"],
        "evaluation_run_id": summary.get("selected_evaluation_run_id"),
        "config_hash": summary["config_hash"],
        "git_commit": (summary.get("environment") or {}).get("git_commit"),
        "study_period": summary["computed_ts_range"],
        "window_minutes": summary["window_minutes"],
        "n_timestamps_processed": summary["n_timestamps_processed"],
        "completeness": {
            "OK": cs["OK"], "PARTIAL": cs["PARTIAL"], "FAILED": cs["FAILED"],
            "OK_pct": cs["OK"] / total if total else None,
            "PARTIAL_pct": cs["PARTIAL"] / total if total else None,
            "FAILED_pct": cs["FAILED"] / total if total else None,
        },
        "agreement": ev.get("agreement"),
        "masking": ev.get("masking"),
        "reference_case_consistency": ev.get("reference_cases"),
        "stability": ev.get("stability"),
        "sensitivity": ev.get("sensitivity"),
        "continuity": ev.get("continuity"),
        "fault_injection": ev.get("fault_injection"),
        "status_proportions": ev.get("status_proportions"),
        "reason_code_frequency": ev.get("reason_code_frequency"),
        "performance": summary.get("performance"),
        "publication_readiness": summary.get("publication_readiness"),
        "dominant_component_frequency": summary.get("dominant_component_frequency"),
    }


def build_article_results_summary(summary: dict) -> str:
    ev = summary.get("evaluation")
    cs = summary["completeness_summary"]
    total = cs["OK"] + cs["PARTIAL"] + cs["FAILED"]
    lines: list[str] = [
        "# Article Results Summary",
        "",
        "> Factual, validated-metrics-only summary for manual adaptation into the",
        "> manuscript's Results/Discussion. Every number here is copied directly from",
        f"> `run_summary_{summary['pipeline_run_id']}.json` -- no claim beyond what the",
        "> numbers themselves support. This is not manuscript prose.",
        "",
    ]

    lines += ["## 1. Dataset and experiment period", ""]
    lines.append(f"- Period: {summary['computed_ts_range'][0]} to {summary['computed_ts_range'][1]}")
    lines.append(f"- Window: {summary['window_minutes']} minutes; recompute grid per config")
    lines.append(f"- pipeline_run_id: `{summary['pipeline_run_id']}`; evaluation_run_id: `{summary.get('selected_evaluation_run_id')}`")
    lines.append(f"- config_hash: `{summary['config_hash']}`; git commit: `{(summary.get('environment') or {}).get('git_commit')}`")
    lines.append("")

    lines += ["## 2. Expected and processed calculation timestamps", ""]
    lines.append(f"- Processed: {summary['n_timestamps_processed']}")
    lines.append("")

    lines += ["## 3. OK / PARTIAL / FAILED counts and percentages", ""]
    lines.append(f"- OK: {cs['OK']} ({_pct(cs['OK']/total if total else None)})")
    lines.append(f"- PARTIAL: {cs['PARTIAL']} ({_pct(cs['PARTIAL']/total if total else None)})")
    lines.append(f"- FAILED: {cs['FAILED']} ({_pct(cs['FAILED']/total if total else None)})")
    lines.append("")

    lines += ["## 4. Air-quality class distribution (successfully formed indices)", ""]
    if ev and ev.get("status_proportions"):
        lines.append("See `index_timeseries.csv` (completeness_status=OK rows, group by index_class) for the exact distribution.")
    else:
        lines.append("Not available -- evaluation not run.")
    dcf = summary.get("dominant_component_frequency") or {}
    if dcf:
        lines.append("")
        lines.append("Dominant-component frequency (which of A/V/M won the priority-hierarchy tie-break, OK/PARTIAL computed_ts only):")
        for component in sorted(dcf):
            lines.append(f"- {component}: {dcf[component]} ({_pct(dcf[component] / sum(dcf.values()))})")
    lines.append("")

    lines += ["## 5. Inter-method agreement (unlabeled real data)", ""]
    if ev and ev.get("agreement"):
        for a in ev["agreement"]:
            lines.append(f"- {a['method_a']} vs {a['method_b']}: {_pct(a['percent_agreement'])} agreement, Cohen's kappa={_num(a['cohens_kappa'])} (n={a['n']}). This is agreement, not accuracy.")
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 6. Adverse-component masking comparison", ""]
    if ev and ev.get("masking"):
        for m in ev["masking"]:
            lines.append(f"- {m['method']} (>= {m['severity_threshold']}): masking_rate={_pct(m['masking_rate'])} ({m['n_masked']}/{m['n_critical_events']} events).")
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 7. HFIS vs CRISP-MAX numerical continuity", ""]
    continuity = ev.get("continuity") if ev else None
    if continuity and continuity.get("by_boundary_method"):
        for method in ("PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"):
            rows = [r for r in continuity["by_boundary_method"] if r["method"] == method and r["max_adjacent_jump"] is not None]
            if rows:
                mean_jump = sum(r["max_adjacent_jump"] for r in rows) / len(rows)
                lines.append(f"- {method}: mean largest adjacent-point jump {_num(mean_jump, 2)} index points across {len(rows)} boundary/context sweeps (see `continuity_summary.csv` for per-boundary detail).")
        smoothness = continuity.get("smoothness_comparison")
        if smoothness:
            lines.append(f"- Smoothness comparison (local Lipschitz ratio, {smoothness['n_boundary_context_pairs_compared']} boundary/context pairs): {smoothness['conclusion']}")
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 8. Multi-point stability results", ""]
    stability = ev.get("stability") if ev else None
    if stability:
        lines.append(f"- {stability['n_samples']} sampled points, {stability['n_trials_per_sample']} trials each, seed={stability['seed']}.")
        for method, s in (stability.get("by_method") or {}).items():
            lines.append(
                f"  - {method}: class_change_rate={_pct(s['class_change_rate'])} "
                f"(moved better={_pct(s.get('prob_moved_better'))}, moved worse={_pct(s.get('prob_moved_worse'))}), "
                f"mean|Δindex|={_num(s['mean_abs_index_change'], 2)}"
            )
        lines.append(
            "- Breakdowns by boundary/channel (`stability_summary_by_variable.csv`) and by originating class "
            "(`stability_summary_by_original_class.csv`) are exported separately; not repeated here."
        )
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 9. Multi-point sensitivity results", ""]
    sensitivity = ev.get("sensitivity") if ev else None
    if sensitivity and sensitivity.get("n_sample_points"):
        lines.append(f"- {sensitivity['n_sample_points']} sampled points across strata: {', '.join(sensitivity.get('strata') or [])}.")
        lines.append("- See `sensitivity_window_summary.csv` / `sensitivity_coverage_summary.csv` for per-value statistics.")
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 10. Synthetic reference-case consistency results", ""]
    if ev and ev.get("reference_cases"):
        for method, score in ev["reference_cases"].items():
            lines.append(f"- {method}: macro-F1={_num(score['macro_f1'])}, Cohen's kappa={_num(score['cohens_kappa'])} (n={score['n']}). Consistency with predefined synthetic labels, NOT empirical accuracy.")
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 11. Fault-injection performance", ""]
    fi = ev.get("fault_injection") if ev else None
    if fi and fi.get("metrics_by_reason_code"):
        split = fi.get("headline_dataset_split", "validation")
        lines.append(f"{fi['n_scenarios']} scenarios across {', '.join(fi.get('channels_covered') or [])}; numbers below are the {split} split (disjoint from calibration -- no parameter was tuned against these numbers).")
        lines.append("")
        lines.append("Row-level (every affected sample counted individually):")
        for m in fi["metrics_by_reason_code"]:
            lines.append(f"- {m['reason_code']}: precision={_num(m['precision'])}, recall={_num(m['recall'])}, F1={_num(m['f1'])}, specificity={_num(m.get('specificity'))} (tp={m['tp']}, fp={m['fp']}, fn={m['fn']}, tn={m.get('tn')}).")
        event_metrics = (fi.get("event_level_metrics_by_split") or {}).get(split) or []
        if event_metrics:
            lines.append("")
            lines.append("Event-level (each injected fault matched at most once, one-to-one):")
            for m in event_metrics:
                lines.append(f"- {m['reason_code']}: precision={_num(m['precision'])}, recall={_num(m['recall'])}, F1={_num(m['f1'])} ({m['n_true_events']} true / {m['n_predicted_events']} predicted event(s)).")
        lines.append("")
        lines.append(f"- False rejection rate for genuine events: {_pct(fi.get('false_rejection_rate_for_genuine_events'))}.")
        lines.append("- Full confusion matrix: `fault_detection_confusion_matrix.csv`.")
    else:
        lines.append("Not available.")
    lines.append("")

    lines += ["## 12. Execution-time and resource results", ""]
    perf = summary.get("performance")
    if perf:
        lat = perf.get("per_timestamp_latency_ms") or {}
        lines.append(f"- Platform: {perf.get('platform')} ({perf.get('processor')}, {perf.get('cpu_count')} CPUs)")
        lines.append(f"- Total pipeline runtime: {_num(perf.get('total_runtime_seconds'), 1)} s for {summary['n_timestamps_processed']} timestamps")
        lines.append(f"- Per-timestamp latency: mean={_num(lat.get('mean'), 1)} ms, median={_num(lat.get('median'), 1)} ms, p95={_num(lat.get('p95'), 1)} ms, max={_num(lat.get('max'), 1)} ms")
        lines.append(f"- Peak memory: {_num(perf.get('peak_memory_mb'), 1)} MB")
        lines.append(f"- Source raw row count: {perf.get('source_raw_row_count')}")
    else:
        lines.append("Not measured for this run.")
    lines.append("")

    lines += ["## 13. Provisional parameters and limitations", ""]
    pr = summary.get("publication_readiness") or {}
    provisional = pr.get("provisional_parameters_used") or summary.get("provisional_parameters_used") or []
    if provisional:
        lines.append(f"{len(provisional)} provisional parameter(s) engaged this run (see `parameter_provenance.csv` for status/source of each):")
        for p in provisional:
            lines.append(f"- {p}")
    else:
        lines.append("None engaged this run.")
    lines.append("")

    lines += ["## 14. Recommended article tables and figures", ""]
    lines.append("| Table/figure | Source CSV |")
    lines.append("|---|---|")
    lines.append("| Study overview & completeness | `index_timeseries.csv`, this document §1-3 |")
    lines.append("| Method agreement | `method_comparison.csv`, `reference_case_consistency.csv` |")
    lines.append("| Masking comparison | `masking_summary.csv` |")
    lines.append("| Boundary continuity curves | `continuity_grid.csv`, `continuity_summary.csv` |")
    lines.append("| Stability under perturbation | `stability_summary.csv`, `stability_summary_by_variable.csv`, `stability_summary_by_original_class.csv`, `stability_by_point.csv`, `stability_trials.csv` |")
    lines.append("| Sensitivity to window/coverage | `sensitivity_window_summary.csv`, `sensitivity_coverage_summary.csv` |")
    lines.append("| Fault-detection performance | `fault_detection_metrics.csv`, `fault_detection_event_metrics.csv`, `fault_detection_confusion_matrix.csv` |")
    lines.append("| Parameter provenance (supplementary) | `parameter_provenance.csv` |")
    lines.append("")

    lines.append("> **This document is generated. Review and rewrite before including any text in the manuscript.**")
    return "\n".join(lines)


def write_article_summary(summary: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / ARTICLE_SUMMARY_MD
    json_path = out_dir / ARTICLE_METRICS_JSON
    md_path.write_text(build_article_results_summary(summary), encoding="utf-8")
    json_path.write_text(json.dumps(build_article_metrics(summary), indent=2), encoding="utf-8")
    return md_path, json_path
