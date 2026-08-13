# Fault-injection benchmark: audit and validation notes

Scope: an audit of `src/iaq_hfis/evaluation/fault_injection.py` against the
specific correctness concerns a synthetic, labeled detection benchmark is
vulnerable to (double-counting, pre-existing anomalies, warm-up periods,
temporal-tolerance choices, multi-detection, overlapping windows), plus a
record of the concrete bugs found and fixed while rebuilding it, and the
scope deliberately left out.

## 1. Structural audit

- **Double-counting.** Row-level metrics (`score_predictions`) count every
  affected *sample*, so a fault spanning N samples (e.g. an 8-sample
  `stuck_value` run) legitimately contributes N true positives at the row
  level -- this is correct and disclosed as "row-level," never mislabeled
  as "N distinct faults." The genuinely double-counting-prone case -- a
  contiguous run of flagged samples being read as N separate *events* --
  is what `match_events`/`score_events` (event-level metrics) fix:
  contiguous predicted indices are grouped into one predicted interval
  before matching (`_group_into_intervals`), so an 8-sample stuck run is
  one predicted event, matched to the one true event.
- **Pre-existing anomalies / warm-up periods.** Every scenario is a fresh,
  independent, isolated synthetic series (`_START` + a fixed offset per
  scenario) with a single injected fault at `n // 2`; nothing is
  concatenated across scenarios, and there is no "burn-in" period the
  detector must first learn from -- the baseline oscillation before the
  fault is itself the only history available, by construction. There is
  no possibility of one scenario's fault leaking into another's warm-up.
- **Overlapping windows.** Each scenario_id is scored independently
  (`run_scenario` builds a self-contained `raw_df`/`matched_slots` per
  scenario); nothing shares a time range with anything else, so there is
  no window-overlap risk between scenarios.
- **Multi-detection / temporal tolerance.** `match_events` takes an
  explicit, configurable `temporal_tolerance_samples` parameter (default
  1); a predicted detection interval and a true event match if they
  overlap or are within that many samples of each other, and matching is
  one-to-one (a predicted interval used for one true event cannot also
  match another). This is the piece that did not exist before this
  rebuild -- previously only row-level TP/FP/FN existed.

## 2. Confirmed bugs found and fixed

1. **PM order-violation scenario's true label was unscoreable.** The real
   quality layer has no distinct `PM_ORDER_VIOLATION` reason code (see
   `iaq_hfis.constants.ReasonCode`) -- `check_pm_ordering()` correctly
   reuses `out_of_range`. The scenario's true label was
   `"pm_order_violation"`, a string that never appears in `REASON_CODES`,
   so it could never be scored as a true positive against anything, and
   -- because the detector correctly flags `out_of_range` at that sample
   -- it silently counted as an `out_of_range` false positive every run.
   Fixed: the true label is now `"out_of_range"`, matching what the system
   actually and correctly reports.
2. **Temperature/humidity genuine-event scenarios could never be confirmed
   usable.** `confirm_dual_channel_event()` requires corroboration from
   either a duplicate sensor reading or an outdoor trend signal; the
   original single-channel scenario builder supplied neither for these two
   (dual-sensor) channels, so `corroborated` was always `False` and a
   genuine sustained event could never reach `usable=True`, regardless of
   how correct the underlying spike/persistence logic was. This was found
   empirically: extending the benchmark to temperature/humidity initially
   produced `false_rejection_rate_for_genuine_events == 0.667` where CO2
   alone always showed `0.0`. Fixed by adding a synthetic secondary-sensor
   reading that exactly tracks the primary (`build_channel_scenarios(...,
   dual_channel=True)`) -- confirmed by rerunning: rate returned to `0.0`
   for both channels, both dataset splits.

## 3. Calibration/validation split

Every scenario belongs to exactly one of two disjoint splits
(`dataset_split_of`, derived from the scenario_id suffix): **calibration**
(scale=1.0, phase=0) and **validation** (scale=1.15, phase=3) -- distinct
scenario_ids AND numerically distinct magnitudes/timing, so nothing overlaps
between the sets. The Hampel grid search (`run_hampel_calibration`) is
tuned only against calibration; `run_summary.json`'s headline
`fault_injection` numbers (`headline_dataset_split: "validation"`,
`metrics_by_reason_code`) are always the validation split -- the split no
explicitly-provisional parameter was tuned against.

