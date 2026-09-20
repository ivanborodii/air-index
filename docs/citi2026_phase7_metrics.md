# CITI-2026 Phase 7 — Metrics, Uncertainty, Window Sensitivity, Compute Cost

Bootstrap: 1000 resamples, seed=42. Recall/event-level metrics resampled BY FAULT INSTANCE; macro-F1/balanced-accuracy resampled BY WHOLE TEST DAY (disclosed as two different, deliberately chosen resampling units — see script docstring).

## Full results

Full table (all pairs/windows/feature sets/methods, every metric + CI): `research_results/citi2026/phase7/full_metrics.csv`.

## Window-size sensitivity (macro-F1, random_forest, feature set c)

| pair | window | macro F1 | 95% CI | fault recall | event recall |
|---|---:|---:|---|---:|---:|
| humidity | 5 | 0.6659 | [0.6390, 0.6936] | 0.2535 | 0.4615 |
| humidity | 10 | 0.6543 | [0.6251, 0.6910] | 0.2329 | 0.4188 |
| humidity | 20 | 0.6233 | [0.5931, 0.6561] | 0.1884 | 0.3889 |
| temperature | 5 | 0.7129 | [0.6680, 0.7572] | 0.3202 | 0.6000 |
| temperature | 10 | 0.6148 | [0.5719, 0.6578] | 0.1712 | 0.4409 |
| temperature | 20 | 0.6097 | [0.5752, 0.6440] | 0.1642 | 0.3727 |

## Explicit target check: gradual-shift recall vs. the ~27% single-channel ceiling

- External reference ceiling (given in the brief): **27%**
- This project's OWN measured single-channel-rule baseline gradual-shift recall (mean across pairs/windows): **56.9%**
- Feature-set (b)/(c) model x pair x window combinations exceeding the EXTERNAL 27% figure: **11 / 36**
- Feature-set (b)/(c) model x pair x window combinations exceeding THIS project's OWN single-channel baseline: **9 / 36**

**Not a universal win, stated plainly**: not every (b)/(c) combination beats even this project's own single-channel baseline on gradual-shift recall — see `full_metrics.csv` for exactly which combinations do and don't, rather than only reporting the favourable aggregate.

## Compute cost (Raspberry Pi 5 Model B Rev 1.0)

| method | mean fit (s) | max fit (s) | mean predict (s) |
|---|---:|---:|---:|
| decision_tree | 3.66 | 6.83 | 0.0177 |
| logistic_regression | 2.93 | 8.26 | 0.1863 |
| random_forest | 40.85 | 59.12 | 0.9875 |

All timings measured directly on the deployment device (Raspberry Pi 5 Model B Rev 1.0) — not a development machine.

## False-event rate (real changes wrongly attributed to faults)

| method | mean false-event rate across all pair/window/feature-set combos |
|---|---:|
| logistic_regression | 0.0050 |
| random_forest | 0.0201 |
| decision_tree | 0.0260 |
| baseline_single_channel_rule | 0.0458 |
| baseline_one_out_of_two_comparator | 0.0969 |
