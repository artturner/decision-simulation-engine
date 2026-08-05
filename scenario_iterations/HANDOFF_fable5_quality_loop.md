# Handoff — Automated Scenario Quality Loop + Conditional Variable Utilization

**For:** Fable 5 · **From:** Opus 4.8 session (2026-07-04) · **Repo:** decision-simulation-engine

You are picking up a project to (A) make the scenario generator **reliably emit
state-gated scenarios** ("conditional variable utilization") and (B) build an
**automated quality loop** that measures and repairs a generated scenario *before*
image generation. This is grounded in a fully-worked manual case study and a
sweep of the existing scenario library. Everything below is verified against the
current code.

---

## 0. TL;DR of what to build

1. **Workstream A — Prevention (highest leverage, cheapest).** Fix the generator
   system prompt so scenarios are *born* state-gated: variables that are actually
   read by conditional endings, early choices with real downstream consequences,
   ≥2 reachable outcomes, every choice point influential.
2. **Workstream B — Cure (the loop).** Insert a quality gate + LLM reviser into the
   generation pipeline right after `generate_scenario()` and before image prompts.
   Gate = cheap structural metrics + LLM contradiction judge (majority-voted).
   Reviser = an LLM that consumes the findings and rewrites the `scenario_json`,
   with validate/re-score/keep-best/max-iters guards.

You have a ground-truth benchmark (fdr-korematsu v0→v4) and severe library repair
targets (rio-grande, cherokee-nation) to measure the loop against.

---

## 1. Evidence base

### 1a. Manual case study: fdr-korematsu v0 → v4
See `scenario_iterations/fdr-korematsu/COMPARE.md` and the `build_v1..v4.py`
scripts (each is a documented, minimal transform from the prior version).

| Metric | v0 (as generated) | v4 (hand-fixed) |
|---|---|---|
| variables_read | 0 (write-only) | 2 |
| influential choice points | 1/3 | 4/4 |
| monotonicity inversions | 53 | 2 |
| outcomes reachable | 3 | 5 |
| stable LLM contradictions | (n/a) | 0 (K=5 vote) |

The four fixes, in order (this is the *shape* the reviser must be able to produce):
- **#1 state-gated endings** — replaced choice-hardcoded outcomes with a
  `conditional` resolver scene that reads accumulated variables and routes to the
  existing end scenes (reframed as legacy tiers). Zero new images.
- **#2 counterfactual scope branch** — an early choice that was silently ignored
  downstream got a real branch (+ a new outcome). Some new scenes/images.
- **#3 new outcome + #4 dedup** — added a state-distinct ending; de-duplicated a
  reveal. Mostly text.
- **v4** — fixed an ending whose narration over-claimed relative to the paths that
  reach it (caught only by the LLM judge, not the structural metrics or the mock).

### 1b. Library sweep (the prevalence + range data)
Run: `PYTHONUTF8=1 PYTHONPATH="packages/engine/src;packages/expr/src" py -3.11 scenario_iterations/library_sweep.py`
Snapshot saved at `scenario_iterations/library_baseline.txt`. Flags: **W**=all vars
write-only, **C**=zero conditional scenes, **G**=some choice points don't change outcome.

```
scenario                     scn vars read w-only cond infl/choice paths outc  flags
cherokee-nation               14    0    0      0    0         0/1     3    1   .CG   <- 1 outcome, choice inert
convention-1787                7    2    2      0    1         2/2     9    3   ...   ok
drawing-the-lines             11    4    3      1    1         4/4     9    3   ...   ok
liberty-park                  15    0    0      0    0         2/4    15    3   .CG   2 of 4 choices inert
motor-voter                   11    4    3      1    1         3/3    27    3   ...   ok
party-realignment             10    0    0      0    0         2/2     4    3   .C.   stateless but branches
probable-cause                10    0    0      0    0         3/3     5    3   .C.   stateless but branches
rio-grande                    12    3    0      3    0         0/3    12    1   WCG   WORST: 0/3 matter, 1 outcome
shaping-the-aca               22    4    3      1    1         5/5   243    4   ...   ok (large)
the-marshall-gambit           14    4    3      1    3         3/3    15    4   ...   ok
fdr-korematsu (v0 as-gen)     13    4    0      4    0         1/3    36    3   WCG   the manual case
fdr-korematsu (v4 fixed)      17    4    2      2    1         4/4    38    5   ...   fixed reference
```

