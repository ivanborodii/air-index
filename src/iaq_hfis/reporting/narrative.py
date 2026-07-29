"""``run_narrative.md``: a deterministic English narrative generated only
from fields already present in ``run_summary_{pipeline_run_id}.json``.

Every sentence with a number formats a value read directly from ``summary``
or ``summary["evaluation"]`` -- no new metric is computed here. This is
what makes "every numeric claim traceable to run_summary.json" true by
construction rather than something to audit after the fact.

Required by the task spec: the software-generated-draft warning must
appear (opening and closing), and the scientific cautions must be present
verbatim so they cannot be silently dropped by a future edit.
"""

from __future__ import annotations

from pathlib import Path

RUN_NARRATIVE_MD = "run_narrative.md"

WARNING_BANNER = "> **This is a reproducible, software-generated draft. Review before inclusion in a publication.**"

#: Required verbatim, per the task spec's scientific-caution list.
CAUTIONS: list[str] = [
    "Outdoor carbon monoxide (CO) is a distinct pollutant from indoor CO2 and is never used as a CO2 substitute.",
    "Outdoor atmospheric data are used only as context (confirming data-quality decisions and selecting the seasonal temperature profile) and are never a direct input to the index.",
    "The WHO PM2.5/PM10 reference points are 24-hour averaging guidelines; using them as control points for a 15-minute index is an operational adaptation, not a WHO compliance assessment.",
    "This 15-minute index is an operational, short-term indicator; it is not a regulatory or WHO compliance measurement.",
    "The CO2 thresholds represent an operational ventilation scale, not a universal toxicity limit -- CO2 interpretation depends on occupancy, ventilation rate, and room type.",
    "Temperature and humidity control regions are room- and season-specific; the profile actually used for this run is recorded above, including whether it is a provisional stand-in.",
    "Several membership transition widths and confirmation/detection thresholds are provisional research configuration, not manuscript-derived values -- see 'Provisional parameters engaged' above.",
    "Method agreement computed against unlabeled real observations is agreement only, never accuracy. Macro-F1/Cohen's kappa are reported only against the synthetic, pre-labeled reference cases under 'Method comparison', and describe consistency with those predefined labels, not real-world classification accuracy.",
]


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "not available"


