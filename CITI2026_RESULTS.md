# CITI-2026 Results

*Distinguishing Sensor Faults from Indoor Climate Changes Using Redundant Measurements*
I. Borodii, supervisor H. Osukhivska, TNTU.

This document reports the complete, honest results of the phased analysis described in
the project brief (Phases 0–7). It reports negative and mixed findings alongside
positive ones, as the brief requires.

Full per-phase detail, all numeric tables, and every generated CSV/JSON live under
`docs/citi2026_phase{0..7}_*.md` and `research_results/citi2026/phase{0..7}/`. This
document synthesizes them; it does not replace them.

---

## 1. Data (Phase 0)

- Node: Raspberry Pi 5 Model B Rev 1.0, kitchen of a residential dwelling. Two dissimilar
  temperature/RH modules (SCD41, BME688) plus independent channels (CO2, PM2.5, PM10,
  gas-sensor resistance, barometric pressure). Cadence 30 s.
- Frozen, immutability-verified primary dataset: 304,110 rows, 2026-04-16 → 2026-09-20.
  0 duplicate timestamps.
- **Analysis window** (author-resolved, see `docs/citi2026_phase0_resolution.md`):
  **2026-06-18 → 2026-09-20 (Kyiv), 94 days, 263,873 rows**, 87/94 fully complete
  (≥99% of expected samples). Pre-gap era (Apr 16–28) excluded from analysis, kept
  (not deleted) for any later sensitivity check.
- 2026-09-13/09-14 (a documented venv-corruption device outage, 18.6%/1.2% coverage) is
  excluded from both the analysis window's completeness accounting and Phase 4's
  train/test day-split — a real device-down period, not imputed or hidden.
- Hard datasheet-range check (reused verbatim from `config/sensor_specs.yaml`, not
  re-derived): 8,810/304,110 rows (2.9%) fail ≥1 channel's technical range, dominated by
  the SPS30 PM channels (~7,600–8,700 rows each — genuinely out-of-range on a meaningful
  fraction of rows, not a rare artefact). Flagged, never deleted or nulled; later phases
  decide how to use the flag. Whether these PM excursions are real cooking-smoke events
  or sensor faults is **left explicitly open** — Phase 3's weak labels do capture some of
  them as real events (§3 below), but this is not treated as a settled question.
- `gas_resistance_ohm` dropped from the independent-channel set (11.2% coverage — mostly
  missing, unusable) used for weak labels/concordance in Phase 3; CO2, PM2.5, PM10, and
  pressure remain.

## 2. Redundant-pair characterisation (Phase 1)

Sign convention: diff = SCD41 − BME688.

| pair | n | bias mean | MAD of diff | Pearson r | day-to-day bias std | drift (p) | median lag |
|---|---:|---:|---:|---:|---:|---:|---:|
| Temperature (°C) | 247,975 | −1.160 | 0.094 | 0.998 | 0.122 | p=2.1e-7, +0.0023/day | −1 sample (−30 s) |
| Humidity (pp) | 247,984 | +6.621 | 0.693 | 0.979 | 0.904 | p=3.1e-15, −0.0240/day | −2 samples (−60 s) |

Both pairs show a small but statistically significant drift in daily-mean bias over the
13-week deployment (temperature ≈ +0.21°C cumulative, humidity ≈ −2.2pp cumulative) —
real, detectable, and worth re-checking as the deployment extends, but not large enough
to explain the fault-detection results below.

BME688 consistently reads warmer **and** drier than SCD41 — both signs point the same
physical direction, consistent with BME688's active gas-sensing heater self-heating its
co-located temperature/RH element (standard finding in the low-cost-sensor literature).
This cannot be tested directly in this deployment because `gas_resistance_ohm`
(heater-cycle correlation) is unusable (§1) — disclosed as a limitation, not glossed
over. The stable day-to-day bias is the expected baseline a fault detector must not
flag; it should watch for the offset **stepping to a new level** instead.

## 3. Absolute humidity (Phase 2)

Magnus/Sonntag(1990) saturation-vapour-pressure formula per WMO-No. 8. Mixed result
comparing RH-based vs. absolute-humidity(AH)-based concordance between the two modules:

| basis | bias as % of typical | MAD as % of typical | Pearson r |
|---|---:|---:|---:|
| Relative humidity | 13.98% | **1.46%** | 0.979 |
| Absolute humidity | **7.70%** | 1.63% | **0.987** |

AH wins on 2 of 3 axes (lower relative bias, higher correlation) but has slightly
*worse* relative dispersion — AH is a defensible alternative concordance basis, not an
unambiguous improvement. Its actual value is tested downstream in feature set (c); see
§6, where the picture stays mixed.

## 4. Weak event labels (Phase 3)

