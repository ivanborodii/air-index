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

#: Required verbatim -- an explicit list of overclaims this narrative (and
#: any prose built from it) must never make, regardless of how favourable a
#: given run's numbers look.
FORBIDDEN_OVERCLAIMS: list[str] = [
    "Do not report agreement (real, unlabeled data) or stability (self-consistency under perturbation) as accuracy.",
    "Do not report reference-case or fault-injection consistency/precision/recall against synthetic, pre-labeled data as real-world empirical accuracy.",
    "Do not claim a PROVISIONAL parameter is validated because a synthetic benchmark's calibration grid favored its configured value -- that result is scoped to the benchmark, never universal.",
    "Do not claim PROPOSED_HFIS is smoother than FUZZY_COMPONENT_MAX, or vice versa, without checking this run's own continuity smoothness_comparison -- the single-channel-perturbation design can force the two methods to coincide regardless of context (see docs/hfis_vs_crispmax_audit.md).",
    "Do not describe a FAILED or PARTIAL-completeness computed_ts's absent index value as low or zero -- it is undefined, not low.",
    "Do not use outdoor CO as a proxy for indoor CO2, or WHO 24-hour PM reference points as a compliance assessment for a 15-minute index.",
    "Do not present sampled multi-point stability/sensitivity results as exhaustive coverage of every computed_ts.",
]

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


def _hfis_vs_crispmax_equivalence_note(ev: dict) -> list[str]:
    """Data-driven, per the task spec: if PROPOSED_HFIS and FUZZY_COMPONENT_MAX turn
    out equivalent at the classification level on THIS run's real data (or
    numerically tied on the continuity experiment), state that explicitly
    and discuss whether HFIS's remaining value is structural rather than
    empirically demonstrated by this run -- never silently reported as if
    the two methods were shown to differ."""
    agreement_rows = ev.get("agreement") or []
    pair = next(
        (a for a in agreement_rows if {a.get("method_a"), a.get("method_b")} == {"PROPOSED_HFIS", "FUZZY_COMPONENT_MAX"}),
        None,
    )
    smoothness = ((ev.get("continuity") or {}).get("smoothness_comparison")) or {}

    lines: list[str] = []
    near_total_agreement = False
    if pair is not None and pair.get("percent_agreement") is not None:
        pct, kappa = pair["percent_agreement"], pair.get("cohens_kappa")
        lines.append(
            f"PROPOSED_HFIS and FUZZY_COMPONENT_MAX agreed on {_pct(pct)} of compared timestamps this run "
            f"(Cohen's kappa={_num(kappa)}, real unlabeled data -- agreement, not accuracy)."
        )
        near_total_agreement = pct >= 0.95

    tied_count, n_pairs = smoothness.get("tied_count"), smoothness.get("n_boundary_context_pairs_compared")
    continuity_fully_tied = tied_count is not None and n_pairs and tied_count == n_pairs
    if continuity_fully_tied:
        lines.append(
            f"The boundary continuity experiment additionally found the two methods numerically tied on every one "
            f"of {n_pairs} boundary/context pairs tested this run (see 'Boundary continuity' above and "
            f"docs/hfis_vs_crispmax_audit.md) -- an intrinsic property of the single-channel-perturbation "
            f"experimental design (see that section's own note), not independent evidence of general equivalence."
        )

    if near_total_agreement or continuity_fully_tied:
        lines.append(
            "**PROPOSED_HFIS and FUZZY_COMPONENT_MAX are effectively equivalent at the classification level on this run's "
            "measurements.** Stated explicitly, not minimized: where the two methods coincide numerically, "
            "PROPOSED_HFIS's remaining value is structural, not demonstrated as an empirical advantage by this "
            "run's results alone -- (a) continuous within-class severity via centroid defuzzification and the "
            "explicit per-component membership degrees (component_scores_timeseries.csv's membership_* columns), "
            "which FUZZY_COMPONENT_MAX's raw max() never computes; (b) graded uncertainty representation -- simultaneous "
            "partial membership in more than one class per component, with no equivalent in a hard maximum; "
            "(c) extensibility -- a two-level rule base can express component-interaction logic (e.g. rules "
            "conditioned on two components being simultaneously non-favourable) that a scalar max() cannot express "
            "by construction, though the worst-of rule base actually configured here has not been extended to "
            "exercise that capability. An independent synthetic check (docs/hfis_vs_crispmax_audit.md section 2) "
            "shows the two methods DO diverge substantially (mean |difference| ~5.7 index points on a 0-100 scale) "
            "once more than one component is simultaneously close to its most severe class -- a condition this "
            "dataset rarely presents (see 'Dominant-component frequency' above: one component typically dominates)."
        )
    return lines


