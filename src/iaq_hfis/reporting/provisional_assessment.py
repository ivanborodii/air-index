"""``provisional_parameter_assessment.md``: one row per PROVISIONAL
parameter, generated -- never hand-maintained -- from
:mod:`iaq_hfis.provenance` (current value, status, rationale, pipeline
stage) plus whatever calibration/sensitivity evidence actually exists for
it in ``run_summary_{pipeline_run_id}.json``, cross-checked against
``summary["provisional_parameters_used"]`` (the single authoritative
engaged-parameter list) so this report can never list a parameter as
engaged when the rest of the run's artifacts disagree.

Per parameter: current value, why provisional, where it's used, whether it
was calibrated (only true for hampel.window_size/mad_multiplier -- the only
parameters with an actual grid-search calibration procedure,
:func:`iaq_hfis.evaluation.fault_injection.run_hampel_calibration`), the
calibration/validation dataset used (if any), the sensitivity result (if
the parameter is directly swept by the multi-point sensitivity experiment,
or has a Hampel-calibration objective score), a plain-language note on
whether run conclusions depend strongly on it, and a recommended future
validation step.

Two hard rules enforced throughout: never claim calibration makes a
parameter universally valid (a synthetic benchmark's calibration result is
scoped to that benchmark, stated explicitly per row); never silently
promote a PROVISIONAL parameter to STANDARD_BASED here or anywhere else --
status changes only happen in provenance.py's own catalog, with a cited
source.
"""

from __future__ import annotations

from dataclasses import dataclass

from iaq_hfis.provenance import ParameterProvenance

PROVISIONAL_PARAMETER_ASSESSMENT_MD = "provisional_parameter_assessment.md"


@dataclass(frozen=True)
class _AssessmentMeta:
    """Hand-authored, reviewable qualitative judgment for one parameter --
    kept separate from the quantitative fields (which are always pulled
    live from run_summary.json/provenance, never hand-typed numbers)."""

    depends_strongly: str
    recommended_future_validation: str


