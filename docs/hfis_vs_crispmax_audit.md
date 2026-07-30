# Audit: is PROPOSED-HFIS accidentally equivalent to CRISP-MAX?

Scope: a source-level and empirical audit of whether the manuscript's proposed
Mamdani fuzzy inference system (PROPOSED-HFIS) is, by implementation accident,
computing the same thing as the hard-max baseline (CRISP-MAX) rather than a
genuinely distinct fuzzy method. Triggered by a final-validation review request;
not a response to a reported bug.

## 1. Source-level review

- **Membership functions** (`src/iaq_hfis/membership.py`): real overlapping
  trapezoids. Adjacent classes share an edge and cross at membership 0.5
  exactly at each manuscript breakpoint; overlap width is tied to the
  channel's own declared sensor uncertainty (`schema.dual_channel_tolerance`,
  `validate_membership_config`). Not degenerate (no zero-width "step
  function" classes) under the current config.
- **Rule base** (`src/iaq_hfis/rules.py`): true Cartesian-product rule
  generation (16 rules for A, 16 for M, 64 for the 2nd-level index), each
  rule's consequent = the antecedent class with the highest severity rank
  ("worst-of"). This is a deliberate, documented manuscript-consistent
  design (monotonicity, "one Critical input forces Critical", "all-favorable
  implies Favorable" all follow from it) — not a shortcut that collapses the
  rule table to a single input.
- **Inference engine** (`src/iaq_hfis/fuzzy_engine.py`): genuine Mamdani
  min/max/centroid, evaluated at both hierarchy levels (component rules,
  then the 2nd-level A/V/M -> index rules), with 401-point centroid
  defuzzification over the real output membership curves. No shortcut to a
  scalar max anywhere in `MamdaniEngine`.
- **CRISP-MAX** (`src/iaq_hfis/baselines.py`): `max(component_crisp_scores.values())`
  — a genuinely different, much simpler computation (no rule firing, no
  centroid). The two methods are architecturally distinct.

**Conclusion of the source review: PROPOSED-HFIS is a real Mamdani system,
not CRISP-MAX with extra steps.** No change to either method's logic is
warranted or was made by this audit.

## 2. Independent multi-component synthetic check

To test whether the two methods nonetheless converge numerically in
practice, a standalone script (not part of the pipeline; see conversation
record) fed the *real* rule base, membership functions and `MamdaniEngine`
a dense grid of independent component crisp scores `(A, V, M) in {0, 2.5,
..., 100}^3` (68,921 points) and compared `infer_index(...).index_value`
against `max(A, V, M)`:

| metric | value |
|---|---|
| exact numeric matches (HFIS == CRISP-MAX, 1e-9 tol) | 5.71% of points |
| mean \|HFIS - CRISP-MAX\| | 5.74 index points |
| median \|HFIS - CRISP-MAX\| | 5.06 |
| p95 \|HFIS - CRISP-MAX\| | 12.44 |
| max \|HFIS - CRISP-MAX\| | 12.69 |

HFIS is **not** numerically equivalent to CRISP-MAX when more than one
component carries a non-trivial score simultaneously — it systematically
scores *higher* than the raw max in this regime, because multiple
simultaneously-firing 2nd-level rules broaden the aggregated output curve
before the centroid is taken. Class-level agreement (Favorable/Acceptable/
Degraded/Critical) was 100% on a coarser sample of the same grid (1,331
points); characterizing this more rigorously (Lipschitz ratio, area between
curves, monotonicity) is carried out by the expanded continuity experiment,
task tracked separately.

## 3. Confirmed finding: the *existing* continuity experiment degenerates to CRISP-MAX

Inspecting the already-generated `continuity_summary.csv` from a real
pipeline run (`c4e93b4c83a641b1bc6c6fbeb1da6a98`) showed **PROPOSED-HFIS and
CRISP-MAX numerically bit-identical on every single boundary** (same
`max_adjacent_jump`, `mean_adjacent_jump`, `total_variation`,
`n_class_transitions`, transition positions, index range). This looked at
first like the exact accidental-equivalence bug this audit was meant to
catch — but tracing it to `src/iaq_hfis/evaluation/continuity.py` shows why,
and it is not a bug in either method:

`continuity.py`'s own docstring documents the design: each boundary sweep
holds every *other* channel at a "deeply-favorable baseline... so the swept
channel's own class dominates the worst-of aggregation." This is a
mathematically special case. Proof sketch: when V and M are pinned fully in
the Favorable class (membership degree 1 for Favorable, 0 for every other
class), the only 2nd-level rules with nonzero firing strength are those with
antecedents `(A=<A's active class>, V=Favorable, M=Favorable)`; because
Favorable is the lowest severity rank, the worst-of consequent for every
such rule is exactly `A`'s own class, at exactly `A`'s own degree. The
resulting 2nd-level class-activation vector is therefore **identical** to
`A`'s own component-level class-activation vector, so the 2nd-level centroid
reproduces `A`'s own `crisp_score` bit-for-bit. Meanwhile `CRISP-MAX =
max(A, V, M)` also reduces to `A`'s crisp_score exactly, since V and M are
pinned near 0. Both methods collapse to "pass through the one swept
component's own score unchanged" — an intrinsic property of testing one
input in isolation, not evidence that the two methods are equivalent in
general (section 2 above shows they are not, once more than one component
carries signal).

**This is a genuine weakness of the current continuity experiment's design
(single-channel-perturbed, others held favorable), not a bug in
PROPOSED-HFIS or CRISP-MAX.** No change was made to either method. The fix —
already scoped as a separate task — is to repeat every boundary sweep under
multiple "other components" contexts (favorable / acceptable / degraded),
which is a strictly additive change to the *experiment*, not the methods
under test.

## 3B. The multi-context expansion alone does not fix the degeneracy either

The continuity experiment was subsequently expanded exactly as described
above: every boundary is now swept under three "other components" contexts
(favorable/acceptable/degraded), with every non-swept channel held at a
fixed representative value for that context. Re-running it against real
pipeline data still shows **PROPOSED-HFIS and CRISP-MAX numerically tied on
all 99 (boundary, context) pairs tested** (`mean_area_between_curves_vs_crisp_max
≈ 1.8e-14`, floating-point noise). Inspecting the raw per-point curves (e.g.
`co2_breakpoint1`, context=`degraded`) confirms why: both methods are
perfectly *flat* across the entire sweep, not just equal to each other --
the swept channel (CO2) never becomes the dominant (highest-severity)
channel within its own narrow +/-sensor-uncertainty sweep window, because
the fixed "degraded" values for the other channels are not close enough to
CO2's local range for a rank crossover to occur. With the worst-of rule
base, whichever channel dominates the whole sweep determines the whole
output, in *both* methods identically -- multi-context alone does not force
a rank crossover unless the other channels' fixed value happens to be close
to the swept channel's local range, which is not the general case.

This is a real property of the *experimental design* (perturb one channel
in isolation, near-uncertainty-width span, others pinned constant), not a
new implementation bug, and not evidence the methods are equivalent in
general -- section 2's independent multi-component synthetic check (all
three inputs varying together across the full 0-100 range) already shows
substantial divergence once more than one channel is simultaneously close
to the maximum severity. Deliberately choosing "other components" context
values specifically so they tie with the swept channel's transient score
was considered and rejected: that would cross from "improving the
measurement" into rigging the experiment for a predetermined outcome, which
the validation task's own constraints forbid. The honest conclusion is
recorded verbatim in `run_summary.json`'s
`evaluation.continuity.smoothness_comparison.conclusion` (and hence in
`run_narrative.md`/`article_results_summary.md`) whenever this tie occurs,
rather than being silently omitted.

## 4. Verdict

- PROPOSED-HFIS is implemented as a genuine Mamdani inference system and is
  **not** an accidental hard-max in general (section 2).
- Neither the original single-context continuity experiment (section 3) nor
  its favorable/acceptable/degraded-context expansion (section 3B) is
  actually capable of detecting HFIS/CRISP-MAX divergence, because both
  perturb only one channel at a time within a narrow sweep while every
  other channel sits at a fixed value -- so one channel trivially dominates
  the whole sweep in both methods identically, regardless of context. A
  "PROPOSED-HFIS is smoother than CRISP-MAX at manuscript boundaries" claim
  is **not supported** by either version of this experiment; it remains
  untested by boundary-sweep methodology, not disproven. What section 2's
  independent multi-component grid check *does* establish is that the two
  methods genuinely diverge (mean |diff| ≈ 5.7 index points) once more than
  one channel simultaneously carries adverse signal -- a condition the
  per-boundary sweep design structurally cannot reach.
- No changes to `fuzzy_engine.py`, `rules.py`, `membership.py`, or
  `baselines.py` were made or are warranted by this audit — the systems
  differ architecturally and numerically once tested outside the degenerate
  single-input case.
- `run_summary.json`'s `evaluation.continuity.smoothness_comparison` field
  (and the narrative/article-summary text derived from it) states this tie
  and its cause explicitly whenever it occurs, rather than omitting the
  comparison or asserting a smoothness advantage that was not measured.