**Key takeaway: the generator's output is bimodal, not uniformly broken.**
- ~5/11 are properly state-gated (conditionals + read variables + all choices matter).
- ~2/11 are stateless but still branch acceptably (choice-tree, no accumulated state).
- ~3–4/11 are broken: inert choices and/or only one reachable outcome.

**Benchmark set for the loop:**
- *Severe repair targets* (must improve): `rio-grande`, `cherokee-nation`, fdr `v0`.
- *Fully-worked ground truth*: fdr `v0` → `v4` (the loop should reach comparable metrics).
- *Negative controls* (must be left ~untouched / pass the gate): the "ok" cluster,
  especially `shaping-the-aca` (243 paths — also a scalability test).

---

## 2. What already exists (reuse; do not rebuild)

Under `scenario_iterations/`:
- **`analyze.py`** — walks every root→end path through the REAL engine and computes
  metrics. GENERIC (transfer to any scenario): `variables_read_count`,
  `influential_points`/`choice_points`, `outcomes_reachable`, `paths`. Also has a
  `--judge {none,mock,llm}` hook.
- **`contradiction_judge.py`** — the narrative-contradiction metric. `make_anthropic_judge_fn`
  mirrors `app.services.ai_grader` (Anthropic `messages.create`, structured output via
  `extra_body`, model `settings.AI_GRADER_MODEL` = `claude-sonnet-4-6`). Also a deterministic
  `make_heuristic_judge_fn` offline stand-in.
- **`stabilize_judge.py`** — runs the LLM judge K times per path and keeps only
  MAJORITY-flagged paths (the trustworthy set). Use this, not a single pass.
- **`library_sweep.py`** — the generic library profiler (section 1b).
- **`build_v1..v4.py`** — the manual transforms; read these to see the concrete edit
  shapes a reviser must be able to generate.

### Engine capabilities (what state-gating can use)
- `packages/engine` supports scene types: `choice`, `auto_advance`, **`conditional`**, `end`.
  A `conditional` scene has `conditions: [{condition, next}]` + optional `default`.
- Expression grammar (`packages/expr`): `&&  ||  !  ==  !=  <  <=  >  >=`, parens,
  numbers, `true`/`false`. **NO ARITHMETIC** (`+`, `-` between vars is not supported).
  → Tiering must use **per-variable threshold conditions**, e.g.
  `ConstitutionalLegitimacy >= 4 && CivilLiberties >= 2` — not `A + B >= 6`.
  `safe_evaluate` is fail-closed (returns false on unknown var / parse error).
- The web client renders a `conditional` scene as a **visible ContinueScene beat**
  (not an invisible auto-step), so a resolver scene should carry purposeful narration.

### Pipeline (where the loop hooks in)
- Entry: `services/api/scripts/scenario_gen/cli.py` → `main()`.
  Order today: `generate_scenario()` (**line ~75**) → image prompts (always) →
  `--images` upload (line ~95) → **`validate_scenario()` (line ~107, AFTER images)** →
  write `<slug>-import.json`.
  → **Insert the loop right after line 75; move validation before the image step.**
- `generate.py` already has a **generate→validate→self-repair loop** — but it only
  repairs to pass the *structural validator*, not quality. Extend this pattern.
- Generator system prompt: `branching_scenario_generator_system_prompt_1.md`
  (pedagogy: `SCENARIO_SKILL.md`). It instructs "2–4 tracking variables" + `effects`
  but does **not** require conditional endings that READ them — the root cause.
- Generation model: `settings.SCENARIO_GEN_MODEL` = `claude-opus-4-8`.

---

## 3. Workstream A — Conditional Variable Utilization (prompt fix)

**Goal:** every generated scenario satisfies the generic gate at birth.

**Edit `branching_scenario_generator_system_prompt_1.md` to REQUIRE:**
1. If variables are declared, at least one `conditional` scene must READ them (no
   write-only "decorative" variables).
2. Final outcome selection should be **state-gated** through a `conditional`
   resolver (accumulated variables → which end scene), not hardcoded per choice —
   unless the branch structure itself already makes every choice consequential.
