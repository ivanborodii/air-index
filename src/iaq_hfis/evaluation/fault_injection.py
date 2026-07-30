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


def dataset_split_of(scenario_id: str) -> str:
    """"calibration" | "validation", derived from the scenario_id suffix
    every scenario builder appends -- the single place this mapping lives,
    so events/predictions/metrics can never disagree on which split a
    scenario belongs to."""
    return "validation" if scenario_id.endswith("_validation") else "calibration"


@dataclass(frozen=True)
class FaultEvent:
    scenario_id: str
    channel: str
    fault_type: str
    injected_at_index: int
    duration_samples: int
    description: str

    @property
    def dataset_split(self) -> str:
        return dataset_split_of(self.scenario_id)


@dataclass(frozen=True)
class SamplePrediction:
    scenario_id: str
    channel: str
    sample_index: int
    true_fault_type: str | None
    predicted_reason_codes: list[str]
    stage2_state: str
    usable: bool

    @property
    def dataset_split(self) -> str:
        return dataset_split_of(self.scenario_id)


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


def build_channel_scenarios(
    channel: str,
    cadence_seconds: int,
    n: int,
    variant: str,
    base: float,
    amplitude: float,
    spike_magnitude: float,
    oor_value: float,
    stuck_value: float,
    drift_step_magnitude: float,
    genuine_step_magnitude: float,
    include_genuine_events: bool = True,
    spike_magnitude_alt: float | None = None,
    stuck_len_alt: int | None = None,
    dual_channel: bool = False,
) -> list[Scenario]:
    """Generic single-input-channel fault-scenario builder, parameterized so
    the same deterministic construction applies to any of CO2, temperature,
    humidity, PM2.5, or PM10 -- each channel gets its own physically
    plausible baseline/amplitude/magnitudes (declared uncertainty and
    technical range differ per datasheet), but the fault *shapes* (spike,
    out-of-range, stuck, data-loss, drift, genuine event) are identical
    across channels so their detection performance is directly comparable.

    ``dual_channel=True`` (temperature, humidity) populates a synthetic
    secondary-sensor reading that exactly tracks the primary value, so the
    real dual-channel confirmation logic (:func:`iaq_hfis.quality.confirmation.confirm_dual_channel_event`)
    has something to corroborate against. Without this, a genuine sustained
    event can NEVER reach "confirmed usable" for these two channels -- their
    confirmation requires agreement with a duplicate sensor OR a
    corroborating outdoor trend (neither available in a synthetic, isolated
    scenario), so omitting secondary_values entirely would silently and
    permanently fail every genuine-event scenario for these channels
    regardless of the fault-detection logic's actual correctness.

    ``variant`` selects a deterministic parameter set: "calibration" for
    grid-search/development, "validation" for a structurally similar but
    numerically distinct set used only for final, one-time held-out
    reporting (see :func:`run_benchmark` / :func:`run_hampel_calibration`) --
    no scenario or timestamp is ever shared between the two variants, so
    there is no data leakage between calibrating a parameter and reporting
    its performance.

    ``spike_magnitude_alt``/``stuck_len_alt``, when given, add a SECOND
    single_spike/stuck_value scenario at a different magnitude/duration --
    "multiple magnitudes/durations where meaningful" is deliberately scoped
    to one extra variant per fault type per channel here (not an exhaustive
    sweep); see docs/fault_injection_audit.md for the disclosed limitation.
    """
    scale = 1.0 if variant == "calibration" else 1.15
    phase = 0 if variant == "calibration" else 3
    scenarios: list[Scenario] = []

    def osc() -> list[float]:
        return [base + amplitude * math.sin(2 * math.pi * (i + phase) / 7.0) for i in range(n)]

    def secondary_for(values: list[float | None]) -> list[float | None] | None:
        # Synthetic secondary sensor that exactly tracks the primary -- see the
        # dual_channel docstring above for why this is necessary, not optional,
        # for temperature/humidity's confirmation logic to ever succeed here.
        return list(values) if dual_channel else None

    def add_spike(suffix: str, magnitude: float) -> None:
        values = osc()
        labels: list[str | None] = [None] * n
        idx = n // 2
        values[idx] = base + magnitude * scale
        labels[idx] = "single_spike"
        sid = f"{channel}_single_spike{suffix}_{variant}"
        scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                                   [FaultEvent(sid, channel, "single_spike", idx, 1, f"One isolated large deviation ({magnitude:+.1f}) reverting immediately.")],
                                   secondary_values=secondary_for(values)))

    add_spike("", spike_magnitude)
    if spike_magnitude_alt is not None:
        add_spike("_alt", spike_magnitude_alt)

    # out_of_range: one value outside the sensor's datasheet technical range.
    values = osc()
    labels = [None] * n
    oor_idx = n // 2
    values[oor_idx] = oor_value
    labels[oor_idx] = "out_of_range"
    sid = f"{channel}_out_of_range_{variant}"
    scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(sid, channel, "out_of_range", oor_idx, 1, "One value far outside the datasheet technical range.")],
                               secondary_values=secondary_for(values)))

    def add_stuck(suffix: str, stuck_len: int) -> None:
        values = osc()
        labels: list[str | None] = [None] * n
        stuck_start = n // 2
        for i in range(stuck_start, stuck_start + stuck_len):
            values[i] = stuck_value
            labels[i] = "stuck_value"
        sid = f"{channel}_stuck_value{suffix}_{variant}"
        scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                                   [FaultEvent(sid, channel, "stuck_value", stuck_start, stuck_len, f"{stuck_len} consecutive identical readings.")],
                                   secondary_values=secondary_for(values)))

    add_stuck("", 8)
    if stuck_len_alt is not None:
        add_stuck("_alt", stuck_len_alt)

    # data_loss: a run of missing samples (no raw row at all).
    values = osc()
    labels = [None] * n
    loss_start, loss_len = n // 2, 5
    for i in range(loss_start, loss_start + loss_len):
        values[i] = None
        labels[i] = "data_loss"
    sid = f"{channel}_data_loss_{variant}"
    scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(sid, channel, "data_loss", loss_start, loss_len, "5 consecutive missing samples.")],
                               secondary_values=secondary_for(values)))

    # gradual_drift: a slow monotonic run whose cumulative magnitude clearly exceeds the real
    # drift gate, NOT explained by the gentle baseline oscillation.
    values = osc()
    labels = [None] * n
    drift_start, drift_len = n // 2, 10
    for j, i in enumerate(range(drift_start, drift_start + drift_len)):
        values[i] = base + drift_step_magnitude * scale * (j + 1)
        labels[i] = "gradual_drift"
    sid = f"{channel}_gradual_drift_{variant}"
    scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                               [FaultEvent(sid, channel, "gradual_drift", drift_start, drift_len, "Steep 10-step monotonic ramp exceeding the magnitude gate.")],
                               secondary_values=secondary_for(values)))

    if include_genuine_events:
        # genuine_rapid_event: a large but PERSISTENT step change (e.g. window opened) -- a real
        # environmental event, not a sensor fault. Must remain usable after persistence confirmation.
        values = osc()
        labels = [None] * n
        step_start = n // 2
        for i in range(step_start, n):
            values[i] = base + genuine_step_magnitude * scale
            labels[i] = "genuine_event"
        sid = f"{channel}_genuine_rapid_event_{variant}"
        scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                                   [FaultEvent(sid, channel, "genuine_event", step_start, n - step_start, "Sustained step change -- must remain usable, not be discarded as a fault.")],
                                   secondary_values=secondary_for(values)))

        # persistent_real_change: similar but a gradual (not instant) sustained rise that holds --
        # must not be discarded as gradual_drift once it has persisted past the drift window.
        values = osc()
        labels = [None] * n
        rise_start = n // 2
        for j, i in enumerate(range(rise_start, n)):
            values[i] = base + min(genuine_step_magnitude * scale * 2.0 / 3.0, (genuine_step_magnitude * scale / 10.0) * (j + 1))
            labels[i] = "genuine_event"
        sid = f"{channel}_persistent_real_change_{variant}"
        scenarios.append(Scenario(sid, channel, _timestamps(n, cadence_seconds), values, labels,
                                   [FaultEvent(sid, channel, "genuine_event", rise_start, n - rise_start, "Gradual but sustained real rise that plateaus and holds -- a genuine change, not a transient fault.")],
                                   secondary_values=secondary_for(values)))

    return scenarios


