# Manuscript update notes

Concrete, per-claim update notes for later manuscript revision. The DOCX
itself was not edited (per task instruction) -- this file is the input for
that later edit. Do not rewrite the whole manuscript from this; each entry
is scoped to one claim.

---

## 1. Second-level fuzzy engine vs. simple max()

- **Exact old claim**: (as characterized by the reviewer) the second Mamdani
  level may be analytically equivalent to taking the maximum component
  class; the previous denser grid found disagreements only when the maximum
  component value was exactly 75, but this was checked at only 41 points
  per axis despite a manifest claiming 101.
- **Exact verified new result**: rule-level worst-of property proven
  exhaustively (64/64 rules). On the full, actually-executed 101^3 =
  1,030,301-point grid, class agreement is 98.34%, and **100% of the 17,101
  disagreements occur exactly when max(A,V,M) == 75** (0 elsewhere on the
  grid). An independent 250,000-point random-continuous check (excluding
  exact boundaries) gives 99.9764% agreement -- not exactly 100%, with a
  small residual discretization effect near (not at) boundaries.
- **Manuscript section**: Methods/Discussion, second-level Mamdani
  equivalence subsection.
- **Old text must be**: REPLACED. The reviewer's own hypothesis ("only at
  max==75") is now fully confirmed and precisely quantified, not just
  observed at a coarser resolution.
- **Source artifact and row**: `second_level_equivalence/second_level_formal_analysis.md`,
  `second_level_boundary_summary.csv` (bucket=`max_component_equals_75`),
  `second_level_boundary_and_random_metadata.json`.
- **Warning**: none -- this result is fully verified and safe to cite.
- **Suggested Ukrainian paragraph**: "Правило другого рівня нечіткого
  висновку задовольняє властивість 'найгіршого з компонентів' для всіх 64
  правил (доведено вичерпним перебором). Проте це не означає чисельної
  еквівалентності агрегованого виходу HFIS та простого максимуму компонентів:
  на повній сітці з 1 030 301 точки (101 значення на вісь) узгодженість
  класів становить 98,34%, а всі розбіжності (17 101 з 17 101) виникають
  виключно тоді, коли максимальне значення компонента дорівнює точно 75 --
  межі класів 'Погіршена'/'Критична'."
- **Suggested English paragraph**: "The second-level rule base satisfies the
  worst-of-antecedents property for all 64 rules (proven by exhaustive
  enumeration). This does not, however, imply numerical equivalence between
  HFIS's aggregated output and a simple component maximum: over the full
  1,030,301-point grid (101 values per axis), class agreement is 98.34%,
  and every one of the 17,101 disagreements occurs exactly when the maximum
  component value equals 75 -- the Degraded/Critical class boundary."

---

## 2. Missing-data handling / causal LOCF

- **Exact old claim**: (implicit in the prior implementation) LOCF
  substitutes "the most recent valid value within the last 2 computed
  positions (~10 minutes)".
- **Exact verified new result**: the prior implementation counted array
  positions, not elapsed time, so across a real data gap it could silently
  carry forward a value that was actually hours old. Fixed to use real
  elapsed time (`target_ts - source_ts <= lookback`). Under temperature
  masking on the validation split, the production strategy ("proposed",
  exclude the component) hides 89.1% of true Critical timestamps; the
  causally-correct hybrid LOCF strategy hides only 1.8%.
- **Manuscript section**: Methods (missing-data handling), Results
  (Experiment A / missing-data strategy comparison).
- **Old text must be**: REPLACED (if it described LOCF by position/step
  count) or the underlying implementation clarified as time-based.
- **Source artifact and row**: `missing_data_strategy/missing_data_strategy_summary.csv`,
  rows `masking_case=direct_input:temperature, dataset_split=validation,
  strategy in {proposed, locf}`.
- **Warning**: **do not yet cite this as a production recommendation.**
  This revision's calibration/validation split (70/30) has no held-out test
  set, so the section 6.6 promotion criteria cannot be evaluated from this
  run. The finding is real and strongly suggestive, not yet a validated
  promotion case.
