# Evaluation protocol

Describes every analysis `iaq_hfis evaluate` runs: sampling strategy,
perturbation protocol, continuity methodology, sensitivity methodology,
masking, reference cases, and the fault-injection benchmark. All of it is
scoped to one `pipeline_run_id` and gets its own fresh `evaluation_run_id`
(see `docs/reproducibility.md`).

## 1. Agreement (unlabeled real data)

Pairwise class agreement (% agreement, Cohen's kappa) between PROPOSED_HFIS,
FUZZY_COMPONENT_MAX, and WEIGHTED_MEAN over every computed_ts in the evaluated range.
**This is agreement, never accuracy** -- there is no ground truth for real
observations. `evaluation/agreement.py`; `evaluation.agreement` in
run_summary.json; `method_comparison.csv`.

## 2. Masking

A "masking event": a computed_ts where at least one available component's
own class reaches `masking_severity_threshold` (default Critical) but a
baseline's aggregated class does not. FUZZY_COMPONENT_MAX cannot mask by construction
(it IS the max). `evaluation/masking.py`; `masking_summary.csv`.

## 3. Reference cases (NOT empirical ground truth)

42 synthetic, deterministic, pre-labeled vectors: each perturbs exactly one
direct-input channel to a point just below/above one of its configured
breakpoints, holding every other channel deeply favourable. Because the rule
base is worst-of, the expected class is exactly the perturbed channel's own
crisp class. Macro-F1/Cohen's kappa here measure **consistency with a
predefined synthetic label**, not real-world classification accuracy --
`evaluation/reference_cases.py`; `reference_case_consistency.csv`.

## 4. Multi-point stability

Two-part deterministic sample selection over the whole evaluated range
(`evaluation/multi_point_stability.py:select_stability_samples`):

- **boundary_adjacent**: up to `stability_max_boundary_samples` computed_ts
  whose aggregated channel values lie closest to any control-region
  boundary.
- **random_comparison**: a reproducible random sample (fixed
  `stability_seed`) of up to `stability_max_random_samples` from the rest.

Each point is perturbed `stability_n_trials` times per method
(PROPOSED_HFIS, FUZZY_COMPONENT_MAX, WEIGHTED_MEAN): every available channel
independently perturbed by U(-declared_uncertainty, +declared_uncertainty),
clipped to the sensor's technical range, PM2.5<=PM10 ordering re-enforced.
Per-sample RNG seeds are derived via SHA-256 of `(seed, sample_id)` --
deterministic across machines/processes (not Python's randomized string
`hash()`).

One shared, deterministic aggregation function
(`multi_point_stability._aggregate_stability_rows`, reading directly from
the persisted `evaluation_stability_trials`/`evaluation_stability_samples`
tables) computes every summary grain -- `run_summary.json` and every
`stability_*.csv` can never numerically disagree, because they call the
exact same function. Per grain: class-change rate (95% Wilson-score CI),
mean/median/p95/max absolute index change, and the probability of moving
to a strictly **better** vs strictly **worse** class under perturbation
(via `CLASS_SEVERITY`; these two always sum to the class-change rate) --
never called "accuracy," since there is no ground truth, only
self-consistency of a method's own output. Reported at three grains:
**overall** (`by_method`), **by_variable** (per boundary channel /
random_comparison), and **by_original_class** (per baseline class the
point started in).
Tables: `evaluation_stability_samples`, `evaluation_stability_trials`.
CSVs: `stability_samples.csv`, `stability_trials.csv`, `stability_by_point.csv`,
`stability_summary.csv`, `stability_summary_by_variable.csv`,
`stability_summary_by_original_class.csv`.

## 5. Boundary continuity (HFIS vs FUZZY_COMPONENT_MAX vs WEIGHTED_MEAN)

Dense deterministic input grids (`evaluation.continuity_grid_points`,
default 41) spanning +/-1 declared sensor uncertainty around every
control-region boundary: 3 breakpoints each for PM2.5/PM10/CO2, 6 edges for
humidity, and 6 edges **per room/season profile** for temperature (every
profile in `room_profiles.yaml`, not just the run's representative one --
"every seasonal temperature boundary"). Each boundary is swept under
THREE "other components" contexts -- **favourable**, **acceptable**,
**degraded** -- not a single favourable-only baseline. Per boundary/context/
method: max/mean/median/p95 adjacent-point jump, total variation, a local
Lipschitz ratio (max \|delta index\| / \|delta input\| between adjacent
grid points -- the discrete-grid Lipschitz constant), class transitions
(count + positions), index range, monotonicity violations (for pollutant
channels), whether a favourable component masked the swept channel's own
severity, and (PROPOSED_HFIS rows only) the area between its own curve and
FUZZY_COMPONENT_MAX's curve (trapezoidal integral of \|HFIS - FUZZY_COMPONENT_MAX\| over the
sweep). `evaluation/continuity.py`.
CSVs: `continuity_grid.csv`, `continuity_summary.csv`.

