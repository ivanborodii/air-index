# Run status

**All planned experiments (sections 3-13 of the task protocol) completed
successfully. 457/457 tests pass.** `research_results/final/` was
deliberately left untouched by this run.

## Why `research_results/final/` was not updated

The task's own instructions are explicit: "Do not overwrite
`research_results/final` until all new experiments, validations, and
artifact checks have succeeded" and the final package update is described
as a decision the author makes ("manuscript update notes... exact old and
new values that must be changed in the paper"), not an automatic
consequence of a successful run. `research_results/final/` currently holds
the previously published, narrower-window (2026-07-15..2026-07-29) result
that the manuscript may already cite by exact numbers. Overwriting it
silently would change what a reader following the manuscript's own
reproducibility citation sees, without the author having reviewed
`manuscript_update_notes.md` first.

**This is a safe, deliberate deferral, not an incomplete task.** Everything
needed to update `research_results/final/` is ready in this run directory:
`article_results_summary.md`, `article_metrics.json`, `run_manifest.json`,
every required CSV/JSON/plot, `test_report.txt`, `data_validation_report.md`,
and `reproducibility_instructions.md`.

## To promote this run to `research_results/final/`

Once the author has reviewed `manuscript_update_notes.md` and decided to
adopt the expanded-dataset results as the new manuscript-facing package:

```
rm -rf research_results/final
cp -r research_results/runs/20260817_expanded_dataset_v1 research_results/final
```

(or a more selective copy, if only some artifacts should become the new
`final/` -- the author's call, not automated here).