- **Suggested Ukrainian paragraph**: "Виявлено та виправлено вразливість
  причинного перенесення останнього дійсного значення (LOCF): попередня
  реалізація рахувала фіксовану кількість попередніх обчислених позицій, а
  не реальний часовий інтервал, що могло призвести до використання значення
  віком у кілька годин після реального розриву в даних. Після виправлення,
  за умови маскування температури, виробнича стратегія приховує 89,1%
  справді критичних показань на валідаційній вибірці, тоді як гібридна
  LOCF-стратегія -- лише 1,8%. Це попередній результат: набір
  тестування, відкладений для остаточної валідації, у цьому запуску
  відсутній."
- **Suggested English paragraph**: "A causal-LOCF defect was identified and
  fixed: the previous implementation counted a fixed number of prior
  computed positions rather than real elapsed time, which could silently
  substitute an hours-old value across a genuine data gap. After the fix,
  under temperature masking, the production strategy hides 89.1% of true
  Critical-class timestamps on the validation split, versus 1.8% for the
  causally-correct hybrid LOCF strategy. This is a preliminary finding; no
  held-out test evaluation was performed in this revision, so it does not
  yet support a production change."

---

## 3. Pollution vs. microclimate domination of the Critical class

- **Exact old claim**: the integrated Critical class may be dominated by
  thermal comfort (microclimate) rather than air pollution (reviewer
  hypothesis); dominance-tie and driver-attribution statistics computed
  previously used a tie definition that flagged non-empty co-dominance
  lists (effectively ~100% of rows) as ties, and a percentile-rank
  attribution method that can misattribute two-sided channels.
- **Exact verified new result**: with both bugs fixed, the corrected tie
  rate is 18.0% (not ~100%). The pollution-oriented index (A, V only) has a
  Critical share of 3.4% versus 44.9% for the current integrated index; only
  7.6% of current-Critical timestamps remain Critical when microclimate is
  excluded. The corrected (membership-based, not percentile-rank) driver
  attribution assigns temperature as the dominant associated input for
  72.6% of Critical timestamps.
- **Manuscript section**: Results (Critical class composition), Discussion
  (microclimate vs. pollution).
- **Old text must be**: REPLACED if it cited a tie rate or dominant-driver
  percentage computed by the pre-fix code; the reviewer's hypothesis is
  strongly supported by the corrected numbers.
- **Source artifact and row**: `pollution_microclimate/pollution_microclimate_summary.json`
  (`tie_rate`, `pollution_oriented_index_critical_share`,
  `share_current_critical_remaining_critical_under_pollution_oriented`),
  `critical_driver_summary.csv` (row `dominant_component=M,
  associated_direct_input=temperature`).
- **Warning**: descriptive association only -- do not phrase as "temperature
  causes Critical classifications" (no causal claim is supported).
- **Suggested Ukrainian paragraph**: "Виправлено дві помилки обчислення:
  визначення 'нічиєї' між домінантними компонентами (раніше майже кожен
  рядок помилково позначався як нічия) та атрибуцію найбільш несприятливого
  прямого входу (раніше -- за процентильним рангом, що є некоректним для
  двобічних змінних, як-от температура). Після виправлення частка справжніх
  нічиїх становить 18,0%. Індекс, орієнтований на забруднення (лише
  компоненти A і V), має частку критичного класу 3,4% проти 44,9% для
  інтегрованого індексу; лише 7,6% часових позначок, критичних за
  інтегрованим індексом, залишаються критичними після виключення
  мікроклімату. Температура є асоційованим провідним чинником для 72,6%
  критичних випадків. Це описова асоціація, а не причинно-наслідковий
  висновок."
