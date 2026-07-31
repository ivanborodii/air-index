# How to interpret a generated result

A reading guide for `run_summary.json` and the report artifacts it
generates (`run_summary.md`, `run_narrative.md`, `article_results_summary.md`,
`provisional_parameter_assessment.md`, every exported CSV). Written for
someone deciding what a result actually supports -- not a developer guide
(see `docs/evaluation_protocol.md` for methodology, `docs/database_schema.md`
for the DB, `docs/manuscript_method_mapping.md` for which manuscript
section each piece implements).

## Start here: is this result trustworthy?

1. Check `readiness.artifact_readiness.ready` AND `readiness.manuscript_readiness.ready`
   in `run_summary.json` (or the "Artifact and Manuscript Readiness"
   section of `run_summary.md` / the standalone `manuscript_readiness.md`)
   -- these are two DIFFERENT questions, never conflate them.
   `artifact_readiness=false` means the computational artifacts themselves
   are incomplete/inconsistent (pipeline/evaluation status, failed
   validation, or failed tests). `manuscript_readiness=false` means the
   result cannot be described as the manuscript's complete proposed method
   -- check `manuscript_readiness.blocking_issues` and `unsupported_claims`
   (e.g. a provisional/missing temperature profile, or `mode=exploratory`).
   A run can have `artifact_readiness=true` and `manuscript_readiness=false`
   at the same time -- that is not a contradiction, it means the
   computation is internally sound but this specific result cannot be
   claimed as the manuscript's full method (see
   `publication_claims_matrix.md` for the per-claim breakdown).
2. Run `iaq_hfis validate-artifacts --pipeline-run-id <id>` (or read the
   tracked `research_results/final/artifact_validation.json`/`.md`) --
   this is the **authoritative** combined check: every CSV, the narrative,
   and run_summary.json cross-validated against the derived database and
   each other. `ok: false` means something is inconsistent; do not trust
   the numbers until it passes.
3. Check `dominant_component_frequency` / `provisional_parameters_used` at
   the top level, and cross-reference `provisional_parameter_assessment.md`
   for what those provisional values actually mean for your specific
   conclusion (see below).

## Completeness status: OK / PARTIAL / FAILED

Every `computed_ts` gets exactly one. **OK** means all three components
(A, V, M) had sufficient window coverage. **PARTIAL** means one component
was unavailable (PARTIAL-mode inference regenerates the rule base from the
available components only -- see `fuzzy_engine.infer_index`'s docstring;
this is a PROVISIONAL design choice, the manuscript does not specify
PARTIAL-mode mechanics). **FAILED** means fewer than two components were
available -- `index_value`/`index_class` are always NULL, never a
placeholder number. `completeness_summary` in `run_summary.json` gives the
counts; never compute a class distribution over anything but OK rows (a
PARTIAL/FAILED row has no comparable index value).

## Agreement, consistency, and stability are NOT accuracy

None of this project's evaluation produces an accuracy number, because
there is no ground-truth-labeled real air-quality dataset. Three distinct,
non-interchangeable concepts appear throughout the outputs -- confusing
them is the single most likely way to overclaim:

- **Agreement** (`evaluation.agreement`, `method_comparison.csv`): how
  often two methods produce the same class on the SAME real, unlabeled
  data. High agreement does not mean either method is "correct."
- **Consistency with a synthetic reference** (`evaluation.reference_cases`):
  macro-F1/kappa against 42 deterministic, pre-labeled synthetic vectors
  constructed FROM the manuscript's own control-region boundaries. This
  checks the rule base implements its own specification correctly, not
  real-world classification accuracy.
- **Stability** (`evaluation.stability`): class-change rate and
  probability of moving to a better/worse class under input perturbation
  within declared sensor uncertainty -- a measure of a method's
  self-consistency, not correctness. `class_change_rate` +
  `prob_moved_better` + `prob_moved_worse` always reconcile
  (`prob_moved_better + prob_moved_worse == class_change_rate`).
- **Fault-injection precision/recall/F1** (`evaluation.fault_injection`)
  IS a real accuracy-like metric, but only against SYNTHETIC, labeled
  scenarios (60 deterministic scenarios, disjoint calibration/validation
  splits) -- it validates the data-quality detection layer, not the fuzzy
  index computation, and is disclosed as row-level vs event-level
  separately (see `docs/evaluation_protocol.md` section 7). Weak results
  (single_spike/stuck_value precision) are reported as-is, not hidden.

