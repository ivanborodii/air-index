from iaq_hfis.baselines import crisp_max, weighted_mean


def test_crisp_max_is_the_max_score():
    result = crisp_max({"A": 10.0, "V": 80.0, "M": 40.0})
    assert result.index_value == 80.0
    assert result.index_class == "Critical"
    assert result.n_components == 3


def test_weighted_mean_is_the_average_score():
    result = weighted_mean({"A": 10.0, "V": 80.0, "M": 30.0})
    assert result.index_value == 40.0
    assert result.n_components == 3


def test_baselines_degrade_over_available_components_only():
    cm = crisp_max({"A": 10.0, "V": 20.0})  # M missing, e.g. PARTIAL completeness
    wm = weighted_mean({"A": 10.0, "V": 20.0})
    assert cm.n_components == 2
    assert wm.n_components == 2
    assert wm.index_value == 15.0


def test_baselines_empty_components_give_none():
    cm = crisp_max({})
    wm = weighted_mean({})
    assert cm.index_value is None and cm.index_class is None
    assert wm.index_value is None and wm.index_class is None


def test_weighted_mean_dilutes_a_critical_component_below_crisp_max():
    # Two favorable components (~13) alongside one critical component (~90) --
    # weighted-mean pulls the result well below crisp-max, the masking scenario.
    scores = {"A": 13.0, "V": 13.0, "M": 90.0}
    cm = crisp_max(scores)
    wm = weighted_mean(scores)
    assert cm.index_class == "Critical"
    assert wm.index_value < cm.index_value
