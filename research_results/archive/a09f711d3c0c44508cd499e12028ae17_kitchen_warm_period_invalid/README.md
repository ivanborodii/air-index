# Final published result snapshot

This directory is a **tracked, static snapshot** of one validated
`(pipeline_run_id, evaluation_run_id)` pair's output -- not a live or
regenerable directory. It was produced by
`src/iaq_hfis/final_snapshot.py:build_final_snapshot` and replaced
atomically (never hand-edited).

- pipeline_run_id: `a09f711d3c0c44508cd499e12028ae17`
- evaluation_run_id: `81fadef3088d4f658fb1cb03ab44d47e`

See `latest_run.json` for the full identity chain (config hash, git
commit, generation timestamp, publication-readiness status) and
`docs/reproducibility.md` (repo root) for how to reproduce it.

`run_narrative.md` and `article_results_summary.md` are software-generated
drafts -- review and rewrite before including any text in a publication.

If you change config or code, this snapshot goes stale. Regenerate it via
the final-run procedure; do not edit these files directly.
