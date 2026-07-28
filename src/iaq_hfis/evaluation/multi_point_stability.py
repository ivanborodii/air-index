"""Multi-point stability analysis: perturbation trials at a deterministic,
stratified sample of computed_ts drawn from the whole evaluated range (not
just the latest timestamp), for all three methods (PROPOSED-HFIS,
CRISP-MAX, WEIGHTED-MEAN).

Sample selection is two-part and fully deterministic for a fixed
(pipeline_run_id, window_minutes, from_ts, to_ts, seed):

- boundary_adjacent: the ``max_boundary_samples`` computed_ts whose
  aggregated channel values lie closest to any configured control-region
  boundary (PM2.5/PM10/CO2/temperature/RH), stratified across channels by
  construction (the nearest boundary of any channel wins per timestamp).
- random_comparison: a reproducible random sample (fixed seed) of
  ``max_random_samples`` computed_ts from everything else, for contrast.

Each selected point is perturbed ``n_trials`` times, independently per
input channel, by an amount drawn uniformly from
[-declared_uncertainty, +declared_uncertainty] (the same per-channel
uncertainty already used everywhere else), clipped to the channel's
sensor technical range, with PM2.5 <= PM10 ordering re-enforced after
perturbation. All three methods are recomputed from the *same* perturbed
component crisp scores per trial, so their outcomes are directly
comparable trial-for-trial.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from iaq_hfis.baselines import BaselineResult, crisp_max, weighted_mean
from iaq_hfis.pipeline import RuntimeContext, infer_from_values
from iaq_hfis.schema import RAW_COLUMN_TO_SENSOR_SPEC, channel_uncertainty

DIRECT_INPUT_CHANNELS = ["pm2_5", "pm10", "co2", "temperature", "humidity"]
METHODS = ["PROPOSED-HFIS", "CRISP-MAX", "WEIGHTED-MEAN"]


@dataclass(frozen=True)
class StabilitySample:
    sample_id: str
    computed_ts: datetime
    selection_reason: str  # "boundary_adjacent" | "random_comparison"
    boundary_channel: str | None
    weighted_means: dict[str, float]
    available_components: frozenset[str]


@dataclass(frozen=True)
class MethodOutcome:
    index_class: str | None
    index_value: float | None


@dataclass(frozen=True)
class SamplePointResult:
    sample: StabilitySample
    baseline: dict[str, MethodOutcome]
    trials: dict[str, list[MethodOutcome]]


def _deterministic_seed(seed: int, sample_id: str) -> int:
    """Derives a per-sample RNG seed deterministically from the run seed and
    sample_id -- NOT Python's built-in hash() (randomized per-process for
    strings unless PYTHONHASHSEED is fixed), so this is reproducible across
    machines and processes."""
    digest = hashlib.sha256(f"{seed}:{sample_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def boundary_targets(control_regions, room_profile) -> dict[str, list[float]]:
    rh = control_regions.relative_humidity
    temp = room_profile.ranges
    return {
        "pm2_5": list(control_regions.pm2_5.breakpoints),
        "pm10": list(control_regions.pm10.breakpoints),
        "co2": list(control_regions.co2.breakpoints),
        "temperature": [temp.critical_low_max, temp.acceptable_low[1], temp.favorable[0], temp.favorable[1], temp.acceptable_high[0], temp.critical_high_min],
        "humidity": [rh.critical_low_max, rh.acceptable_low[1], rh.favorable[0], rh.favorable[1], rh.acceptable_high[0], rh.critical_high_min],
    }


def select_stability_samples(
    con,
    pipeline_run_id: str,
    window_minutes: int,
    from_ts: datetime,
    to_ts: datetime,
    control_regions,
    room_profile,
    seed: int,
    max_boundary_samples: int = 20,
    max_random_samples: int = 10,
) -> list[StabilitySample]:
    rows = con.execute(
        "SELECT computed_ts, channel, weighted_mean FROM window_aggregates "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? AND weighted_mean IS NOT NULL",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    by_ts: dict[datetime, dict[str, float]] = {}
    for ts, channel, value in rows:
        by_ts.setdefault(ts, {})[channel] = value

    avail_rows = con.execute(
        "SELECT computed_ts, component FROM component_scores "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND available = TRUE AND computed_ts > ? AND computed_ts <= ?",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    avail_by_ts: dict[datetime, set[str]] = {}
    for ts, comp in avail_rows:
        avail_by_ts.setdefault(ts, set()).add(comp)

    targets = boundary_targets(control_regions, room_profile)

    scored: list[tuple[float, datetime, str]] = []
    for ts, values in by_ts.items():
        if not avail_by_ts.get(ts):
            continue
        best_dist, best_channel = None, None
        for channel, boundaries in targets.items():
            v = values.get(channel)
            if v is None:
                continue
            for b in boundaries:
                d = abs(v - b)
                if best_dist is None or d < best_dist:
                    best_dist, best_channel = d, channel
        if best_dist is not None:
            scored.append((best_dist, ts, best_channel))
    scored.sort(key=lambda t: (t[0], t[1].isoformat()))

    boundary_selected = scored[:max_boundary_samples]
    boundary_ts_set = {ts for _, ts, _ in boundary_selected}

    remaining_ts = sorted(ts for ts in by_ts if ts not in boundary_ts_set and avail_by_ts.get(ts))
    rng = np.random.RandomState(_deterministic_seed(seed, "random_comparison_selection") % (2**32))
    random_selected_ts: list[datetime] = []
    if remaining_ts:
        n = min(max_random_samples, len(remaining_ts))
        idx = sorted(rng.choice(len(remaining_ts), size=n, replace=False).tolist())
        random_selected_ts = [remaining_ts[i] for i in idx]

    samples: list[StabilitySample] = []
    for dist, ts, channel in boundary_selected:
        samples.append(
            StabilitySample(
                sample_id=f"boundary_{channel}_{ts.isoformat()}",
                computed_ts=ts,
                selection_reason="boundary_adjacent",
                boundary_channel=channel,
                weighted_means=by_ts[ts],
                available_components=frozenset(avail_by_ts[ts]),
            )
        )
    for ts in random_selected_ts:
        samples.append(
            StabilitySample(
                sample_id=f"random_{ts.isoformat()}",
                computed_ts=ts,
                selection_reason="random_comparison",
                boundary_channel=None,
                weighted_means=by_ts[ts],
                available_components=frozenset(avail_by_ts[ts]),
            )
        )
    return samples


def _clip_to_technical_range(channel: str, value: float, ctx: RuntimeContext) -> float:
    source_column = ctx.settings.schema_mapping.channel(channel).source_column
    key = RAW_COLUMN_TO_SENSOR_SPEC.get(source_column)
    if key is None or key not in ctx.sensor_specs.channels:
        return value
    spec = ctx.sensor_specs.channels[key]
    return min(max(value, spec.min), spec.max)


def _perturb_once(values: dict[str, float], ctx: RuntimeContext, rng: np.random.RandomState) -> dict[str, float]:
    perturbed = dict(values)
    for channel in DIRECT_INPUT_CHANNELS:
        v = values.get(channel)
        if v is None:
            continue
        u = channel_uncertainty(channel, ctx.settings.schema_mapping, ctx.sensor_specs)
        new_value = v + rng.uniform(-u, u) if u > 0 else v
        perturbed[channel] = _clip_to_technical_range(channel, new_value, ctx)
    # Preserve physically valid PM ordering (PM10 >= PM2.5) after independent perturbation.
    if "pm2_5" in perturbed and "pm10" in perturbed and perturbed["pm10"] < perturbed["pm2_5"]:
        perturbed["pm10"] = perturbed["pm2_5"]
    return perturbed


def _baseline_outcomes(ctx: RuntimeContext, values: dict[str, float], available_components: set[str], profile) -> tuple[dict[str, MethodOutcome], dict[str, float]]:
    component_results, index_result = infer_from_values(ctx, values, available_components, profile)
    scores = {c: r.crisp_score for c, r in component_results.items()}
    cm: BaselineResult = crisp_max(scores)
    wm: BaselineResult = weighted_mean(scores)
    outcomes = {
        "PROPOSED-HFIS": MethodOutcome(index_result.index_class if index_result else None, index_result.index_value if index_result else None),
        "CRISP-MAX": MethodOutcome(cm.index_class, cm.index_value),
        "WEIGHTED-MEAN": MethodOutcome(wm.index_class, wm.index_value),
    }
    return outcomes, scores


def run_multi_point_stability(ctx: RuntimeContext, profile, samples: list[StabilitySample], seed: int, n_trials: int) -> list[SamplePointResult]:
    results: list[SamplePointResult] = []
    for sample in samples:
        baseline, _ = _baseline_outcomes(ctx, sample.weighted_means, set(sample.available_components), profile)
        rng = np.random.RandomState(_deterministic_seed(seed, sample.sample_id) % (2**32))

        trials: dict[str, list[MethodOutcome]] = {m: [] for m in METHODS}
        for _ in range(n_trials):
            perturbed_values = _perturb_once(sample.weighted_means, ctx, rng)
            outcomes, _ = _baseline_outcomes(ctx, perturbed_values, set(sample.available_components), profile)
            for method in METHODS:
                trials[method].append(outcomes[method])

        results.append(SamplePointResult(sample=sample, baseline=baseline, trials=trials))
    return results


@dataclass(frozen=True)
class MethodStabilitySummary:
    method: str
    n_samples: int
    n_trials_total: int
    n_class_changes: int
    class_change_rate: float
    class_change_rate_ci95: tuple[float, float] | None
    mean_abs_index_change: float | None
    median_abs_index_change: float | None
    p95_abs_index_change: float | None
    max_abs_index_change: float | None


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score confidence interval for a binomial proportion --
    reproducible (closed-form, no resampling) and reasonable for small n,
    unlike the normal approximation. Returns None when n == 0."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half_width = (z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)) / denom
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def summarize_stability(results: list[SamplePointResult]) -> dict[str, MethodStabilitySummary]:
    summaries: dict[str, MethodStabilitySummary] = {}
    for method in METHODS:
        n_changes = 0
        n_trials_total = 0
        abs_changes: list[float] = []
        for r in results:
            baseline = r.baseline[method]
            for trial in r.trials[method]:
                n_trials_total += 1
                if trial.index_class != baseline.index_class:
                    n_changes += 1
                if trial.index_value is not None and baseline.index_value is not None:
                    abs_changes.append(abs(trial.index_value - baseline.index_value))
        rate = (n_changes / n_trials_total) if n_trials_total > 0 else 0.0
        arr = np.array(abs_changes) if abs_changes else None
        summaries[method] = MethodStabilitySummary(
            method=method,
            n_samples=len(results),
            n_trials_total=n_trials_total,
            n_class_changes=n_changes,
            class_change_rate=rate,
            class_change_rate_ci95=wilson_ci(n_changes, n_trials_total),
            mean_abs_index_change=float(arr.mean()) if arr is not None else None,
            median_abs_index_change=float(np.median(arr)) if arr is not None else None,
            p95_abs_index_change=float(np.percentile(arr, 95)) if arr is not None else None,
            max_abs_index_change=float(arr.max()) if arr is not None else None,
        )
    return summaries
