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

Single_spike and stuck_value both reach **recall = 1.0** (every injected
occurrence is detected, both row- and event-level, both splits) but have
materially lower **precision** than the other three fault types (row-level
precision on the validation split: single_spike ≈0.02, stuck_value ≈0.24,
vs. ≥0.49 for gradual_drift/data_loss/out_of_range) -- both fall below F1
0.5. This means these two reason codes fire on many samples across *other*
scenarios that were not actually single_spike/stuck_value faults (a real,
disclosed false-positive rate, visible in `fault_detection_confusion_matrix.csv`'s
off-diagonal cells). `run_narrative.md`/`article_results_summary.md`
surface this automatically (any reason code with row-level F1 < 0.5 is
listed under "Disclosed limitation") rather than only reporting the
flattering aggregate.
