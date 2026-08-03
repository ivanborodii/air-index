# Final result: BLOCKED -- no manuscript-ready result currently exists

**Status: `manuscript_readiness.ready = false`.** No `mode=publication`
pipeline run can currently complete for this deployment. See
`manuscript_readiness.md` for the full readiness record and
`publication_claims_matrix.md` for the per-claim evidence status (8 of 9
claims UNSUPPORTED, 1 BLOCKED -- none can be evaluated without a completed
run).

## Why

TEMPERATURE_PROFILE_NOT_DEFINED: requested room='kitchen', season='warm_period'. No standards-based temperature control region is defined for this room/season combination (DBN V.2.5-67:2013, mandatory Appendix D, Table D.4 has a literal dash for the standalone-kitchen row's warm-period column). All raw data currently available for this deployment (2026-04-16 through present) falls entirely within the warm-period months (Apr-Sep); no cold-period data exists yet. The deployment is a confirmed standalone/enclosed kitchen (README.md 'Deployment'), not a kitchen-dining/general-residential space, so the general_residential/warm_period profile cannot be truthfully substituted. 'iaq_hfis run' (mode=publication, the default) correctly aborts with this exact error before any computation -- verified live on 2026-07-31.

## What you can look at instead

- **`research_results/exploratory/`** -- a real A/V-only (aerosol +
  ventilation) analysis of this deployment's actual data, computed in
  `mode=exploratory` (the microclimate component structurally omitted,
  never fabricated). Clearly labeled exploratory; must never be presented
  as the manuscript's complete proposed method.
- **`research_results/archive/a09f711d3c0c44508cd499e12028ae17_kitchen_warm_period_invalid/`**
  -- the previous `research_results/final/` snapshot, kept for audit only.
  It used a temperature profile that has since been removed as invalid
  (see its `INVALIDATION_NOTICE.md`); do not cite it as current.

## The scientifically valid paths to a manuscript-ready result

1. Collect standalone-kitchen data during the DBN cold period (roughly
   October-March), where `kitchen/cold_period` (a real, DBN-confirmed
   profile) applies; or
2. If the deployment room is genuinely reclassified as a kitchen-dining /
   general-residential space (not merely to unblock this result), document
   that reclassification explicitly and use `general_residential/warm_period`
   truthfully.

Never substitute a different room's DBN numbers to manufacture a result.

## Git commit

`1655f36cb9a6e9a0fe451650107cf3e2dfd6e92b`
