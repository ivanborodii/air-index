# Second-level rule audit

Index-level (2nd fuzzy level) rule base has 64 rules (iaq_hfis.rules.build_rule_base().index_rules, a full 4^3 Cartesian product over {A,V,M} x CLASS_ORDER).

**Exhaustive check (all 64 rules, not a sample): 64/64 rules assign the consequent class equal to the most adverse (max-severity) antecedent class.** This is a complete proof by exhaustion for this finite rule set.

## Important distinction (do not conflate these two claims)

1. The rule-level property above (every individual rule's consequent is the worst-of its antecedents) is proven by exhaustive enumeration.
2. This does NOT by itself prove the AGGREGATE Mamdani engine output (PROPOSED_HFIS, which fires potentially several rules at once when inputs have graded/partial membership in more than one class, then combines them via max-OR and centroid defuzzification) is numerically identical to FUZZY_COMPONENT_MAX (a hard max of crisp component scores). See second_level_equivalence_real.csv / _grid.csv / _summary.json for the actual empirical numerical comparison -- those results, not this rule audit, are what determine whether the two methods agree in practice.

## All rules (machine-readable copy also at second_level_rule_audit.csv)

```
                                                  antecedents consequent_class expected_worst_of_antecedents  matches_worst_of_property
0   {'A': 'Acceptable', 'M': 'Acceptable', 'V': 'Acceptable'}       Acceptable                    Acceptable                       True
1     {'A': 'Acceptable', 'M': 'Acceptable', 'V': 'Critical'}         Critical                      Critical                       True
2     {'A': 'Acceptable', 'M': 'Acceptable', 'V': 'Degraded'}         Degraded                      Degraded                       True
3   {'A': 'Acceptable', 'M': 'Acceptable', 'V': 'Favourable'}       Acceptable                    Acceptable                       True
4     {'A': 'Acceptable', 'M': 'Critical', 'V': 'Acceptable'}         Critical                      Critical                       True
5       {'A': 'Acceptable', 'M': 'Critical', 'V': 'Critical'}         Critical                      Critical                       True
6       {'A': 'Acceptable', 'M': 'Critical', 'V': 'Degraded'}         Critical                      Critical                       True
7     {'A': 'Acceptable', 'M': 'Critical', 'V': 'Favourable'}         Critical                      Critical                       True
8     {'A': 'Acceptable', 'M': 'Degraded', 'V': 'Acceptable'}         Degraded                      Degraded                       True
9       {'A': 'Acceptable', 'M': 'Degraded', 'V': 'Critical'}         Critical                      Critical                       True
10      {'A': 'Acceptable', 'M': 'Degraded', 'V': 'Degraded'}         Degraded                      Degraded                       True
11    {'A': 'Acceptable', 'M': 'Degraded', 'V': 'Favourable'}         Degraded                      Degraded                       True
12  {'A': 'Acceptable', 'M': 'Favourable', 'V': 'Acceptable'}       Acceptable                    Acceptable                       True
13    {'A': 'Acceptable', 'M': 'Favourable', 'V': 'Critical'}         Critical                      Critical                       True
14    {'A': 'Acceptable', 'M': 'Favourable', 'V': 'Degraded'}         Degraded                      Degraded                       True
15  {'A': 'Acceptable', 'M': 'Favourable', 'V': 'Favourable'}       Acceptable                    Acceptable                       True
16    {'A': 'Critical', 'M': 'Acceptable', 'V': 'Acceptable'}         Critical                      Critical                       True
17      {'A': 'Critical', 'M': 'Acceptable', 'V': 'Critical'}         Critical                      Critical                       True
18      {'A': 'Critical', 'M': 'Acceptable', 'V': 'Degraded'}         Critical                      Critical                       True
19    {'A': 'Critical', 'M': 'Acceptable', 'V': 'Favourable'}         Critical                      Critical                       True
20      {'A': 'Critical', 'M': 'Critical', 'V': 'Acceptable'}         Critical                      Critical                       True
21        {'A': 'Critical', 'M': 'Critical', 'V': 'Critical'}         Critical                      Critical                       True
22        {'A': 'Critical', 'M': 'Critical', 'V': 'Degraded'}         Critical                      Critical                       True
23      {'A': 'Critical', 'M': 'Critical', 'V': 'Favourable'}         Critical                      Critical                       True
24      {'A': 'Critical', 'M': 'Degraded', 'V': 'Acceptable'}         Critical                      Critical                       True
25        {'A': 'Critical', 'M': 'Degraded', 'V': 'Critical'}         Critical                      Critical                       True
26        {'A': 'Critical', 'M': 'Degraded', 'V': 'Degraded'}         Critical                      Critical                       True
27      {'A': 'Critical', 'M': 'Degraded', 'V': 'Favourable'}         Critical                      Critical                       True
28    {'A': 'Critical', 'M': 'Favourable', 'V': 'Acceptable'}         Critical                      Critical                       True
29      {'A': 'Critical', 'M': 'Favourable', 'V': 'Critical'}         Critical                      Critical                       True
30      {'A': 'Critical', 'M': 'Favourable', 'V': 'Degraded'}         Critical                      Critical                       True
31    {'A': 'Critical', 'M': 'Favourable', 'V': 'Favourable'}         Critical                      Critical                       True
32    {'A': 'Degraded', 'M': 'Acceptable', 'V': 'Acceptable'}         Degraded                      Degraded                       True
33      {'A': 'Degraded', 'M': 'Acceptable', 'V': 'Critical'}         Critical                      Critical                       True
34      {'A': 'Degraded', 'M': 'Acceptable', 'V': 'Degraded'}         Degraded                      Degraded                       True
35    {'A': 'Degraded', 'M': 'Acceptable', 'V': 'Favourable'}         Degraded                      Degraded                       True
36      {'A': 'Degraded', 'M': 'Critical', 'V': 'Acceptable'}         Critical                      Critical                       True
37        {'A': 'Degraded', 'M': 'Critical', 'V': 'Critical'}         Critical                      Critical                       True
38        {'A': 'Degraded', 'M': 'Critical', 'V': 'Degraded'}         Critical                      Critical                       True
39      {'A': 'Degraded', 'M': 'Critical', 'V': 'Favourable'}         Critical                      Critical                       True
40      {'A': 'Degraded', 'M': 'Degraded', 'V': 'Acceptable'}         Degraded                      Degraded                       True
41        {'A': 'Degraded', 'M': 'Degraded', 'V': 'Critical'}         Critical                      Critical                       True
42        {'A': 'Degraded', 'M': 'Degraded', 'V': 'Degraded'}         Degraded                      Degraded                       True
43      {'A': 'Degraded', 'M': 'Degraded', 'V': 'Favourable'}         Degraded                      Degraded                       True
44    {'A': 'Degraded', 'M': 'Favourable', 'V': 'Acceptable'}         Degraded                      Degraded                       True
45      {'A': 'Degraded', 'M': 'Favourable', 'V': 'Critical'}         Critical                      Critical                       True
46      {'A': 'Degraded', 'M': 'Favourable', 'V': 'Degraded'}         Degraded                      Degraded                       True
47    {'A': 'Degraded', 'M': 'Favourable', 'V': 'Favourable'}         Degraded                      Degraded                       True
48  {'A': 'Favourable', 'M': 'Acceptable', 'V': 'Acceptable'}       Acceptable                    Acceptable                       True
49    {'A': 'Favourable', 'M': 'Acceptable', 'V': 'Critical'}         Critical                      Critical                       True
50    {'A': 'Favourable', 'M': 'Acceptable', 'V': 'Degraded'}         Degraded                      Degraded                       True
51  {'A': 'Favourable', 'M': 'Acceptable', 'V': 'Favourable'}       Acceptable                    Acceptable                       True
52    {'A': 'Favourable', 'M': 'Critical', 'V': 'Acceptable'}         Critical                      Critical                       True
53      {'A': 'Favourable', 'M': 'Critical', 'V': 'Critical'}         Critical                      Critical                       True
54      {'A': 'Favourable', 'M': 'Critical', 'V': 'Degraded'}         Critical                      Critical                       True
55    {'A': 'Favourable', 'M': 'Critical', 'V': 'Favourable'}         Critical                      Critical                       True
56    {'A': 'Favourable', 'M': 'Degraded', 'V': 'Acceptable'}         Degraded                      Degraded                       True
57      {'A': 'Favourable', 'M': 'Degraded', 'V': 'Critical'}         Critical                      Critical                       True
58      {'A': 'Favourable', 'M': 'Degraded', 'V': 'Degraded'}         Degraded                      Degraded                       True
59    {'A': 'Favourable', 'M': 'Degraded', 'V': 'Favourable'}         Degraded                      Degraded                       True
60  {'A': 'Favourable', 'M': 'Favourable', 'V': 'Acceptable'}       Acceptable                    Acceptable                       True
61    {'A': 'Favourable', 'M': 'Favourable', 'V': 'Critical'}         Critical                      Critical                       True
62    {'A': 'Favourable', 'M': 'Favourable', 'V': 'Degraded'}         Degraded                      Degraded                       True
63  {'A': 'Favourable', 'M': 'Favourable', 'V': 'Favourable'}       Favourable                    Favourable                       True
```
