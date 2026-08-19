# Reproducibility instructions

Run from the repository root (`/home/ivan/python_scripts/air_ml`) with the
project virtualenv (`.venv/bin/python3`). Every command below is also
recorded verbatim in `run_manifest.json`'s `reproduce_commands`, generated
by actually executing each one for this run (task section 5.5: the manifest
must match what was executed, not an aspirational list).

```bash
# 0. Baseline pipeline run is reused unchanged (see baseline/baseline_run_manifest.json
#    note_on_rerun_policy for why re-running it was not necessary for this revision):
#    pipeline_run_id=7f04698725dd4f35a432ba4a0de2934f

# 1. Section 3: frozen snapshot + independent interval verification
.venv/bin/python3 scripts/research/data_snapshot_and_interval_verification.py

# 2. Section 4: baseline manifest
.venv/bin/python3 scripts/research/baseline_run_manifest.py

# 3. Evaluation run (grid FIXED to the full 101^3 = 1,030,301-point grid;
#    needed for sections 8 and 9)
.venv/bin/python3 -m iaq_hfis.cli evaluate \
  --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 --window-minutes 15 \
  --pipeline-run-id 7f04698725dd4f35a432ba4a0de2934f \
  --multi-component-grid-points 101
# -> prints evaluation_run_id; substitute it below as <EVALUATION_RUN_ID>

# 4. Section 6 (Experiment A): missing-data strategy comparison (causal LOCF fix)
.venv/bin/python3 scripts/research/missing_data_strategy_comparison.py 7f04698725dd4f35a432ba4a0de2934f

# 5. Section 7 (Experiment B): pollution/microclimate decomposition (tie + attribution fixes)
.venv/bin/python3 scripts/research/pollution_microclimate_decomposition.py 7f04698725dd4f35a432ba4a0de2934f

# 6. Section 8 (Experiment C): second-level equivalence (full 101^3 grid)
.venv/bin/python3 scripts/research/second_level_equivalence.py 7f04698725dd4f35a432ba4a0de2934f <EVALUATION_RUN_ID>

# 7. Section 9 (Experiment D): boundary/stability paired analysis
.venv/bin/python3 scripts/research/boundary_stability_paired_analysis.py <EVALUATION_RUN_ID>

# 8. Section 5.4/9.3: real chronological class-flapping analysis (new)
.venv/bin/python3 scripts/research/real_time_class_flapping.py 7f04698725dd4f35a432ba4a0de2934f <EVALUATION_RUN_ID>

# 9. Section 10 (Experiment E): Hampel MAD-multiplier sweep (no code change; rerun only)
.venv/bin/python3 scripts/research/hampel_threshold_sweep.py

# 10. Section 11 (Experiment F): membership-function audit + PM10 width sensitivity (new)
.venv/bin/python3 scripts/research/membership_function_audit.py

# 11. Section 12 (Experiment G): data-quality reason analysis
.venv/bin/python3 scripts/research/data_quality_reason_analysis.py 7f04698725dd4f35a432ba4a0de2934f

# 12. Section 13 (Experiment H): runtime profiling
.venv/bin/python3 scripts/research/runtime_profiling.py 7f04698725dd4f35a432ba4a0de2934f

# 13. Full test suite (before AND after -- both saved in this run directory)
.venv/bin/python3 -m pytest tests/ -q

# 14. This manifest
.venv/bin/python3 scripts/research/build_run_manifest.py
```

## Seeds used (recorded once, reused everywhere they apply)

- `20260815` -- Hampel calibration/validation split, missing-data-strategy
  subsample + bootstrap, boundary/stability bootstrap, real-time flapping
  bootstrap.
- `42` -- evaluation stability sample perturbation trials
  (`settings.evaluation.stability_seed`).

## Notes

- The derived DuckDB database (`data/iaq_hfis/iaq_hfis.duckdb`) only
  supports one writer at a time; run the `evaluate` step to completion
  before starting any script that reads from it (data-quality reasons,
  runtime profiling, second-level equivalence, boundary/stability, flapping).
- `hampel_threshold_sweep.py` and `membership_function_audit.py` are
  self-contained (no DB access) and can run concurrently with everything
  else.
