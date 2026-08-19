# Run status

**Run**: `20260818_peer_review_revision_v2`
**Started**: 2026-08-19 (Raspberry Pi 5, local session)
**Data interval**: 2026-06-18T00:00:00Z (inclusive) to 2026-08-16T00:00:00Z
(exclusive) -- through 2026-08-15.
**Pipeline run reused**: `7f04698725dd4f35a432ba4a0de2934f` (unchanged; see
`baseline/baseline_run_manifest.json`).
**Evaluation run**: `74deb744a581423b99e4cb7e68be33ce` (full 101^3 grid).

## Git safety (task section 2, verified before any change)

- Initial branch: `main`
- Initial tree: clean
- Initial commit: `a1232dafe14c15d7d62a25954f5589bf9406de13`
- Remote: `https://github.com/ivanborodii/air-index.git`
- Local main == origin/main at start (fetched and confirmed)
- Disk space at start: 75G available (31% used) -- ample

## What was fixed (task section 5)

1. Causal LOCF (position-based -> time-based) -- `src/iaq_hfis/research_helpers.py::causal_locf`
2. Dominance-tie detection (`len(list)>0` -> `len(set(list))>1`) -- `has_dominance_tie`
3. Direct-input attribution (percentile rank -> membership-class-based) -- `most_adverse_direct_input`
4. Real chronological class flapping (new; replaces arbitrary-trial-order metric)
5. Grid manifest defect (41 actual vs. 101 claimed) -- fixed procedurally, full grid rerun and verified

All four core fixes have new, passing unit tests (34 total) in
`tests/unit/test_research_helpers.py`.

## What was rerun / newly created

| Experiment | Status | Notes |
|---|---|---|
| Section 3: snapshot + interval verification | Done | Independently reverified, matches prior run exactly |
| Section 4: baseline manifest | Done | Pipeline reused, not rerun (unaffected by fixes) |
| Evaluate (full 101^3 grid) | Done | 1,030,301 rows confirmed |
| Experiment A: missing-data strategy | Done | Causal LOCF fix + lookback sweep; scope-limited (see limitations.md) |
| Experiment B: pollution/microclimate | Done | Tie + attribution fixes |
| Experiment C: second-level equivalence | Done | Full grid + boundary buckets + 250k random + formal analysis |
| Experiment D: stability + real-time flapping | Done | Existing paired-trial analysis reused; new chronological flapping added |
| Experiment E: Hampel sweep | Done | No defect found; rerun only |
| Experiment F: membership audit + PM10 sensitivity | Done | PM10 width sweep added (was missing) |
| Experiment G: data quality reasons | Done | Independently reverified |
| Experiment H: runtime profiling | Done | Rerun only; filenames differ from spec (documented in evidence matrix) |

## Quality gates

- [x] Baseline test suite (before changes): 457 passed, 0 failed (`test_report_before.txt`)
- [x] New unit tests for every corrected defect (34 tests, all passing)
- [x] Full requested timestamp interval independently verified (0 leaks, 0 duplicates, 0 ordering violations)
- [x] Grid point count cross-checked against manifest claim (`verify_grid_point_count`, 1,030,301 == 101**3)
- [x] Final test suite (after changes): 491 passed, 0 failed (43m26s) -- see `test_report_after.txt`
- [x] Promotion: `research_results/final/CURRENT_RUN.txt` added, pointing to this run (production pipeline artifacts under `research_results/final/` unchanged -- see that file for why)
- [ ] Commit and push: in progress

## Known scope limitations (see `limitations.md` for full detail)

- Missing-data strategy: single-timestamp masking only (no contiguous 5/10/15/30-min intervals); calibration/validation split only (no held-out test) -- section 6.6 promotion decision not evaluated.
- Runtime profiling deliverable filenames differ from the task's requested names (equivalent content, different file layout).
- No single global multiple-comparison correction across all experiments combined.

This file will be updated with final commit SHA and push confirmation once
the remaining quality gates pass.
