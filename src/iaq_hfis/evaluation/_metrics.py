"""Shared classification-comparison math: percent agreement, Cohen's kappa,
macro-F1. Deliberately dependency-free (no scikit-learn) — these are small,
well-defined formulas and the project otherwise has no ML-library need.

Cohen's kappa is used in two different roles by callers of this module:
inter-method agreement on unlabeled real data
(:mod:`iaq_hfis.evaluation.agreement`, no notion of "correct"), and
agreement with known synthetic labels
(:mod:`iaq_hfis.evaluation.ground_truth`, where macro-F1 is also valid).
macro-F1 is intentionally NOT exposed for the unlabeled case — it requires
a true/predicted distinction that doesn't exist between two peer methods.
"""

from __future__ import annotations

from collections import Counter


def percent_agreement(a: list[str], b: list[str]) -> float:
    """Fraction of paired positions where a[i] == b[i]. Raises if empty."""
    if len(a) != len(b):
        raise ValueError("a and b must be the same length")
    if not a:
        raise ValueError("cannot compute agreement over zero paired observations")
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / len(a)


def cohens_kappa(a: list[str], b: list[str], labels: list[str]) -> float:
    """Cohen's kappa between two raters (or a rater and known labels) over
    a fixed label set. Returns 1.0 for perfect agreement when chance
    agreement is already 1.0 (degenerate single-label case)."""
    if len(a) != len(b):
        raise ValueError("a and b must be the same length")
    n = len(a)
    if n == 0:
        raise ValueError("cannot compute kappa over zero paired observations")

    po = sum(1 for x, y in zip(a, b) if x == y) / n
    count_a = Counter(a)
    count_b = Counter(b)
    pe = sum((count_a.get(label, 0) / n) * (count_b.get(label, 0) / n) for label in labels)

    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def macro_f1(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    """Unweighted mean of per-class F1 scores. A label with no true and no
    predicted instances contributes an F1 of 1.0 (vacuously perfect);
    a label with true instances but zero predictions (or vice versa)
    contributes 0.0.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")

    scores = []
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)

        if tp == 0 and fp == 0 and fn == 0:
            scores.append(1.0)
            continue
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        scores.append(f1)

    return sum(scores) / len(scores) if scores else 0.0
