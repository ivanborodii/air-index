# Article results summary -- peer-review revision (2026-08-19)

Run: `20260818_peer_review_revision_v2`. Data interval: 2026-06-18T00:00:00Z
(inclusive) to 2026-08-16T00:00:00Z (exclusive), i.e. through 2026-08-15.
Pipeline run reused unchanged (`7f04698725dd4f35a432ba4a0de2934f`);
evaluation run `74deb744a581423b99e4cb7e68be33ce` (full 101^3 grid).

## Dataset

- 169,331 raw rows, 169,331 unique timestamps, 0 duplicates, 0 ordering
  violations, 6 gaps > 5 minutes -- independently reverified (`snapshot/`).
- 16,992 computed index timestamps: OK 15,242 (89.70%), PARTIAL 1,004
  (5.91%), FAILED 746 (4.39%) -- independently reverified, matches the
  prior run's reported figures.

## Five defects fixed (task section 5), each with new unit tests

1. **Causal LOCF** was position-based, not time-based -- could cross a real
   data gap. Fixed; 9 new tests.
2. **Dominance-tie detection** flagged nearly every row as a tie (bug: any
   non-empty co-dominant list, which always includes the dominant component
   itself, counted as a tie). Fixed; 5 new tests. Corrected tie rate: 18.0%.
3. **Direct-input attribution** used percentile rank, unsound for two-sided
   channels (temperature, humidity). Replaced with membership-class-based
   ranking. Fixed; 7 new tests.
4. **Class flapping** was computed from an arbitrary perturbation-trial
   order, never a real temporal metric. Replaced with a genuine
   chronological analysis (10-minute consecutiveness rule). 9 new tests.
5. **Grid manifest** claimed 101 points/axis while only 41^3 was actually
   persisted. Fixed procedurally: the full 101^3 = 1,030,301-point grid was
   executed and cross-checked against the manifest claim. 3 new tests.

Total: 34 new unit tests in `tests/unit/test_research_helpers.py`, all
passing, alongside the full pre-existing suite.

## Experiment A: missing-data strategy (highest priority per reviewer)

Under direct-input masking on the validation split (see
`missing_data_strategy/`):

- Temperature masked: production strategy hides 89.1% of true Critical
  cases; corrected causal-LOCF hybrid hides 1.8%.
- Humidity masked: production hides 94.7% (calibration) / 89.1%
  (validation); hybrid LOCF hides 0% / 0.33%.
- Component-level masking (whole A/V/M unavailable) shows smaller
  differences since the production "exclude" strategy is already close to
  the hybrid's fallback behavior there.
- Validation-selected LOCF lookback (predeclared rule, mechanically
  applied): **5 minutes**.
- **Not promoted to production** -- no held-out test split exists in this
  revision (see `limitations.md`).

## Experiment B: pollution vs. microclimate decomposition

- Corrected tie rate: 18.0% (previously computed as effectively 100% due to
  a code defect).
- Pollution-oriented (A, V only) index Critical share: **3.4%** vs. **44.9%**
  for the current integrated index.
- Only **7.6%** of current-Critical timestamps remain Critical when
  microclimate is excluded.
- Corrected driver attribution: temperature is the associated adverse input
  for **72.6%** of Critical timestamps (membership-based, not percentile
  rank). This is a strong, corrected confirmation of the reviewer's
  microclimate-domination hypothesis. Descriptive association, not causal.

## Experiment C: second-level equivalence

- Rule-level worst-of property: proven exhaustively, 64/64 rules.
- Full 101^3 = 1,030,301-point grid: class agreement **98.34%**.
- **100% of the 17,101 disagreements occur exactly when max(A,V,M) == 75**
  (the Degraded/Critical class boundary) -- the reviewer's own hypothesis,
  now precisely confirmed at full grid resolution.
- Independent 250,000-point random-continuous check: 99.9764% agreement
  (not exactly 100% -- a small residual discretization effect near, not at,
  boundaries).
- Attainable index range: [12.44, 87.56]; neither 0 nor 100 attained.
- Real-timestamp class agreement (HFIS vs. FUZZY_COMPONENT_MAX): 100.0%.
- See `second_level_equivalence/second_level_formal_analysis.md` for the
  full mathematical treatment.

## Experiment D: stability and real-time flapping

- Paired 900-trial (30 samples x 30 trials) perturbation experiment:
  PROPOSED_HFIS vs. WEIGHTED_MEAN, McNemar p=3.44e-40, bootstrap CI on rate
  difference [0.127, 0.299] (excludes 0, significant). PROPOSED_HFIS vs.
  CRISP_CLASS_MAX: p=0.77 (not significant). PROPOSED_HFIS vs.
  FUZZY_COMPONENT_MAX: identical (p=1.0).
- Real chronological flapping (new): on OK-completeness data, the three
  fuzzy-logic methods share an identical transition rate (5.85/day);
  WEIGHTED_MEAN's lower rate (3.93/day) is explained by its 97.6%
  Critical-masking rate, not genuine stability.

## Experiment E: Hampel / MAD multiplier

- No code defect found; existing S_new = (F1_spike + P_event)/2 objective
  and calibration/validation split already implemented.
- Sweep selects h=5.0 on calibration (both S_old and S_new objectives,
  structural and seeded-group splits agree); **production h=3.0 retained
  unchanged** per the explicit no-auto-promotion policy.
- Calibration precision at h=3.0 is low (~0.44); the ~0.024 figure the
  reviewer referenced is confirmed to be a precision (not recall) value.

## Experiment F: membership function audit

- PM10 Degraded is triangular (b==c) at the production effective width
  (25 ug/m3).
- PM10 width sensitivity (10/15/20/25 ug/m3): class distribution over real
  PM10 readings is **identical across all four tested widths** -- a
  negative/null finding, reported as such, not manufactured.

## Experiment G: data quality reasons

- Completeness and reason-code breakdown independently reverified; no
  hardware-fault/restart cause asserted without an operational log (none
  exists for this deployment).

## Experiment H: runtime profiling

- PROPOSED_HFIS: ~1.96 ms/timestamp (full 2-level inference, mean of 5
  timed repetitions over 2,000 timestamps).
- FUZZY_COMPONENT_MAX baseline: ~0.53 ms/timestamp.

## Production impact

**No production parameter was changed by this revision.** Every fix is to
research/evaluation code only (`scripts/research/*.py`,
`src/iaq_hfis/research_helpers.py`) -- `pipeline.py`, `fuzzy_engine.py`,
`membership.py`, `rules.py`, and `quality/*` are untouched, so the
production index computation is unchanged for identical input data.

## See also

- `manuscript_update_notes.md` -- per-claim old/new text with suggested
  Ukrainian and English paragraphs.
- `reviewer_response_evidence_matrix.md` -- full criticism-to-evidence
  mapping.
- `claims_traceability.csv` -- every number above traced to its source file
  and field.
- `limitations.md` -- honest scope gaps.
