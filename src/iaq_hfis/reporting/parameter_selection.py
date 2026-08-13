"""``parameter_selection.json``: the machine-readable parameter-selection
provenance artifact required by the manuscript-validation task spec
(section 5.2's numbered requirements). Scoped to the one parameter pair in
this codebase that has an actual grid-search calibration procedure --
``hampel.window_size`` / ``hampel.mad_multiplier``
(:func:`iaq_hfis.evaluation.fault_injection.run_hampel_calibration`).

Records, for full auditability:

- the candidate grid searched;
- the calibration objective used to score it;
- the parameters actually selected and why;
- the frozen effective-configuration hash this applies to;
- the validation-split metrics for the selected value (never the split
  used to search the grid, and never used to change the selection);
- an explicit statement that synthetic calibration is not equivalent to
  validation on manually labelled real faults.

``window_size`` is LITERATURE_INFORMED (point count only, per the
manuscript's own cited source -- see :mod:`iaq_hfis.quality.hampel`'s
module docstring for why the window SHAPE is causal, not that source's
centered example). ``mad_multiplier`` is
CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT: selected by
:func:`iaq_hfis.evaluation.fault_injection.select_hampel_multiplier` from
the calibration-split rows only, at window_size=11, comparing h in
{1.0, 2.0, 3.0}, via a deterministic tie-break order (highest calibration
S, then highest isolated-anomaly recall, then highest genuine-event
preservation, then lowest isolated-anomaly false-positive rate, then
smallest multiplier). The validation split is scored once for the selected
value and reported separately -- it is never inspected during selection.
"""

from __future__ import annotations

from iaq_hfis.evaluation.fault_injection import (
    HAMPEL_MULTIPLIER_GRID,
    HAMPEL_SELECTION_MULTIPLIER_GRID,
    HAMPEL_SELECTION_WINDOW_SIZE,
    HAMPEL_WINDOW_GRID,
    select_hampel_multiplier,
)

SYNTHETIC_CALIBRATION_DISCLAIMER = (
    "Synthetic calibration does not equal validation on manually labelled real faults. This grid search is "
    "scored entirely on deterministic synthetic fault-injection scenarios (see docs/fault_injection_audit.md); "
    "it has not been checked against any manually labelled real-world fault event. Treat "
    "validation_split_metrics_for_selected_value below as a synthetic-benchmark cross-check only, not a "
    "real-world accuracy claim."
)


def build_parameter_selection_artifact(
    hampel_calibration_rows: list,  # list[HampelCalibrationRow]-like objects
    current_window_size: int,
    current_mad_multiplier: float,
    config_hash: str,
) -> dict:
    calibration_rows = [r for r in hampel_calibration_rows if r.dataset_split == "calibration"]
    validation_rows = [r for r in hampel_calibration_rows if r.dataset_split == "validation"]

    selected_multiplier = select_hampel_multiplier(calibration_rows)
    selected_calibration_row = next(
        (r for r in calibration_rows if r.window_size == HAMPEL_SELECTION_WINDOW_SIZE and r.mad_multiplier == selected_multiplier),
        None,
    )
    selected_validation_row = next(
        (r for r in validation_rows if r.window_size == HAMPEL_SELECTION_WINDOW_SIZE and r.mad_multiplier == selected_multiplier),
        None,
    )
    config_matches_selection = current_window_size == HAMPEL_SELECTION_WINDOW_SIZE and current_mad_multiplier == selected_multiplier

    return {
        "parameter_group": "hampel_filter",
        "candidate_grid": {
            "window_size": list(HAMPEL_WINDOW_GRID),
            "mad_multiplier": list(HAMPEL_MULTIPLIER_GRID),
            "n_combinations": len(HAMPEL_WINDOW_GRID) * len(HAMPEL_MULTIPLIER_GRID),
        },
        "selection_grid": {
            "window_size": HAMPEL_SELECTION_WINDOW_SIZE,
            "mad_multiplier": list(HAMPEL_SELECTION_MULTIPLIER_GRID),
            "note": "The main comparison (task spec section 6): window size held fixed at the manuscript's causal-window size; only the multiplier is actually selected.",
        },
        "calibration_objective": {
            "description": (
                "S = (R_spike + P_event + (1 - FPR_spike)) / 3, where R_spike is isolated-anomaly (single_spike) "
                "recall, P_event is the genuine sustained-event preservation rate, and FPR_spike is the isolated-"
                "anomaly false-positive rate. See iaq_hfis.evaluation.fault_injection._objective."
            ),
            "dataset_split_used_for_search": "calibration",
            "selection_order": [
                "highest calibration S",
                "highest isolated-anomaly (single_spike) recall",
                "highest genuine-event preservation rate",
                "lowest isolated-anomaly (single_spike) false-positive rate",
                "smallest multiplier if still exactly tied",
            ],
        },
        "selected_parameters": {
            "window_size": HAMPEL_SELECTION_WINDOW_SIZE,
            "mad_multiplier": selected_multiplier,
            "window_size_status": "LITERATURE_INFORMED",
            "mad_multiplier_status": "CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT",
        },
        "selection_rationale": (
            f"window_size={HAMPEL_SELECTION_WINDOW_SIZE} carries over the point count from the manuscript's cited "
            "source (Pearson, Neuvo, Astola, Gabbouj, \"Generalized Hampel Filters\", 2016, Sec. 2 / Figs. 3-5: "
            "K=5 -> 11 points) -- literature-informed, held fixed for this comparison. mad_multiplier is selected "
            f"purely from the calibration split via the deterministic order above: h={selected_multiplier} scored "
            "highest calibration S among {1.0, 2.0, 3.0}. The validation split is scored once for this value and "
            "reported below, but was never inspected while selecting."
        ),
        "configured_value_matches_selection": config_matches_selection,
        "frozen_effective_config_hash": config_hash,
        "calibration_split_results": [
            {
                "window_size": r.window_size,
                "mad_multiplier": r.mad_multiplier,
                "fault_recall": r.fault_recall,
                "genuine_event_preservation_rate": r.genuine_event_preservation_rate,
                "single_spike_false_positive_rate": r.single_spike_false_positive_rate,
                "objective_score": r.objective_score,
            }
            for r in calibration_rows
            if r.window_size == HAMPEL_SELECTION_WINDOW_SIZE and r.mad_multiplier in HAMPEL_SELECTION_MULTIPLIER_GRID
        ],
        "validation_split_metrics_for_selected_value": (
            {
                "window_size": selected_validation_row.window_size,
                "mad_multiplier": selected_validation_row.mad_multiplier,
                "fault_recall": selected_validation_row.fault_recall,
                "genuine_event_preservation_rate": selected_validation_row.genuine_event_preservation_rate,
                "single_spike_false_positive_rate": selected_validation_row.single_spike_false_positive_rate,
                "objective_score": selected_validation_row.objective_score,
            }
            if selected_validation_row is not None
            else None
        ),
        "synthetic_calibration_disclaimer": SYNTHETIC_CALIBRATION_DISCLAIMER,
    }
