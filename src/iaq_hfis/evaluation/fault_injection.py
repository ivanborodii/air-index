"""Deterministic, labeled fault-injection benchmark for the data-quality
detection layer (:mod:`iaq_hfis.quality.hard_checks` /
:mod:`iaq_hfis.quality.soft_checks`), fully separate from analysis of real,
unlabeled observations (reason-code frequency on real data proves nothing
about detector correctness -- this benchmark does, because every injected
fault's true label is known in advance).

Each scenario is a short synthetic per-channel time series with one known
fault (or, for the two "should NOT be flagged" scenarios, a known genuine
event) injected at a known position. Running it through the real quality
layer and comparing assigned ``reason_codes``/``usable`` against the known
label gives true/false positive/negative counts per reason code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

from iaq_hfis.config import ConfirmationConfig, HampelConfig, SchemaMappingConfig, SensorSpecs
from iaq_hfis.quality.hard_checks import run_hard_checks
from iaq_hfis.quality.soft_checks import run_soft_checks
from iaq_hfis.schema import channel_uncertainty, dual_channel_tolerance
from iaq_hfis.timegrid import align_columns_to_slots

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_STATUS_MAP = {"ok": "VALID", "partial": "VALID", "failed": "INVALID", "disabled": "MISSING", "data_not_ready": "MISSING"}

REASON_CODES = ["single_spike", "stuck_value", "data_loss", "gradual_drift", "out_of_range"]


@dataclass(frozen=True)
class FaultEvent:
    scenario_id: str
    channel: str
    fault_type: str
    injected_at_index: int
    duration_samples: int
    description: str


@dataclass(frozen=True)
class SamplePrediction:
    scenario_id: str
    channel: str
    sample_index: int
    true_fault_type: str | None
    predicted_reason_codes: list[str]
    stage2_state: str
    usable: bool


@dataclass
class Scenario:
    scenario_id: str
    channel: str
    timestamps: list[datetime]
    values: list[float | None]
    true_fault_type: list[str | None]  # None = genuinely clean/no fault at this sample
    events: list[FaultEvent] = field(default_factory=list)
    secondary_values: list[float | None] | None = None  # for dual-channel (temperature/humidity)
    aux_pm: dict[str, list[float | None]] | None = None  # for PM cross-order check


def _oscillate(base: float, amplitude: float, n: int) -> list[float]:
    return [base + amplitude * math.sin(2 * math.pi * i / 7.0) for i in range(n)]


def _timestamps(n: int, cadence_seconds: int) -> list[datetime]:
    return [_START + timedelta(seconds=cadence_seconds * i) for i in range(n)]


def build_co2_scenarios(cadence_seconds: int, n: int = 40, variant: str = "dev") -> list[Scenario]:
    """``variant`` selects a deterministic parameter set: "dev" for
    calibration/development, "holdout" for a structurally similar but
    numerically distinct set used only for the final, one-time holdout
    evaluation (see :func:`run_hampel_calibration`)."""
    scale = 1.0 if variant == "dev" else 1.15
    phase = 0 if variant == "dev" else 3
    scenarios = []

    def osc(base: float, amplitude: float) -> list[float]:
        return [base + amplitude * math.sin(2 * math.pi * (i + phase) / 7.0) for i in range(n)]

    # single_spike: one isolated large deviation that reverts immediately (not confirmed).
    values = osc(700.0, 10.0)
    labels: list[str | None] = [None] * n
    spike_idx = n // 2
    values[spike_idx] = 700.0 + 400.0 * scale
    labels[spike_idx] = "single_spike"
    scenarios.append(Scenario(f"co2_single_spike_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_single_spike_{variant}", "co2", "single_spike", spike_idx, 1, "One isolated large deviation reverting immediately.")]))

    # out_of_range: one value outside the sensor's datasheet technical range.
    values = osc(700.0, 10.0)
    labels = [None] * n
    oor_idx = n // 2
    values[oor_idx] = 999999.0  # far outside SCD4x's 400-40000ppm technical range
    labels[oor_idx] = "out_of_range"
    scenarios.append(Scenario(f"co2_out_of_range_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_out_of_range_{variant}", "co2", "out_of_range", oor_idx, 1, "One value far outside the datasheet technical range.")]))

    # stuck_value: a run of exactly-equal values (sensor frozen).
    values = osc(700.0, 10.0)
    labels = [None] * n
    stuck_start, stuck_len = n // 2, 8
    for i in range(stuck_start, stuck_start + stuck_len):
        values[i] = 705.0
        labels[i] = "stuck_value"
    scenarios.append(Scenario(f"co2_stuck_value_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_stuck_value_{variant}", "co2", "stuck_value", stuck_start, stuck_len, "8 consecutive identical readings.")]))

    # data_loss: a run of missing samples (no raw row at all).
    values = osc(700.0, 10.0)
    labels = [None] * n
    loss_start, loss_len = n // 2, 5
    for i in range(loss_start, loss_start + loss_len):
        values[i] = None
        labels[i] = "data_loss"
    scenarios.append(Scenario(f"co2_data_loss_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_data_loss_{variant}", "co2", "data_loss", loss_start, loss_len, "5 consecutive missing samples.")]))

    # gradual_drift: a slow monotonic run whose cumulative magnitude clearly exceeds the real
    # drift gate (declared CO2 uncertainty x gradual_drift_magnitude_multiplier = 70 x 3 = 210ppm),
    # NOT explained by the gentle baseline oscillation.
    values = osc(700.0, 10.0)
    labels = [None] * n
    drift_start, drift_len = n // 2, 10
    for j, i in enumerate(range(drift_start, drift_start + drift_len)):
        values[i] = 700.0 + 35.0 * scale * (j + 1)  # cumulative ~350ppm over 10 steps, well beyond the 210ppm gate
        labels[i] = "gradual_drift"
    scenarios.append(Scenario(f"co2_gradual_drift_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_gradual_drift_{variant}", "co2", "gradual_drift", drift_start, drift_len, "Steep 10-step monotonic ramp exceeding the magnitude gate.")]))

    # genuine_rapid_event: a large but PERSISTENT step change (e.g. window opened) -- a real
    # environmental event, not a sensor fault. Must remain usable after persistence confirmation.
    values = osc(700.0, 10.0)
    labels = [None] * n
    step_start = n // 2
    for i in range(step_start, n):
        values[i] = 700.0 + 300.0 * scale  # sustained shift, holds for the rest of the scenario
        labels[i] = "genuine_event"
    scenarios.append(Scenario(f"co2_genuine_rapid_event_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_genuine_rapid_event_{variant}", "co2", "genuine_event", step_start, n - step_start, "Sustained step change (e.g. ventilation) -- must remain usable, not be discarded as a fault.")]))

    # persistent_real_change: similar but a gradual (not instant) sustained rise that holds --
    # must not be discarded as gradual_drift once it has persisted past the drift window.
    values = osc(700.0, 10.0)
    labels = [None] * n
    rise_start = n // 2
    for j, i in enumerate(range(rise_start, n)):
        values[i] = 700.0 + min(200.0 * scale, 20.0 * scale * (j + 1))
        labels[i] = "genuine_event"
    scenarios.append(Scenario(f"co2_persistent_real_change_{variant}", "co2", _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(f"co2_persistent_real_change_{variant}", "co2", "genuine_event", rise_start, n - rise_start, "Gradual but sustained real rise that plateaus and holds -- a genuine change, not a transient fault.")]))

    return scenarios


def build_pm_scenario(cadence_seconds: int, n: int = 40) -> Scenario:
    pm2_5 = _oscillate(4.0, 0.2, n)
    pm1 = [v - 0.5 for v in pm2_5]
    pm4 = [v + 0.5 for v in pm2_5]
    pm10 = [v + 1.0 for v in pm2_5]
    labels: list[str | None] = [None] * n
    idx = n // 2
    pm1[idx] = pm2_5[idx] + 5.0  # PM1 > PM2.5 -- violates cumulative-mass ordering
    labels[idx] = "pm_order_violation"
    return Scenario(
        "pm2_5_order_violation", "pm2_5", _timestamps(n, cadence_seconds), pm2_5, labels,
        [FaultEvent("pm2_5_order_violation", "pm2_5", "pm_order_violation", idx, 1, "PM1 mass exceeds PM2.5 mass at one sample, violating cumulative ordering.")],
        aux_pm={"mass_pm1_0": pm1, "mass_pm4_0": pm4, "mass_pm10": pm10},
    )


def run_scenario(
    scenario: Scenario,
    schema_mapping: SchemaMappingConfig,
    sensor_specs: SensorSpecs,
    hampel_cfg: HampelConfig,
    confirmation_cfg: ConfirmationConfig,
    pm_ordering_tolerance_pct: float,
) -> list[SamplePrediction]:
    channel_map = schema_mapping.channel(scenario.channel)
    # For data_loss samples the "actual" row must be genuinely absent (None) so run_hard_checks
    # takes its real DATA_LOSS path, not a present-but-null value.
    matched_slots = {t: (None if v is None else t) for t, v in zip(scenario.timestamps, scenario.values)}

    rows = []
    for t, v in zip(scenario.timestamps, scenario.values):
        if v is None:
            continue
        row = {"ts": t, channel_map.source_column: v, channel_map.device_status_column: "ok"}
        if scenario.aux_pm:
            for col, vals in scenario.aux_pm.items():
                row[col] = vals[scenario.timestamps.index(t)]
            row["mass_pm2_5"] = v
            row["mass_pm10"] = scenario.aux_pm.get("mass_pm10", [None] * len(scenario.timestamps))[scenario.timestamps.index(t)]
        if scenario.secondary_values is not None and channel_map.secondary_column:
            row[channel_map.secondary_column] = scenario.secondary_values[scenario.timestamps.index(t)]
        rows.append(row)
    raw_df = pd.DataFrame(rows)

    stage1_df = run_hard_checks(raw_df, matched_slots, scenario.channel, channel_map, sensor_specs, _STATUS_MAP, pm_ordering_tolerance_pct)

    align_columns = [channel_map.source_column]
    if scenario.aux_pm:
        align_columns += list(scenario.aux_pm.keys()) + ["mass_pm2_5", "mass_pm10"]
    if scenario.secondary_values is not None and channel_map.secondary_column:
        align_columns.append(channel_map.secondary_column)
    aligned_raw = align_columns_to_slots(raw_df, matched_slots, align_columns) if not raw_df.empty else pd.DataFrame(columns=align_columns, index=list(matched_slots.keys()))

    drift_gate = channel_uncertainty(scenario.channel, schema_mapping, sensor_specs) * confirmation_cfg.gradual_drift_magnitude_multiplier
    dual_tol = dual_channel_tolerance(scenario.channel, schema_mapping, sensor_specs) if scenario.channel in ("temperature", "humidity") else 0.0

    stage2_df = run_soft_checks(stage1_df, scenario.channel, channel_map, aligned_raw, None, hampel_cfg, confirmation_cfg, drift_gate, dual_tol)

    predictions = []
    for i, (t, true_label) in enumerate(zip(scenario.timestamps, scenario.true_fault_type)):
        row = stage2_df[stage2_df["ts"] == t].iloc[0]
        predictions.append(
            SamplePrediction(
                scenario_id=scenario.scenario_id, channel=scenario.channel, sample_index=i, true_fault_type=true_label,
                predicted_reason_codes=list(row["reason_codes"]), stage2_state=row["stage2_state"], usable=bool(row["usable"]),
            )
        )
    return predictions


def run_benchmark(
    schema_mapping: SchemaMappingConfig,
    sensor_specs: SensorSpecs,
    hampel_cfg: HampelConfig,
    confirmation_cfg: ConfirmationConfig,
    pm_ordering_tolerance_pct: float,
    cadence_seconds: int,
) -> tuple[list[FaultEvent], list[SamplePrediction]]:
    scenarios = build_co2_scenarios(cadence_seconds) + [build_pm_scenario(cadence_seconds)]
    events = [e for s in scenarios for e in s.events]
    predictions = [p for s in scenarios for p in run_scenario(s, schema_mapping, sensor_specs, hampel_cfg, confirmation_cfg, pm_ordering_tolerance_pct)]
    return events, predictions


@dataclass(frozen=True)
class FaultDetectionMetric:
    reason_code: str
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    false_positive_rate: float | None
    mean_detection_delay: float | None


def score_predictions(predictions: list[SamplePrediction]) -> list[FaultDetectionMetric]:
    """TP/FP/FN per reason code, computed against ``true_fault_type``.
    'genuine_event' true labels are never a fault -- any reason_code
    predicted there counts as a false positive under that reason_code."""
    metrics = []
    for code in REASON_CODES:
        tp = fp = fn = 0
        delays = []
        for scenario_id in {p.scenario_id for p in predictions}:
            scenario_preds = sorted((p for p in predictions if p.scenario_id == scenario_id), key=lambda p: p.sample_index)
            true_indices = [p.sample_index for p in scenario_preds if p.true_fault_type == code]
            first_detected = None
            for p in scenario_preds:
                predicted = code in p.predicted_reason_codes
                is_true = p.true_fault_type == code
                if predicted and is_true:
                    tp += 1
                    if first_detected is None:
                        first_detected = p.sample_index
                elif predicted and not is_true:
                    fp += 1
                elif not predicted and is_true:
                    fn += 1
            if true_indices and first_detected is not None:
                delays.append(first_detected - true_indices[0])
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall and (precision + recall) > 0 else None
        n_negative = sum(1 for p in predictions if p.true_fault_type != code)
        fpr = fp / n_negative if n_negative > 0 else None
        metrics.append(FaultDetectionMetric(code, tp, fp, fn, precision, recall, f1, fpr, (sum(delays) / len(delays)) if delays else None))
    return metrics


def false_rejection_rate_for_genuine_events(predictions: list[SamplePrediction]) -> float | None:
    """Of samples labeled 'genuine_event' (a real environmental change, not
    a fault), the fraction that ended up unusable -- these must NOT be
    discarded."""
    genuine = [p for p in predictions if p.true_fault_type == "genuine_event"]
    if not genuine:
        return None
    rejected = sum(1 for p in genuine if not p.usable)
    return rejected / len(genuine)


def confirmation_recovery_rate(predictions: list[SamplePrediction]) -> float | None:
    """Of samples that reached SUSPECT (a candidate anomaly), the fraction
    ultimately confirmed usable -- i.e. correctly recovered rather than
    discarded."""
    suspect = [p for p in predictions if p.stage2_state == "SUSPECT"]
    if not suspect:
        return None
    return sum(1 for p in suspect if p.usable) / len(suspect)


#: Candidate grid for Hampel calibration. Only single_spike detection and
#: genuine-event preservation depend on these parameters -- stuck_value,
#: data_loss, and gradual_drift use separate, Hampel-independent detectors.
#: Deliberately small (bounded runtime: this grid re-runs the full quality
#: layer on every 'iaq_hfis evaluate' call, not just once).
HAMPEL_WINDOW_GRID = [7, 11, 15]
HAMPEL_MULTIPLIER_GRID = [1.0, 2.0, 3.0]


@dataclass(frozen=True)
class HampelCalibrationRow:
    dataset_split: str  # "development" | "holdout"
    window_size: int
    mad_multiplier: float
    fault_recall: float | None
    genuine_event_preservation_rate: float | None
    objective_score: float | None
    selected: bool


def _hampel_affected_scenarios(cadence_seconds: int, variant: str) -> list[Scenario]:
    all_scenarios = build_co2_scenarios(cadence_seconds, variant=variant)
    return [s for s in all_scenarios if s.scenario_id.startswith(("co2_single_spike", "co2_genuine_rapid_event", "co2_persistent_real_change"))]


def _objective(fault_recall: float | None, preservation_rate: float | None, single_spike_fpr: float | None) -> float | None:
    """Balances 3 concerns: catching real spikes (recall), not discarding
    genuine sustained events (preservation), and not over-labeling ordinary
    points near a real transition as single_spike even when they remain
    usable (1 - false_positive_rate) -- the concern that originally
    motivated this calibration (a very high real-data single_spike count)."""
    if fault_recall is None or preservation_rate is None or single_spike_fpr is None:
        return None
    return (fault_recall + preservation_rate + (1.0 - single_spike_fpr)) / 3.0


def run_hampel_calibration(
    schema_mapping: SchemaMappingConfig,
    sensor_specs: SensorSpecs,
    confirmation_cfg: ConfirmationConfig,
    pm_ordering_tolerance_pct: float,
    cadence_seconds: int,
    current_window_size: int,
    current_mad_multiplier: float,
) -> list[HampelCalibrationRow]:
    """Documented calibration protocol (task spec section 10.3):

    1. Grid-search ``HAMPEL_WINDOW_GRID`` x ``HAMPEL_MULTIPLIER_GRID`` on the
       *development* scenario split only.
    2. Score each combination by a balanced objective: single_spike recall
       (fault_recall) and the fraction of genuine sustained events NOT
       falsely rejected (genuine_event_preservation_rate), averaged.
    3. Report the *holdout* split's performance for the config actually
       kept in use -- computed once, not used to pick the parameters.
    4. The originally configured (window_size, mad_multiplier) is always
       marked ``selected`` here: per the calibration policy, a change is
       only adopted after separate empirical verification against real
       live data (see config/iaq_hfis.yaml's hampel section for that
       history), not from synthetic-benchmark evidence alone. This grid is
       diagnostic, not a proposal to silently override the configured value.
    """
    rows: list[HampelCalibrationRow] = []
    dev_scenarios = _hampel_affected_scenarios(cadence_seconds, "dev")
    holdout_scenarios = _hampel_affected_scenarios(cadence_seconds, "holdout")

    for split, scenarios in (("development", dev_scenarios), ("holdout", holdout_scenarios)):
        for window_size in HAMPEL_WINDOW_GRID:
            for mad_multiplier in HAMPEL_MULTIPLIER_GRID:
                hampel_cfg = HampelConfig(window_size=window_size, mad_multiplier=mad_multiplier)
                predictions = [p for s in scenarios for p in run_scenario(s, schema_mapping, sensor_specs, hampel_cfg, confirmation_cfg, pm_ordering_tolerance_pct)]
                metrics = {m.reason_code: m for m in score_predictions(predictions)}
                fault_recall = metrics["single_spike"].recall
                single_spike_fpr = metrics["single_spike"].false_positive_rate
                preservation = 1.0 - fr if (fr := false_rejection_rate_for_genuine_events(predictions)) is not None else None
                objective = _objective(fault_recall, preservation, single_spike_fpr)
                selected = window_size == current_window_size and mad_multiplier == current_mad_multiplier
                rows.append(HampelCalibrationRow(split, window_size, mad_multiplier, fault_recall, preservation, objective, selected))
    return rows