## 4. Channel coverage and its scope

Benchmarked channels: CO2, temperature, humidity, PM10, PM2.5 (order-check).
Fault types per channel: `single_spike` (2 magnitudes), `out_of_range`,
`stuck_value`, `data_loss`, `gradual_drift`, plus genuine-event preservation
checks (CO2/temperature/humidity only). 60 total scenarios (30 per split).

**Deliberately out of scope, disclosed rather than silently omitted:**
"multiple magnitudes/durations where meaningful" is implemented as ONE
additional spike magnitude per channel (`spike_magnitude_alt`), not an
exhaustive sweep across all fault types x multiple magnitudes x multiple
durations -- that combinatorial expansion was judged not to fit this
validation pass's scope. `include_genuine_events` is disabled for PM10 (the
Hampel-calibration genuine-event target is CO2-specific per the
manuscript's original concern; PM10 genuine-event preservation is not
currently benchmarked). These are scope limitations of the *benchmark*, not
claims about the detector's real-world behavior outside what was tested.

## 5. Weak results, disclosed not hidden

**Resolved 2026-08-13 (stuck_value):** stuck_value's row-level precision was
previously ≈0.24 on the validation split. Root cause, found by auditing the
benchmark itself (not the detector): the synthetic `genuine_rapid_event` and
`persistent_real_change` scenarios modeled a sustained real environmental
change as a **perfectly constant plateau** for many consecutive samples --
logically indistinguishable from a deliberately injected stuck sensor,
since `detect_stuck_value` is (correctly) an exact-equality run-length
check. Fixed by superimposing a small, deterministic ripple (30% of the
channel's own normal ambient-variation amplitude, phase-shifted from the
baseline oscillation) on genuine-event plateaus, and by making the
temperature/humidity dual-channel secondary signal a corroborating-but-
independently-varying signal rather than an exact copy of the primary (see
`iaq_hfis.evaluation.fault_injection.build_channel_scenarios`'s
`_ripple`/`secondary_for`). Deliberately injected stuck_value scenarios
remain exactly constant, unchanged. Result: stuck_value row-level precision
is now 1.0 on both splits (verified 2026-08-13) -- this was a benchmark
construction defect, not a detector defect; the label was never changed to
manufacture the improvement.

single_spike still has low precision (validation ≈0.10) -- this reason code
fires on many samples across *other* scenarios that were not actually
single_spike faults (visible in `fault_detection_confusion_matrix.csv`'s
off-diagonal cells; the Hampel calibration in section 6 below is CO2-scoped
per the manuscript's original concern, so other channels' single_spike
behavior at `mad_multiplier=3.0` was not independently tuned).
`run_narrative.md`/`article_results_summary.md` surface any reason code
with row-level F1 < 0.5 under "Disclosed limitation" rather than only
reporting the flattering aggregate. Exact current numbers (both splits, all
five reason codes, plus the section-9 primary-vs-final-exclusion split) are
in `fault_detection_metrics.csv` / `fault_final_exclusion_metrics.csv` for
each run -- see `research_results/hampel_causal_revision_report.md` for the
before/after comparison from this revision.

**gradual_drift causality (2026-08-13):** the detector previously
retroactively marked a run's earlier points as `gradual_drift` once a LATER
point confirmed the run had reached `gradual_drift_min_consecutive_steps` --
changing an earlier measurement's status based on data that didn't exist
yet at that measurement's own time, which is not causal. Fixed in
`iaq_hfis.quality.reasons.detect_gradual_drift`: a point is now flagged only
once IT is the latest point of a qualifying run. This necessarily lowers
row-level recall for short drift runs (a run cannot be flagged before it has
actually accumulated the minimum run length) while preserving event-level
recall (the event is still detected, just with an honest, nonzero minimum
detection delay instead of an artifactual zero-delay retroactive flag) --
both row-level and event-level metrics, plus mean detection delay, are
reported separately and honestly, not collapsed into one number.