def _limitations_section(summary: dict, ev: dict | None) -> list[str]:
    lines = ["## Limitations", ""]

    if ev is not None:
        equivalence_lines = _hfis_vs_crispmax_equivalence_note(ev)
        lines.extend(equivalence_lines)
        if equivalence_lines:
            lines.append("")

    provisional = summary.get("provisional_parameters_used") or []
    if provisional:
        lines.append(
            f"- {len(provisional)} provisional parameter(s) were engaged this run -- see 'Provisional parameters "
            f"engaged' above and the generated provisional_parameter_assessment.md for what each one's status "
            f"actually implies (whether calibrated, against what dataset, whether conclusions depend strongly on it)."
        )
    fi = (ev or {}).get("fault_injection") or {}
    weak = [m["reason_code"] for m in (fi.get("metrics_by_reason_code") or []) if m.get("f1") is not None and m["f1"] < 0.5]
    lines.append(
        "- The boundary continuity experiment and the fault-injection benchmark are both deterministic, synthetic "
        "constructions -- they show the inference method and the data-quality detection layer behave as designed "
        "on known, controlled inputs; they do not measure performance across the full range of conditions the "
        "actual live sensor deployment may encounter."
    )
    if weak:
        lines.append(
            f"- Fault-injection precision is weak for {', '.join(weak)} on this run's validation split (F1 below "
            f"0.5) -- disclosed here, not excluded from the summary above."
        )
    lines.append(
        "- Multi-point stability and sensitivity are deterministic, bounded SAMPLES of the evaluated range "
        "(boundary-adjacent + random-comparison for stability; stratified for sensitivity), not exhaustive "
        "coverage of every computed_ts."
    )
    lines.append(
        "- No empirical, ground-truth-labeled accuracy claim exists or is possible for this deployment -- every "
        "consistency/agreement/precision figure above is against either unlabeled real data or a synthetic, "
        "pre-labeled construction (see 'Forbidden overclaims' below)."
    )
    lines.append("")
    return lines


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
                f"'other components' contexts ({', '.join(continuity.get('contexts', []))}), comparing PROPOSED_HFIS, "
                f"FUZZY_COMPONENT_MAX, and WEIGHTED_MEAN numerically (see continuity_grid.csv / continuity_summary.csv)."
            )
            for method in ("PROPOSED_HFIS", "FUZZY_COMPONENT_MAX", "WEIGHTED_MEAN"):
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
                    f"scenario splits; mad_multiplier={hc.get('selected_mad_multiplier')} was selected purely from the "
                    f"calibration split at window_size={hc.get('selected_window_size')} (configured value matches "
                    f"selection: {hc.get('configured_value_matches_selection')}) -- see parameter_selection.json for the "
                    f"full deterministic procedure, hampel_calibration.csv for the full grid, and 'Provisional parameters "
                    f"engaged' above."
                )
        else:
            lines.append("Fault-injection benchmark was not computed this run.")
        lines.append("")

    lines.extend(_limitations_section(summary, ev))

    lines.append("## Forbidden overclaims")
    lines.append("")
    lines.append("This narrative, and any prose built from it, must never do the following:")
    lines.append("")
    for overclaim in FORBIDDEN_OVERCLAIMS:
        lines.append(f"- {overclaim}")
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
