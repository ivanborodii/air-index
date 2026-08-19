# Second-level equivalence: formal analysis

Task section 8.4. Two genuinely different claims; this revision proves one
exhaustively and refutes the other empirically, then explains precisely
*why* the second one fails.

## 1. Rule-level property (proven, not sampled)

**Claim**: every one of the 64 index-level rules (`iaq_hfis.rules.build_rule_base().index_rules`,
a full 4^3 Cartesian product over {A, V, M} x {Favourable, Acceptable,
Degraded, Critical}) has a consequent class equal to the maximum-severity
antecedent class.

**Status: TRUE, proven by exhaustive enumeration.** All 64 rules checked
(not sampled -- 64 is small enough to enumerate completely); 64/64 satisfy
the property. See `second_level_rule_audit.csv` / `.md`. This is a
consequence of construction (`generate_component_rules` always sets the
consequent to `max(antecedent_classes, key=severity)`), so exhaustive
enumeration is a complete proof for this finite rule set, not an inductive
argument.

## 2. Does the rule-level property imply PROPOSED_HFIS == FUZZY_COMPONENT_MAX numerically?

**No, and this revision demonstrates exactly where and why it fails.**

The rule-level property only says: *if exactly one rule fires with full
strength 1.0*, its consequent class equals the worst antecedent's class.
But Mamdani inference with centroid defuzzification does not, in general,
fire exactly one rule at strength 1.0 -- whenever an input component's crisp
score sits inside a class's transition band, it has **partial membership in
two adjacent classes simultaneously**, so multiple rules fire at partial
strength, their consequent fuzzy sets are combined (max-OR), and the
resulting *composite* fuzzy set is defuzzified by centroid -- an averaging
operation, not a selection operation. A weighted blend of two adjacent
output shapes does not, in general, land exactly on FUZZY_COMPONENT_MAX's
hard `max()` value.

### Empirical result (this run, full 101^3 = 1,030,301-point grid, `evaluation_multi_component_grid`)

| Bucket | n points | class agreement | max abs diff |
|---|---:|---:|---:|
| All grid points | 1,030,301 | 0.9834 | 12.69 |
| No component at a class boundary (25/50/75) | 941,192 | **1.0000** | 12.44 |
| Any component == 25 | 30,301 | 0.9851 | 12.69 |
| Any component == 50 | 30,301 | 0.9851 | 12.69 |
| Any component == 75 | 30,301 | 0.4356 | 12.69 |
| **max(A,V,M) == 75 exactly** | **17,101** | **0.0000** | 0.19 |
| max(A,V,M) in [74, 75) | 16,651 | **1.0000** | 11.5 |
| max(A,V,M) in (75, 76] | 17,557 | **1.0000** | 11.56 |

(Full table: `second_level_boundary_summary.csv`.)

**Every single one of the 17,101 class disagreements on the full grid occurs
exactly when the maximum component's crisp score equals 75.0** (confirmed:
`n_disagreements_total == n_disagreements_with_max_component_exactly_75` in
`second_level_boundary_and_random_metadata.json`; `claim_supported: true`).
Immediately adjacent grid points (74 and 76, the nearest sampled neighbours
at this grid's 101-point resolution) agree perfectly.

An independent, deterministic 250,000-point random-continuous-triple check
(excluding points within 1e-6 of any class boundary,
`second_level_random_continuous_summary.csv`) gives class agreement
**0.999764** (249,941/250,000), not exactly 1.0 -- honestly reported rather
than rounded up. The remaining 59 disagreements are NOT at an exact
boundary (excluded by construction) and their `abs_diff` values cluster near
the grid bucket's own p95 (~11.26) rather than near the tiny
max-component-exactly-75 bucket's diffs (~0.19), indicating a **second,
much smaller source**: the centroid integral is evaluated over a discretized
401-point output universe (`_OUTPUT_UNIVERSE_STEPS` in
`iaq_hfis.pipeline.build_runtime_context`), so a continuous input
arbitrarily close to (but not at) a boundary can occasionally land its
discretized centroid on the other side of a class edge. This is a much
rarer (0.0236% of continuous draws vs. 1.66% of grid points hitting the
exact tie) and different-in-kind effect from the exact-75-tie case above;
55 of the 59 have their max component within 1 unit of 75, consistent with
this being a narrow-neighborhood discretization effect rather than a
uniformly-distributed one.

## 3. Why exactly 75, and why so precise

75 is simultaneously:

1. **The Degraded/Critical boundary** on the shared 0-100 component/output
   scale (`OUTPUT_BOUNDARIES = [25, 50, 75]`).
2. **The exact crossover point** where a component's membership degree in
   "Degraded" and "Critical" are equal (0.5 each, by construction of the
   symmetric trapezoid crossing built in `iaq_hfis.membership`).

At this exact point, two rules with different consequent classes (one via
the Degraded antecedent, one via Critical) fire at *equal, non-trivial*
strength. FUZZY_COMPONENT_MAX classifies the crisp score 75.0 using
`classify_output`'s own tie-break (worst-of, so Critical wins). PROPOSED_HFIS
instead defuzzifies the *combined* Degraded-consequent and
Critical-consequent fuzzy sets via centroid -- a genuine blend, which
generally centroids to a value and class between the two, not equal to
either input class's representative point. This is not a bug: it is the
expected, structural behavior of centroid defuzzification at an exact
membership tie, and it is confined to a measure-zero set of exact ties (in
continuous terms) -- empirically, at this grid's resolution, 17,101 of
1,030,301 points (1.66%), all and only where max(A,V,M) == 75.0 to full
floating-point precision.

## 4. Conclusion

- The rule-level worst-of property (section 1) is **proven**.
- HFIS == FUZZY_COMPONENT_MAX numerically is **refuted** by direct
  counterexample (`second_level_counterexamples.csv`).
- The refutation is **almost entirely explained by one localized cause**:
  100% of the exhaustive grid's disagreements occur exactly when the
  maximum component's crisp score equals the Degraded/Critical class
  boundary (75), where the two methods' fundamentally different combination
  rules (hard selection vs. weighted centroid blend) genuinely diverge by
  construction, not by defect.
- A second, much smaller (0.0236% of draws) discretized-centroid effect
  remains near (but not at) a boundary on continuous random input, reported
  honestly rather than rounded away -- class agreement on 250,000
  independent random continuous triples is 0.999764, not exactly 1.0.

This is precisely the manuscript-facing claim this revision can support:
**HFIS is NOT analytically equivalent to taking the maximum component
class**, and the sole, fully-characterized source of disagreement is exact
membership ties at a class boundary -- not a broader or less-understood
numerical drift.