**Honesty note -- read `docs/hfis_vs_crispmax_audit.md` before citing this
experiment.** When only ONE channel is swept, holding every other channel
at a FIXED value (even under the acceptable/degraded contexts), the
worst-of rule base can make PROPOSED_HFIS mathematically collapse to
exactly FUZZY_COMPONENT_MAX's computation for the whole sweep -- proven and observed
empirically on real data (`smoothness_comparison` in
`run_summary.json:evaluation.continuity`, and the audit doc's section 3B).
This is a property of the single-channel-perturbation experimental design,
not evidence the two methods are equivalent in general (an independent
multi-component synthetic check in the audit doc shows real divergence once
more than one channel carries signal simultaneously) -- but it does mean a
"HFIS is smoother than FUZZY_COMPONENT_MAX" claim is **not** supported by this
continuity experiment as currently designed. Always read the actual
`smoothness_comparison.conclusion` string for the run in question; never
assume HFIS is smoother without checking it.

## 6. Multi-point sensitivity

Deterministic stratified sample (`evaluation/multi_point_sensitivity.py`)
covering: each air-quality class among OK results, PARTIAL cases,
boundary-adjacent observations (bottom decile of distance-to-any-boundary),
ordinary OK observations, fresh vs. stale outdoor context, and computed_ts
with a data-quality event (some channel's window had `coverage_ok = FALSE`).
Up to `sensitivity_max_samples_per_stratum` per stratum, seeded the same way
as stability. For each sampled point: sweep window duration (5/15/30/60 min)
and coverage threshold (0.70/0.80/0.90), diff against that point's own
15-minute/configured-threshold reference. Reports index-difference
mean/median/p95/max and class agreement, per swept value.
CSVs: `sensitivity_window_by_point.csv`, `sensitivity_window_summary.csv`,
`sensitivity_coverage_by_point.csv`, `sensitivity_coverage_summary.csv`.

## 7. Fault-injection benchmark (labeled, synthetic, separate from real data)

60 deterministic scenarios (5 channels -- CO2, temperature, humidity,
PM10, PM2.5 -- x 5 reason codes, plus genuine-event preservation checks for
CO2/temperature/humidity) run through the real `hard_checks`/`soft_checks`
layer (not a simulation of it): isolated spike (2 magnitudes per channel),
out-of-range value, stuck-at run, missing/data-loss run, gradual drift, and
"must remain usable" genuine-event scenarios (a sustained step change and a
gradual-but-persistent rise). See `docs/fault_injection_audit.md` for the
structural audit (double-counting, pre-existing-anomaly, warm-up,
temporal-tolerance, multi-detection, overlapping-window risks) and two
confirmed bugs found and fixed while rebuilding this benchmark.
`evaluation/fault_injection.py`.

**Calibration/validation split**: every scenario belongs to exactly one of
two disjoint sets (`dataset_split_of`, derived from the scenario_id suffix)
-- **calibration** (scale=1.0) and **validation** (scale=1.15, distinct
scenario_ids) -- no scenario or timestamp is shared. The Hampel grid search
is tuned only against calibration; every headline, publication-facing
number (`run_summary.json:evaluation.fault_injection`,
`headline_dataset_split: "validation"`) is always the validation split, the
split no explicitly-provisional parameter was ever tuned against.

**Row-level vs event-level metrics**: row-level (`score_predictions`)
counts every affected sample individually (a fault spanning N samples
contributes N true positives). Event-level (`match_events`/`score_events`)
does one-to-one matching between each injected fault and predicted
detection intervals within a configurable temporal tolerance
(`temporal_tolerance_samples`, default 1) -- preventing a multi-sample
fault from being double-counted as many separate detections. Both are
reported, per reason code: TP/FP/FN(/TN and specificity for row-level),
precision, recall, F1, mean detection delay. Plus a full row-level
confusion matrix (`fault_detection_confusion_matrix.csv`, true label vs.
every reason code actually predicted, including "none"), false-rejection
rate for genuine events (must be zero), and confirmation-recovery rate.
**Weak results are disclosed, never hidden**: single_spike still has
materially lower row-level precision than the other reason codes (stuck_value
now reaches precision 1.0 after the 2026-08-13 benchmark fix -- see
`docs/fault_injection_audit.md` section 5); `run_narrative.md`/
`article_results_summary.md` automatically flag any reason code with
row-level F1 below 0.5 as a "Disclosed limitation."
Tables: `fault_injection_events`, `fault_detection_predictions`,
`fault_detection_metrics`, `fault_detection_event_metrics`,
`fault_detection_confusion_matrix`. CSVs of the same names.

**Primary screening vs. final exclusion** (section 9 of the manuscript-
validation task spec): `fault_detection_metrics`/`fault_detection_event_metrics`
score the PRIMARY reason-code candidate (`predicted_reason_codes`) against
the true label. A primary SUSPECT candidate can later be CONFIRMED usable
by the confirmation stage -- `fault_final_exclusion_metrics` scores the
separate, final question (was the sample ultimately excluded, `usable=False`)
instead: a confirmed-usable primary candidate is a false negative there, not
a true positive. The two tables/metrics are never conflated under the same
name; see `iaq_hfis.evaluation.fault_injection.score_final_exclusion`.

### Hampel calibration

Only `single_spike` detection and genuine-event preservation depend on the
Hampel `window_size`/`mad_multiplier` (stuck-value/data-loss/gradual-drift
use separate, Hampel-independent detectors). Two grids exist:

- **Diagnostic**: `HAMPEL_WINDOW_GRID` (7/11/15) x `HAMPEL_MULTIPLIER_GRID`
  (1.0/2.0/3.0), both splits, for context (`hampel_calibration.csv` has all
  18 rows per split).
- **Selection** (task spec section 6): window size held fixed at
  `HAMPEL_SELECTION_WINDOW_SIZE=11` (the manuscript's causal-window point
  count); `iaq_hfis.evaluation.fault_injection.select_hampel_multiplier`
  reads *only* `dataset_split == "calibration"` rows at that window size and
  picks the multiplier maximizing
  `S = (fault_recall + genuine_event_preservation_rate + (1 - single_spike_FPR)) / 3`,
  with a deterministic tie-break (highest S, then recall, then preservation,
  then lowest FPR, then smallest multiplier). The **validation** split is
  scored once for the selected value and reported separately -- never
  inspected while selecting, and changing it cannot change the selection
  (see `tests/unit/test_fault_injection.py::test_select_hampel_multiplier_ignores_validation_rows_entirely`).
  `config/iaq_hfis.yaml`'s configured `mad_multiplier` is kept in sync with
  this selection (`selected=true` rows in `hampel_calibration.csv`); status
  is `CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT`, not literature-informed --
  see `parameter_selection.json` and
  `research_results/hampel_causal_revision_report.md` for the full
  calibration table and the frozen validation-split result.

## 8. Publication readiness

`iaq_hfis validate-artifacts --pipeline-run-id <id>` cross-checks
run_summary.json/.md, run_narrative.md, every CSV, and plot_manifest.json
against the derived DB and each other: timestamp counts, completeness sums,
FAILED-row nullness, agreement/masking reconciliation, stability trial
counts and every aggregation dimension's totals, continuity threshold
coverage and grid density/recomputed metrics, fault-injection event counts
and one-to-one-matching sanity and confusion-matrix agreement,
config-hash consistency between `run` and `evaluate`, sensitivity
recomputation from detailed data, provisional-parameter cross-artifact
agreement, and plot-manifest/rendered-PNG consistency (46 checks on the
tracked reference run; `src/iaq_hfis/validation.py`). Writes
`artifact_validation.json`/`.md` (plus a plain-text rendering) -- exits
nonzero on any violation.

`assess_readiness` (`src/iaq_hfis/provenance.py`) is a lighter,
always-computable signal (pipeline/evaluation status + provisional-parameter
disclosure) merged into `run_summary.json:readiness` at report-generation
time, split into `artifact_readiness` (computational artifacts are
internally complete and consistent) and `manuscript_readiness` (this run
is eligible to be described as the manuscript's complete proposed method
-- requires a DBN-supported temperature profile, `mode=publication`, and a
full A/V/M/I OK-completeness result). The two are complementary, not
identical: `validate-artifacts`'s result is the authoritative combined
check, folded into both readiness signals at `finalize` time via
`iaq_hfis.provenance.fold_late_artifact_checks`, and recorded in the
tracked `research_results/final/` snapshot (see `docs/reproducibility.md`).
