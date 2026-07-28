"""Multi-point sensitivity analysis: window-length and coverage-threshold
sweeps evaluated at a deterministic, stratified sample of computed_ts drawn
from the whole evaluated range (not just the latest timestamp).

Strata (each contributing up to
``EvaluationConfig.sensitivity_max_samples_per_stratum`` computed_ts,
deterministically sampled with the run's stability seed so results are
reproducible):

- one per available air-quality class (Favorable/Acceptable/Degraded/Critical)
  among OK results;
- PARTIAL completeness cases;
- boundary_adjacent: aggregated values close to a control-region boundary;
- ordinary: OK, not boundary-adjacent -- a general baseline sample;
- outdoor_context_fresh / outdoor_context_stale;
- data_quality_event: at least one channel's window had coverage_ok = FALSE.

A computed_ts may belong to more than one stratum; each stratum is sampled
independently so cross-stratum comparisons stay well-populated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from iaq_hfis.evaluation.multi_point_stability import boundary_targets


def _deterministic_seed(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2**32)


@dataclass(frozen=True)
class SensitivitySamplePoint:
    sample_id: str
    computed_ts: datetime
    stratum: str
    reference_completeness_status: str
    reference_index_class: str | None
    reference_index_value: float | None


def _sample_stratum(label: str, candidates: list[datetime], seed: int, max_samples: int) -> list[datetime]:
    if not candidates:
        return []
    ordered = sorted(candidates)
    if len(ordered) <= max_samples:
        return ordered
    rng = np.random.RandomState(_deterministic_seed(seed, label))
    idx = sorted(rng.choice(len(ordered), size=max_samples, replace=False).tolist())
    return [ordered[i] for i in idx]


def select_sensitivity_samples(
    con,
    pipeline_run_id: str,
    window_minutes: int,
    from_ts: datetime,
    to_ts: datetime,
    control_regions,
    room_profile,
    seed: int,
    max_samples_per_stratum: int,
) -> list[SensitivitySamplePoint]:
    reference_rows = con.execute(
        "SELECT computed_ts, completeness_status, index_class, index_value FROM iaq_index_results "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ?",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    reference = {ts: (status, cls, value) for ts, status, cls, value in reference_rows}

    stale_rows = con.execute(
        "SELECT computed_ts, is_stale FROM outdoor_context WHERE pipeline_run_id = ? AND computed_ts > ? AND computed_ts <= ?",
        [pipeline_run_id, from_ts, to_ts],
    ).fetchall()
    is_stale = {ts: bool(s) for ts, s in stale_rows}

    bad_coverage_rows = con.execute(
        "SELECT DISTINCT computed_ts FROM window_aggregates "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? AND coverage_ok = FALSE",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    had_quality_event = {r[0] for r in bad_coverage_rows}

    agg_rows = con.execute(
        "SELECT computed_ts, channel, weighted_mean FROM window_aggregates "
        "WHERE pipeline_run_id = ? AND window_minutes = ? AND computed_ts > ? AND computed_ts <= ? AND weighted_mean IS NOT NULL",
        [pipeline_run_id, window_minutes, from_ts, to_ts],
    ).fetchall()
    by_ts: dict[datetime, dict[str, float]] = {}
    for ts, channel, value in agg_rows:
        by_ts.setdefault(ts, {})[channel] = value

    targets = boundary_targets(control_regions, room_profile)
    boundary_dist: dict[datetime, float] = {}
    for ts, values in by_ts.items():
        best = None
        for channel, boundaries in targets.items():
            v = values.get(channel)
            if v is None:
                continue
            for b in boundaries:
                d = abs(v - b)
                if best is None or d < best:
                    best = d
        if best is not None:
            boundary_dist[ts] = best
    boundary_threshold = np.percentile(list(boundary_dist.values()), 10) if boundary_dist else None
    boundary_adjacent_ts = {ts for ts, d in boundary_dist.items() if boundary_threshold is not None and d <= boundary_threshold}

    strata: dict[str, list[datetime]] = {}
    for cls in ("Favorable", "Acceptable", "Degraded", "Critical"):
        strata[f"class_{cls}"] = [ts for ts, (status, c, _) in reference.items() if status == "OK" and c == cls]
    strata["completeness_PARTIAL"] = [ts for ts, (status, _, _) in reference.items() if status == "PARTIAL"]
    strata["boundary_adjacent"] = [ts for ts in boundary_adjacent_ts if reference.get(ts, (None,))[0] == "OK"]
    strata["ordinary"] = [ts for ts, (status, _, _) in reference.items() if status == "OK" and ts not in boundary_adjacent_ts]
    strata["outdoor_context_fresh"] = [ts for ts in reference if is_stale.get(ts) is False]
    strata["outdoor_context_stale"] = [ts for ts in reference if is_stale.get(ts) is True]
    strata["data_quality_event"] = [ts for ts in reference if ts in had_quality_event]

    samples: list[SensitivitySamplePoint] = []
    seen: set[tuple[str, datetime]] = set()
    for stratum, candidates in strata.items():
        for ts in _sample_stratum(stratum, candidates, seed, max_samples_per_stratum):
            key = (stratum, ts)
            if key in seen:
                continue
            seen.add(key)
            status, cls, value = reference[ts]
            samples.append(
                SensitivitySamplePoint(
                    sample_id=f"{stratum}_{ts.isoformat()}",
                    computed_ts=ts,
                    stratum=stratum,
                    reference_completeness_status=status,
                    reference_index_class=cls,
                    reference_index_value=value,
                )
            )
    return samples


def summarize_sensitivity(points: list[tuple[SensitivitySamplePoint, list]]) -> list[dict]:
    """One summary row per (varied_parameter, value): sample count, status
    and class transition counts, index-difference statistics from each
    sample point's own reference (15-minute window / configured coverage
    threshold) value, and class agreement rate -- aggregated across every
    sampled point, not a single instant."""
    by_key: dict[tuple[str, float], list[tuple]] = {}
    for sp, results in points:
        for r in results:
            by_key.setdefault((r.varied_parameter, r.value), []).append((sp, r))

    summary = []
    for (varied_parameter, value), pairs in sorted(by_key.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        n = len(pairs)
        status_transitions = sum(1 for sp, r in pairs if r.completeness_status != sp.reference_completeness_status)
        class_transitions = sum(1 for sp, r in pairs if r.index_class != sp.reference_index_class)
        class_agreement = (n - class_transitions) / n if n > 0 else None
        diffs = [abs(r.index_value - sp.reference_index_value) for sp, r in pairs if r.index_value is not None and sp.reference_index_value is not None]
        arr = np.array(diffs) if diffs else None
        summary.append(
            {
                "varied_parameter": varied_parameter,
                "value": value,
                "n_samples": n,
                "n_status_transitions": status_transitions,
                "n_class_transitions": class_transitions,
                "class_agreement_with_reference": class_agreement,
                "mean_abs_index_diff": float(arr.mean()) if arr is not None else None,
                "median_abs_index_diff": float(np.median(arr)) if arr is not None else None,
                "p95_abs_index_diff": float(np.percentile(arr, 95)) if arr is not None else None,
                "max_abs_index_diff": float(arr.max()) if arr is not None else None,
            }
        )
    return summary
