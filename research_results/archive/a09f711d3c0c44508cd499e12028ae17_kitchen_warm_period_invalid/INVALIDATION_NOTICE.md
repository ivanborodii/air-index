# This snapshot is scientifically invalid -- archived, not current

This directory was previously published at `research_results/final/`
(pipeline_run_id `a09f711d3c0c44508cd499e12028ae17`, git commit
`5f284166076b56f1d9b561626544cab87c3e5d4a`). It has been moved here and is
**no longer the current result** for one specific reason:

**The `kitchen/warm_period` temperature profile it used has been removed
from `config/room_profiles.yaml`.**

That profile reused `general_residential/warm_period`'s DBN numbers for a
standalone kitchen by author decision. On closer audit against DBN
V.2.5-67:2013 Table D.4, the standalone-kitchen row has a literal dash in
the warm-period column -- the standard defines no room-specific value for
a kitchen in the warm period. Substituting a different room's numbers
misrepresented which DBN row governs the result, so the profile was
deleted rather than kept as merely "provisional."

Every computed_ts in this snapshot's `2026-07-15T19:11:17` to
`2026-07-29T19:11:17` period falls in the warm-period months, so this
snapshot's microclimate (M) component and therefore its full A/V/M/I
integrated index rest on that now-removed substitution.

**What replaced it:** `research_results/final/` now holds an honest
`manuscript_readiness=false` record explaining that no full three-component
result is currently possible (no cold-period data exists for this
deployment, and the deployment is a confirmed standalone kitchen, not a
kitchen-dining space, so the general_residential profile cannot be
truthfully substituted either). `research_results/exploratory/` holds an
A/V-only (aerosol + ventilation) analysis over the same real dataset, using
the current code, clearly labeled as exploratory and never presented as
the manuscript's complete proposed method.

This directory is kept for provenance/audit only. Do not cite any number
from it as a current or valid result.
