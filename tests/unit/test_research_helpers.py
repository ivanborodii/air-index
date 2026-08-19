from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from iaq_hfis.constants import CLASS_ORDER, CLASS_SEVERITY
from iaq_hfis.research_helpers import (
    causal_locf,
    classify_class_transition,
    f1_of,
    has_dominance_tie,
    is_aba_reversal,
    is_chronologically_consecutive,
    mcnemar_exact,
    monotonic_shape_type,
    most_adverse_direct_input,
    s_new_objective,
    scenario_family,
    verify_grid_point_count,
)

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


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


# --- causal_locf (task section 5.1) ----------------------------------------


def test_causal_locf_previous_row_within_lookback():
    target = _at(10)
    candidates = [(_at(5), 42.0, True)]
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.value == 42.0
    assert r.fallback_required is False
    assert r.age_minutes == pytest.approx(5.0)
    assert r.source_valid is True


def test_causal_locf_previous_row_older_than_lookback_falls_back():
    target = _at(20)
    candidates = [(_at(5), 42.0, True)]  # 15 minutes old, lookback is 10
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.value is None
    assert r.fallback_required is True
    assert r.fallback_reason == "no_valid_source_within_lookback"


def test_causal_locf_multi_hour_gap_does_not_cross_the_gap():
    # A prior valid row exists, but hours before the target -- must not be
    # used just because it is the nearest row in array position.
    target = _at(300)
    candidates = [(_at(10), 42.0, True)]  # ~4h50m old
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.fallback_required is True
    assert r.value is None


def test_causal_locf_no_previous_valid_value():
    target = _at(10)
    r = causal_locf(target, candidates=[], lookback_seconds=600)
    assert r.fallback_required is True
    assert r.value is None
    assert r.source_ts is None


def test_causal_locf_never_uses_a_future_value():
    target = _at(10)
    candidates = [(_at(15), 99.0, True)]  # 5 minutes in the FUTURE relative to target
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.fallback_required is True
    assert r.value is None


def test_causal_locf_exact_lookback_boundary_is_accepted():
    target = _at(10)
    candidates = [(_at(0), 7.0, True)]  # exactly 600s = lookback_seconds old
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.value == 7.0
    assert r.age_seconds == pytest.approx(600.0)
    assert r.fallback_required is False


def test_causal_locf_just_past_boundary_is_rejected():
    target = _at(10)
    candidates = [(_at(0) - timedelta(seconds=1), 7.0, True)]  # 601s old
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.fallback_required is True


def test_causal_locf_invalid_previous_value_is_skipped_for_an_older_valid_one():
    target = _at(10)
    candidates = [(_at(9), None, False), (_at(5), 42.0, True)]
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.value == 42.0
    assert r.source_ts == _at(5)


def test_causal_locf_all_candidates_invalid_falls_back():
    target = _at(10)
    candidates = [(_at(9), 1.0, False), (_at(5), None, True)]
    r = causal_locf(target, candidates, lookback_seconds=600)
    assert r.fallback_required is True


# --- has_dominance_tie (task section 5.2) -----------------------------------


def test_has_dominance_tie_one_dominant_component_is_not_a_tie():
    assert has_dominance_tie(["A"]) is False


def test_has_dominance_tie_two_tied_components():
    assert has_dominance_tie(["A", "V"]) is True


def test_has_dominance_tie_three_tied_components():
    assert has_dominance_tie(["A", "V", "M"]) is True


def test_has_dominance_tie_empty_list_is_not_a_tie():
    assert has_dominance_tie([]) is False


def test_has_dominance_tie_duplicated_values_are_not_a_tie():
    # Defensive: even if a caller ever passed duplicates of the SAME
    # component, that is still only one distinct component.
    assert has_dominance_tie(["A", "A"]) is False


# --- most_adverse_direct_input (task section 5.3) ---------------------------


def _degrees(**active) -> dict[str, float]:
    d = {cls: 0.0 for cls in CLASS_ORDER}
    d.update(active)
    return d


def test_most_adverse_direct_input_low_temperature_beats_favourable_humidity():
    channel_degrees = {
        "temperature": _degrees(Critical=0.8, Degraded=0.2),  # low-side Critical
        "humidity": _degrees(Favourable=1.0),
    }
    ch, tied = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    assert ch == "temperature"
    assert tied is False


