"""``run_narrative.md``: a deterministic English narrative generated only
from fields already present in ``run_summary_{run_id}.json``.

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
    "No accuracy or macro-F1/kappa claim is made against unlabeled real observations; those metrics are computed only against the synthetic, pre-labeled ground-truth vectors reported under 'Method comparison'.",
]


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "not available"


def _num(value: float | None, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if value is not None else "not available"


def build_run_narrative(summary: dict) -> str:
    lines: list[str] = [WARNING_BANNER, "", "# iaq_hfis Run Narrative", ""]

    lines.append(
        f"Run `{summary['run_id']}` computed the hierarchical fuzzy indoor air quality index over "
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
    lines.append("")

    ev = summary.get("evaluation")
    lines.append("## Method comparison")
    if ev is None:
        lines.append("Evaluation (baselines, agreement, masking, ground-truth scoring, stability, sensitivity) was not run for this run_id. Run `iaq_hfis evaluate --run-id <id>` to add it.")
        lines.append("")
    else:
        for a in ev.get("agreement", []):
            if a["percent_agreement"] is not None:
                lines.append(f"- {a['method_a']} and {a['method_b']} agreed on {_pct(a['percent_agreement'])} of {a['n']} compared timestamps (Cohen's kappa={_num(a['cohens_kappa'])}).")
            else:
                lines.append(f"- {a['method_a']} and {a['method_b']}: no comparable timestamps this run.")
        for m in ev.get("masking", []):
            if m["masking_rate"] is not None:
                lines.append(f"- {m['method']} hid a component that individually reached {m['severity_threshold']} in {_pct(m['masking_rate'])} of {m['n_critical_events']} such events.")
            else:
                lines.append(f"- {m['method']}: no component reached {m['severity_threshold']} this run, so a masking rate could not be computed.")
        for method, score in (ev.get("ground_truth") or {}).items():
            if score["macro_f1"] is not None:
                lines.append(f"- Against the synthetic boundary-adjacent ground truth (n={score['n']}), {method} scored macro-F1={_num(score['macro_f1'])}, Cohen's kappa={_num(score['cohens_kappa'])}.")
        lines.append("")

        lines.append("## Stability and sensitivity")
        stability = ev.get("stability")
        if stability is not None:
            lines.append(
                f"Under {stability['n_trials']} perturbation trials (fixed seed={stability['seed']}, each channel "
                f"perturbed within its declared sensor uncertainty) sampled at {stability['computed_ts']}, the index "
                f"class changed from the baseline ({stability['baseline_class']}) in {_pct(stability['class_change_rate'])} of trials."
            )
        else:
            lines.append("Stability was not sampled this run (no computed_ts had available components).")
        if ev.get("sensitivity"):
            lines.append(
                "Sensitivity to window duration and coverage threshold was swept at the manuscript-specified values "
                "(see the Sensitivity section of run_summary.md and sensitivity_window.csv / sensitivity_coverage.csv)."
            )
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