# Keyed by provenance path. Every config-level PROVISIONAL parameter in
# provenance.collect_parameter_provenance must have an entry here (enforced
# by a unit test) -- a new provisional parameter with no entry would
# otherwise silently fall back to a generic placeholder.
_ASSESSMENTS: dict[str, _AssessmentMeta] = {
    "cadence.slot_match_tolerance_seconds": _AssessmentMeta(
        "Indirect: affects which raw samples are matched to the sample-cadence grid before aggregation; "
        "too tight a tolerance would silently manufacture MISSING samples, too loose would blend adjacent "
        "cadence slots. Does not affect fuzzy inference logic itself.",
        "Confirm the deployed sensors' actual sample-time jitter against this value over a longer live "
        "deployment window; tighten only if jitter is measurably smaller than half the cadence.",
    ),
    "hampel.window_size": _AssessmentMeta(
        "Direct but scoped: affects which raw samples are flagged single_spike and therefore excluded before "
        "aggregation -- changes here can shift window completeness and, rarely, which OK/PARTIAL/FAILED status "
        "a timestamp receives. Does not affect the fuzzy inference/HFIS-vs-baseline comparison logic itself.",
        "The synthetic fault-injection calibration grid (see below) is diagnostic only; any change to the "
        "configured value must be separately verified against a real live-data deployment period showing "
        "fewer false single_spike flags without missing genuine spikes, per the existing calibration policy.",
    ),
    "hampel.mad_multiplier": _AssessmentMeta(
        "Direct but scoped: same as hampel.window_size (paired parameter of the same filter).",
        "Same as hampel.window_size -- verify jointly, not independently, since they interact.",
    ),
    "confirmation.persistence_min_consecutive_samples": _AssessmentMeta(
        "Indirect: affects the SUSPECT-to-usable confirmation delay for every soft-check-flagged sample, "
        "which can shift window completeness. Does not affect fuzzy inference logic.",
        "Compare against real-data confirmation delay statistics once enough live SUSPECT events have "
        "accumulated to characterize a typical genuine-event confirmation time.",
    ),
    "confirmation.stuck_value_min_repeats": _AssessmentMeta(
        "Indirect: determines the exact-equality repeat count that triggers a stuck_value flag; affects "
        "completeness, not fuzzy inference.",
        "Review against the sensors' actual quantization step -- too small a repeat count risks flagging "
        "genuinely stable real readings (e.g. a steady room) as stuck.",
    ),
    "confirmation.gradual_drift_min_consecutive_steps": _AssessmentMeta(
        "Indirect: determines how many consecutive monotonic steps are required before a slow trend is "
        "even considered for the gradual_drift check; affects completeness, not fuzzy inference.",
        "Cross-check against real ventilation-driven CO2 decay curves to confirm this window is short enough "
        "to catch genuine sensor drift without false-flagging normal decay.",
    ),
    "confirmation.gradual_drift_magnitude_multiplier": _AssessmentMeta(
        "Indirect: sets the magnitude gate (x declared sensor uncertainty) a drift must clear to be flagged; "
        "affects completeness, not fuzzy inference. Directly benchmarked by the fault-injection gradual_drift "
        "scenarios (see fault_detection_metrics.csv) -- but that is a synthetic-scenario result, not a "
        "real-data validation of this exact multiplier value.",
        "Track real-data gradual_drift flagging frequency over time; a multiplier producing implausibly many "
        "or zero real flags would indicate this needs revisiting.",
    ),
    "confirmation.pm_cross_channel_tolerance_pct": _AssessmentMeta(
        "Indirect: affects only the PM1/PM2.5/PM4/PM10 cumulative-ordering hard-check, i.e. completeness "
        "for PM channels, not fuzzy inference.",
        "Verify against the SPS30's actual observed cross-channel noise on live data over a representative "
        "pollution-level range (this benchmark's synthetic scenario only tests one magnitude).",
    ),
    "profile_selection.season_month_ranges": _AssessmentMeta(
        "Direct: determines WHICH room/season temperature profile (and therefore which membership functions) "
        "applies to a given computed_ts -- a wrong season boundary would apply the wrong control region to "
        "real data near a seasonal transition.",
        "Confirm season cutover months against the actual regional climate the deployment site experiences, "
        "not a generic calendar split.",
    ),
    "control_regions.relative_humidity.transition_width": _AssessmentMeta(
        "Direct: a membership-construction parameter -- changes here directly change every computed index "
        "value and class whenever humidity is near a control-region boundary.",
        "This transition width is already floored at the RH sensor's declared uncertainty (auto-expanded if "
        "narrower); no further action beyond re-verifying that floor if the sensor is ever replaced.",
    ),
    "control_regions.output.transition_widths": _AssessmentMeta(
        "Direct: a membership-construction parameter for the OUTPUT scale itself -- changes here directly "
        "change the index value and class near every 25/50/75 output boundary.",
        "No manuscript-specified value exists; if a future manuscript revision specifies these widths "
        "explicitly, this becomes STANDARD_BASED and this entry should be removed.",
    ),
    "membership.output_transition_width": _AssessmentMeta(
        "Direct: same role as control_regions.output.transition_widths (used identically in "
        "membership construction for the output scale).",
        "Same as control_regions.output.transition_widths.",
    ),
    "evaluation.stability_seed": _AssessmentMeta(
        "None on the primary index computation: only affects which perturbation trials the multi-point "
        "stability experiment happens to draw, not the index/class computation itself. A different seed "
        "would change stability_summary.csv's exact numbers but not the pipeline's primary output.",
        "None needed -- the manuscript requires a fixed seed for reproducibility, not a specific value; "
        "any fixed value satisfies that requirement equally.",
    ),
    "evaluation.stability_n_trials": _AssessmentMeta(
        "None on the primary index computation: only affects the statistical precision (confidence interval "
        "width) of the stability experiment's own summary statistics, not the index/class computation itself.",
        "Increase if a future run's Wilson confidence intervals in stability_summary.csv are judged too wide "
        "to support a specific claim; bounded mainly by Raspberry Pi 5 runtime.",
    ),
    "evaluation.masking_severity_threshold": _AssessmentMeta(
        "None on the primary index computation: only defines which severity counts as 'hidden' for the "
        "masking-comparison diagnostic (masking_summary.csv), not the index/class computation itself.",
        "Consider reporting masking at multiple severity thresholds (not just Critical) if the manuscript "
        "ultimately wants a threshold-sensitivity view of the masking claim.",
    ),
    "fuzzy_engine.partial_mode_inference_rule": _AssessmentMeta(
        "Direct, but PARTIAL-only: this design choice governs every PARTIAL-completeness computed_ts's index "
        "value and dominance -- a materially different fraction of the dataset than OK timestamps, but real "
        "and non-negligible whenever any component is unavailable.",
        "If the manuscript is later revised to specify PARTIAL-mode mechanics explicitly, replace this "
        "AUTHOR-level design choice with the specified mechanism.",
    ),
}

_ROOM_PROFILE_ASSESSMENT = _AssessmentMeta(
    "Direct: a room/season profile's temperature control region is used for every computed_ts assigned to "
    "that room/season -- if provisional, every such timestamp's temperature membership (and therefore index "
    "value near a temperature boundary) rests on an unconfirmed number.",
    "Confirm against DBN B.2.5-67:2013's table for this exact room/season combination, or against a "
    "documented author decision citing a specific alternative source.",
)


