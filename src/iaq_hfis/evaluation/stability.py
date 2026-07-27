"""Stability near classification thresholds: class-change frequency under
small perturbations of the aggregated input values, within each channel's
already-configured (Phase 1) sensor uncertainty.

Uses a fixed random seed (``EvaluationConfig.stability_seed``) so results
are byte-for-byte reproducible across runs, per the manuscript's stated
verification protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from iaq_hfis.config import RoomTemperatureProfile
from iaq_hfis.pipeline import RuntimeContext, infer_from_values
from iaq_hfis.schema import channel_uncertainty  # re-exported: shared with quality.reasons's drift gating

__all__ = ["StabilityResult", "channel_uncertainty", "run_stability_analysis"]


@dataclass(frozen=True)
class StabilityResult:
    seed: int
    n_trials: int
    baseline_class: str | None
    n_class_changes: int
    class_change_rate: float
    trial_classes: list[str | None] = field(default_factory=list)


def run_stability_analysis(
    ctx: RuntimeContext,
    weighted_means: dict[str, float],
    available_components: set[str],
    profile: RoomTemperatureProfile,
    seed: int,
    n_trials: int,
) -> StabilityResult:
    """Perturbs every available channel's value by U(-uncertainty,
    +uncertainty) independently per trial, recomputes the final index
    class, and reports how often it differs from the unperturbed baseline.
    """
    rng = np.random.RandomState(seed)
    _, baseline_result = infer_from_values(ctx, weighted_means, available_components, profile)
    baseline_class = baseline_result.index_class if baseline_result else None

    trial_classes: list[str | None] = []
    for _ in range(n_trials):
        perturbed = dict(weighted_means)
        for channel, value in weighted_means.items():
            if value is None:
                continue
            uncertainty = channel_uncertainty(channel, ctx.settings.schema_mapping, ctx.sensor_specs)
            if uncertainty > 0:
                perturbed[channel] = value + rng.uniform(-uncertainty, uncertainty)
        _, trial_result = infer_from_values(ctx, perturbed, available_components, profile)
        trial_classes.append(trial_result.index_class if trial_result else None)

    n_changes = sum(1 for c in trial_classes if c != baseline_class)
    return StabilityResult(
        seed=seed,
        n_trials=n_trials,
        baseline_class=baseline_class,
        n_class_changes=n_changes,
        class_change_rate=(n_changes / n_trials) if n_trials > 0 else 0.0,
        trial_classes=trial_classes,
    )
