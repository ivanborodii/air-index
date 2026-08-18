# The previously-observed "value near 0.024"

**Identity**: `evaluation.fault_injection.row_level_metrics_by_split.calibration[0].precision`
in `research_results/exploratory/run_summary.json` (and the equivalent path in
`research_results/exploratory/article_metrics.json`), for `reason_code = "single_spike"`.

**Exact value**: `precision = 0.02147239263803681` (not exactly 0.024, but the
closest fault-detection metric to it anywhere in the currently committed
`research_results/{final,exploratory}/` artifacts -- confirmed by an
exhaustive walk of both JSON files' numeric leaves within +/-0.003 of 0.024;
every other candidate within that tolerance belongs to the unrelated
`evaluation.stability.*` section, i.e. class-stability-under-perturbation
metrics such as `prob_moved_better`/`class_change_rate`, NOT Hampel
precision/recall/F1/FPR).

**What it is, precisely**: it is **precision**, not recall, not F1, not
FPR, and not a calculation error. The full confusion counts behind it:

| metric | value |
|---|---|
| TP | 7 |
| FP | 319 |
| FN | 0 |
| TN | 874 |
| precision | 0.02147 |
| recall | 1.0 |
| F1 | 0.04204 |
| false_positive_rate | 0.26739 |

This is the calibration-split row-level confusion for the `single_spike`
synthetic fault category in the **exploratory-mode** evaluation run
(`research_results/exploratory/`). It never appears in
`research_results/final/run_summary.json` or `article_metrics.json` at all --
the `evaluation.fault_injection` section is absent from the published
`final/` package (fault-injection/synthetic-anomaly evaluation is gated to
exploratory mode by the repository's `mode=publication` vs `mode=exploratory`
distinction; see commit 90ecdec). So this number was never part of the
manuscript-facing publication package, only the exploratory diagnostic run.

**Honest interpretation**: recall is perfect (every genuine injected spike
was flagged), but precision is very poor (319 false positives for only 7
true positives) -- i.e. the Hampel-based `single_spike` reason code, at
whatever multiplier this exploratory run used, is extremely over-sensitive:
it flags far more points as spike-like than are genuinely injected spikes.
This is exactly the kind of poor-precision result the task's section 5
preamble refers to, and it is reported here as-is, not renamed or
reinterpreted to look better.

**Relationship to today's new sweep**: `hampel_selected_parameter.json` in
this same directory separately investigated values near 0.024 WITHIN the
new h in {1.0..5.0} multiplier sweep's own calibration/validation metrics
(finding `single_spike_fpr` values of ~0.0212-0.0339 there, under the
`seeded_group` split method) -- that is a distinct search over different
data than this document's finding, and the two should not be conflated.
This document identifies the actual PRE-EXISTING committed value the task
asked about; `hampel_selected_parameter.json`'s own section documents a
similar-looking coincidence in the new sweep's FPR metric, not the same
number.
