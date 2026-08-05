# Automated Quality Loop — Benchmark Results (2026-07-04)

Loop: `services/api/scripts/scenario_gen/quality.py` (structural gate → K=5
majority-vote LLM judge → Opus reviser, keep-best, ≤3 iters/run). Runner:
`scenario_iterations/run_quality_loop.py`. Repair runs chain by feeding
`.revised.json` back in with `--judge-on-pass`.

## Severe repair targets (must improve)

| target | before (as-was) | after (loop) | runs×iters | verdict |
|---|---|---|---|---|
| cherokee-nation | vars_read 0, infl 0/1, 1 outcome | vars_read 3, infl 1/1, 3 outcomes, 0 stable contra | 1×2 | **PASSED** |
| rio-grande (library worst) | vars_read 0, infl 0/3, 1 outcome, 2 stable contra | vars_read 3, infl 4/4, 4 outcomes, 0 stable contra | 3 chained (7 revisions) | **PASSED** |
| fdr v0 (ground truth) | vars_read 0, infl 1/3, 3 outcomes, 13 stable contra | vars_read 2, infl 3/3, 3 outcomes, **1 stable (minor)** | 2 chained (6 revisions so far) | 1 minor from the bar; one more chained run recommended |

- Hand-made v4 reference bar: vars_read 2, infl 4/4, 5 outcomes, 0 stable. The
  loop's fdr structural repair (1 revision) matches the v1 hand-fix shape
  exactly (conditional resolver reading ConstitutionalLegitimacy/CivilLiberties,
  endings reframed as tiers). Stage 2 (narrative) converged 11→3→1; its 4th
  revision REGRESSED (1→5 stable) and **keep-best correctly discarded it**,
  returning the 1-stable version (`fdr-v0.revised.revised.json` = that best).
  Remaining flag: the `6.candid` middle ending calls the record "ambivalent"
  on a path that chose the broadest removal scope. Finish with:
  `py -3.11 scenario_iterations/run_quality_loop.py scenario_iterations/benchmark/fdr-v0.revised.revised.json --judge-on-pass --iters 2`
- Repair economy: every repair reused existing images (cherokee +1 scene,
  rio-grande +2 scenes, 0 new image files).

## Negative controls (must be left untouched)

| control | gate | judge spend | revisions |
|---|---|---|---|
| shaping-the-aca (243 paths — scalability) | PASS | 0 calls | 0 |
| the-marshall-gambit | PASS | 0 calls | 0 |

## Workstream A (generator prompt fix) — born quality

Regenerated from the U.S. Constitution PDF (govinfo CDOC-110hdoc50), quality
loop disabled, then gate-scored:

| regen | born metrics | gate at birth |
|---|---|---|
| regen-check-1 (Great Compromise, 23 scenes) | vars_read 3, infl 5/5, 6 outcomes | **PASS** |
| regen-check-2 (25th Amendment, 23 scenes) | vars_read 4, infl 4/5, 4 outcomes | FAIL (1 inert choice) → loop repaired end-to-end: infl 5/5, 5 outcomes, 0 stable contra — **PASSED** (2 chained runs) |

Old baseline for comparison: 3–4 of 11 library scenarios were severely broken
(W/C/G flags). Both regens under the new prompt are state-gated at birth; one
fully passes, the other trips a single check that the loop then fixes — the
intended belt (prompt) + suspenders (loop) behavior.

## Key operational findings

1. **Structural failures fix in ONE revision** once findings include the
   end-scene→outcome-code map (distinct endings are counted by `outcome` code —
   the reviser's original blind spot was giving every ending `success`).
2. **Narrative contradictions converge monotonically** (rio: 4→3→2→1→0) but
   often need more than one 3-iteration run — chain repair runs. The dominant
   failure shape: endings that enumerate hypothetical decision arcs; guidance
   added to the reviser addendum.
3. **Judge robustness**: judge/reviser API failures no longer crash the loop or
   produce vacuous passes (`all_errors` guard; keep-best exit).
