"""Inter-method agreement on unlabeled real data.

Per the manuscript: for unlabeled real observations, only agreement between
methods' results is evaluated — never accuracy, never macro-F1 (which
presupposes a true/predicted distinction that doesn't exist between two
peer methods). Cohen's kappa is reported here strictly as inter-rater
reliability between two methods, not as a measure of correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from iaq_hfis.constants import CLASS_ORDER
from iaq_hfis.evaluation._metrics import cohens_kappa, percent_agreement


@dataclass(frozen=True)
class AgreementResult:
    method_a: str
    method_b: str
    n: int
    n_excluded: int
    percent_agreement: float | None
    cohens_kappa: float | None


def pairwise_agreement(method_classes: dict[str, list[str | None]]) -> list[AgreementResult]:
    """``method_classes`` maps method name -> list of classified outputs
    (aligned by position across methods, e.g. one entry per computed_ts).
    Positions where either method has no class (FAILED) are excluded from
    that pair's comparison, not silently treated as a class.
    """
    lengths = {len(v) for v in method_classes.values()}
    if len(lengths) > 1:
        raise ValueError("all methods must have the same number of aligned observations")

    results = []
    for method_a, method_b in combinations(sorted(method_classes), 2):
        a_all, b_all = method_classes[method_a], method_classes[method_b]
        paired = [(a, b) for a, b in zip(a_all, b_all) if a is not None and b is not None]
        n_excluded = len(a_all) - len(paired)
        if not paired:
            results.append(AgreementResult(method_a, method_b, n=0, n_excluded=n_excluded, percent_agreement=None, cohens_kappa=None))
            continue
        a = [p[0] for p in paired]
        b = [p[1] for p in paired]
        results.append(
            AgreementResult(
                method_a=method_a,
                method_b=method_b,
                n=len(paired),
                n_excluded=n_excluded,
                percent_agreement=percent_agreement(a, b),
                cohens_kappa=cohens_kappa(a, b, CLASS_ORDER),
            )
        )
    return results