Built **only** from CO2, PM2.5, PM10, pressure (never temperature/humidity — the
channels being fault-tested) to avoid circular reasoning. 6.52% of samples fall inside a
labelled event; 1,085 distinct events, median duration 4.5 min. Threshold (3.0 MAD) and
persistence (4 samples) are literature-typical, **not calibrated against any ground
truth** — disclosed, not hidden.

## 5. Fault injection (Phase 4)

Seed 42 throughout. Day split: 65 train / 27 test / 2 excluded (the venv-outage days),
stratified by calendar month. Amplitude grid computed as multiples of each channel's
first-difference MAD, **on train days only** (no test leakage into the injection scale).

1,528 fault instances injected across 4 types (gradual shift, stuck value, spike, noise
burst) × 4 channels (both modules' T and RH). 18.1% of injected faults temporally
overlap a real Phase-3 event — this is the expected base rate (events cover ~6.5% of
samples) from uniform random placement, not a deliberately designed stress test, but it
is enough (277 instances) for a meaningful false-event-rate metric.

## 6. Feature sets and models (Phases 5–6)

Causal (past-only) windows of 5/10/20 samples. Four feature sets: (a) single-channel
only (12 features), (b) + cross-channel (18), (c) + absolute-humidity concordance (24),
(d) cross-channel only (6). Target: pair-level fault presence (OR of both channels'
ground-truth fault flags). Three models (logistic regression, decision tree, random
forest) × two rule-based baselines (single-channel threshold; one-out-of-two
comparator), same day-split/seed throughout.

## 7. Metrics, uncertainty, and the explicit target check (Phase 7)

Bootstrap: 1,000 resamples, seed 42. Recall and event-level metrics resampled **by
fault instance**; macro-F1 and balanced accuracy resampled **by whole test day** (two
different, disclosed resampling units — see `scripts/research/citi2026_phase7_metrics.py`
docstring for why).

### Best-performing combinations (macro-F1)

| pair | window | feature set | method | macro-F1 (95% CI) | fault recall (95% CI) | event recall | false-event rate |
|---|---:|---|---|---|---|---:|---:|
| Temperature | 5 | **a_single_only** | random_forest | 0.725 [0.683, 0.765] | 0.354 [0.299, 0.423] | 0.636 | 0.0155 |
| Temperature | 5 | b_single_plus_cross | random_forest | 0.715 [0.673, 0.760] | 0.338 [0.285, 0.408] | 0.605 | 0.0157 |
| Humidity | 5 | **a_single_only** | decision_tree | 0.666 [0.640, 0.693] | 0.252 [0.209, 0.331] | 0.483 | 0.0112 |
| Humidity | 5 | c_plus_ah | random_forest | 0.666 [0.639, 0.694] | 0.253 [0.203, 0.332] | 0.462 | 0.0177 |

**Honest headline finding: the single-channel-only feature set (a) is tied for best, or
outright best, on both pairs.** Adding cross-channel and absolute-humidity concordance
features (b, c) does not clearly improve the tree-based models over single-channel
features alone — it sometimes helps by a small margin, sometimes slightly hurts. The
cross-channel *hurt* is smallest for logistic regression, where (b)/(c) reliably beat
(a) by a wide margin (e.g. temperature w=5: 0.534/0.540 vs 0.471) — cross-channel
information helps a weak linear model much more than it helps an already-strong tree
model that can already exploit non-linear structure in the single-channel features.
Feature set (d) — cross-channel only, no single-channel information — is consistently
the *worst* tree-model performer, confirming the single-channel signal is doing most of
the work, not the cross-channel addition. Full table:
`research_results/citi2026/phase7/full_metrics.csv`.

### Window-size sensitivity

Shorter causal windows (5 samples / 2.5 min) outperform longer ones (10, 20 samples) on
every pair/method combination tested — macro-F1, fault recall, and event recall all
degrade monotonically as the window grows. This suggests the fault signatures modelled
here (gradual shift, stuck value, spike, noise burst) are dominated by short-timescale
structure that a longer trailing window smooths away rather than clarifies. Full table
in `docs/citi2026_phase7_metrics.md`.

### Explicit target check: gradual-shift recall vs. the ~27% ceiling

- External reference ceiling (given in the brief): **27%**
- **This project's own single-channel-rule baseline gradual-shift recall: 56.9%**
  (mean across pairs/windows) — already more than double the external figure.
- Feature-set (b)/(c) combinations exceeding the *external* 27% figure: **11 / 36**
- Feature-set (b)/(c) combinations exceeding *this project's own* single-channel
  baseline: **9 / 36**

**This is a negative result for the paper's central hypothesis, stated plainly.** The
external 27% ceiling does not describe this deployment's single-channel baseline at
all — this project's own simple threshold rule already detects gradual shifts far more
often than that figure, largely because the baseline's recall is highest at the shortest
matching window (92.5% at w=5, falling to 20.8% at w=20 for temperature) where a
single-sample threshold crossing is easy to match to a nearby true instance. Once
compared against this project's own (much stronger) baseline rather than the external
number, cross-channel/AH feature sets beat it in only a minority of tested combinations
(9/36) — the redundancy-based features do **not** demonstrate a clear, broad advantage
for gradual-shift detection specifically over a simple single-channel rule in this
dataset. This should be reported to the paper's readers as an open, negative finding,
not minimised.

### Compute cost (measured on Raspberry Pi 5 Model B Rev 1.0, the deployment device)

| method | mean fit (s) | max fit (s) | mean predict (s) |
|---|---:|---:|---:|
| decision_tree | 3.66 | 6.83 | 0.018 |
| logistic_regression | 2.93 | 8.26 | 0.186 |
| random_forest | 40.85 | 59.12 | 0.988 |

Random forest is ~14× slower to fit than the other two methods on-device; given its
macro-F1 advantage is modest (and it is not consistently the best model — decision tree
wins several combinations), the compute/accuracy trade-off should be weighed explicitly
if this is ever deployed for on-device retraining rather than treated as a free win.

### False-event rate (real changes wrongly attributed to faults)

| method | mean false-event rate |
|---|---:|
| logistic_regression | 0.0050 |
| random_forest | 0.0201 |
| decision_tree | 0.0260 |
| baseline_single_channel_rule | 0.0458 |
| baseline_one_out_of_two_comparator | 0.0969 |

All learned models beat both rule-based baselines on false-event rate — this is the
clearest, most consistent positive finding in Phase 7: ML models are substantially less
likely to mistake a real microclimate event (independently labelled, §4) for a sensor
fault than either hand-written rule, even though their raw fault-detection recall is not
dramatically higher.

## 8. Overall discussion

- **Positive, well-supported finding**: learned models (decision tree, random forest)
  substantially outperform both rule-based baselines on macro-F1 and, most clearly, on
  false-event rate — they are meaningfully better at not confusing real climate events
  with faults.
- **Negative/mixed finding, reported honestly**: the paper's core redundancy hypothesis
  — that cross-channel (SCD41-vs-BME688) and absolute-humidity concordance features
  improve fault detection over single-channel features — is **not clearly supported** by
  this deployment's data for the tree-based models that otherwise perform best. It helps
  a weak linear model a lot, and helps tree models a little on some combinations, but
  hurts on others, and does not exceed this project's own single-channel baseline on
  gradual-shift recall in the majority of tested combinations.
- **Negative finding on the external ceiling comparison**: this project's own
  single-channel baseline already exceeds the ~27% external ceiling reported for
  single-channel gradual-shift recall by a wide margin, so the "beats a weak baseline"
  framing does not transfer cleanly to this deployment; readers should be told this
  plainly rather than have the comparison silently dropped or reframed.
- **Window-size finding**: shorter causal windows are consistently better across the
  board — worth noting as a design recommendation independent of the feature-set
  question.
- **Scope/limitation**: single deployment, single kitchen, ~13 weeks, synthetic (not
  naturally occurring) faults — generalisation to other rooms/seasons/fault mixes is
  untested.

## Reproducibility appendix

- **Seeds**: fault injection & day split — `np.random.default_rng(42)`
  (`scripts/research/citi2026_phase4_fault_injection.py`); bootstrap resampling —
  `np.random.default_rng(42)` (`scripts/research/citi2026_phase7_metrics.py`).
- **Hardware**: Raspberry Pi 5 Model B Rev 1.0 (all data collection, model fitting, and
  timing measurements — named explicitly per phase, never a development machine).
- **Software**: Python 3.13.5, DuckDB 1.5.5, pandas 3.0.2, numpy 2.4.4,
  scikit-learn 1.8.0, Linux 6.12.62+rpt-rpi-2712 (aarch64). Full environment record:
  `research_results/citi2026/phase0/environment.json`.
- **Repository state**: commit `9476d7087b92b24588983a01ca474481debf8eae` on `main`,
  `github.com/ivanborodii/air-index`.
- **Exact commands** (run in order from the repo root, `.venv/bin/python3`, no
  `source .venv/bin/activate`):

```
scripts/research/citi2026_phase0_data_audit.py
scripts/research/citi2026_phase0_resolve_decisions.py
scripts/research/citi2026_phase1_pair_characterisation.py
scripts/research/citi2026_phase2_absolute_humidity.py
scripts/research/citi2026_phase3_weak_labels.py
scripts/research/citi2026_phase4_fault_injection.py
scripts/research/citi2026_phase5_features.py
scripts/research/citi2026_phase6_models.py
scripts/research/citi2026_phase7_metrics.py
```

- **Data provenance**: raw duckdb snapshots (`data/citi2026/*.duckdb`) are gitignored —
  reproducible from the live `air-monitor` database plus the scripts above, not
  version-controlled themselves. All tracked numeric results are in
  `research_results/citi2026/phase{0..7}/`.
