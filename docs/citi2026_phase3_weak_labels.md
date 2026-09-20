# CITI-2026 Phase 3 — Weak Event Labels

Built entirely from independent channels — CO2, PM2.5, PM10, pressure (`gas_resistance_ohm` excluded per Phase 0). No temperature/humidity channel is read here, by design: this label is the ground truth Phase 6/7 use to check whether a classifier confuses a real event with an injected fault, so it must never be derived from the same channels being classified.

- Rolling window: 241 samples (~120.5 min), centered, per-day only
- Deviation score threshold: 3.0 (robust-MAD units, literature-typical Hampel default — provisional, not tuned against anything in this project)
- Minimum persistence to count as a sustained event: 4 samples (2.0 min) — filters transient blips/single-sample noise

## Coverage

- Total samples: 263,873
- Samples inside a weak-labelled event: 17,217 (**6.52%** of the analysis window)
- Distinct events: 1,085
- Duration: median 4.5 min, p90 19.5 min, max 52.0 min

### Per-channel contribution

| channel | event samples | % of all samples |
|---|---:|---:|
| co2_ppm | 10,158 | 3.850% |
| mass_pm2_5 | 4,240 | 1.607% |
| mass_pm10 | 4,226 | 1.601% |
| pressure_hpa | 4,119 | 1.561% |

Full interval table (start/end/duration/triggering channel/peak score): `research_results/citi2026/phase3/event_intervals.csv`.

## Disclosed limitations

- All four independent channels share the SAME rolling window and threshold, for simplicity — CO2/pressure move on slower timescales than PM cooking-smoke spikes, so a single window is a compromise, not independently tuned per channel.
- Threshold=3.0 and persistence=4 samples are literature-typical, not calibrated against any ground truth (there is none available) — same epistemic status as the sibling iaq_hfis project's still-open Hampel parameters.
- Rows failing Phase 0's hard-range check are excluded from event detection for that channel (masked, not deleted) — a known-impossible reading can never itself become a "real event", and cannot corrupt the local median/MAD baseline used to detect real events nearby in time.