3. Early/scope choices must have **downstream consequences** (don't converge silently).
4. **≥2 outcomes reachable**; **every choice point influential**.
5. Conditions use **per-variable thresholds only** (no arithmetic — see §2).

**Validate the fix empirically:** regenerate 2–3 subjects and re-run
`library_sweep.py`; expect the W/C/G flags to clear at birth. This is cheaper and
higher-leverage than repairing after the fact.

---

## 4. Workstream B — Automated Quality Loop

**Architecture (cost-ordered):**
```
generate_scenario()
   │
   ├─ cheap gate: analyze.py structural metrics (+ generic mock)   # free, instant
   │     pass? ──────────────────────────────────────────────┐
   │     fail                                                 │
   ├─ LLM judge (stabilize_judge, K-sample majority vote)     │   # only if cheap gate is ambiguous/failed
   │     stable contradictions == 0 and metrics pass? ───────►│ proceed → image prompts → images
   │     else                                                 │
   └─ REVISER (LLM): (scenario_json + failing metrics +       │
        stable findings) → revised scenario_json              │
        → validate → re-score → keep-best → loop (max iters) ─┘
```

**Key methodology finding (proven this session):** a *single* LLM judge pass is too
noisy to gate on — v3 and v4 runs flagged *different* endings. Use **K-sample
majority voting** (`stabilize_judge.py`). The mock stand-in is a useful free CI gate
but has **false negatives** (it missed the v4 ending over-claim the LLM caught), so
the LLM judge is the authority; voting makes it trustworthy.

**The reviser is the unproven crux.** It must produce edits of the shape in
`build_v1..v4.py` (add a conditional resolver, reframe endings, add a branch/outcome,
fix over-claiming narration). Guardrails: re-validate every revision; re-score; keep
the best-scoring version; cap iterations; prefer targeted per-finding edits over
whole-file rewrites. **Benchmark it** by starting from fdr `v0` and the severe library
cases and checking it reaches metrics comparable to the hand-made `v4` — and that it
leaves the "ok" cluster essentially untouched.

---

## 5. Prerequisite: generalize the harness (currently fdr-tuned)

Three spots are specialized to fdr-korematsu and must be generalized before
library-wide contradiction/monotonicity scoring:
- `contradiction_judge.py` `_JUDGE_SYSTEM` prompt names removal/citizens specifics →
  make scenario-agnostic (feed it the scenario's own premise, not hardcoded facts).
- `analyze.py` `VIRTUE_VARS` + `OUTCOME_RANK` (monotonicity + contradiction predicate)
  are fdr-specific → make config-driven or infer per scenario. The other structural
  metrics are already generic.
- `contradiction_judge.py` `make_heuristic_judge_fn` rules (`_NARROWER_SCOPE`,
  `_REMOVAL_RAIL`) are fdr-specific → generalize or treat mock as fdr-only.

---

## 6. Open decisions (need a human/product call)
- **Acceptance thresholds:** e.g. `variables_read ≥ 1` (if vars declared),
  `influential == choice_points`, `outcomes_reachable ≥ 2`, `stable_contradictions == 0`,
  and a monotonicity bound once generalized. Calibrate against the library distribution.
- **Gate mode:** advisory (warn) vs hard-block before images (`--strict`).
- **Budget:** K (samples/path), max reviser iterations, model tier per step.
- **Reviser ambition:** fully-automated vs human-in-the-loop (gate reports, human approves).

---

## 7. Environment & ops (so commands actually run)
- Use **`py -3.11`** (has `anthropic` 0.116.0, `openai`, `fastapi`, all deps). The
  agent-sandbox `python` on PATH is a separate venv with only some deps and no pip.
- Secrets live in `services/api/.env`; pydantic `env_file=".env"` resolves relative to
  **CWD**, so run judge/image/generation tools **from `services/api`**.
- On Windows set **`PYTHONUTF8=1`** (scripts print unicode; cp1252 console errors otherwise).
- Models: gen `claude-opus-4-8`, scout/art-director + judge `claude-sonnet-4-6`,
  images `gpt-image-2`.
- Anthropic calls: mirror `app/services/ai_grader.py` (structured output via `extra_body`).
- Publishing is DB-backed via the admin API (`/api/v1/admin/scenarios/import` →
  `/versions` → `/versions/{n}/publish`); no deploy-time seeding, so a git push does NOT
  publish. Admin API is ID-keyed (no slug lookup); get a draft's id via SQL
  `SELECT id FROM scenarios WHERE slug='…'`.

## 8. Suggested first steps
1. Generalize the judge prompt (§5) — unblocks library-wide contradiction scoring.
2. Wire the **advisory** gate into `cli.py` after `generate_scenario()` (§2 hook) — low risk.
3. Fix the generator prompt (§3) — regenerate + re-sweep to confirm flags clear.
4. Prototype the reviser (§4); benchmark against fdr v0→v4 and rio-grande/cherokee-nation.
```
```
