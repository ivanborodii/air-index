# iaq_hfis Run Summary

Run ID: `3c6f93bfb3194de0a95002793b686a30`

## Run Metadata

- Status: **success**
- Started: 2026-07-25T11:05:05.044893+00:00
- Finished: 2026-07-25T12:06:47.018935+00:00
- Computed range: 2026-06-18T21:00:00+00:00 to 2026-07-27T20:29:16+00:00
- Window: 15 minutes
- Timestamps processed: 11231
- Snapshot retries: 0
- Config hash: `4edee11f418f0114d4856ac2cf43c8b43e893093d0bd83abe9c246c956fbe356`
- Engine version: 0.1.0

## Environment

- iaq_hfis_version: 0.1.0
- python_version: 3.13.5
- duckdb_version: 1.5.2
- platform: Linux-6.12.62+rpt-rpi-2712-aarch64-with-glibc2.41
- processor: aarch64
- cpu_count: 4
- git_commit: not available
- rule_generation_version: worst-of-max-severity-v1

## Completeness Summary

- OK: 10242
- PARTIAL: 442
- FAILED: 547

## Provisional Parameters Used

None engaged this run.

## Baseline Comparison (agreement, unlabeled real data)

- CRISP-MAX vs PROPOSED-HFIS: 1 agreement, Cohen's kappa=1 (n=10678, excluded=547)
- CRISP-MAX vs WEIGHTED-MEAN: 0.2434 agreement, Cohen's kappa=0.07776 (n=10696, excluded=529)
- PROPOSED-HFIS vs WEIGHTED-MEAN: 0.2421 agreement, Cohen's kappa=0.07662 (n=10678, excluded=547)

## Masking

- CRISP-MAX (>= Critical): rate=0 (0/4231 events)
- WEIGHTED-MEAN (>= Critical): rate=0.9941 (4206/4231 events)

## Ground-Truth Scoring

- PROPOSED-HFIS: macro-F1=0.8689, Cohen's kappa=0.8073 (n=42, excluded=0)
- CRISP-MAX: macro-F1=0.8689, Cohen's kappa=0.8073 (n=42, excluded=0)
- WEIGHTED-MEAN: macro-F1=0.1528, Cohen's kappa=-0.04077 (n=42, excluded=0)

## Stability

- Sampled at: 2026-07-27T23:25:00+03:00
- Seed: 42 (fixed, reproducible)
- Trials: 30
- Baseline class: Acceptable
- Class-change rate: 0.1667

## Sensitivity

- window_minutes=5: status=OK, index=37.5 (Acceptable)
- window_minutes=15: status=OK, index=37.5 (Acceptable)
- window_minutes=30: status=OK, index=37.5 (Acceptable)
- window_minutes=60: status=OK, index=37.5 (Acceptable)
- coverage_threshold=0.7: status=OK, index=37.5 (Acceptable)
- coverage_threshold=0.8: status=OK, index=37.5 (Acceptable)
- coverage_threshold=0.9: status=PARTIAL, index=37.5 (Acceptable)

## Fault / Reason-Code Frequency

- Status proportions (n=11225): OK=0.912, PARTIAL=0.03929, FAILED=0.04873
  - single_spike: 57106
  - out_of_range: 24920
  - stuck_value: 11773
  - data_loss: 2686
  - gradual_drift: 1371
