# Scenario Generator (`scripts.scenario_gen`)

Turn a source PDF into a ready-to-import branching scenario.

## What it does

PDF (local path or URL) → propose candidate subjects → you pick one → generate a
best-practices branching scenario → validate it against the engine
(`engine.validator.validate_scenario`) with a self-repair loop → **quality loop**
(below) → write:

- `<slug>-import.json` — the import body for `POST /api/v1/admin/scenarios/import`
- `<slug>-image-prompts.json` — one image prompt per scene
- `<slug>-quality-report.json` — per-version gate metrics, judge results, verdict

## Quality loop (pre-image)

Before any image spend, `quality.run_quality_loop` gates the generated scenario
(cost-ordered):

1. **Structural gate** (free): every root→end path is walked through the real
   engine. Requires: declared variables are READ by a conditional, every choice
   point can change the outcome, ≥2 outcomes reachable.
2. **LLM contradiction judge** (only when needed): K-sample majority vote per
   path (`--judge-k`, default 5) — single passes are too noisy to gate on. Only
   STABLE (majority-flagged) contradictions count.
3. **Reviser**: on failure, the gen model rewrites the scenario from the
   findings; each revision is re-validated and re-scored, the best version is
   kept, iterations capped at `--quality-iters` (default 3).

Default mode is **advisory** (warn + report, images proceed); `--strict`
blocks the image step on a failing gate (exit code 2). `--no-quality` skips the
loop; `--no-judge` keeps the structural gate but skips LLM judging.

To run the same loop on an existing import JSON (repair or benchmark):
`py -3.11 scenario_iterations/run_quality_loop.py <import.json> [--gate-only]`
(writes `<input>.revised.json` + report; never overwrites the original).
For repair runs add `--judge-on-pass` (existing files don't get the
as-generated benefit of the doubt). Structural failures typically fix in one
revision; narrative contradictions converge monotonically but can need more
than one 3-iteration run — chain runs by feeding `.revised.json` back in until
PASSED (benchmarks: rio-grande needed 3 chained runs from the worst library
state to a full pass).

Image prompts are written by an **art-director pass**: an LLM reads the whole scenario
(title, description, every scene) and infers a single consistent setting (era, place,
recurring people), then writes literal, visually-concrete prompts anchored to that setting.
This keeps the image set coherent and stops the image model from over-interpreting abstract
or political phrasing in the learner-facing text. It infers the setting from the scenario —
no hardcoded country/era — and falls back to a deterministic template if the LLM call fails.

With `--images`, it also generates each scene image (OpenAI `gpt-image-1`), uploads
to Cloudflare R2 (reusing `app.services.storage.upload_media`), and rewrites each
scene's `image` to the absolute hosted URL.

It does **not** import anything — you POST the JSON via Postman as usual.

## Usage

Run from `services/api` (so `app`, `engine`, and `scripts` are importable):

```bash
python -m scripts.scenario_gen --pdf path/to/source.pdf
python -m scripts.scenario_gen --pdf https://example.com/source.pdf --images
python -m scripts.scenario_gen --pdf source.pdf --non-interactive --slug my-topic
```

Flags: `--pdf` (required), `--out <dir>` (default repo root), `--subjects N`,
`--slug`, `--images`, `--gen-model`, `--scout-model`, `--non-interactive`,
`--strict`, `--no-quality`, `--no-judge`, `--quality-iters N`, `--judge-k N`,
`--min-decisions N`.

`--min-decisions N` requires every route from start to an ending to pass
through at least N choice scenes. The floor is enforced *during generation*:
a shortfall is injected as a validation error into the model's self-repair
loop (engine errors are reported first; prompt-level depth instructions alone
under-deliver, while the injected error fixes depth on the first retry).
Default 0 (off). The measured floor is surfaced as `decisions_min` in each
version's metrics in the quality report.

## Required environment (services/api/.env)

- `ANTHROPIC_API_KEY` — subject scouting + scenario generation
- `OPENAI_API_KEY` — only for `--images`
- `R2_*` + `R2_PUBLIC_URL` — only for `--images`; set `R2_PUBLIC_URL` to the public
  base (e.g. `https://media.cruxlabs.academy`) so uploaded URLs are the public ones.

Model defaults (overridable via env or flags): `SCENARIO_GEN_MODEL=claude-opus-4-8`,
`SCENARIO_SCOUT_MODEL=claude-sonnet-4-6`, `SCENARIO_IMAGE_MODEL=gpt-image-1`.

The output JSON format is the contract in `branching_scenario_generator_system_prompt_1.md`
(and `SAMPLE_SCENARIO.json`); both are fed to the model as system context.
