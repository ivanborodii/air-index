# CITI-2026 Phase 6 — Models & Baselines

3 models (LogisticRegression, DecisionTree, RandomForest) x 4 feature sets x 2 pairs x 3 windows = 72 fits, plus 2 rule-based baselines x 2 pairs x 3 windows = 12 baseline evaluations. Same day-level train/test split (Phase 4, seed=42) for every combination. All test-set predictions persisted to `data/citi2026/phase6_predictions.duckdb` (`predictions` table) for Phase 7.

**This is a quicklook (macro-F1 only) — full metrics, uncertainty, and the explicit ceiling-comparison target check are Phase 7's job, not repeated here.**

## Quicklook: macro-F1 by pair / window / feature set / method

| pair | window | method | a_single_only | b_single_plus_cross | c_plus_ah | d_cross_only | n/a |
|---|---|---|---|---|---|---|---|
| humidity | 5 | baseline_one_out_of_two_comparator | nan | nan | nan | nan | 0.4825 |
| humidity | 5 | baseline_single_channel_rule | nan | nan | nan | nan | 0.4930 |
| humidity | 5 | decision_tree | 0.6659 | 0.6546 | 0.6578 | 0.6447 | nan |
| humidity | 5 | logistic_regression | 0.4678 | 0.5600 | 0.5631 | 0.5620 | nan |
| humidity | 5 | random_forest | 0.6512 | 0.6609 | 0.6659 | 0.6474 | nan |
| humidity | 10 | baseline_one_out_of_two_comparator | nan | nan | nan | nan | 0.4825 |
| humidity | 10 | baseline_single_channel_rule | nan | nan | nan | nan | 0.4777 |
| humidity | 10 | decision_tree | 0.6536 | 0.6378 | 0.6399 | 0.6255 | nan |
| humidity | 10 | logistic_regression | 0.4674 | 0.5275 | 0.5276 | 0.5292 | nan |
| humidity | 10 | random_forest | 0.6357 | 0.6456 | 0.6543 | 0.6323 | nan |
| humidity | 20 | baseline_one_out_of_two_comparator | nan | nan | nan | nan | 0.4827 |
| humidity | 20 | baseline_single_channel_rule | nan | nan | nan | nan | 0.4788 |
| humidity | 20 | decision_tree | 0.6205 | 0.6178 | 0.6208 | 0.5986 | nan |
| humidity | 20 | logistic_regression | 0.4670 | 0.5213 | 0.5226 | 0.5246 | nan |
| humidity | 20 | random_forest | 0.6067 | 0.6214 | 0.6233 | 0.6027 | nan |
| temperature | 5 | baseline_one_out_of_two_comparator | nan | nan | nan | nan | 0.5053 |
| temperature | 5 | baseline_single_channel_rule | nan | nan | nan | nan | 0.4951 |
| temperature | 5 | decision_tree | 0.7015 | 0.7139 | 0.7044 | 0.5783 | nan |
| temperature | 5 | logistic_regression | 0.4710 | 0.5343 | 0.5396 | 0.5323 | nan |
| temperature | 5 | random_forest | 0.7248 | 0.7153 | 0.7129 | 0.5811 | nan |
| temperature | 10 | baseline_one_out_of_two_comparator | nan | nan | nan | nan | 0.5047 |
| temperature | 10 | baseline_single_channel_rule | nan | nan | nan | nan | 0.4833 |
| temperature | 10 | decision_tree | 0.6685 | 0.6561 | 0.6656 | 0.5692 | nan |
| temperature | 10 | logistic_regression | 0.4707 | 0.5184 | 0.5274 | 0.5191 | nan |
| temperature | 10 | random_forest | 0.6720 | 0.6307 | 0.6148 | 0.5756 | nan |
| temperature | 20 | baseline_one_out_of_two_comparator | nan | nan | nan | nan | 0.5037 |
| temperature | 20 | baseline_single_channel_rule | nan | nan | nan | nan | 0.4843 |
| temperature | 20 | decision_tree | 0.7147 | 0.6558 | 0.6431 | 0.5829 | nan |
| temperature | 20 | logistic_regression | 0.4706 | 0.5341 | 0.5406 | 0.5357 | nan |
| temperature | 20 | random_forest | 0.6494 | 0.6217 | 0.6097 | 0.5938 | nan |

## Fit timing (Raspberry Pi 5 Model B Rev 1.0)

| method | mean_fit_s | max_fit_s |
|---|---|---|
| decision_tree | 3.6600 | 6.8300 |
| logistic_regression | 2.9300 | 8.2600 |
| random_forest | 40.8500 | 59.1200 |

Full per-combination timing: `research_results/citi2026/phase6/fit_timing_raspberry_pi5.csv`.