from iaq_hfis.constants import CLASS_ORDER, CLASS_SEVERITY
from iaq_hfis.rules import build_rule_base, generate_component_rules


def test_rule_counts_are_exact():
    rb = build_rule_base()
    assert len(rb.aerosol_rules) == 16
    assert len(rb.microclimate_rules) == 16
    assert len(rb.index_rules) == 64
    assert rb.total_count == 96


def test_rule_generation_is_deterministic():
    a = build_rule_base()
    b = build_rule_base()
    assert a.aerosol_rules == b.aerosol_rules
    assert a.index_rules == b.index_rules


def test_worst_of_consequent_is_max_severity():
    rules = generate_component_rules(["pm2_5", "pm10"], level=1)
    for rule in rules:
        classes = dict(rule.antecedents)
        expected = max(classes.values(), key=lambda c: CLASS_SEVERITY[c])
        assert rule.consequent_class == expected


def test_all_favorable_antecedents_give_favorable_consequent():
    rules = generate_component_rules(["A", "V", "M"], level=2)
    all_favorable = [r for r in rules if all(cls == "Favourable" for _, cls in r.antecedents)]
    assert len(all_favorable) == 1
    assert all_favorable[0].consequent_class == "Favourable"


def test_any_critical_antecedent_gives_critical_consequent():
    rules = generate_component_rules(["A", "V", "M"], level=2)
    for rule in rules:
        classes = dict(rule.antecedents)
        if "Critical" in classes.values():
            assert rule.consequent_class == "Critical"


def test_worsening_one_input_never_improves_consequent():
    rules = {r.antecedents: r for r in generate_component_rules(["A", "V", "M"], level=2)}
    for antecedents, rule in rules.items():
        for i, (name, cls) in enumerate(antecedents):
            idx = CLASS_ORDER.index(cls)
            if idx + 1 >= len(CLASS_ORDER):
                continue
            worse_cls = CLASS_ORDER[idx + 1]
            worse_antecedents = tuple(sorted((n, worse_cls if n == name else c) for n, c in antecedents))
            worse_rule = rules[worse_antecedents]
            assert CLASS_SEVERITY[worse_rule.consequent_class] >= CLASS_SEVERITY[rule.consequent_class]
