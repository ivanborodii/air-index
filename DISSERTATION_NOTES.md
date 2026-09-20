# Dissertation Notes — CITI-2026 Mapping

Maps the CITI-2026 sensor-fault-detection project (see `CITI2026_RESULTS.md` for the
full results) onto dissertation subsections 2.2–2.4. Each subsection cites the exact
scripts/docs/data that support it, so claims here can be traced back to a reproducible
artefact rather than restated from memory.

## 2.2 — Node model with internal channel redundancy

The physical node (Raspberry Pi 5, kitchen deployment) is modelled as carrying two
kinds of channel:

- **Redundant pairs**: temperature and relative humidity, each measured independently
  by two dissimilar modules (SCD41 photoacoustic CO2/T/RH sensor; BME688 gas/T/RH/
  pressure sensor). Dissimilar measurement principles are the point — a shared-mode
  fault (e.g. a firmware bug affecting both identically) is far less likely than a
  fault specific to one module's sensing technology.
- **Independent channels**: CO2, PM2.5, PM10, gas-sensor resistance, barometric
  pressure — used as a source of ground truth *independent of* the redundant pair, so
  that event labels and cross-channel concordance never share a causal path with the
  channels being fault-tested (see 2.3 and 2.4 below).

Model characterisation (`docs/citi2026_phase1_pair_characterisation.md`,
`scripts/research/citi2026_phase1_pair_characterisation.py`):

- Systematic bias between modules is **small, stable, and physically explicable**
  (self-heating from BME688's active gas-sensing heater — consistent direction across
  both temperature, +warmer, and humidity, −drier), not itself a fault signature. This
  motivates the node model's key design point: a fault detector must characterise and
  subtract the *expected* baseline disagreement before it can usefully flag deviations
  from it.
- Response lag between the two modules (~1 sample/30s for temperature, ~2 samples/60s
  for humidity) reflects thermal/hygroscopic mass differences between the sensor
  packages, not a fault — any redundancy-comparison feature must be lag-aware or it
  will mistake normal transient lag for disagreement.
- `gas_resistance_ohm` (BME688's own heater-cycle indicator) turned out to have only
  11.2% coverage in this deployment (`docs/citi2026_phase0_data_audit.md`) — a
  concrete illustration that "redundancy" in the node model is only as good as the
  weakest channel's actual field reliability, not its datasheet spec. Documented as a
  limitation rather than assumed away.

## 2.3 — Sensor-data state model

The state model built here is a three-tier judgement, kept strictly separated to avoid
circular reasoning:

1. **Hard technical-range validity** (`docs/citi2026_phase0_resolution.md`, Decision 3):
   a boolean `hardcheck_fail_<channel>` flag per channel, reused verbatim from
   manufacturer datasheets (not re-derived). 2.9% of all rows fail at least one
   channel's technical range, dominated by PM mass/number channels whose SPS30 range is
   genuinely, non-rarely exceeded. Flags are additive metadata — **no row is ever
   deleted, nulled, or modified** — matching the project's scientific-integrity
   constraint that only copies are transformed, never the primary record.
2. **Real-event state** (`docs/citi2026_phase3_weak_labels.md`,
   `scripts/research/citi2026_phase3_weak_labels.py`): a weak label derived *only* from
   the independent channels (CO2, PM2.5, PM10, pressure), used as this dissertation's
   operational definition of "the sensor data reflects a real change in the physical
   environment, not a fault." 6.52% of samples fall inside a labelled event. This is
   the ground truth against which false-event rate (§2.4/Phase 7) is measured — by
   construction, it cannot correlate with the temperature/humidity fault labels except
   through genuine physical co-occurrence, since it never reads those channels.
3. **Injected-fault state** (`docs/citi2026_phase4_fault_injection.md`,
   `scripts/research/citi2026_phase4_fault_injection.py`): a synthetic ground-truth
   mask covering 1,528 controlled fault instances of 4 canonical types (gradual shift,
   stuck value, spike, noise burst), amplitude-graded in multiples of each channel's
   own first-difference MAD (computed on train days only, so the injection scale itself
   never leaks test information). This state model explicitly separates *plausible
   fault shapes* (the four types, each with disclosed, fixed shape parameters) from
   *severity* (the MAD-multiple amplitude grid), which is the axis Phase 7's
   sensitivity analysis is built around.

The three states compose into the four-way row classification the dissertation's data
model needs: (valid & fault-free), (valid & real-event), (valid & injected-fault),
(hard-range-invalid) — with the last state excluded upstream of the other three rather
than conflated with "fault," since an out-of-range reading and an in-range-but-wrong
reading are different failure modes with different physical causes.

## 2.4 — Micro-batch feature model

Causal (past-only, per-day, never bridging a day boundary) trailing windows of 5, 10,
and 20 samples (`docs/citi2026_phase5_features.md`,
`scripts/research/citi2026_phase5_features.py`) form the micro-batch unit this
dissertation's feature model operates on. Four feature-set variants isolate exactly
which information source drives detection performance:

- (a) single-channel rolling statistics only (12 features: 6 stats × 2 channels)
- (b) (a) + cross-channel (redundant-pair) comparison features (18)
- (c) (b) + absolute-humidity concordance features, derived via the Magnus/Sonntag(1990)
  saturation-vapour-pressure formula per WMO-No. 8 (24) — this is the feature-model
  novelty most directly tied to the node model's redundant-pair structure (2.2)
- (d) cross-channel features alone, with single-channel information withheld (6) — a
  deliberate ablation to isolate the redundancy signal's standalone value

**Key finding for the feature model, reported plainly**: on this deployment's data, (a)
ties for or wins outright the best macro-F1 on both pairs (Phase 7,
`docs/citi2026_phase7_metrics.md`); (b)/(c) help a weak model (logistic regression) far
more than they help the strongest models (decision tree, random forest); and (d) is
consistently the worst-performing tree-model feature set. This is a substantive result
for subsection 2.4: it says the micro-batch feature model's *window-based single-channel
statistics* already carry most of the exploitable signal for detecting these four
canonical fault types in this deployment, and the cross-channel/redundancy features this
project was specifically built to test do not demonstrate a broad, consistent advantage
over them — a negative result for the feature model's central hypothesis that should be
stated in the dissertation as such, not reframed as a qualified win. The one place the
redundancy signal is unambiguously valuable is false-event rate (learned models overall
beat both rule-based single/pairwise baselines there), which is a genuine, positive
contribution of the redundant-pair design even though it does not manifest as higher raw
recall.

Window-size sensitivity is itself a feature-model finding: shorter causal windows (5
samples) consistently outperform longer ones (10, 20) across every pair/method
combination — the micro-batch feature model should prefer short windows for these fault
types rather than assuming longer context always helps.

## Cross-cutting notes for the write-up

- All numeric claims above are traceable to a specific script + CSV/JSON under
  `research_results/citi2026/phase{0..7}/` — see `CITI2026_RESULTS.md`'s
  reproducibility appendix for exact commands, seeds, hardware, and software versions.
- Whole-day train/test split (Phase 4, seed 42) is applied **before** any fault
  injection, per the brief's leakage-prevention rule — cited here because it is a
  data-model design choice (2.3), not just an ML-training convenience.
- Bootstrap CIs in Phase 7 use two deliberately different resampling units (by fault
  instance for recall metrics; by whole test day for macro-F1/balanced accuracy) — worth
  a methods-section paragraph explaining why a single resampling unit would misrepresent
  at least one of the two metric families.
