# CITI-2026 Phase 2 — Absolute Humidity

Formula: Magnus-type saturation-vapour-pressure approximation, coefficients (17.62, 243.12) per Sonntag (1990) as adopted in WMO-No.8 *Guide to Meteorological Instruments and Methods of Observation*; ideal-gas conversion to absolute humidity (Rv = 461.5 J/(kg K) for water vapour). Computed separately per module from its own T and RH — `scd_ah_gm3` from (scd_temp_c, scd_humidity_pct), `bme_ah_gm3` from (bme_temp_c, bme_humidity_pct). Stored as new columns on the Phase 0 working copy (`raw_observations_analysis` / `raw_observations_full_history`) only — the raw snapshot is untouched.

## RH-based vs absolute-humidity-based concordance

| basis | n | bias mean | MAD of diff | Pearson r | Spearman rho | typical value | bias as % of typical | MAD as % of typical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| relative_humidity_pct | 247,984 | 6.6212 | 0.6928 | 0.97918 | 0.98541 | 47.359 | 13.98% | 1.46% |
| absolute_humidity_gm3 | 247,975 | 0.8579 | 0.1812 | 0.98696 | 0.99224 | 11.141 | 7.70% | 1.63% |

**Correlation**: AH-space has the higher Pearson r (0.98696 AH vs 0.97918 RH). **Relative dispersion**: RH-space has the smaller MAD-as-%-of-typical-value.

**Mixed result, stated plainly, not rounded up to a clean win**: AH improves two of three concordance measures — higher Pearson r (0.987 vs 0.979) and a much smaller bias relative to its own typical value (7.7% vs 14.0%, since AH's bias in g/m3 does not carry over RH's dependence on the ambient temperature level) — but has a slightly *larger* MAD relative to its typical value (1.63% vs 1.46%): the two modules' AH estimates agree better on average but scatter a bit more around that average, because each AH value is a nonlinear function of BOTH T and RH, so it inherits noise from both of Phase 1's already-imperfect pairs rather than cancelling either. Net assessment: AH is a defensible, arguably preferable, alternative concordance basis (lower relative bias, higher correlation) but not an unambiguous improvement on every axis. Feature set (c) in Phase 5 ("+ absolute-humidity concordance") should still be evaluated on its actual downstream classification performance, not assumed from this result alone.
