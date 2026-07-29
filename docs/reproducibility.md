# Result reproducibility

How to reproduce, identify, and validate any specific `iaq_hfis` result.

## Identity chain

Every computed result traces back through three identifiers, all recorded
in `run_summary_{pipeline_run_id}.json`:

1. **`pipeline_run_id`** -- one `iaq_hfis run` invocation. Tags every row in
   `observation_quality`, `window_aggregates`, `outdoor_context`,
   `component_scores`, `iaq_index_results`. A second `run` over the same or
   overlapping timestamps gets its own `pipeline_run_id` and never
   overwrites or is read by the first.
2. **`evaluation_run_id`** -- one `iaq_hfis evaluate` invocation against a
   `pipeline_run_id`. Tags `baseline_results` and every `evaluation_*`
   table. Re-running evaluate always creates a new `evaluation_run_id`
   (never mixes rows with a prior one); `run_summary.json`'s
   `selected_evaluation_run_id` names the one currently reported.
3. **`config_hash`** -- SHA-256 over the three config models
   (`iaq_hfis.yaml`, `sensor_specs.yaml`, `room_profiles.yaml`), recorded on
   both `pipeline_runs` and `evaluation_runs` (as `config_hash` and
   `evaluation_config_hash` respectively -- normally identical unless config
   changed between `run` and `evaluate`).

Plus the **git commit** the code was run at (`environment.git_commit` in
run_summary.json, and `pipeline_runs.source_git_commit`).

## Reproducing a result

```bash
# 1. Compute the index over a time range (creates pipeline_run_id)
python -m iaq_hfis.cli run --from 2026-06-19T00:00:00+00:00 --to 2026-07-28T00:00:00+00:00

# 2. Run the full evaluation suite against that pipeline_run_id
python -m iaq_hfis.cli evaluate --pipeline-run-id <id> \
  --from 2026-06-19T00:00:00+00:00 --to 2026-07-28T00:00:00+00:00

# 3. Generate every report artifact (CSVs, plots manifest, markdown, provenance)
python -m iaq_hfis.cli report --pipeline-run-id <id>

# 4. Render plots
python -m iaq_hfis.cli plot --pipeline-run-id <id>

# 5. Cross-validate every artifact against the derived DB and each other
python -m iaq_hfis.cli validate-artifacts --pipeline-run-id <id>
```

Given the same raw data, the same config (same `config_hash`), and the same
code (same git commit), steps 1-2 are numerically deterministic (fixed
seeds throughout: `stability_seed` for perturbation trials and stratified
sampling, SHA-256-derived per-sample seeds -- never Python's randomized
`hash()`). Steps 3-4 are byte-for-byte deterministic given the same
`run_summary.json` (tested:
`tests/integration/test_report_orchestration.py::test_report_is_deterministic_when_regenerated`).

## Rebuilding the derived database

The derived database (`data/iaq_hfis/iaq_hfis.duckdb`) is entirely
reproducible from raw source data + config -- it is never itself a source
of truth. If it predates the run-isolated schema (schema_version 2) or its
version otherwise mismatches the code, `DerivedResultsWriter` raises
`LegacySchemaError` rather than silently reinterpreting old rows:

```bash
python -m iaq_hfis.cli rebuild-db --confirm
```

This only deletes `paths.derived_db_path` (+ its `.wal`) and recreates it
empty with the current schema. It never touches `air_monitor.duckdb` or
`weather.duckdb` (both opened strictly read-only, via the snapshot
mechanism in `src/iaq_hfis/db.py`).

## What "final" means

`research_results/final/` is a **tracked, static snapshot** of one
validated `(pipeline_run_id, evaluation_run_id)` pair's output -- not a
live/regenerable directory. It is replaced atomically by the final-run
procedure (see its own `README.md`) and includes `latest_run.json`
(identity chain + config hashes + git commit + timestamp + publication
readiness) plus a full copy of the report artifacts and the
`validate-artifacts` result at the time of publication. If you change
config or code, the snapshot goes stale -- regenerate it, don't hand-edit it.
