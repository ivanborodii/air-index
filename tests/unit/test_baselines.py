from iaq_hfis.baselines import crisp_class_max, fuzzy_component_max, weighted_mean


def test_crisp_max_is_the_max_score():
    result = fuzzy_component_max({"A": 10.0, "V": 80.0, "M": 40.0})
    assert result.index_value == 80.0
    assert result.index_class == "Critical"
    assert result.n_components == 3


def test_weighted_mean_is_the_average_score():
    result = weighted_mean({"A": 10.0, "V": 80.0, "M": 30.0})
    assert result.index_value == 40.0
    assert result.n_components == 3


def test_baselines_degrade_over_available_components_only():
    cm = fuzzy_component_max({"A": 10.0, "V": 20.0})  # M missing, e.g. PARTIAL completeness
    wm = weighted_mean({"A": 10.0, "V": 20.0})
    assert cm.n_components == 2
    assert wm.n_components == 2
    assert wm.index_value == 15.0


def test_baselines_empty_components_give_none():
    cm = fuzzy_component_max({})
    wm = weighted_mean({})
    assert cm.index_value is None and cm.index_class is None
    assert wm.index_value is None and wm.index_class is None


def test_weighted_mean_dilutes_a_critical_component_below_crisp_max():
    # Two favourable components (~13) alongside one critical component (~90) --
    # weighted-mean pulls the result well below crisp-max, the masking scenario.
    scores = {"A": 13.0, "V": 13.0, "M": 90.0}
    cm = fuzzy_component_max(scores)
    wm = weighted_mean(scores)
    assert cm.index_class == "Critical"
    assert wm.index_value < cm.index_value


def test_crisp_class_max_is_genuinely_discontinuous_at_a_boundary(base_settings, room_profiles):
    from iaq_hfis import profiles
    from datetime import datetime, timezone

    control_regions = base_settings.control_regions
    profile = profiles.select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    co2_boundary = control_regions.co2.breakpoints[0]  # Favourable/Acceptable boundary
    values_below = {"pm2_5": 1.0, "pm10": 1.0, "co2": co2_boundary - 0.01, "temperature": 19.5, "humidity": 40.0}
    values_at = {**values_below, "co2": co2_boundary}

    below = crisp_class_max(values_below, control_regions, profile.ranges)
    at = crisp_class_max(values_at, control_regions, profile.ranges)

    assert below.method == "CRISP_CLASS_MAX"
    assert below.index_class == "Favourable"
    assert at.index_class == "Acceptable"
    # A genuine step, not a smooth ramp: the two representative values differ
    # by a fixed jump regardless of how close the inputs are to the boundary.
    assert at.index_value - below.index_value == 25.0


def test_crisp_class_max_selects_most_adverse_component(base_settings, room_profiles):
    from iaq_hfis import profiles
    from datetime import datetime, timezone

    control_regions = base_settings.control_regions
    profile = profiles.select_room_season(room_profiles, datetime(2026, 1, 15, tzinfo=timezone.utc), base_settings.profile_selection)
    values = {"pm2_5": 1.0, "pm10": 1.0, "co2": 2000.0, "temperature": 19.5, "humidity": 40.0}  # co2 clearly Critical

    result = crisp_class_max(values, control_regions, profile.ranges)
    assert result.index_class == "Critical"
    assert result.n_components == 3


def test_crisp_class_max_omits_microclimate_when_no_profile(base_settings):
    control_regions = base_settings.control_regions
    values = {"pm2_5": 1.0, "pm10": 1.0, "co2": 700.0, "temperature": 19.5, "humidity": 40.0}

    result = crisp_class_max(values, control_regions, None)
    assert result.n_components == 2  # A, V only -- M never fabricated without a profile


def test_crisp_class_max_empty_inputs_give_none(base_settings):
    result = crisp_class_max({}, base_settings.control_regions, None)
    assert result.index_value is None and result.index_class is None and result.n_components == 0


def test_fuzzy_component_max_is_never_labelled_bare_crisp_max():
    # Spec requirement: FUZZY_COMPONENT_MAX (already-fuzzified component scores) must never
    # be mislabelled as "CRISP_MAX" / "CRISP-MAX" -- that name is reserved for the genuinely
    # hard baseline, CRISP_CLASS_MAX.
    result = fuzzy_component_max({"A": 10.0, "V": 20.0, "M": 30.0})
    assert result.method == "FUZZY_COMPONENT_MAX"
    assert result.method not in ("CRISP_MAX", "CRISP-MAX", "CRISP_CLASS_MAX")


def test_all_four_baseline_method_labels_are_canonical(base_settings):
    scores = {"A": 10.0, "V": 20.0, "M": 30.0}
    fc = fuzzy_component_max(scores)
    wm = weighted_mean(scores)
    cc = crisp_class_max({"pm2_5": 1.0, "pm10": 1.0, "co2": 700.0}, base_settings.control_regions, None)
    assert fc.method == "FUZZY_COMPONENT_MAX"
    assert wm.method == "WEIGHTED_MEAN"
    assert cc.method == "CRISP_CLASS_MAX"
    assert {fc.method, wm.method, cc.method} == {"FUZZY_COMPONENT_MAX", "WEIGHTED_MEAN", "CRISP_CLASS_MAX"}