def build_co2_scenarios(cadence_seconds: int, n: int = 40, variant: str = "calibration") -> list[Scenario]:
    return build_channel_scenarios(
        "co2", cadence_seconds, n, variant,
        base=700.0, amplitude=10.0, spike_magnitude=400.0, oor_value=999999.0,  # far outside SCD4x's 400-40'000ppm range
        stuck_value=705.0, drift_step_magnitude=35.0, genuine_step_magnitude=300.0,
        spike_magnitude_alt=120.0,  # a materially smaller spike, closer to the detection threshold
    )


def build_temperature_scenarios(cadence_seconds: int, n: int = 40, variant: str = "calibration") -> list[Scenario]:
    return build_channel_scenarios(
        "temperature", cadence_seconds, n, variant,
        base=20.0, amplitude=0.3, spike_magnitude=8.0, oor_value=200.0,  # far outside BME688's -40..85 degC range
        stuck_value=20.2, drift_step_magnitude=0.4, genuine_step_magnitude=4.0,
        spike_magnitude_alt=2.5, dual_channel=True,
    )


def build_humidity_scenarios(cadence_seconds: int, n: int = 40, variant: str = "calibration") -> list[Scenario]:
    return build_channel_scenarios(
        "humidity", cadence_seconds, n, variant,
        base=45.0, amplitude=2.0, spike_magnitude=35.0, oor_value=150.0,  # far outside the 0-100% RH range
        stuck_value=46.0, drift_step_magnitude=3.0, genuine_step_magnitude=25.0,
        spike_magnitude_alt=15.0, dual_channel=True,
    )


