# Article results summary -- expanded-dataset research run (2026-08-17/18)

Run ID: `20260817_expanded_dataset_v1`. Baseline pipeline run:
`7f04698725dd4f35a432ba4a0de2934f` (git commit `3916a57`, unchanged
production config). Full paths, hashes, and reproduction commands are in
`run_manifest.json`. Deviations from the requested protocol are listed at
the end of this document and in `manuscript_update_notes.md`.

## 1. Unchanged baseline results on the expanded dataset

- Data interval: 2026-06-18T00:00:00Z (inclusive) to 2026-08-16T00:00:00Z
  (exclusive). 169,331 raw rows, 169,331 unique timestamps, 0 duplicates,
  0 ordering violations, 0 rows outside the interval
  (`snapshot/data_interval_verification.json`, SHA256 of both the frozen
  CSV export and full-DB snapshot recorded there).
- Baseline pipeline (config/rules unchanged from production): 16,992
  computed timestamps at the 15-minute window. Completeness: **OK=15,242
  (89.7%)**, **PARTIAL=1,004 (5.9%)**, **FAILED=746 (4.4%)**
  (`baseline/baseline_run_manifest.json`).
- This baseline pipeline run was executed once, at git commit `3916a57`
  (current HEAD, unchanged by anything in this research run) -- not
  rerun for this summary, since the recorded run's `source_git_commit`
  already matches HEAD and its row/timestamp counts exactly match the
  frozen section-3 snapshot.

## 2. Hampel calibration results

Calibration/validation group split: seed **20260815**, 70/30 by scenario
family, verified disjoint (`hampel_selected_parameter.json`). Swept h in
{1.0, 1.5, ..., 5.0}, window_size fixed at 11 (production value).

- Under every split method (`structural`, `seeded_group`) and both
  objectives (S_old, S_new), the calibration-optimal multiplier is **h=5.0**
  -- the edge of the tested grid. Recall and genuine-event preservation
  saturate to 1.0 well before h=5.0; precision/F1 are still rising at the
  edge. **This sweep does not prove h=5.0 is a true optimum** -- only the
  best of the 9 tested values.
- Calibration point (seeded_group, h=5.0): precision=0.444, recall=1.0,
  genuine_event_preservation=1.0, S_new=0.808.
- Production value (h=3.0) is unchanged; this sweep is diagnostic only, per
  the task's explicit constraint against changing the model merely to
  improve a metric.

## 3. Hampel validation results (locked multiplier, evaluated once)

- `structural` split, h=5.0: precision=0.182, recall=1.0, F1=0.308,
  FPR=0.057, genuine_event_preservation=1.0 (n=4 scenarios, 160 predictions).
- `seeded_group` split, h=5.0: precision=0.0, recall=NaN (undefined --
  zero predicted positives in this tiny 2-scenario validation subset),
  FPR=0.125. **Reported honestly**: the seeded_group validation set is too
  small (2 scenarios) for a stable precision/recall estimate; this is a
  genuine limitation of the seeded cross-check, not a coding error.

## 4. Final results using the selected multiplier

No production config change was made (task section 1 explicitly forbids
changing the model merely to obtain better numbers). The "selected"
multiplier (h=5.0) is reported as a diagnostic finding for the author to
weigh against the manuscript's own literature citation for the shipped
h=3.0, not applied to `config/iaq_hfis.yaml`.

## 5. Missing-data strategy results (task's "most important new experiment")

8 masking cases (5 direct-input + 3 component) x 5 strategies x 2 splits
(calibration/validation, chronological 70/30). 10,669 calibration + 4,573
validation complete-record-reference instances per case (subsampled to
840/360 per case for the actual masked-recompute experiment after an
unsampled attempt exceeded a 10-minute wall-clock budget on this Pi --
documented in `missing_data_strategy_metadata.json`; the mean-imputation
fit itself used the FULL unsampled calibration data).

- **Headline, unflattering finding**: for `component:M` and
  `direct_input:temperature` masking, the production "proposed" strategy
  (exclude the missing component) **hides 89-95% of complete-record-
  reference CRITICAL results** on both splits -- worse at preserving
  CRITICAL detection than `locf` (~0-2%), though LOCF has its own coverage
  limit (10-minute lookback, else falls back to "proposed").
  `missing_data_strategy/missing_data_strategy_summary.csv`, column
  `rate_hiding_critical_complete_record_reference`.
- For PM/CO2 (aerosol/ventilation) masking, all strategies perform far
  better (class agreement >=0.977 in most cases) -- the CRITICAL-hiding
  problem is specific to microclimate.
- 10,000-rep block-by-day bootstrap CIs (seed 20260815, no degradation
  below target): `missing_data_bootstrap_intervals.csv`.
- Confusion matrices: `missing_data_confusion_matrices.csv`.

## 6. Pollution and microclimate decomposition

Over 15,242 OK-completeness timestamps:

- Current integrated index: Critical 44.9% of the time.
- Pollution-oriented index (A,V only, via the real engine): Critical only
  3.4% of the time.
- Microclimate component (M) alone: Critical 44.1% of the time.
- Of 6,841 timestamps where the current index is Critical, only 521 (7.6%)
  remain Critical when only pollution (A,V) is considered.
- **Association finding (not causal)**: microclimate, not aerosol/
  ventilation pollution, is associated with the large majority of Critical
  classifications in this deployment.
- `co_dominant_components` was non-empty for 100% of OK-completeness
  timestamps (tie_rate=1.0) -- flagged for author review; verify this
  matches the manuscript's intended tie definition before citing.
- `pollution_microclimate/pollution_microclimate_summary.json`,
  `critical_driver_summary.csv`, `_by_day.csv`, `_by_hour.csv`.

## 7. Second fuzzy level equivalence results

- Rule level: all 64 index-level rules proven (exhaustively, all 64
  checked) to assign the worst-of-antecedents class.
- Real timestamps (n=15,242): 100% class agreement between PROPOSED_HFIS
  and FUZZY_COMPONENT_MAX, despite nonzero numerical differences at 2,209
  timestamps (mean |diff|=0.021, p99=0.266).
- Synthetic grid, 41 points/axis (68,921 points): **95.95% class
  agreement** (2,791 disagreements) -- corrects an earlier 11-point-grid
  finding of spuriously perfect agreement (too sparse to catch the
  disagreement region). **The two methods are not generally class-
  equivalent; they happen to agree on every real timestamp observed in
  this deployment.** Do not claim general equivalence from the real-data
  result alone.
- `second_level_equivalence/second_level_equivalence_summary.json`.

## 8. Boundary and stability results

- PROPOSED_HFIS vs FUZZY_COMPONENT_MAX: 0 discordant pairs across 900
  paired stability trials (exact McNemar p=1.0).
- PROPOSED_HFIS vs WEIGHTED_MEAN: highly significant difference (McNemar
  p=3.4e-40); WEIGHTED_MEAN's class_change_rate is 0.211 higher (95% CI
  [0.127, 0.299]) under the same input perturbations.
- `boundary_stability_paired/stability_paired_sign_test.csv`,
  `stability_paired_bootstrap_ci.csv`, `stability_class_flapping_summary.csv`.

## 9. Data quality reason analysis

- Status: OK=89.7%, PARTIAL=5.9%, FAILED=4.4% (16,992 total timestamps).
- `temperature` has the highest SUSPECT rate (27.0%) and highest
  `stuck_value` rate (13.8%) of any channel; `co2`/`humidity` have the
  highest `single_spike` rates (7.1%/7.7%). No hardware cause is inferred
  from these codes.
- 223 continuous PARTIAL/FAILED intervals; longest 77,100s (~21.4h).
- `data_quality_reasons/*.csv`.

## 10. Runtime results

- Inference-only (no I/O), 2,000 real timestamps, 1 warmup + 5 reps:
  PROPOSED_HFIS 1.37ms/timestamp mean; FUZZY_COMPONENT_MAX 0.58ms/timestamp
  mean. Both negligible relative to the 5-minute recompute cadence.
- This is narrower than (and should not be conflated with) the README's
  previously-cited ~5s/timestamp full-pipeline (I/O+validation+aggregation
  included) figure.
- `runtime_profiling/runtime_profiling_report.json`.

## 11. Negative / inconclusive findings (collected)

- Missing-data "proposed" strategy hides most CRITICAL results when M is
  masked -- a real weakness in the manuscript's own missing-data handling,
  not a strength.
- Hampel sweep's seeded_group validation precision/recall is degenerate
  (0/NaN) due to a too-small validation subset (2 scenarios) -- inconclusive
  by data-size limitation, not a proof of anything about h=5.0.
- The Hampel multiplier sweep does not establish an optimum -- the
  objective was still rising at the edge of the tested range.
- 100% `co_dominant_components` tie rate is unexplained and flagged for
  author review, not interpreted further here.

## 12. Limitations

- Multi-component grid run at 41 points/axis (68,921 combinations), not
  the requested 101 (1,030,301) -- a first 101-point attempt exceeded a
  practical time budget on this Raspberry Pi. The 41-point grid already
  materially changed the conclusion versus an 11-point attempt, so it is
  informative, not a token substitute -- but the exact 95.95% figure could
  still shift somewhat with a full 101-point run.
- Missing-data strategy's per-instance masked-recompute experiment used a
  documented, seeded 1,200-instance subsample (from 15,242 available)
  rather than the full set, after an unsampled attempt exceeded 10 minutes
  without finishing.
- `research_results/final/` was intentionally left untouched by this run
  (see `run_status.md`) pending the author's explicit decision to publish
  these expanded-dataset results as the new manuscript-facing package.

See `manuscript_update_notes.md` for exact old/new values to change in the
manuscript text, and `run_manifest.json` for full reproducibility metadata
and per-artifact SHA256 hashes.