def _num(value: float | None, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if value is not None else "not available"


def build_run_narrative(summary: dict) -> str:
    lines: list[str] = [WARNING_BANNER, "", "# iaq_hfis Run Narrative", ""]

    lines.append(
        f"Run `{summary['pipeline_run_id']}` computed the hierarchical fuzzy indoor air quality index over "
        f"{summary['computed_ts_range'][0]} to {summary['computed_ts_range'][1]}, using a "
        f"{summary['window_minutes']}-minute rolling window, recomputed at each aligned timestamp "
        f"({summary['n_timestamps_processed']} timestamps processed)."
    )
    lines.append("")

    provisional = summary.get("provisional_parameters_used") or []
    if provisional:
        lines.append(
            f"Provisional parameters engaged this run ({len(provisional)}): " + "; ".join(provisional) + ". "
            "Results depending on these should be treated as preliminary until the author confirms the underlying values."
        )
    else:
        lines.append("No provisional parameters were engaged for this run's actual computed timestamps.")
    lines.append("")

    lines.append("## Completeness")
    cs = summary["completeness_summary"]
    total = cs["OK"] + cs["PARTIAL"] + cs["FAILED"]
    if total > 0:
        lines.append(
            f"Of {total} computed timestamps, {cs['OK']} were OK (all three components available with sufficient "
            f"coverage), {cs['PARTIAL']} were PARTIAL (one component unavailable), and {cs['FAILED']} were FAILED "
            f"(index and class not formed)."
        )
    else:
        lines.append("No timestamps were processed in this run.")
    dcf = summary.get("dominant_component_frequency") or {}
    if dcf:
        total_dominant = sum(dcf.values())
        parts = ", ".join(f"{c}: {n} ({_pct(n / total_dominant)})" for c, n in sorted(dcf.items()))
        lines.append(f"Dominant-component frequency across OK/PARTIAL computed timestamps: {parts}.")
    lines.append("")

    ev = summary.get("evaluation")
    lines.append("## Method comparison")
    if ev is None:
        lines.append(
            f"Evaluation (baselines, agreement, masking, reference-case consistency, stability, sensitivity) was not "
            f"run for this pipeline_run_id. Run `iaq_hfis evaluate --pipeline-run-id {summary['pipeline_run_id']}` to add it."
        )
        lines.append("")
    else:
        lines.append(f"Evaluation run `{ev['evaluation_run_id']}` (the selected evaluation for this pipeline run):")
        for a in ev.get("agreement", []):
            if a["percent_agreement"] is not None:
                lines.append(f"- {a['method_a']} and {a['method_b']} agreed on {_pct(a['percent_agreement'])} of {a['n']} compared timestamps (unlabeled agreement, Cohen's kappa={_num(a['cohens_kappa'])}).")
            else:
                lines.append(f"- {a['method_a']} and {a['method_b']}: no comparable timestamps this run.")
        for m in ev.get("masking", []):
            if m["masking_rate"] is not None:
                lines.append(f"- {m['method']} hid a component that individually reached {m['severity_threshold']} in {_pct(m['masking_rate'])} of {m['n_critical_events']} such events.")
            else:
                lines.append(f"- {m['method']}: no component reached {m['severity_threshold']} this run, so a masking rate could not be computed.")
        for method, score in (ev.get("reference_cases") or {}).items():
            if score["macro_f1"] is not None:
                lines.append(f"- Against the synthetic, pre-labeled boundary-adjacent reference cases (n={score['n']}), {method} scored macro-F1={_num(score['macro_f1'])}, Cohen's kappa={_num(score['cohens_kappa'])} (consistency, not empirical accuracy).")
        lines.append("")

        lines.append("## Stability and sensitivity")
        stability = ev.get("stability")
        if stability is not None:
            lines.append(
                f"Multi-point stability: {stability['n_samples']} deterministically-sampled computed_ts "
                f"(boundary-adjacent + random-comparison, seed={stability['seed']}), {stability['n_trials_per_sample']} "
                f"perturbation trials each (every available channel perturbed within its declared sensor uncertainty)."
            )
            for method, s in (stability.get("by_method") or {}).items():
                ci = s.get("class_change_rate_ci95")
                ci_text = f", 95% CI [{_pct(ci[0])}, {_pct(ci[1])}]" if ci else ""
                lines.append(
                    f"- {method}: class changed in {_pct(s['class_change_rate'])} of {s['n_trials_total']} trials{ci_text} "
                    f"(moved to a strictly better class in {_pct(s.get('prob_moved_better'))} of trials, a strictly worse class "
                    f"in {_pct(s.get('prob_moved_worse'))} -- these two sum to the class-change rate); "
                    f"mean absolute index change {_num(s['mean_abs_index_change'], 2)}, p95 {_num(s['p95_abs_index_change'], 2)}."
                )
        else:
            lines.append("Stability was not sampled this run (no eligible computed_ts with available components).")
        sensitivity = ev.get("sensitivity")
        if sensitivity and sensitivity.get("n_sample_points"):
            strata = ", ".join(sensitivity.get("strata") or [])
            lines.append(
                f"Multi-point sensitivity: {sensitivity['n_sample_points']} stratified sample points "
                f"(strata: {strata}), swept across window durations and coverage thresholds "
                f"(see sensitivity_window_summary.csv / sensitivity_coverage_summary.csv for per-value statistics)."
            )
        else:
            lines.append("Sensitivity was not swept this run (no computed_ts available to sample).")
        lines.append("")

        lines.append("## Boundary continuity")
        continuity = ev.get("continuity")
        by_bm = (continuity or {}).get("by_boundary_method") or []
        if by_bm:
            lines.append(
                f"Deterministic input grids ({continuity['grid_points_per_boundary']} points each) around "
                f"{continuity['n_boundaries']} control-region boundaries, each swept under {continuity.get('n_contexts', 1)} "
                f"'other components' contexts ({', '.join(continuity.get('contexts', []))}), comparing PROPOSED-HFIS, "
                f"CRISP-MAX, and WEIGHTED-MEAN numerically (see continuity_grid.csv / continuity_summary.csv)."
            )
            for method in ("PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"):
                rows = [r for r in by_bm if r["method"] == method and r["max_adjacent_jump"] is not None]
                if not rows:
                    continue
                mean_max_jump = sum(r["max_adjacent_jump"] for r in rows) / len(rows)
                total_transitions = sum(r["n_class_transitions"] for r in rows)
                lines.append(f"- {method}: mean largest adjacent-point jump {_num(mean_max_jump, 2)} index points across {len(rows)} boundary/context sweeps, {total_transitions} class transitions total.")
            smoothness = continuity.get("smoothness_comparison")
            if smoothness:
                lines.append(f"- Smoothness (local Lipschitz ratio, {smoothness['n_boundary_context_pairs_compared']} boundary/context pairs compared): {smoothness['conclusion']}")
        else:
            lines.append("Boundary continuity was not computed this run.")
        lines.append("")

        lines.append("## Fault-injection benchmark")
        fi = ev.get("fault_injection")
        if fi and fi.get("metrics_by_reason_code"):
            lines.append(
                f"Deterministic, pre-labeled synthetic scenarios ({fi['n_scenarios']} across {', '.join(fi.get('channels_covered') or [])}), "
                f"fully separate from the unlabeled real-data reason-code frequency below. Numbers here are the {fi.get('headline_dataset_split', 'validation')} "
                f"split ONLY -- a disjoint scenario set from calibration (which the Hampel grid below is tuned against), so no "
                f"parameter was tuned against the numbers being reported (see fault_detection_metrics.csv, "
                f"fault_detection_event_metrics.csv, fault_detection_confusion_matrix.csv for row-level, event-level, and confusion-matrix detail)."
            )
            weak_codes = []
            for m in fi["metrics_by_reason_code"]:
                lines.append(f"- {m['reason_code']} (row-level): precision={_num(m['precision'], 3)}, recall={_num(m['recall'], 3)}, F1={_num(m['f1'], 3)} (tp={m['tp']}, fp={m['fp']}, fn={m['fn']}).")
                if m["f1"] is not None and m["f1"] < 0.5:
                    weak_codes.append(m["reason_code"])
            event_metrics = (fi.get("event_level_metrics_by_split") or {}).get(fi.get("headline_dataset_split", "validation")) or []
            for m in event_metrics:
                lines.append(
                    f"- {m['reason_code']} (event-level, tolerance={m['temporal_tolerance_samples']} samples): "
                    f"precision={_num(m['precision'], 3)}, recall={_num(m['recall'], 3)}, F1={_num(m['f1'], 3)} "
                    f"({m['n_true_events']} true event(s), {m['n_predicted_events']} predicted event(s))."
                )
            if weak_codes:
                lines.append(
                    f"- **Disclosed limitation**: {', '.join(weak_codes)} scored row-level F1 below 0.5 on this benchmark -- "
                    f"reported here as-is, not hidden or excluded from the summary."
                )
            if fi.get("false_rejection_rate_for_genuine_events") is not None:
                lines.append(f"- Genuine sustained events falsely rejected: {_pct(fi['false_rejection_rate_for_genuine_events'])}.")
            hc = fi.get("hampel_calibration") or {}
            if hc:
                lines.append(
                    f"- Hampel calibration grid (window_size x mad_multiplier) evaluated on calibration and validation "
                    f"scenario splits; current configuration (window_size={hc.get('current_window_size')}, "
                    f"mad_multiplier={hc.get('current_mad_multiplier')}) is retained regardless of this synthetic grid's "
                    f"outcome -- see hampel_calibration.csv and 'Provisional parameters engaged' above."
                )
        else:
            lines.append("Fault-injection benchmark was not computed this run.")
        lines.append("")

    lines.append("## Scientific cautions")
    lines.append("")
    for caution in CAUTIONS:
        lines.append(f"- {caution}")
    lines.append("")
    lines.append(WARNING_BANNER)
    return "\n".join(lines)


def write_run_narrative(summary: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RUN_NARRATIVE_MD
    path.write_text(build_run_narrative(summary), encoding="utf-8")
    return path
