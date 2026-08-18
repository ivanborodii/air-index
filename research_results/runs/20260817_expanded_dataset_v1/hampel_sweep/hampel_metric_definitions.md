# Hampel threshold sweep -- metric definitions

Window size held fixed at 11 (production `HAMPEL_SELECTION_WINDOW_SIZE`).
Multiplier `h` swept over [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0].

- **single_spike_precision / recall**: row-level precision/recall of the
  `single_spike` reason code against the fault-injection benchmark's known
  labels (`iaq_hfis.evaluation.fault_injection.score_predictions`).
- **single_spike_f1** (`F1_spike`): harmonic mean of the two above.
- **single_spike_fpr** (`FPR_spike`): false-positive rate of `single_spike`
  (real, non-fault samples incorrectly flagged as a spike).
- **genuine_event_preservation_rate** (`P_event`): `1 - false_rejection_rate`
  for samples labeled `genuine_event` (real, non-fault environmental
  changes) -- the fraction NOT discarded.
- **s_old** (production objective, unchanged):
  `S_old = (R_spike + P_event + (1 - FPR_spike)) / 3`
  (`iaq_hfis.evaluation.fault_injection._objective`).
- **s_new** (this task's requested alternative):
  `S_new = (F1_spike + P_event) / 2`

## Split methodologies

- **structural**: production benchmark's built-in split: disjoint scenario_ids, different deterministic scale/phase per variant (build_channel_scenarios).
- **seeded_group**: robustness cross-check: 4 scenario families pooled from both variants, shuffled with random.Random(seed=20260815), first 3 families -> calibration (['co2_persistent_real_change', 'co2_single_spike', 'co2_single_spike_alt']), remaining 1 -> validation (['co2_genuine_rapid_event']). No family appears in both groups.

Selection procedure for each (split_method, objective) pair mirrors the
production `select_hampel_multiplier` tie-break order: highest objective,
then highest `single_spike_recall`, then highest `genuine_event_preservation_rate`,
then lowest `single_spike_fpr`, then smallest `h`. Always computed from the
**calibration** rows of that split method only; validation rows are reported
for context but never used in selection.
