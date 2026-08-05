from iaq_hfis.evaluation.multi_point_stability import _aggregate_stability_rows, wilson_ci

# Row shape (matches _fetch_stability_rows's SELECT order exactly):
# (method, trial_class, changed_from_baseline, abs_index_change, sample_id, selection_reason, boundary_channel, baseline_class)


def _row(method, trial_class, changed, abs_change, sample_id, selection_reason="boundary_adjacent", boundary_channel="pm2_5", baseline_class="Favourable"):
    return (method, trial_class, changed, abs_change, sample_id, selection_reason, boundary_channel, baseline_class)


def test_wilson_ci_zero_n_is_none():
    assert wilson_ci(0, 0) is None


def test_wilson_ci_bounds_are_valid_probability():
    ci = wilson_ci(5, 20)
    assert ci is not None
    assert 0.0 <= ci[0] <= ci[1] <= 1.0


def test_aggregate_overall_counts_class_changes_and_index_change_stats():
    rows = [
        _row("PROPOSED_HFIS", "Favourable", False, 0.0, "s1"),
        _row("PROPOSED_HFIS", "Acceptable", True, 5.0, "s1"),
        _row("PROPOSED_HFIS", "Favourable", False, 1.0, "s2"),
    ]
    out = _aggregate_stability_rows(rows, ["method"], key_fn=lambda r: (r[0],))
    assert len(out) == 1
    row = out[0]
    assert row["method"] == "PROPOSED_HFIS"
    assert row["n_samples"] == 2
    assert row["n_trials_total"] == 3
    assert row["n_class_changes"] == 1
    assert row["class_change_rate"] == 1 / 3
    assert row["mean_abs_index_change"] == (0.0 + 5.0 + 1.0) / 3
    assert row["max_abs_index_change"] == 5.0


def test_aggregate_moved_better_and_worse_use_class_severity():
    # baseline Acceptable (severity 1): Favourable (0) is better, Degraded (2) and Critical (3) are worse.
    rows = [
        _row("PROPOSED_HFIS", "Favourable", True, 10.0, "s1", baseline_class="Acceptable"),   # better
        _row("PROPOSED_HFIS", "Degraded", True, 10.0, "s1", baseline_class="Acceptable"),    # worse
        _row("PROPOSED_HFIS", "Acceptable", False, 0.0, "s1", baseline_class="Acceptable"),  # unchanged
    ]
    out = _aggregate_stability_rows(rows, ["method"], key_fn=lambda r: (r[0],))[0]
    assert out["n_comparable_for_direction"] == 3
    assert out["n_moved_better"] == 1
    assert out["n_moved_worse"] == 1
    assert out["prob_moved_better"] == 1 / 3
    assert out["prob_moved_worse"] == 1 / 3
    # every class change is either better or worse -- the two must sum to the class-change rate's numerator
    assert out["n_moved_better"] + out["n_moved_worse"] == out["n_class_changes"]


def test_aggregate_excludes_rows_with_undefined_class_from_direction_stats():
    # trial_class=None (e.g. a FAILED trial) can't be compared for direction, but still counts toward n_trials_total.
    rows = [
        _row("PROPOSED_HFIS", None, True, None, "s1"),
        _row("PROPOSED_HFIS", "Favourable", False, 0.0, "s1"),
    ]
    out = _aggregate_stability_rows(rows, ["method"], key_fn=lambda r: (r[0],))[0]
    assert out["n_trials_total"] == 2
    assert out["n_comparable_for_direction"] == 1
    assert out["n_moved_better"] == 0
    assert out["n_moved_worse"] == 0


def test_aggregate_by_variable_separates_boundary_channels():
    rows = [
        _row("FUZZY_COMPONENT_MAX", "Acceptable", True, 5.0, "s1", boundary_channel="pm2_5"),
        _row("FUZZY_COMPONENT_MAX", "Favourable", False, 0.0, "s2", boundary_channel="co2"),
    ]
    out = _aggregate_stability_rows(rows, ["method", "selection_reason", "boundary_channel"], key_fn=lambda r: (r[0], r[5], r[6]))
    channels = {row["boundary_channel"] for row in out}
    assert channels == {"pm2_5", "co2"}
    pm25_row = next(row for row in out if row["boundary_channel"] == "pm2_5")
    assert pm25_row["n_class_changes"] == 1


def test_aggregate_by_original_class_groups_by_baseline_class():
    rows = [
        _row("WEIGHTED_MEAN", "Acceptable", True, 5.0, "s1", baseline_class="Favourable"),
        _row("WEIGHTED_MEAN", "Critical", True, 20.0, "s2", baseline_class="Degraded"),
    ]
    out = _aggregate_stability_rows(rows, ["method", "original_class"], key_fn=lambda r: (r[0], r[7]))
    classes = {row["original_class"] for row in out}
    assert classes == {"Favourable", "Degraded"}


def test_aggregate_by_point_is_one_row_per_sample_method():
    rows = [
        _row("PROPOSED_HFIS", "Favourable", False, 0.0, "s1"),
        _row("PROPOSED_HFIS", "Favourable", False, 0.0, "s2"),
        _row("FUZZY_COMPONENT_MAX", "Favourable", False, 0.0, "s1"),
    ]
    out = _aggregate_stability_rows(
        rows, ["sample_id", "method", "selection_reason", "boundary_channel", "original_class"], key_fn=lambda r: (r[4], r[0], r[5], r[6], r[7])
    )
    keys = {(row["sample_id"], row["method"]) for row in out}
    assert keys == {("s1", "PROPOSED_HFIS"), ("s2", "PROPOSED_HFIS"), ("s1", "FUZZY_COMPONENT_MAX")}


def test_aggregate_is_deterministic_and_sorted():
    rows = [
        _row("WEIGHTED_MEAN", "Favourable", False, 0.0, "s1"),
        _row("FUZZY_COMPONENT_MAX", "Favourable", False, 0.0, "s1"),
        _row("PROPOSED_HFIS", "Favourable", False, 0.0, "s1"),
    ]
    out1 = _aggregate_stability_rows(rows, ["method"], key_fn=lambda r: (r[0],))
    out2 = _aggregate_stability_rows(rows, ["method"], key_fn=lambda r: (r[0],))
    assert out1 == out2
    assert [row["method"] for row in out1] == sorted(row["method"] for row in out1)
