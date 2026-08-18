from __future__ import annotations

import pytest

from iaq_hfis.research_helpers import (
    f1_of,
    mcnemar_exact,
    monotonic_shape_type,
    s_new_objective,
    scenario_family,
)


def test_f1_of_harmonic_mean():
    assert f1_of(1.0, 1.0) == pytest.approx(1.0)
    assert f1_of(0.5, 0.5) == pytest.approx(0.5)
    assert f1_of(1.0, 0.0) == pytest.approx(0.0)


def test_f1_of_none_when_inputs_missing_or_zero_sum():
    assert f1_of(None, 0.5) is None
    assert f1_of(0.5, None) is None
    assert f1_of(0.0, 0.0) is None


def test_s_new_objective_is_mean_of_f1_and_preservation():
    assert s_new_objective(0.8, 0.6) == pytest.approx(0.7)
    assert s_new_objective(None, 0.6) is None
    assert s_new_objective(0.8, None) is None


def test_scenario_family_strips_variant_suffix():
    assert scenario_family("co2_single_spike_calibration") == "co2_single_spike"
    assert scenario_family("co2_single_spike_validation") == "co2_single_spike"
    assert scenario_family("co2_genuine_rapid_event_calibration") == "co2_genuine_rapid_event"


def test_scenario_family_no_suffix_returns_unchanged():
    assert scenario_family("co2_single_spike") == "co2_single_spike"


def test_mcnemar_exact_no_discordant_pairs_is_one():
    assert mcnemar_exact(0, 0) == 1.0


def test_mcnemar_exact_symmetric_in_b_and_c():
    assert mcnemar_exact(3, 7) == pytest.approx(mcnemar_exact(7, 3))


def test_mcnemar_exact_large_imbalance_is_significant():
    # 0 vs 20 discordant pairs: overwhelming evidence of a real difference.
    p = mcnemar_exact(0, 20)
    assert p < 0.001


def test_mcnemar_exact_balanced_discordant_pairs_not_significant():
    # Perfectly balanced discordant pairs: no evidence of a directional difference.
    p = mcnemar_exact(10, 10)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_monotonic_shape_type_trapezoidal_when_plateau_exists():
    # b < c: rising edge finishes before falling edge starts -> flat top.
    assert monotonic_shape_type(0.0, 1.0, 2.0, 3.0) == "trapezoidal"


def test_monotonic_shape_type_triangular_when_edges_meet_exactly():
    # b == c: no flat top, a single peak point.
    assert monotonic_shape_type(0.0, 1.5, 1.5, 3.0) == "triangular"


def test_monotonic_shape_type_invalid_when_edges_cross():
    # b > c: rising edge finishes after falling edge starts -- should never
    # happen for a validated config, but must be reported, not hidden.
    assert monotonic_shape_type(0.0, 2.0, 1.0, 3.0) == "INVALID_CROSSED_EDGES"
