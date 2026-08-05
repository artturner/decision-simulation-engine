# FDR / Korematsu — Iterative Improvement Log

Quantified via `scenario_iterations/analyze.py` (all paths through the real engine).
Judge: `--judge mock` (offline stand-in) / `--judge llm` (real Anthropic).
Stability: `stabilize_judge.py` runs the LLM judge K times and keeps only MAJORITY-flagged paths.

## Versions  (v4 = PROMOTED to root fdr-korematsu-import.json; 3 images published to R2)
- v0 original (archived) -> v1 state-gated endings -> v2 counterfactual scope branch
  -> v3 unilateral-military ending + Scene-5 de-dup -> **v4 ending-overclaim fix**.

## Structural + mock metrics

| Metric | v0 | v1 | v2 | v3 | v4 |
|---|---|---|---|---|---|
| paths | 36 | 36 | 37 | 38 | 38 |
| variables_read | 0 | 2 | 2 | 2 | 2 |
| influential choice pts | 1/3 | 3/3 | 4/4 | 4/4 | 4/4 |
| monotonicity inversions | 53 | 5 | 2 | 2 | 2 |
| outcomes reachable | 3 | 3 | 4 | 5 | 5 |
| contradictions (mock) | 27 | 27 | 0 | 0 | 0 |

## LLM judge (claude-sonnet-4-6) — the real narrative-contradiction metric
- v3 single pass: 3 contradictions (2 major + 1 minor), ALL on the `6.retreat`/principled_restraint
  ending — my v1 legacy-tier rewrite overclaimed ("consistently toward restraint", "spared its
  deepest self-inflicted wound") and collided with v2's new `removal_averted` outcome.
- **v4** re-scoped that ending ("couldn't prevent removal / sometimes came to support it, but kept it
  lawful and blunted the precedent"). Single pass then showed 1 minor on a DIFFERENT ending — which
  the stability pass proved was noise.
- **v4 stability (K=5, majority>=3, 190 calls, 0 errors): 0 STABLE contradictions.**
  Flaky (variance, not acted on): `[3,2,1,2]` 2/5, `[0,2,2]` 1/5. Clean: 36/38.

## Methodology finding (for the automated pre-image loop)
A single LLM judge pass is too noisy to gate on (v3 vs v4 flagged different endings run-to-run).
Use K-sample MAJORITY VOTING; act only on the stable set. The mock stand-in is a cheap CI check but
has false negatives (it missed the v3 6.retreat overclaim that the LLM caught) — the LLM judge is the
authority, voting makes it trustworthy.

## Images (published to media.cruxlabs.academy/fdr_korematsu/1/)
3 new, all serving valid PNGs: scene_2d_pressure.png, scene_6_removal_averted.png, scene_6_unilateral.png.
13 originals reused unchanged; `5.verdict` reuses scene_5.png.
