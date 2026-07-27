from iaq_hfis.evaluation import agreement
from iaq_hfis.evaluation.agreement import AgreementResult, pairwise_agreement


def test_no_macro_f1_or_accuracy_computed_by_agreement_module():
    """Agreement is computed on unlabeled real data -- macro-F1/'accuracy'
    presuppose a true/predicted distinction that doesn't exist between two
    peer methods, and the manuscript never claims them here. Checks the
    actual computed surface (function names, dataclass fields), not prose
    -- the module docstring legitimately discusses why these are excluded.
    """
    public_names = {name for name in dir(agreement) if not name.startswith("_")}
    assert "macro_f1" not in public_names
    assert not any("accuracy" in name.lower() for name in public_names)

    field_names = {f.name for f in agreement.AgreementResult.__dataclass_fields__.values()}
    assert "accuracy" not in field_names
    assert "macro_f1" not in field_names


def test_pairwise_agreement_is_labeled_agreement_not_accuracy():
    results = pairwise_agreement({"A": ["Favorable", "Critical"], "B": ["Favorable", "Critical"]})
    assert len(results) == 1
    assert isinstance(results[0], AgreementResult)
    assert results[0].percent_agreement == 1.0


def test_pairwise_agreement_excludes_none_positions():
    results = pairwise_agreement({"A": ["Favorable", None, "Critical"], "B": ["Favorable", "Degraded", "Critical"]})
    r = results[0]
    assert r.n == 2
    assert r.n_excluded == 1
    assert r.percent_agreement == 1.0


def test_pairwise_agreement_covers_every_method_pair():
    results = pairwise_agreement({"A": ["Favorable"], "B": ["Favorable"], "C": ["Critical"]})
    pairs = {(r.method_a, r.method_b) for r in results}
    assert pairs == {("A", "B"), ("A", "C"), ("B", "C")}


def test_pairwise_agreement_all_none_reports_zero_n_not_error():
    results = pairwise_agreement({"A": [None], "B": [None]})
    assert results[0].n == 0
    assert results[0].percent_agreement is None
