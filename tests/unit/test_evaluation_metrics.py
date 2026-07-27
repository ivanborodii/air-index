import pytest

from iaq_hfis.evaluation._metrics import cohens_kappa, macro_f1, percent_agreement


def test_percent_agreement_perfect():
    assert percent_agreement(["A", "B", "A"], ["A", "B", "A"]) == 1.0


def test_percent_agreement_partial():
    assert percent_agreement(["A", "B", "A", "B"], ["A", "B", "B", "B"]) == 0.75


def test_percent_agreement_requires_nonempty():
    with pytest.raises(ValueError):
        percent_agreement([], [])


def test_cohens_kappa_perfect_agreement():
    labels = ["A", "B", "C"]
    assert cohens_kappa(["A", "B", "C", "A"], ["A", "B", "C", "A"], labels) == pytest.approx(1.0)


def test_cohens_kappa_chance_level_is_near_zero():
    # Two independent-looking uniform-ish label sequences over a large n should
    # be close to 0 (not testing randomness, just that pure disagreement --
    # complementary labels -- gives a low/negative kappa, not near 1).
    a = ["A", "B"] * 10
    b = ["B", "A"] * 10  # always disagrees
    labels = ["A", "B"]
    kappa = cohens_kappa(a, b, labels)
    assert kappa < 0  # systematic disagreement -> worse than chance


def test_macro_f1_perfect():
    labels = ["A", "B", "C"]
    assert macro_f1(["A", "B", "C"], ["A", "B", "C"], labels) == pytest.approx(1.0)


def test_macro_f1_all_wrong():
    labels = ["A", "B"]
    score = macro_f1(["A", "A", "A"], ["B", "B", "B"], labels)
    assert score == pytest.approx(0.0)


def test_macro_f1_label_with_no_instances_scores_perfect_vacuously():
    labels = ["A", "B", "C"]
    # C never appears in true or predicted -- should not drag the average down
    score_without_c = macro_f1(["A", "B"], ["A", "B"], ["A", "B"])
    score_with_c = macro_f1(["A", "B"], ["A", "B"], labels)
    assert score_without_c == pytest.approx(1.0)
    assert score_with_c == pytest.approx(1.0)
