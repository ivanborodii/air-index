# Reproducibility instructions

All commands assume the repo root (`/home/ivan/python_scripts/air_ml`) as
the working directory and the project's `.venv` (`.venv/bin/python3`, never
`source .venv/bin/activate`).

1. Check out git commit `3916a5717a85e86903fc99183f0882ec913c4a36` (the
   commit this whole run was computed against -- `run_manifest.json`
   records this and cross-checks it against the persisted
   `pipeline_runs.source_git_commit` for the baseline run).
2. The baseline pipeline run (`pipeline_run_id=7f04698725dd4f35a432ba4a0de2934f`)
   is already persisted in `data/iaq_hfis/iaq_hfis.duckdb` and does not need
   to be rerun unless that database is unavailable. If it must be rerun:
   `iaq_hfis run --from 2026-06-18T00:00:00+00:00 --to 2026-08-16T00:00:00+00:00 --window-minutes 15 --mode publication`
   (takes several hours on a Raspberry Pi 5 -- 8h43m for this run).
3. Run every step in `run_manifest.json`'s `reproduce_commands` list, in
   order. Steps 2-6 and 10-12 are independent of each other and can run in
   any order once step 2 (baseline) exists; step 7 (`iaq_hfis evaluate`)
   must complete before steps 8 and 9 (both need its `evaluation_run_id`,
   printed to stdout as `Evaluation <id> (...)`).
4. All random seeds are fixed and recorded: **20260815** (Hampel
   calibration/validation split, missing-data-strategy subsample and
   bootstrap) and **42** (production `evaluation.stability_seed`, unrelated
   to this task but inherited from the existing evaluation config).
5. `scripts/research/missing_data_strategy_comparison.py` is resumable: if
   interrupted, rerunning the same command skips any masking case whose
   checkpoint already exists under
   `missing_data_strategy/_checkpoints/<case>.csv` and only computes the
   remaining ones.
6. Run `python -m pytest tests/ -q` (full suite: 457 tests, ~55 minutes on
   this Raspberry Pi 5 -- do not use a short foreground timeout; run
   backgrounded and poll, or accept the wait).
7. Run `python scripts/research/build_run_manifest.py` last, after every
   other script above has produced its artifacts -- it hashes everything
   under this run directory.

See `run_manifest.json` for exact dependency versions, Python version, OS/
kernel/Pi model, and per-artifact SHA256 hashes.
