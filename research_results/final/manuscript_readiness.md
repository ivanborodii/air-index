# Manuscript Readiness

> Software-generated from `iaq_hfis.provenance.assess_readiness` -- not hand-maintained.

**`artifact_readiness`** means only that the computational artifacts (pipeline run, evaluation, `iaq_hfis validate-artifacts`, the test suite) are internally complete and consistent. It says nothing about whether this run's result is eligible to be described as the manuscript's complete proposed method -- that is `manuscript_readiness`, below, which may be `true` only when the temperature profile is directly DBN-supported, the run was executed in `mode=publication`, and a full A/V/M/I (`completeness_status=OK`) result actually exists.

## Artifact readiness: NOT READY

- Blocking: No pipeline run exists for this snapshot: mode='publication' aborts immediately at the first computed_ts (see manuscript_readiness blocker).

## Manuscript readiness: NOT READY

- Blocking: TEMPERATURE_PROFILE_NOT_DEFINED: requested room='kitchen', season='warm_period'. No standards-based temperature control region is defined for this room/season combination (DBN V.2.5-67:2013, mandatory Appendix D, Table D.4 has a literal dash for the standalone-kitchen row's warm-period column). All raw data currently available for this deployment (2026-04-16 through present) falls entirely within the warm-period months (Apr-Sep); no cold-period data exists yet. The deployment is a confirmed standalone/enclosed kitchen (README.md 'Deployment'), not a kitchen-dining/general-residential space, so the general_residential/warm_period profile cannot be truthfully substituted. 'iaq_hfis run' (mode=publication, the default) correctly aborts with this exact error before any computation -- verified live on 2026-07-31.

## Unsupported claims

- Full three-component (A/V/M/I) proposed-method result
- The microclimate component is standards-based for the deployed room/season

## Scientific blockers

- TEMPERATURE_PROFILE_NOT_DEFINED: requested room='kitchen', season='warm_period'. No standards-based temperature control region is defined for this room/season combination (DBN V.2.5-67:2013, mandatory Appendix D, Table D.4 has a literal dash for the standalone-kitchen row's warm-period column). All raw data currently available for this deployment (2026-04-16 through present) falls entirely within the warm-period months (Apr-Sep); no cold-period data exists yet. The deployment is a confirmed standalone/enclosed kitchen (README.md 'Deployment'), not a kitchen-dining/general-residential space, so the general_residential/warm_period profile cannot be truthfully substituted. 'iaq_hfis run' (mode=publication, the default) correctly aborts with this exact error before any computation -- verified live on 2026-07-31.