def _assessment_for(path: str) -> _AssessmentMeta:
    if path.startswith("room_profiles."):
        return _ROOM_PROFILE_ASSESSMENT
    return _ASSESSMENTS.get(
        path,
        _AssessmentMeta(
            "Not yet assessed -- this parameter has no reviewed dependency judgment on file.",
            "Add a reviewed assessment for this parameter to reporting/provisional_assessment.py.",
        ),
    )


def _sensitivity_result_for(path: str, summary: dict) -> str:
    ev = summary.get("evaluation") or {}
    if path in ("cadence.aggregation_window_minutes",):
        rows = ((ev.get("sensitivity") or {}).get("by_parameter_value")) or []
        window_rows = [r for r in rows if r.get("varied_parameter") == "window_minutes"]
        if window_rows:
            return f"Swept directly by the multi-point sensitivity experiment: {len(window_rows)} window sizes tested; see sensitivity_window_summary.csv."
    if path in ("hampel.window_size", "hampel.mad_multiplier"):
        hc = (ev.get("fault_injection") or {}).get("hampel_calibration") or {}
        validation_score = hc.get("validation_objective_score_for_current_config")
        if validation_score is not None:
            return (
                f"Fault-injection calibration grid objective score for the currently configured value, "
                f"on the VALIDATION split (disjoint from the split used to search the grid): {validation_score:.3f} "
                f"(1.0 = perfect single_spike recall + perfect genuine-event preservation + zero single_spike FPR). "
                f"See hampel_calibration.csv for the full grid on both splits."
            )
        return "Fault-injection Hampel calibration grid was not computed for this run."
    return "Not directly swept by the multi-point sensitivity experiment or the fault-injection benchmark; no dedicated sensitivity result exists for this parameter in this run."


def _is_calibrated(path: str) -> bool:
    return path in ("hampel.window_size", "hampel.mad_multiplier")


def _calibration_dataset_for(path: str) -> str:
    if _is_calibrated(path):
        return (
            "Fault-injection benchmark's calibration split (single_spike + genuine-event scenarios, CO2 channel) "
            "for the grid search; validation split (disjoint scenario_ids and a numerically distinct scale/phase) "
            "for the reported objective score -- see docs/fault_injection_audit.md."
        )
    return "Not applicable -- no calibration procedure exists for this parameter."


def build_provisional_parameter_assessment_markdown(provenance: list[ParameterProvenance], summary: dict) -> str:
    from iaq_hfis.provenance import PROVISIONAL_LIKE_STATUSES

    engaged_paths = set(summary.get("provisional_parameters_used") or [])
    provisional_rows = sorted((p for p in provenance if p.status in PROVISIONAL_LIKE_STATUSES), key=lambda p: p.path)

    lines: list[str] = [
        "# Provisional Parameter Assessment",
        "",
        "> Software-generated from `iaq_hfis.provenance` and this run's `run_summary.json` -- not hand-maintained. "
        "Regenerate rather than hand-edit if anything here looks stale.",
        "",
        "**Two hard rules enforced throughout:** a synthetic benchmark's calibration result is scoped to that "
        "benchmark and is never claimed to make a parameter universally valid, and a parameter grounded in a "
        "literature example is never described as \"calibrated\" merely because of that citation; no parameter is "
        "promoted to STANDARD_BASED in this report -- that only happens in `iaq_hfis.provenance`'s own catalog, "
        "with a cited source, never here.",
        "",
        f"{len(provisional_rows)} parameter(s) with a provisional-like status "
        "(PROVISIONAL, AUTHOR_DEFINED_PROVISIONAL, LITERATURE_INFORMED, or CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT) "
        f"in the current configuration; {len(engaged_paths)} engaged (actually applied) this run.",
        "",
    ]

    for row in provisional_rows:
        engaged = row.path in engaged_paths
        meta = _assessment_for(row.path)
        lines += [
            f"## `{row.path}`",
            "",
            f"- **Status**: `{row.status}`",
            f"- **Current value**: `{row.effective_value}`{f' {row.unit}' if row.unit else ''}",
            f"- **Engaged this run**: {'yes' if engaged else 'no -- config-level default not exercised by this run’s data'}",
            f"- **Why provisional**: {row.scientific_rationale}",
            f"- **Where used**: pipeline stage `{row.pipeline_stage}`; source `{row.source_file}` (`{row.source_key_path}`)",
            f"- **Diagnostic calibration grid exists**: {'yes -- see parameter_selection.json (diagnostic only; the configured value is NOT selected from this grid, see below)' if _is_calibrated(row.path) else 'no'}",
            f"- **Calibration/validation dataset**: {_calibration_dataset_for(row.path)}",
            f"- **Sensitivity result**: {_sensitivity_result_for(row.path, summary)}",
            f"- **Do conclusions depend strongly on it?**: {meta.depends_strongly}",
            f"- **Recommended future validation**: {meta.recommended_future_validation}",
            "",
        ]

    return "\n".join(lines)
