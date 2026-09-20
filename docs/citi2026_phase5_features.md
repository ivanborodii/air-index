# CITI-2026 Phase 5 — Causal Feature Sets

Target: pair-level fault presence, y(t) = OR of both channels' Phase 4 ground-truth fault-active flags. All features causal (trailing window, per-day, never bridging a day boundary).

## Build manifest

| pair | window | rows (after warm-up drop) | dropped (warm-up) | positive rate |
|---|---:|---:|---:|---:|
| temperature | 5 | 244,443 | 19,430 | 0.1102 |
| temperature | 10 | 241,663 | 22,210 | 0.1108 |
| temperature | 20 | 237,657 | 26,216 | 0.1116 |
| humidity | 5 | 244,478 | 19,395 | 0.1127 |
| humidity | 10 | 241,624 | 22,249 | 0.1133 |
| humidity | 20 | 237,654 | 26,219 | 0.1144 |

## Feature sets

- **(a) single-channel only**: 12 features (6 rolling stats x 2 channels)
- **(b) single + cross-channel**: (a) + 6 cross features = 18
- **(c) + absolute-humidity concordance**: (b) + 6 AH-cross features = 24 (applies to BOTH pairs, not just humidity -- AH is a joint function of T and RH)
- **(d) cross-channel only**: the 6 cross features alone

Exact column lists: `research_results/citi2026/phase5/feature_set_definitions.json`. Per-(pair,window) tables in `data/citi2026/features.duckdb` (`features_<pair>_w<W>`, gitignored, rebuildable from this script).