"""``parameter_selection.json``: the machine-readable parameter-selection
provenance artifact required by the manuscript-validation task spec
(section 5.2's numbered requirements). Scoped to the one parameter pair in
this codebase that has an actual grid-search calibration procedure --
``hampel.window_size`` / ``hampel.mad_multiplier``
(:func:`iaq_hfis.evaluation.fault_injection.run_hampel_calibration`).

Records, for full auditability:

- the candidate grid searched;
- the calibration objective used to score it;
- the parameters actually selected (i.e. currently configured) and why;
- the frozen effective-configuration hash this applies to;
- the validation-split metrics for the configured value (never the split
  used to search the grid);
- an explicit statement that synthetic calibration is not equivalent to
  validation on manually labelled real faults.

Selected != best-on-calibration-grid here: the configured Hampel parameters
are LITERATURE_INFORMED (see :mod:`iaq_hfis.provenance`), retained
regardless of this grid's outcome -- the grid is a diagnostic cross-check,
not a selection procedure that actually changes the config. This is
deliberate and must never be described otherwise (spec: "Never label
parameters 'calibrated' merely because they came from a literature
example").
"""

from __future__ import annotations

from iaq_hfis.evaluation.fault_injection import HAMPEL_MULTIPLIER_GRID, HAMPEL_WINDOW_GRID

SYNTHETIC_CALIBRATION_DISCLAIMER = (
    "Synthetic calibration does not equal validation on manually labelled real faults. This grid search is "
    "scored entirely on deterministic synthetic fault-injection scenarios (see docs/fault_injection_audit.md); "
    "it has not been checked against any manually labelled real-world fault event. Treat "
    "validation_split_metrics_for_configured_value below as a synthetic-benchmark cross-check only, not a "
    "real-world accuracy claim."
)


def build_parameter_selection_artifact(
    hampel_calibration_rows: list,  # list[HampelCalibrationRow]-like objects with .dataset_split/.window_size/.mad_multiplier/.fault_recall/.genuine_event_preservation_rate/.objective_score/.selected
    current_window_size: int,
    current_mad_multiplier: float,
    config_hash: str,
) -> dict:
    calibration_rows = [r for r in hampel_calibration_rows if r.dataset_split == "calibration"]
    validation_rows = [r for r in hampel_calibration_rows if r.dataset_split == "validation"]

    best_calibration = max(
        (r for r in calibration_rows if r.objective_score is not None), key=lambda r: r.objective_score, default=None
    )
    configured_validation_row = next(
        (r for r in validation_rows if r.window_size == current_window_size and r.mad_multiplier == current_mad_multiplier),
        None,
    )

    return {
        "parameter_group": "hampel_filter",
        "candidate_grid": {
            "window_size": list(HAMPEL_WINDOW_GRID),
            "mad_multiplier": list(HAMPEL_MULTIPLIER_GRID),
            "n_combinations": len(HAMPEL_WINDOW_GRID) * len(HAMPEL_MULTIPLIER_GRID),
        },
        "calibration_objective": {
            "description": (
                "Balances 3 concerns, averaged: single_spike recall (catching real spikes), genuine-event "
                "preservation rate (not discarding genuine sustained events), and 1 - single_spike false-positive "
                "rate (not over-labeling ordinary points near a real transition). See "
                "iaq_hfis.evaluation.fault_injection._objective."
            ),
            "dataset_split_used_for_search": "calibration",
        },
        "selected_parameters": {
            "window_size": current_window_size,
            "mad_multiplier": current_mad_multiplier,
            "status": "LITERATURE_INFORMED",
        },
        "selection_rationale": (
            "The configured values are NOT selected from this calibration grid. They are retained from the "
            "manuscript's cited source (Pearson, Neuvo, Astola, Gabbouj, \"Generalized Hampel Filters\", 2016, "
            "Sec. 2 / Figs. 3-5 worked example: K=5 -> 11-point window, t=1) regardless of this grid's outcome. "
            "A change would only be adopted after separate empirical verification against real live-data "
            "deployment, never from synthetic-benchmark evidence alone -- see "
            "iaq_hfis.provenance.STATUS_VALUES: LITERATURE_INFORMED is deliberately distinct from "
            "CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT for exactly this reason."
        ),
        "frozen_effective_config_hash": config_hash,
        "best_calibration_split_result": (
            {
                "window_size": best_calibration.window_size,
                "mad_multiplier": best_calibration.mad_multiplier,
                "objective_score": best_calibration.objective_score,
            }
            if best_calibration is not None
            else None
        ),
        "validation_split_metrics_for_configured_value": (
            {
                "window_size": configured_validation_row.window_size,
                "mad_multiplier": configured_validation_row.mad_multiplier,
                "fault_recall": configured_validation_row.fault_recall,
                "genuine_event_preservation_rate": configured_validation_row.genuine_event_preservation_rate,
                "objective_score": configured_validation_row.objective_score,
            }
            if configured_validation_row is not None
            else None
        ),
        "synthetic_calibration_disclaimer": SYNTHETIC_CALIBRATION_DISCLAIMER,
    }
