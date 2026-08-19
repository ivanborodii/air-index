# Limitations of this revision (2026-08-19)

Honest accounting of what this revision does and does not establish, per the
task's requirement to report negative/partial results and scope gaps
explicitly rather than silently.

## Deployment and generalizability

- Single-site, single-room (with per-season profile) deployment. No
  replication across rooms, buildings, or climates.
- No occupancy, ventilation, window-opening, or cooking log exists for this
  deployment. Every "associated input" / "dominant component" finding is a
  descriptive association over real data, never a causal claim, and CO2 is
  never interpreted as an occupancy proxy.
- Outdoor weather context is used only at hourly/daily aggregation to
  describe broad seasonal association (see `warm_season_analysis.md`), never
  to confirm or reject a sub-minute indoor spike.

## Missing-data strategy experiment (Experiment A) scope

- Masking is single-timestamp only. The task's contiguous 5/10/15/30-minute
  missing-interval masking (section 6.2) is **not implemented** in this
  revision -- documented gap, not a fabricated pass. See
  `missing_data_strategy/missing_data_strategy_metadata.json`'s
  `scope_limitations`.
- The split is a single chronological calibration/validation (70/30)
  division, not the task's three-way calibration/validation/held-out-test
  (60/20/20, day-blocked) split. **There is no held-out test evaluation for
  the missing-data strategy comparison in this revision**, so the section
  6.6 promotion decision (whether to adopt the hybrid LOCF candidate as
  production) cannot be made from this run alone. The causal-LOCF
  correctness fix (task 5.1) is real and tested; the full promotion
  evaluation is future work.
- The masked-recompute experiment is evaluated on a deterministic,
  seeded subsample (up to ~1,200 instances) rather than every eligible
  timestamp, because an unsampled attempt exceeded a 10-minute wall-clock
  budget on this Raspberry Pi. Documented in the same metadata file.

## Second-level equivalence (Experiment C)

- The full 101 grid_points_per_axis (101^3 = 1,030,301 combinations) run was
  executed for this revision (see `second_level_equivalence/` and
  `run_manifest.json` for the persisted row count, verified equal to
  101**3). The previous run's manifest claim of 101 while only 41^3 rows
  were actually persisted was a real defect (task section 5.5), now fixed
  procedurally: the manifest command and the persisted grid size are
  cross-checked (`iaq_hfis.research_helpers.verify_grid_point_count`).

## Real chronological class flapping (Experiment D / section 5.4)

- This is a genuinely new analysis in this revision (the prior "flapping"
  artifact used an arbitrary perturbation-trial order and has been retired
  as a temporal-flapping claim; it remains valid only as a
  perturbation-sensitivity statistic, which is what
  `boundary_stability_paired_analysis.py` now reports it as).
- The 10-minute maximum-gap consecutiveness rule is a single fixed choice,
  not swept or validated against an independent notion of "true" continuity.

## Hampel / MAD multiplier (Experiment E)

- This revision reused the existing `hampel_threshold_sweep.py`, which
  already implements the S_new = (F1_spike + P_event)/2 selection objective,
  a calibration/validation split, and an explicit no-auto-promotion policy.
  It was not modified for this revision (no defect was found in it), only
  rerun into the new run directory.

## Statistical scope

- Multiple-comparison correction: applied per-experiment (documented in each
  experiment's own report) rather than as one single global correction
  across all ~8 experiments' hypothesis tests combined.
- Block bootstrap target is 10,000 repetitions; scripts fall back to a lower
  count with the actual count and reason recorded when a wall-clock budget
  is exceeded (never silently).

## Production impact

- No production parameter (Hampel h, membership widths, LOCF lookback) was
  changed by this revision. Every fix in section 5 is a correction to
  **research/evaluation code**, not to `src/iaq_hfis/pipeline.py`,
  `fuzzy_engine.py`, `membership.py`, `rules.py`, or `quality/*` -- the
  production index computation is byte-identical to the prior run for the
  same input data.
