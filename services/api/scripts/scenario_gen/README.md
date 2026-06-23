# Scenario Generator (`scripts.scenario_gen`)

Turn a source PDF into a ready-to-import branching scenario.

## What it does

PDF (local path or URL) → propose candidate subjects → you pick one → generate a
best-practices branching scenario → validate it against the engine
(`engine.validator.validate_scenario`) with a self-repair loop → write:

- `<slug>-import.json` — the import body for `POST /api/v1/admin/scenarios/import`
- `<slug>-image-prompts.json` — one image prompt per scene

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
`--slug`, `--images`, `--gen-model`, `--scout-model`, `--non-interactive`.

## Required environment (services/api/.env)

- `ANTHROPIC_API_KEY` — subject scouting + scenario generation
- `OPENAI_API_KEY` — only for `--images`
- `R2_*` + `R2_PUBLIC_URL` — only for `--images`; set `R2_PUBLIC_URL` to the public
  base (e.g. `https://media.cruxlabs.academy`) so uploaded URLs are the public ones.

Model defaults (overridable via env or flags): `SCENARIO_GEN_MODEL=claude-opus-4-8`,
`SCENARIO_SCOUT_MODEL=claude-sonnet-4-6`, `SCENARIO_IMAGE_MODEL=gpt-image-1`.

The output JSON format is the contract in `branching_scenario_generator_system_prompt_1.md`
(and `SAMPLE_SCENARIO.json`); both are fed to the model as system context.