def test_most_adverse_direct_input_high_temperature_also_wins_on_severity():
    # Two-sided: a HIGH-side Critical must be picked correctly too, not just
    # low-side -- this is exactly what percentile rank could get backwards.
    channel_degrees = {
        "temperature": _degrees(Critical=0.6),  # high-side Critical
        "humidity": _degrees(Acceptable=1.0),
    }
    ch, _ = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    assert ch == "temperature"


def test_most_adverse_direct_input_favourable_channel_never_wins_over_active_one():
    channel_degrees = {
        "temperature": _degrees(Favourable=1.0),
        "humidity": _degrees(Degraded=0.3, Acceptable=0.7),
    }
    ch, _ = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    assert ch == "humidity"


def test_most_adverse_direct_input_pm_and_co2_threshold_case():
    channel_degrees = {
        "pm2_5": _degrees(Degraded=1.0),
        "pm10": _degrees(Acceptable=1.0),
    }
    ch, _ = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    assert ch == "pm2_5"


def test_most_adverse_direct_input_exact_class_boundary_equal_severity_breaks_on_degree():
    channel_degrees = {
        "pm2_5": _degrees(Degraded=0.5, Acceptable=0.5),
        "pm10": _degrees(Degraded=0.9, Critical=0.1),
    }
    ch, tied = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    # pm10 reaches Critical (higher severity) even at low degree -- severity rank wins first.
    assert ch == "pm10"
    assert tied is False


def test_most_adverse_direct_input_explicit_tie_is_preserved():
    channel_degrees = {
        "pm2_5": _degrees(Critical=0.4),
        "pm10": _degrees(Critical=0.4),
    }
    ch, tied = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    assert tied is True
    assert ch == "pm10"  # deterministic tie-break: alphabetically first


def test_most_adverse_direct_input_no_active_class_returns_none():
    channel_degrees = {"temperature": {cls: 0.0 for cls in CLASS_ORDER}}
    ch, tied = most_adverse_direct_input(channel_degrees, CLASS_SEVERITY)
    assert ch is None
    assert tied is False


# --- chronological consecutiveness / transitions (task section 5.4) --------


def test_is_chronologically_consecutive_within_gap():
    assert is_chronologically_consecutive(_at(0), _at(9), max_gap_minutes=10) is True


def test_is_chronologically_consecutive_exact_boundary():
    assert is_chronologically_consecutive(_at(0), _at(10), max_gap_minutes=10) is True


def test_is_chronologically_consecutive_beyond_gap_is_false():
    assert is_chronologically_consecutive(_at(0), _at(10.001), max_gap_minutes=10) is False


def test_is_chronologically_consecutive_large_multi_hour_gap_is_false():
    assert is_chronologically_consecutive(_at(0), _at(300), max_gap_minutes=10) is False


def test_classify_class_transition_none_when_unchanged():
    assert classify_class_transition("Acceptable", "Acceptable", CLASS_ORDER) == "none"


def test_classify_class_transition_adjacent_when_one_severity_step():
    assert classify_class_transition("Acceptable", "Degraded", CLASS_ORDER) == "adjacent"
    assert classify_class_transition("Degraded", "Acceptable", CLASS_ORDER) == "adjacent"


def test_classify_class_transition_nonadjacent_when_multiple_severity_steps():
    assert classify_class_transition("Favourable", "Critical", CLASS_ORDER) == "nonadjacent"


def test_is_aba_reversal_true_case():
    assert is_aba_reversal("Favourable", "Degraded", "Favourable") is True


def test_is_aba_reversal_false_when_no_return():
    assert is_aba_reversal("Favourable", "Degraded", "Critical") is False


def test_is_aba_reversal_false_when_no_change_at_all():
    assert is_aba_reversal("Favourable", "Favourable", "Favourable") is False


# --- verify_grid_point_count (task section 5.5) -----------------------------


def test_verify_grid_point_count_matches_cube():
    assert verify_grid_point_count(101, 101**3) is True


def test_verify_grid_point_count_catches_the_original_41_vs_101_defect():
    # The exact bug this task found: manifest claimed 101, persisted grid had 41**3 rows.
    assert verify_grid_point_count(101, 41**3) is False


def test_verify_grid_point_count_exact_match_required():
    assert verify_grid_point_count(41, 68921) is True