def build_pm10_scenarios(cadence_seconds: int, n: int = 40, variant: str = "calibration") -> list[Scenario]:
    return build_channel_scenarios(
        "pm10", cadence_seconds, n, variant,
        base=6.0, amplitude=0.3, spike_magnitude=40.0, oor_value=99999.0,  # far outside SPS30's 0-1'000 ug/m3 range
        stuck_value=6.5, drift_step_magnitude=8.0, genuine_step_magnitude=30.0,
        include_genuine_events=False,  # genuine-event preservation is only benchmarked for CO2 (Hampel calibration target)
    )


def build_pm_scenario(cadence_seconds: int, n: int = 40, variant: str = "calibration") -> Scenario:
    scale = 1.0 if variant == "calibration" else 1.15
    phase = 0 if variant == "calibration" else 3
    pm2_5 = [4.0 + 0.2 * math.sin(2 * math.pi * (i + phase) / 7.0) for i in range(n)]
    pm1 = [v - 0.5 for v in pm2_5]
    pm4 = [v + 0.5 for v in pm2_5]
    pm10 = [v + 1.0 for v in pm2_5]
    labels: list[str | None] = [None] * n
    idx = n // 2
    pm1[idx] = pm2_5[idx] + 5.0 * scale  # PM1 > PM2.5 -- violates cumulative-mass ordering
    # The real quality layer has no distinct PM_ORDER_VIOLATION reason code (see
    # iaq_hfis.constants.ReasonCode) -- check_pm_ordering() correctly reuses
    # 'out_of_range' for a physically-implausible mass ordering. The true label
    # here MUST match that, not an unscoreable label absent from REASON_CODES:
    # confirmed bug fix (2026) -- "pm_order_violation" could never be a true
    # positive against any tracked reason code and silently inflated
    # out_of_range's false-positive count every time this scenario ran.
    labels[idx] = "out_of_range"
    sid = f"pm2_5_order_violation_{variant}"
    return Scenario(
        sid, "pm2_5", _timestamps(n, cadence_seconds), pm2_5, labels,
        [FaultEvent(sid, "pm2_5", "out_of_range", idx, 1, "PM1 mass exceeds PM2.5 mass at one sample, violating cumulative ordering -- correctly classified as out_of_range (no distinct PM-ordering reason code exists).")],
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


def build_all_scenarios(cadence_seconds: int) -> list[Scenario]:
    """Every fault-injection scenario across every benchmarked channel
    (CO2, temperature, humidity, PM10, PM2.5 order-check) and both dataset
    splits (calibration, validation) -- disjoint scenario_ids and a
    different deterministic scale/phase per split, so nothing here can leak
    from calibration into the validation numbers actually reported."""
    scenarios: list[Scenario] = []
    for variant in ("calibration", "validation"):
        scenarios += build_co2_scenarios(cadence_seconds, variant=variant)
        scenarios += build_temperature_scenarios(cadence_seconds, variant=variant)
        scenarios += build_humidity_scenarios(cadence_seconds, variant=variant)
        scenarios += build_pm10_scenarios(cadence_seconds, variant=variant)
        scenarios.append(build_pm_scenario(cadence_seconds, variant=variant))
    return scenarios


def run_benchmark(
    schema_mapping: SchemaMappingConfig,
    sensor_specs: SensorSpecs,
    hampel_cfg: HampelConfig,
    confirmation_cfg: ConfirmationConfig,
    pm_ordering_tolerance_pct: float,
    cadence_seconds: int,
) -> tuple[list[FaultEvent], list[SamplePrediction]]:
    scenarios = build_all_scenarios(cadence_seconds)
    events = [e for s in scenarios for e in s.events]
    predictions = [p for s in scenarios for p in run_scenario(s, schema_mapping, sensor_specs, hampel_cfg, confirmation_cfg, pm_ordering_tolerance_pct)]
    return events, predictions


@dataclass(frozen=True)
class FaultDetectionMetric:
    reason_code: str
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None
    f1: float | None
    specificity: float | None
    false_positive_rate: float | None
    mean_detection_delay: float | None


def score_predictions(predictions: list[SamplePrediction], dataset_split: str | None = None) -> list[FaultDetectionMetric]:
    """Row-level TP/FP/FN/TN per reason code, computed against
    ``true_fault_type``. 'genuine_event' true labels are never a fault --
    any reason_code predicted there counts as a false positive under that
    reason_code. See :func:`match_events` for the corresponding event-level
    metrics (row-level counts every affected sample; event-level counts
    each injected fault once, regardless of its duration).

    ``dataset_split``, when given, restricts scoring to "calibration" or
    "validation" predictions only -- the final, publication-facing numbers
    must come from the validation split (never calibration, which is what
    any provisional parameter was tuned against)."""
    if dataset_split is not None:
        predictions = [p for p in predictions if p.dataset_split == dataset_split]
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
        tn = n_negative - fp
        fpr = fp / n_negative if n_negative > 0 else None
        specificity = 1.0 - fpr if fpr is not None else None
        metrics.append(FaultDetectionMetric(code, tp, fp, fn, tn, precision, recall, f1, specificity, fpr, (sum(delays) / len(delays)) if delays else None))
    return metrics


@dataclass(frozen=True)
class EventDetectionMetric:
    reason_code: str
    dataset_split: str
    temporal_tolerance_samples: int
    n_true_events: int
    n_predicted_events: int
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    mean_detection_delay: float | None


def _group_into_intervals(indices: list[int], temporal_tolerance_samples: int) -> list[tuple[int, int]]:
    """Groups a sorted set of sample indices where a reason_code was
    predicted into contiguous "predicted event" intervals [start, end],
    merging indices no more than ``temporal_tolerance_samples`` apart into
    the SAME interval -- otherwise a single multi-sample detection would be
    double-counted as many separate events."""
    if not indices:
        return []
    ordered = sorted(set(indices))
    intervals: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for idx in ordered[1:]:
        if idx - prev <= temporal_tolerance_samples + 1:
            prev = idx
        else:
            intervals.append((start, prev))
            start = prev = idx
    intervals.append((start, prev))
    return intervals


def match_events(
    events: list[FaultEvent], predictions: list[SamplePrediction], reason_code: str, temporal_tolerance_samples: int = 1
) -> EventDetectionMetric:
    """Event-level matching for one reason_code: each injected fault
    (regardless of how many samples it spans) is matched to at most one
    predicted detection interval, and vice versa (one-to-one) -- this is
    what prevents a single multi-sample fault from being double-counted as
    N separate true positives (a real risk of the row-level metric alone).

    Matching, per scenario: predicted sample indices carrying ``reason_code``
    are grouped into contiguous intervals (:func:`_group_into_intervals`,
    same tolerance); a true event and a predicted interval match if they
    overlap or are within ``temporal_tolerance_samples`` of each other.
    Matching is greedy by absolute start-distance (deterministic, and exact
    for the benchmark's one-event-per-scenario scenarios; still well-defined
    if a scenario is ever extended to carry multiple events of the same
    type). Every scenario is self-contained (a short, isolated synthetic
    series) with only one event of a given fault type -- there is no
    warm-up period, no pre-existing anomaly carried over from a previous
    scenario, and no possibility of overlapping windows between scenarios,
    since each scenario_id is scored independently and never concatenated
    with another.
    """
    tp = fp = fn = 0
    n_true_events = 0
    n_predicted_events = 0
    delays: list[int] = []
    scenario_ids = {e.scenario_id for e in events} | {p.scenario_id for p in predictions}
    for scenario_id in scenario_ids:
        true_events = [e for e in events if e.scenario_id == scenario_id and e.fault_type == reason_code]
        n_true_events += len(true_events)
        predicted_indices = [p.sample_index for p in predictions if p.scenario_id == scenario_id and reason_code in p.predicted_reason_codes]
        predicted_intervals = _group_into_intervals(predicted_indices, temporal_tolerance_samples)
        n_predicted_events += len(predicted_intervals)

        remaining_intervals = list(predicted_intervals)
        # Deterministic greedy matching: true events processed in start order, each
        # matched to its nearest still-unmatched predicted interval within tolerance.
        for true_event in sorted(true_events, key=lambda e: e.injected_at_index):
            t_start, t_end = true_event.injected_at_index, true_event.injected_at_index + true_event.duration_samples - 1
            best = None
            best_dist = None
            for interval in remaining_intervals:
                p_start, p_end = interval
                overlap = p_start <= t_end and p_end >= t_start
                dist = 0 if overlap else min(abs(p_start - t_end), abs(t_start - p_end))
                if dist <= temporal_tolerance_samples and (best is None or dist < best_dist):
                    best, best_dist = interval, dist
            if best is not None:
                tp += 1
                delays.append(best[0] - t_start)
                remaining_intervals.remove(best)
            else:
                fn += 1
        fp += len(remaining_intervals)  # predicted intervals with no matching true event

    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall and (precision + recall) > 0 else None
    return EventDetectionMetric(
        reason_code=reason_code, dataset_split="", temporal_tolerance_samples=temporal_tolerance_samples,
        n_true_events=n_true_events, n_predicted_events=n_predicted_events,
        tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1,
        mean_detection_delay=(sum(delays) / len(delays)) if delays else None,
    )


def score_events(
    events: list[FaultEvent], predictions: list[SamplePrediction], dataset_split: str, temporal_tolerance_samples: int = 1
) -> list[EventDetectionMetric]:
    """Event-level metrics for every reason code, restricted to one dataset
    split (matching only ever happens WITHIN a scenario, and every
    scenario belongs to exactly one split, so this restriction cannot
    accidentally match a calibration event against a validation
    prediction)."""
    split_events = [e for e in events if e.dataset_split == dataset_split]
    split_predictions = [p for p in predictions if p.dataset_split == dataset_split]
    results = []
    for code in REASON_CODES:
        m = match_events(split_events, split_predictions, code, temporal_tolerance_samples)
        results.append(EventDetectionMetric(
            reason_code=m.reason_code, dataset_split=dataset_split, temporal_tolerance_samples=m.temporal_tolerance_samples,
            n_true_events=m.n_true_events, n_predicted_events=m.n_predicted_events,
            tp=m.tp, fp=m.fp, fn=m.fn, precision=m.precision, recall=m.recall, f1=m.f1,
            mean_detection_delay=m.mean_detection_delay,
        ))
    return results


@dataclass(frozen=True)
class ConfusionMatrixCell:
    dataset_split: str
    true_label: str  # a REASON_CODES value or "none"
    predicted_label: str  # a REASON_CODES value or "none"
    count: int


def build_confusion_matrix(predictions: list[SamplePrediction], dataset_split: str) -> list[ConfusionMatrixCell]:
    """Row-level confusion matrix: for every sample, its true label (a
    reason code, or "none" if genuinely clean/a genuine_event) against
    EVERY reason code it was actually predicted as (a sample can carry more
    than one predicted reason_code; "none" is used if it carried zero).
    Restricted to one dataset split, same isolation rationale as
    :func:`score_events`."""
    labels = REASON_CODES + ["none"]
    counts: dict[tuple[str, str], int] = {}
    for p in predictions:
        if p.dataset_split != dataset_split:
            continue
        true_label = p.true_fault_type if p.true_fault_type in REASON_CODES else "none"
        predicted_labels = [c for c in p.predicted_reason_codes if c in REASON_CODES] or ["none"]
        for predicted_label in predicted_labels:
            key = (true_label, predicted_label)
            counts[key] = counts.get(key, 0) + 1
    return [
        ConfusionMatrixCell(dataset_split, true_label, predicted_label, counts.get((true_label, predicted_label), 0))
        for true_label in labels
        for predicted_label in labels
        if counts.get((true_label, predicted_label), 0) > 0
    ]


def false_rejection_rate_for_genuine_events(predictions: list[SamplePrediction], dataset_split: str | None = None) -> float | None:
    """Of samples labeled 'genuine_event' (a real environmental change, not
    a fault), the fraction that ended up unusable -- these must NOT be
    discarded."""
    if dataset_split is not None:
        predictions = [p for p in predictions if p.dataset_split == dataset_split]
    genuine = [p for p in predictions if p.true_fault_type == "genuine_event"]
    if not genuine:
        return None
    rejected = sum(1 for p in genuine if not p.usable)
    return rejected / len(genuine)


def confirmation_recovery_rate(predictions: list[SamplePrediction], dataset_split: str | None = None) -> float | None:
    """Of samples that reached SUSPECT (a candidate anomaly), the fraction
    ultimately confirmed usable -- i.e. correctly recovered rather than
    discarded."""
    if dataset_split is not None:
        predictions = [p for p in predictions if p.dataset_split == dataset_split]
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
    dataset_split: str  # "calibration" | "validation"
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
       *calibration* scenario split only.
    2. Score each combination by a balanced objective: single_spike recall
       (fault_recall) and the fraction of genuine sustained events NOT
       falsely rejected (genuine_event_preservation_rate), averaged.
    3. Report the *validation* split's performance for the config actually
       kept in use -- computed once, not used to pick the parameters. The
       calibration and validation splits use disjoint scenario_ids AND a
       different deterministic scale/phase (see build_channel_scenarios),
       so no scenario or timestamp is shared between them -- no leakage.
    4. The originally configured (window_size, mad_multiplier) is always
       marked ``selected`` here: per the calibration policy, a change is
       only adopted after separate empirical verification against real
       live data (see config/iaq_hfis.yaml's hampel section for that
       history), not from synthetic-benchmark evidence alone. This grid is
       diagnostic, not a proposal to silently override the configured value.
    """
    rows: list[HampelCalibrationRow] = []
    calibration_scenarios = _hampel_affected_scenarios(cadence_seconds, "calibration")
    validation_scenarios = _hampel_affected_scenarios(cadence_seconds, "validation")

    for split, scenarios in (("calibration", calibration_scenarios), ("validation", validation_scenarios)):
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
