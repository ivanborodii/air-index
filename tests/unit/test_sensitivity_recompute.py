import pandas as pd

from iaq_hfis.validation import _recompute_sensitivity_summary_from_by_point


def test_both_failed_rows_are_not_counted_as_a_class_transition():
    # Regression test: pandas NaN != NaN is True (unlike Python's None != None).
    # Two rows where BOTH index_class and reference_index_class are null (both
    # FAILED completeness) must contribute zero class transitions, not two.
    df = pd.DataFrame(
        {
            "value": [15, 15],
            "completeness_status": ["FAILED", "FAILED"],
            "reference_completeness_status": ["FAILED", "FAILED"],
            "index_class": [None, None],
            "reference_index_class": [None, None],
            "index_value": [None, None],
            "reference_index_value": [None, None],
        }
    )
    recomputed = _recompute_sensitivity_summary_from_by_point(df)
    assert recomputed[15]["n_class_transitions"] == 0
    assert recomputed[15]["class_agreement_with_reference"] == 1.0


def test_one_failed_one_classified_counts_as_a_transition():
    df = pd.DataFrame(
        {
            "value": [15, 15],
            "completeness_status": ["FAILED", "OK"],
            "reference_completeness_status": ["OK", "OK"],
            "index_class": [None, "Favorable"],
            "reference_index_class": ["Acceptable", "Favorable"],
            "index_value": [None, 10.0],
            "reference_index_value": [30.0, 10.0],
        }
    )
    recomputed = _recompute_sensitivity_summary_from_by_point(df)
    assert recomputed[15]["n_class_transitions"] == 1
    assert recomputed[15]["class_agreement_with_reference"] == 0.5


def test_genuinely_different_classes_still_count():
    df = pd.DataFrame(
        {
            "value": [15],
            "completeness_status": ["OK"],
            "reference_completeness_status": ["OK"],
            "index_class": ["Critical"],
            "reference_index_class": ["Favorable"],
            "index_value": [90.0],
            "reference_index_value": [5.0],
        }
    )
    recomputed = _recompute_sensitivity_summary_from_by_point(df)
    assert recomputed[15]["n_class_transitions"] == 1
