# Exploratory result snapshot -- NOT manuscript-final

This directory is a **tracked, static snapshot** of one validated
`(pipeline_run_id, evaluation_run_id)` pair's output -- not a live or
regenerable directory. It was produced by
`src/iaq_hfis/final_snapshot.py:build_exploratory_snapshot` and replaced
atomically (never hand-edited).

**This is an exploratory-mode run.** The microclimate (M) component was structurally omitted because no DBN-supported temperature profile exists for this run's room/season -- see `manuscript_readiness.md` for the exact blocker. This directory therefore reports an A/V-only (aerosol + ventilation) analysis and must never be presented as the manuscript's complete proposed method. It is kept OUTSIDE `research_results/final/` for exactly this reason.

- pipeline_run_id: `5cadd5e4f1cb4a84ab62be376f5e9728`
- evaluation_run_id: `05f1c0bbf3d34bad99c5fdcd6157f4cc`

See `latest_run.json` for the full identity chain (config hash, git
commit, generation timestamp, readiness status) and
`docs/reproducibility.md` (repo root) for how to reproduce it.

`run_narrative.md` and `article_results_summary.md` are software-generated
drafts -- review and rewrite before including any text in a publication.

If you change config or code, this snapshot goes stale. Regenerate it via
the final-run procedure; do not edit these files directly.
