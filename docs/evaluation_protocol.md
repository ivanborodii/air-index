# Evaluation protocol

Describes every analysis `iaq_hfis evaluate` runs: sampling strategy,
perturbation protocol, continuity methodology, sensitivity methodology,
masking, reference cases, and the fault-injection benchmark. All of it is
scoped to one `pipeline_run_id` and gets its own fresh `evaluation_run_id`
(see `docs/result_reproducibility.md`).

## 1. Agreement (unlabeled real data)

Pairwise class agreement (% agreement, Cohen's kappa) between PROPOSED-HFIS,
CRISP-MAX, and WEIGHTED-MEAN over every computed_ts in the evaluated range.
**This is agreement, never accuracy** -- there is no ground truth for real
observations. `evaluation/agreement.py`; `evaluation.agreement` in
run_summary.json; `method_comparison.csv`.

## 2. Masking

A "masking event": a computed_ts where at least one available component's
own class reaches `masking_severity_threshold` (default Critical) but a
baseline's aggregated class does not. CRISP-MAX cannot mask by construction
(it IS the max). `evaluation/masking.py`; `masking_summary.csv`.

## 3. Reference cases (NOT empirical ground truth)

42 synthetic, deterministic, pre-labeled vectors: each perturbs exactly one
direct-input channel to a point just below/above one of its configured
breakpoints, holding every other channel deeply favorable. Because the rule
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
(PROPOSED-HFIS, CRISP-MAX, WEIGHTED-MEAN): every available channel
independently perturbed by U(-declared_uncertainty, +declared_uncertainty),
clipped to the sensor's technical range, PM2.5<=PM10 ordering re-enforced.
Per-sample RNG seeds are derived via SHA-256 of `(seed, sample_id)` --
deterministic across machines/processes (not Python's randomized string
`hash()`). Reports: class-change rate with a 95% Wilson-score confidence
interval, mean/median/p95/max absolute index change.
Tables: `evaluation_stability_samples`, `evaluation_stability_trials`.
CSVs: `stability_samples.csv`, `stability_trials.csv`, `stability_by_point.csv`,
`stability_summary.csv`.

## 5. Boundary continuity (HFIS vs CRISP-MAX vs WEIGHTED-MEAN)

Dense deterministic input grids (`evaluation.continuity_grid_points`,
default 41) spanning +/-1 declared sensor uncertainty around every
control-region boundary (3 breakpoints each for PM2.5/PM10/CO2; 6 edges
each for temperature/humidity), other channels held deeply favorable. Per
boundary/method: max/mean adjacent-point jump, total variation, class
transitions (count + positions), index range, monotonicity violations (for
pollutant channels), and whether a favorable component masked the swept
channel's own severity. `evaluation/continuity.py`.
CSVs: `continuity_grid.csv`, `continuity_summary.csv`.

**Honesty note**: because CRISP-MAX's per-component score is itself already
a Mamdani centroid (the same smooth function HFIS's components use), CRISP-MAX
and HFIS may show *similar* smoothness in these single-channel sweeps -- the
structural difference is in aggregation (max vs. two-level rule inference
over all three components simultaneously), not necessarily in per-channel
continuity. Read the actual numbers in `continuity_summary.csv`; do not
assume HFIS is smoother without checking.

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

8 deterministic scenarios run through the real `hard_checks`/`soft_checks`
layer (not a simulation of it): isolated spike, out-of-range value,
stuck-at run, missing/data-loss run, gradual drift, PM-order violation, and
two "must remain usable" genuine-event scenarios (a sustained step change
and a gradual-but-persistent rise) -- these must NOT be discarded as
faults. `evaluation/fault_injection.py`.

Metrics per reason code: TP/FP/FN, precision, recall, F1,
false-positive-rate, mean detection delay. Plus: false-rejection rate for
genuine events (must be low/zero) and confirmation-recovery rate (fraction
of SUSPECT candidates ultimately confirmed usable).
Tables: `fault_injection_events`, `fault_detection_predictions`,
`fault_detection_metrics`. CSVs of the same names.

### Hampel calibration

Only `single_spike` detection depends on the Hampel `window_size`/
`mad_multiplier` (stuck-value/data-loss/gradual-drift use separate,
Hampel-independent detectors). Grid search (`HAMPEL_WINDOW_GRID` x
`HAMPEL_MULTIPLIER_GRID`) over a **development** scenario split, scored by
`(fault_recall + genuine_event_preservation_rate + (1 - single_spike_FPR)) / 3`;
**holdout** split scored once, never used to pick parameters. The configured
`hampel.window_size`/`mad_multiplier` are **always retained** regardless of
this grid's outcome -- a change is only adopted after separate empirical
verification against real live data (see `config/iaq_hfis.yaml`'s hampel
section for that history), never from synthetic-benchmark evidence alone.
`hampel_calibration.csv`.

## 8. Publication readiness

`iaq_hfis validate-artifacts --pipeline-run-id <id>` cross-checks
run_summary.json/.md, run_narrative.md, every CSV, and plot_manifest.json
against the derived DB and each other (timestamp counts, completeness sums,
FAILED-row nullness, agreement/masking reconciliation, stability trial
counts, plot-manifest column references). `src/iaq_hfis/validation.py`.

`assess_publication_readiness` (`src/iaq_hfis/provenance.py`) is a
lighter, always-computable signal (pipeline/evaluation status +
provisional-parameter disclosure) merged into
`run_summary.json:publication_readiness` at report-generation time. The two
are complementary, not identical: `validate-artifacts`'s result is the
authoritative combined check, recorded in the tracked
`research_results/final/` snapshot (see `docs/result_reproducibility.md`).
