"""Multi-point stability analysis: perturbation trials at a deterministic,
stratified sample of computed_ts drawn from the whole evaluated range (not
just the latest timestamp), for all four methods (PROPOSED_HFIS,
FUZZY_COMPONENT_MAX, CRISP_CLASS_MAX, WEIGHTED_MEAN).

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
perturbation. All four methods are recomputed from the *same* perturbed
values per trial, so their outcomes are directly comparable trial-for-trial.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from iaq_hfis.baselines import BaselineResult, crisp_class_max, fuzzy_component_max, weighted_mean
from iaq_hfis.constants import CLASS_SEVERITY
from iaq_hfis.pipeline import RuntimeContext, infer_from_values
from iaq_hfis.schema import RAW_COLUMN_TO_SENSOR_SPEC, channel_uncertainty

DIRECT_INPUT_CHANNELS = ["pm2_5", "pm10", "co2", "temperature", "humidity"]
METHODS = ["PROPOSED_HFIS", "FUZZY_COMPONENT_MAX", "CRISP_CLASS_MAX", "WEIGHTED_MEAN"]


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
    """``room_profile`` may be ``None`` (exploratory mode, no DBN profile for
    this room/season) -- the temperature axis is simply omitted, never
    fabricated; every other channel's boundaries are unaffected."""
    rh = control_regions.relative_humidity
    targets = {
        "pm2_5": list(control_regions.pm2_5.breakpoints),
        "pm10": list(control_regions.pm10.breakpoints),
        "co2": list(control_regions.co2.breakpoints),
        "humidity": [rh.critical_low_max, rh.acceptable_low[1], rh.favourable[0], rh.favourable[1], rh.acceptable_high[0], rh.critical_high_min],
    }
    if room_profile is not None:
        temp = room_profile.ranges
        targets["temperature"] = [temp.critical_low_max, temp.acceptable_low[1], temp.favourable[0], temp.favourable[1], temp.acceptable_high[0], temp.critical_high_min]
    return targets


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
    cm: BaselineResult = fuzzy_component_max(scores)
    ccm: BaselineResult = crisp_class_max(values, ctx.settings.control_regions, profile.ranges if profile is not None else None)
    wm: BaselineResult = weighted_mean(scores)
    outcomes = {
        "PROPOSED_HFIS": MethodOutcome(index_result.index_class if index_result else None, index_result.index_value if index_result else None),
        "FUZZY_COMPONENT_MAX": MethodOutcome(cm.index_class, cm.index_value),
        "CRISP_CLASS_MAX": MethodOutcome(ccm.index_class, ccm.index_value),
        "WEIGHTED_MEAN": MethodOutcome(wm.index_class, wm.index_value),
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


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score confidence interval for a binomial proportion --
    reproducible (closed-form, no resampling) and reasonable for small n,
    unlike the normal approximation. Returns None when n == 0. Intervals
    from very small n (e.g. a single sample point's 30 trials) will be
    wide -- that width is the honest signal, not hidden."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half_width = (z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)) / denom
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def _fetch_stability_rows(con, evaluation_run_id: str) -> list[tuple]:
    """(method, trial_class, changed_from_baseline, abs_index_change,
    sample_id, selection_reason, boundary_channel, baseline_class) --
    joined directly from the persisted trial/sample tables so every
    aggregation dimension below reads the exact same rows."""
    return con.execute(
        """
        SELECT t.method, t.trial_class, t.changed_from_baseline, t.abs_index_change,
               s.sample_id, s.selection_reason, s.boundary_channel,
               CASE t.method
                   WHEN 'PROPOSED_HFIS' THEN s.baseline_class_hfis
                   WHEN 'FUZZY_COMPONENT_MAX' THEN s.baseline_class_crisp_max
                   WHEN 'CRISP_CLASS_MAX' THEN s.baseline_class_crisp_class_max
                   WHEN 'WEIGHTED_MEAN' THEN s.baseline_class_weighted_mean
               END AS baseline_class
        FROM evaluation_stability_trials t
        JOIN evaluation_stability_samples s
          ON s.evaluation_run_id = t.evaluation_run_id AND s.sample_id = t.sample_id
        WHERE t.evaluation_run_id = ?
        """,
        [evaluation_run_id],
    ).fetchall()


def _aggregate_stability_rows(rows: list[tuple], key_fields: list[str], key_fn) -> list[dict]:
    """The ONE deterministic aggregation function for every stability
    summary grouping (overall / by-variable / by-original-class /
    by-point) -- always computed directly from the persisted
    evaluation_stability_trials rows (via ``_fetch_stability_rows``), never
    independently recomputed. Both ``run_summary.json`` (:mod:`iaq_hfis.evaluate`)
    and every ``stability_*.csv`` export (:mod:`iaq_hfis.reporting.exports`)
    call this exact function, so they can never numerically disagree.

    "Better"/"worse" is determined by :data:`iaq_hfis.constants.CLASS_SEVERITY`
    (lower severity = better); this is a class-agreement/movement statistic,
    never called "accuracy" -- there is no ground truth here, only
    consistency of the method's own output under input perturbation.
    """
    by_key: dict[tuple, list[tuple]] = {}
    for row in rows:
        by_key.setdefault(key_fn(row), []).append(row)

    out = []
    for key in sorted(by_key.keys(), key=lambda k: tuple(str(x) for x in k)):
        group = by_key[key]
        n_trials = len(group)
        n_changes = sum(1 for r in group if r[2])
        abs_changes = [r[3] for r in group if r[3] is not None]
        arr = np.array(abs_changes) if abs_changes else None

        n_better, n_worse, n_comparable = 0, 0, 0
        for r in group:
            trial_class, baseline_class = r[1], r[7]
            ts, bs = CLASS_SEVERITY.get(trial_class), CLASS_SEVERITY.get(baseline_class)
            if ts is None or bs is None:
                continue
            n_comparable += 1
            if ts < bs:
                n_better += 1
            elif ts > bs:
                n_worse += 1

        entry = dict(zip(key_fields, key))
        entry.update(
            {
                "n_samples": len({r[4] for r in group}),
                "n_trials_total": n_trials,
                "n_class_changes": n_changes,
                "class_change_rate": (n_changes / n_trials) if n_trials else None,
                "class_change_rate_ci95": wilson_ci(n_changes, n_trials),
                "mean_abs_index_change": float(arr.mean()) if arr is not None else None,
                "median_abs_index_change": float(np.median(arr)) if arr is not None else None,
                "p95_abs_index_change": float(np.percentile(arr, 95)) if arr is not None else None,
                "max_abs_index_change": float(arr.max()) if arr is not None else None,
                "n_comparable_for_direction": n_comparable,
                "n_moved_better": n_better,
                "n_moved_worse": n_worse,
                "prob_moved_better": (n_better / n_comparable) if n_comparable else None,
                "prob_moved_worse": (n_worse / n_comparable) if n_comparable else None,
                "prob_moved_better_ci95": wilson_ci(n_better, n_comparable),
                "prob_moved_worse_ci95": wilson_ci(n_worse, n_comparable),
            }
        )
        out.append(entry)
    return out


def compute_stability_summary_overall(con, evaluation_run_id: str) -> list[dict]:
    rows = _fetch_stability_rows(con, evaluation_run_id)
    return _aggregate_stability_rows(rows, ["method"], key_fn=lambda r: (r[0],))


def compute_stability_summary_by_variable(con, evaluation_run_id: str) -> list[dict]:
    """Aggregated by (method, selection_reason, boundary_channel) -- the
    channel whose boundary a sample was selected as adjacent to
    (``boundary_channel`` is null for random_comparison samples, grouped
    under selection_reason alone)."""
    rows = _fetch_stability_rows(con, evaluation_run_id)
    return _aggregate_stability_rows(rows, ["method", "selection_reason", "boundary_channel"], key_fn=lambda r: (r[0], r[5], r[6]))


def compute_stability_summary_by_original_class(con, evaluation_run_id: str) -> list[dict]:
    """Aggregated by (method, original_class) -- the method's own baseline
    (unperturbed) class at each sample point, i.e. does stability differ
    depending on which class a point started in."""
    rows = [r for r in _fetch_stability_rows(con, evaluation_run_id) if r[7] is not None]
    return _aggregate_stability_rows(rows, ["method", "original_class"], key_fn=lambda r: (r[0], r[7]))


def compute_stability_summary_by_point(con, evaluation_run_id: str) -> list[dict]:
    """Per (sample_id, method) -- the finest-grained breakdown, one row per
    sampled point per method."""
    rows = _fetch_stability_rows(con, evaluation_run_id)
    return _aggregate_stability_rows(
        rows, ["sample_id", "method", "selection_reason", "boundary_channel", "original_class"], key_fn=lambda r: (r[4], r[0], r[5], r[6], r[7])
    )