## Continuity: what "HFIS is smoother" would require

`evaluation.continuity.smoothness_comparison` gives an aggregate,
non-cherry-picked verdict across every (boundary, context) pair actually
tested (favorable/acceptable/degraded). **Read the `conclusion` string
directly rather than assuming an outcome.** On the real reference run, this
experiment finds PROPOSED_HFIS and FUZZY_COMPONENT_MAX numerically tied across every
pair tested -- not because the methods are equivalent (an independent
synthetic multi-component check in `docs/hfis_vs_crispmax_audit.md` shows
real divergence once more than one channel carries signal), but because
perturbing one channel while holding every other channel fixed is a
degenerate case both methods are mathematically forced to agree on. Do not
cite a smoothness advantage for HFIS without checking this field for the
specific run being cited.

## Provisional parameters: what "provisional" does and doesn't mean

`provisional_parameters_used` (top level of `run_summary.json`) is the
single authoritative list -- every artifact (`run_summary.md`,
`run_narrative.md`, `article_results_summary.md`, `parameter_provenance.csv`,
`readiness`) is required to report the identical list (enforced by
`validate-artifacts`). Note the provenance taxonomy has finer-grained
categories than a single PROVISIONAL flag -- LITERATURE_INFORMED,
AUTHOR_DEFINED_PROVISIONAL, and CALIBRATED_ON_SYNTHETIC_CALIBRATION_SPLIT
are all collectively "provisional-like" for disclosure purposes (see
`iaq_hfis.provenance.PROVISIONAL_LIKE_STATUSES`) even though they carry
more justification than a bare guess. "Provisional" means: not given
numerically in the manuscript, and not yet confirmed against an external
standard or extended real-data validation. It does **not** mean untested --
`provisional_parameter_assessment.md` documents, per parameter, whether it
was calibrated (true for exactly two: `hampel.window_size`/`mad_multiplier`,
the only parameters with an actual grid-search calibration procedure),
against what dataset, what the sensitivity result is (if any), and whether
conclusions depend strongly on it. **A synthetic benchmark's calibration
result is never evidence that a parameter is universally valid** -- it is
scoped to that benchmark, stated explicitly in the assessment doc. No
parameter is ever silently promoted from PROVISIONAL to STANDARD_BASED
without a cited source in `iaq_hfis.provenance`'s own catalog.

## Sensitivity: which parameters were actually stress-tested

`evaluation.sensitivity.by_parameter_value` covers exactly two swept axes
(window duration, coverage threshold) -- NOT every provisional parameter.
Check `provisional_parameter_assessment.md`'s "Sensitivity result" field
per parameter before assuming something was stress-tested; most provisional
parameters (e.g. confirmation thresholds) have no dedicated sensitivity
sweep and are marked as such, honestly, rather than implying coverage that
doesn't exist.

## Forbidden overclaims (a preview -- see `run_narrative.md`'s own
Limitations section for the authoritative, per-run statement)

- Do not report agreement, reference-case consistency, or stability
  numbers as "accuracy."
- Do not claim empirical validation of a PROVISIONAL parameter from a
  synthetic benchmark's calibration result alone.
- Do not claim HFIS is smoother than FUZZY_COMPONENT_MAX without checking
  `smoothness_comparison.conclusion` for the run in question.
- Do not use outdoor CO as a substitute for indoor CO2, or WHO 24-hour PM
  reference points as a compliance assessment for a 15-minute index --
  both are structurally prevented in the pipeline, but should also never
  be implied in prose.
- Do not describe a FAILED or PARTIAL-completeness row's absence of an
  index value as "low" or "zero" -- it is undefined, not low.

## Where the authoritative, tracked numbers live

`research_results/final/` -- a static, checksummed snapshot of one
validated `(pipeline_run_id, evaluation_run_id)` pair (see
`docs/reproducibility.md`). Live `data/iaq_hfis/reports/{pipeline_run_id}/`
directories are working outputs of individual `iaq_hfis run`/`evaluate`/
`report` invocations and may be superseded or stale.
