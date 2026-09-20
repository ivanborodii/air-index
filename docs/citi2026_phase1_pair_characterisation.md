# CITI-2026 Phase 1 — Redundant-Pair Characterisation

Source: `data/citi2026/analysis_dataset_20260920T120752Z.duckdb` (`raw_observations_analysis`), analysis window resolved in Phase 0. Sign convention: **diff = SCD41 - BME688**.

## Exclusions (declared, not silent)

| pair | total rows | both channels present | excluded (hard-range fail) | used for stats |
|---|---:|---:|---:|---:|
| temperature | 263,873 | 247,984 | 9 | 247,975 |
| humidity | 263,873 | 247,984 | 0 | 247,984 |

## Overall pair statistics

| pair | n | bias mean | bias median | bias std | MAD of diff | Pearson r | Spearman rho | day-to-day bias std | bias trend slope/day (p) | median lag (samples) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Temperature (SCD41 - BME688), degC | 247,975 | -1.1597 | -1.1354 | 0.1768 | 0.0944 | 0.99826 | 0.99849 | 0.1215 | 0.00232 (p=2.09e-07) | -1.0 |
| Relative humidity (SCD41 - BME688), pct | 247,984 | 6.6212 | 6.4988 | 1.3980 | 0.6928 | 0.97918 | 0.98541 | 0.9039 | -0.02395 (p=3.12e-15) | -2.0 |

`bias_day_to_day_std` = std-dev of the per-day mean bias across all valid days — small relative to the bias itself indicates a **stable systematic offset** (the pair disagrees by a consistent amount, not an intermittent one). `bias trend slope/day` is the linear-regression slope of daily mean bias against day index (p-value from `scipy.stats.linregress`) — tests whether the offset is drifting over the ~13-week deployment rather than being a fixed hardware characteristic.

**Both pairs show a statistically significant (p<0.001) drift** in the daily-mean bias over the deployment window: **Temperature** (p=2.1e-07, slope=0.0023/day, cumulative over 92 days ≈ 0.213); **Relative humidity** (p=3.1e-15, slope=-0.0240/day, cumulative over 92 days ≈ -2.204). Significance here comes from low day-to-day noise (see `bias_day_to_day_std` above), not from a large sample size inflating an unimportant effect — n for this regression is the number of days (~94), not the row count. The magnitude is modest over this window but real and detectable; worth re-checking as the deployment extends further, since a genuine long-term calibration drift is exactly the kind of slow change a fault-detection system must NOT mistake for a real microclimate event (or vice versa).

## Response lag (cross-correlation, samples @ 30 s cadence)

Computed only on the **fully-complete days** from Phase 0's day-completeness table (≥99% of 2880 expected samples that day, and both channels non-null after a short-gap interpolation limited to 4 samples/2 min used ONLY for this lag calculation). Positive lag = BME688 lags SCD41 (SCD41 leads); negative lag = SCD41 lags BME688 (BME688 leads) — sign convention verified against a synthetic known-lag test, not just derived. Search range ±20 samples (±10 min).

| pair | days used | median lag (samples) | mean lag (samples) | median lag (s) |
|---|---:|---:|---:|---:|
| Temperature | 69 | -1.0 | -1.75 | -30 |
| Relative humidity | 69 | -2.0 | -2.41 | -60 |

Full per-day lag distribution: `research_results/citi2026/phase1/lag_estimates_by_day.csv`.

## Self-heating discussion

Neither sensor has an independent ground-truth reference in this deployment, so self-heating cannot be isolated and quantified in absolute terms from this pair alone — only discussed qualitatively against the measured bias:

- BME688 is a gas sensor with an active heater plate (used for its VOC/gas-resistance measurement) sharing the same package as its temperature element; SCD41 uses Sensirion's PASens photoacoustic CO2-sensing technology, with no comparable continuous internal heater. This is the standard explanation in the low-cost-sensor literature for why a BME680/688 co-located with a non-heated sensor tends to read warmer (and, via the Magnus/Clausius-Clapeyron relationship, correspondingly *drier* at fixed absolute humidity) than its neighbour — consistent in direction with the measured bias here: BME688 reads warmer (`bias_mean` < 0 for SCD41-BME688) AND drier (`bias_mean` > 0 for SCD41-BME688, i.e. SCD41 reads more humid) — both signs point the same physical direction, not just one of the two.
- The bias being **stable day-to-day** (small `bias_day_to_day_std` relative to `bias_mean`, see table above) is itself evidence FOR a fixed hardware/self-heating explanation rather than an intermittent fault — a fault-detection system built on this pair should treat this stable offset as the expected baseline, not flag it, and should instead watch for the offset **stepping to a new level** or its variance suddenly increasing, which the drift-trend slope above is one first check for.
- `gas_resistance_ohm` (the channel that would let us test heater-cycle correlation directly) was already found unusable in Phase 0 (11.2% coverage) — this limits how far the self-heating hypothesis can be tested quantitatively with this deployment's data; disclosed as a limitation, not glossed over.
