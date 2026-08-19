# Data availability statement (draft)

The indoor air-quality sensor data analysed in this study (SCD41 CO2/temperature/
humidity, BME688 temperature/humidity/pressure/gas-resistance, SPS30 particulate
matter; 2026-06-18T00:00:00Z to 2026-08-16T00:00:00Z, exclusive) were collected by
a single-site deployment (`air-monitor/`) and are **not currently uploaded to a
public repository**. This statement must not be read as a claim that the raw data
are publicly available -- they are not, as of this run.

The exact bytes analysed in this revision are frozen and content-hashed under
`research_results/runs/20260818_peer_review_revision_v2/snapshot/`:

- `raw_observations_2026-06-18_to_2026-08-16.csv` (CSV export of the interval)
- `air_monitor_frozen_snapshot.duckdb` (full read-only DuckDB snapshot)
- SHA-256 hashes for both in `dataset_sha256.txt` / `data_interval_verification.json`

Outdoor weather context data (used only at hourly/daily aggregation, never to
confirm or reject sub-minute indoor events -- see `warm_season_analysis.md`) come
from a third-party weather API under that provider's own terms; the exact fetched
records used are cached locally under `air-monitor/data/weather.duckdb` and are
subject to the same access restrictions as the source, not this project's data
availability policy.

**Action needed before submission**: if the target venue requires public data
deposit, the frozen snapshot files above are the exact artifact to upload (e.g.
to Zenodo/OSF); update this statement with the resulting DOI once that is done.
Until then, data are available from the corresponding author on reasonable
request, subject to the constraints above.