- **Suggested English paragraph**: "Two computation defects were identified
  and fixed: the dominance-tie definition (previously flagging nearly every
  row as tied) and the most-adverse-direct-input attribution (previously
  percentile-rank based, which is unsound for two-sided channels like
  temperature). After correction, the true tie rate is 18.0%. A
  pollution-oriented index (components A and V only) has a Critical share
  of 3.4% versus 44.9% for the integrated index; only 7.6% of
  integrated-Critical timestamps remain Critical once microclimate is
  excluded. Temperature is the corrected associated driver for 72.6% of
  Critical timestamps. This is a descriptive association, not a causal
  claim."

---

## 4. Real-time class flapping / stability

- **Exact old claim**: a "class flapping rate" computed from perturbation
  trials at fixed sample points, ordered by an arbitrary trial index.
- **Exact verified new result**: this was never a temporal metric (trial
  order has no relationship to elapsed sensor time). Replaced with a
  genuine chronological analysis (10-minute maximum-gap consecutiveness
  rule) over the full real time series for all four methods. On
  OK-completeness data, PROPOSED_HFIS / FUZZY_COMPONENT_MAX / CRISP_CLASS_MAX
  all show identical transitions/day (5.85); WEIGHTED_MEAN shows fewer
  (3.93/day), which reflects its high Critical-hiding rate (97.6% masking),
  not genuine extra stability.
- **Manuscript section**: Results (stability analysis).
- **Old text must be**: RETAINED as a perturbation-sensitivity statistic
  (relabeled, not deleted) but must not be cited as a "flapping rate" or
  temporal stability claim; REPLACED with the new real-time analysis for
  any temporal-stability claim.
- **Source artifact and row**: `real_time_class_flapping/real_time_class_flapping_summary.csv`
  (scope=`completeness_ok_only`), `boundary_stability_paired/stability_class_flapping_summary.csv`
  (retained, relabeled as perturbation-sensitivity).
- **Warning**: when reporting WEIGHTED_MEAN's lower transitions/day, always
  pair it with its masking rate (97.6% at Critical severity) -- reporting
  one without the other is misleading (task explicitly requires this
  pairing).
- **Suggested Ukrainian paragraph**: "Попередній показник 'мерехтіння
  класів' обчислювався за довільним порядком випробувань збурення в
  окремих точках вибірки і не був реальним часовим показником. Замінено на
  аналіз за справжньою хронологічною послідовністю (правило безперервності
  з максимальним розривом 10 хвилин). За повних (OK) записів усі три методи
  на основі нечіткої логіки демонструють однакову частоту переходів класів
  (5,85/добу); метод зваженого середнього демонструє нижчу частоту
  (3,93/добу), що пояснюється високою часткою прихованих критичних випадків
  (97,6%), а не справжньою стабільністю."
- **Suggested English paragraph**: "The previous 'class flapping rate' was
  computed from an arbitrary perturbation-trial order and was never a
  temporal metric. It has been replaced with a genuine chronological
  analysis (10-minute maximum-gap consecutiveness rule). On complete
  (OK-completeness) records, all three fuzzy-logic-based methods show an
  identical transition rate (5.85/day); the weighted-mean baseline shows a
  lower rate (3.93/day), which reflects its high Critical-hiding rate
  (97.6%) rather than genuine additional stability."

---

## 5. Second-level grid manifest defect (methodological correction, may not need manuscript text)

- **Exact old claim**: manifest stated 101 grid points per axis; actual
  persisted grid had 41^3 = 68,921 rows.
- **Exact verified new result**: fixed procedurally -- the evaluate command
  was actually executed with `--multi-component-grid-points 101`, and the
  persisted row count (1,030,301) is now cross-checked against the claim
  (`verify_grid_point_count`).
- **Manuscript section**: none directly (methodological/reproducibility
  correction); relevant only if the manuscript cites a specific grid size.
- **Old text must be**: RETAINED if no specific number was cited;
  REPLACED with "101 points per axis, 1,030,301 combinations" if it was.
- **Source artifact and row**: `run_manifest.json` (`multi_component_grid_consistency_check`).
- **Warning**: none.
