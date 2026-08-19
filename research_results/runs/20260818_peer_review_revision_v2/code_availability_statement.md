# Code availability statement (draft)

All code implementing the fuzzy IAQ index (HFIS), the evaluation suite, and
every analysis script used to produce this revision's results is version
controlled with Git and hosted at:

**Repository**: https://github.com/ivanborodii/air-index

**Commit analysed in this revision's final, verified state**:
`0639233f4a44e9fe81dba9874661f71e4db81534` (all quality gates passed: 491
tests, 0 failed; see `research_results/final/CURRENT_RUN.txt` and
`run_manifest.json` in this run directory).

**Relevant paths**:
- `src/iaq_hfis/` -- production package (pipeline, fuzzy engine, membership
  functions, rule base, quality checks, evaluation suite).
- `scripts/research/` -- standalone research scripts for this and the prior
  (`20260817_expanded_dataset_v1`) revision, each documented with its exact
  reproduce command in `run_manifest.json`.
- `tests/` -- unit and integration test suite (`pytest tests/`).
- `research_results/runs/20260818_peer_review_revision_v2/` -- this run's
  full, immutable set of results, manifests, and reports.

**License**: not yet declared at the repository level as of this run; add
before public citation if the venue requires it.

The repository is currently private/unpublished at the time of this revision;
this statement records where the code lives and will be updated with public
access details (or a stated reason for restricted access) before submission.
