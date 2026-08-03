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
run_summary.json, and `pipeline_runs.source_git_commit`), and **`mode`**
(`publication` \| `exploratory`, `pipeline_runs.mode` / `run_summary.json:mode`)
-- see "Publication vs. exploratory mode" below.

## Same-commit invariant

`iaq_hfis finalize` additionally requires that the CURRENT git commit and
working-tree state match what was recorded when `iaq_hfis run` computed the
result -- checked live by
`iaq_hfis.validation.check_same_commit_and_clean_tree` (git commit
comparison + `git status --porcelain` dirty-tree check), folded into
`artifact_validation.json`/`.md` and both readiness signals. This is
deliberately NOT part of the general `iaq_hfis validate-artifacts` check
list (a development sandbox routinely has uncommitted changes, and that
command is used throughout development) -- only `finalize` enforces it,
since that is the one place a dirty tree or commit drift genuinely
disqualifies the result from being published.

## Publication vs. exploratory mode

`iaq_hfis run --mode publication` (default, strict): a missing DBN
temperature profile for any computed_ts aborts the entire run --
`TEMPERATURE_PROFILE_NOT_DEFINED` propagates uncaught, since a full A/V/M/I
manuscript result must never be produced with a substituted or omitted
microclimate component.

`iaq_hfis run --mode exploratory`: the microclimate component is
structurally omitted (never fabricated) wherever no profile is defined;
the run is tagged `mode=exploratory` and `build_final_snapshot` refuses to
promote it into `research_results/final` -- use
`iaq_hfis finalize --exploratory` (-> `build_exploratory_snapshot`) to
publish it to `research_results/exploratory` instead.

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
of truth. `iaq_hfis.db.SCHEMA_VERSION` (currently 8; see that module's
docstring for the full version history) is stamped into the database on
creation; if an existing file predates it, or its version otherwise
mismatches the code, `DerivedResultsWriter` raises `LegacySchemaError`
rather than silently reinterpreting old rows under a newer column layout:

```bash
python -m iaq_hfis.cli rebuild-db --confirm
```

This only deletes `paths.derived_db_path` (+ its `.wal`) and recreates it
empty with the current schema. It never touches `air_monitor.duckdb` or
`weather.duckdb` (both opened strictly read-only, via the snapshot
mechanism in `src/iaq_hfis/db.py`). See `docs/database_schema.md` for the
full table-by-table schema.

## What "final" means

`research_results/final/` is a **tracked, static snapshot** of one
validated, `mode=publication`, manuscript-eligible `(pipeline_run_id,
evaluation_run_id)` pair's output -- not a live/regenerable directory. It
is replaced atomically by the final-run procedure (`iaq_hfis run` ->
`evaluate` -> `report` -> `plot` -> `validate-artifacts` -> `finalize`;
see its own `README.md`) and includes:

- `latest_run.json` -- identity chain (run IDs, config hashes, git commit,
  timestamp, readiness).
- `manifest.json` -- the full integrity record: run IDs, git commit,
  config hash, input date range, raw/derived row counts, a SHA-256
  checksum for every source database, and a SHA-256 checksum for every
  file physically present in the snapshot (so a stale or tampered snapshot
  is mechanically detectable, not just trusted by convention -- see
  `src/iaq_hfis/final_snapshot.py:_build_manifest`).
- `artifact_validation.json` / `.md` / `.txt` -- the `validate-artifacts`
  result (folded with the same-commit/clean-tree check) at the time of
  publication, in three equivalent formats.
- `manuscript_readiness.json` / `.md` -- standalone artifact_readiness /
  manuscript_readiness record (see `docs/result_interpretation.md`).
- `publication_claims_matrix.csv` / `.md` -- evidence-graded verdict for
  each of the manuscript's minimum 9 claims.
- `parameter_selection.json` -- the Hampel calibration grid's candidate
  values, objective, and selection rationale.
- A full copy of every report artifact (`run_summary.md`,
  `run_narrative.md`, `article_results_summary.md`,
  `provisional_parameter_assessment.md`, every exported CSV, plots,
  `plot_manifest.json`, `output_data_dictionary.csv`,
  `parameter_provenance.csv`).

**`iaq_hfis finalize` refuses** (raises `ConfigError`, exits nonzero) if
the given `pipeline_run_id` was computed in `mode=exploratory` -- use
`iaq_hfis finalize --exploratory` for those, which targets
`research_results/exploratory/` instead and is never presented as the
manuscript's complete proposed method. If no `mode=publication` run is
currently possible for this deployment (e.g. no DBN-supported temperature
profile exists for the available data period), `research_results/final/`
holds a hand-authored `manuscript_readiness=false` record explaining the
exact blocker rather than a stale or substituted result -- see its own
`README.md` for the current status.

If you change config or code, the snapshot goes stale -- regenerate it via
the final-run procedure, don't hand-edit it.
