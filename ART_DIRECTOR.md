# The Art-Director Pattern — Coherent AI Images for Multi-Scene Works

A portable design for generating a *set* of AI images that look like they belong
together. Written to be lifted into any project (story-engine, scenario engine,
comic generator, slide decks). It assumes a text LLM plus an image model with no
cross-call memory (e.g. OpenAI `gpt-image-1` / `gpt-image-2`).

---

## The problem it solves

Image models have **no memory between calls** and **over-interpret evocative
language**. Feeding each scene's prose straight to the model produces two failures:

1. **Drift** — each image invents its own era / place / look, so the set is incoherent.
2. **Latching** — abstract or loaded phrases ("reform-minded", "party leadership")
   get rendered literally (a Progressive-Era office; authoritarian imagery) instead
   of the actual scene.

The **art-director pass** inserts an LLM "director" between the narrative and the
image model. Its only job: convert story prose into **literal, consistent,
model-friendly image prompts**.

---

## Core principle

**Separate what stays constant from what changes per image.**

- **Constant (decided once):** the *setting bible* — era, place, recurring characters
  and their appearance, wardrobe, locations, palette, and the rendering style.
- **Per-image:** only the specific moment — who is present, what they are doing,
  composition, lighting / mood.

Every prompt = `constant layer` + `this-moment layer`. Coherence comes from the
constant layer being **identical across all images**.

---

## Architecture

```
narrative (all scenes / chapters)
        │
        ▼
[1] Director LLM call  ── reads the WHOLE work at once
        │                 → infers ONE setting bible
        │                 → writes one literal prompt per image-bearing scene
        ▼
[2] Code layer        ── prepends a FIXED style preamble to each prompt
        │                 → per-item fallback to a template if the LLM omitted one
        ▼
[3] Image model       ── one call per prompt → bytes → store
```

Three deliberate choices make it work:

1. **One LLM call over the entire work.** The director sees all scenes together, so
   it commits to a single setting and reuses the same characters / locations
   everywhere. Per-scene calls (each blind to the others) reintroduce drift.
2. **Literal / concrete translation.** The director describes *only what is visible*
   and **translates abstract / political / ideological terms into neutral, concrete
   depictions**. The loaded words never reach the image model.
3. **Style applied in code, not by the LLM.** A fixed style string is concatenated
   onto every prompt deterministically — guarantees a uniform look and keeps the LLM
   focused on *content* rather than restating style (which it does inconsistently).

---

## The director prompt (reusable as-is)

System prompt:

```
You are the art director for an illustrated work. You write prompts for an AI
image model — one per scene — that are LITERAL and VISUALLY CONCRETE.

You are given the work's title and description and every scene's text. First infer
a single consistent SETTING for the whole work: time period, geographic/cultural
place, the recurring people and their roles, their attire, and the locations. Infer
this from the content. Do NOT assume a default country, culture, or era, and do NOT
force a modern or American setting — let the material decide. Only if it is genuinely
ambiguous, choose a neutral, realistic setting.

Then write one prompt per requested scene. For each prompt:
- Describe ONLY what is concretely visible: place, people (count, role, approximate
  age, attire), key objects, time of day, weather, and mood conveyed through
  lighting/composition.
- Anchor the era and place explicitly in EVERY prompt, identical across scenes.
- Keep recurring characters, wardrobe, and locations consistent scene to scene.
- Do NOT use abstract, political, ideological, or judgmental terms. Translate any
  such idea into a neutral, concrete depiction of people and place.
- No text, captions, logos, UI, charts, or speech bubbles.

Return JSON: a `setting_brief` string and a `prompts` array of objects with
`scene_id` (exactly as given) and `prompt`.
```

Structured-output JSON schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "setting_brief": { "type": "string" },
    "prompts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "scene_id": { "type": "string" },
          "prompt": { "type": "string" }
        },
        "required": ["scene_id", "prompt"]
      }
    }
  },
  "required": ["setting_brief", "prompts"]
}
```

Two notes:

- **Requiring `setting_brief`** forces the model to write the bible down *first*,
  which measurably improves cross-image consistency even if you never display it.
- **Echoing back the exact `scene_id`** lets you map prompts to scenes reliably.

Fixed style layer, prepended in **code**:

```
Editorial illustration, consistent across the set: painterly, cinematic lighting,
muted realistic palette, period- and context-accurate detail, no text, no captions,
no logos, no UI. 16:9 composition.
```

---

## Reference skeleton (Python — adapt freely)

```python
def art_direct(work, scenes, model, call_llm):
    """work: {title, description}; scenes: list[(scene_id, scene_dict)] needing images.
    call_llm(system, user, model, json_schema) -> str.
    Returns ({scene_id: final_prompt}, setting_brief)."""
    user = render_context(work["title"], work["description"], scenes)  # ALL scenes
    raw = call_llm(system=DIRECTOR_SYSTEM, user=user,
                   model=model, json_schema=DIRECTOR_SCHEMA)
    data = parse_json(raw)
    by_id = {
        p["scene_id"]: p["prompt"]
        for p in data.get("prompts", [])
        if p.get("scene_id") and p.get("prompt")
    }

    out = {}
    for scene_id, scene in scenes:
        body = by_id.get(scene_id) or template_prompt(scene)   # per-scene fallback
        out[scene_id] = f"{STYLE_PREAMBLE}\n\n{body.strip()}"
    return out, data.get("setting_brief", "")
```

Keep **prompt-writing decoupled from image generation/storage**, so you can
regenerate a single image without re-running the director.

---

## Adapting to a story-engine (the important deltas)

A story is longer, more character-driven, and spans more images than a one-shot
scenario. Add:

1. **A persistent setting + character bible, computed once and reused.** Run the
   inference once over a synopsis + cast, **store the bible**, and feed it as fixed
   context into every later prompt-writing call — continuity across chapters and
   across sessions, not just within one batch.

2. **Stable character descriptors (identity locking).** Image models cannot remember
   a face. Give each recurring character a **fixed, specific physical signature**
   (e.g. *"Mara, woman ~40, short auburn hair, wire-rim glasses, navy wool coat"*)
   and require the director to **repeat it verbatim** every time they appear. Vague
   references ("the captain") yield a different-looking person each time.

3. **Reference images for true identity persistence.** Text alone gets you "similar".
   If your image model supports **image-edit / reference inputs** (`gpt-image-2`
   does), generate one canonical portrait per main character and pass it as a
   reference on every scene that character appears in. This is the strongest lever
   for a long work where the same faces recur across dozens of images.

4. **Chunk long narratives.** Don't send a whole novel in one call. Infer the bible
   once; then write prompts per chapter in batches, always prepending the bible.

5. **Continuity fields.** Carry small structured state per scene —
   `characters_present`, `location`, `time_of_day` — so consecutive images respect
   what just happened (same room, nightfall progressing, etc.).

---

## Practical notes

- **Model:** a mid-tier text model is plenty for the director — it's a rewriting
  task, not deep reasoning. Cheap; one call (or one per chunk).
- **Structured output** for reliable parsing; **always keep a deterministic template
  fallback** per item so a flaky call never blocks the pipeline.
- **Exclusion rules** ("no text, no logos") live in the fixed style layer so they're
  always present.
- **Decouple regeneration:** store prompts and images separately so a single bad
  image can be re-rolled or hand-edited, and you can overwrite just that asset.
- **Cost:** director = 1 text call per work / chunk; images = 1 call each. The
  director is a rounding error next to image generation.

---

## Pitfalls

- Per-scene director calls (kills coherence) — do **one call** over the whole
  work / chunk.
- Letting the LLM own the style string (inconsistent) — **prepend it in code**.
- Vague character references (different face every time) — **fixed verbatim
  descriptors**, plus **reference images** for long works.
- Hardcoding a default era / locale — **infer from the material**; fall back to
  neutral only when genuinely ambiguous.
- Passing raw narrative prose to the image model — that's the original bug; the
  director's whole purpose is to replace it.

---

## Concrete sketch: character bible + reference images (gpt-image-2)

For a long, character-driven work, extend the director to also emit a **character
roster with stable descriptors**, generate **one canonical portrait per character**,
and then render each scene with `images.edit`, passing the present characters'
portraits as reference images. Two levers stack: verbatim descriptors (text) +
reference images (pixels).

> Verified against the OpenAI image-generation guide: reference images go through
> `client.images.edit(model="gpt-image-2", image=[...files], prompt=...)`, results
> come back as `b64_json`, and gpt-image-2 processes inputs at high fidelity
> automatically (no `input_fidelity` knob). The docs also caution that consistency is
> improved but **not guaranteed** — expect to re-roll the occasional stubborn scene.

### Extended director schema (adds characters + per-scene presence)

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "setting_brief": { "type": "string" },
    "characters": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "id":         { "type": "string" },
          "name":       { "type": "string" },
          "descriptor": { "type": "string" }
        },
        "required": ["id", "name", "descriptor"]
      }
    },
    "scenes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "scene_id":           { "type": "string" },
          "characters_present": { "type": "array", "items": { "type": "string" } },
          "prompt":             { "type": "string" }
        },
        "required": ["scene_id", "characters_present", "prompt"]
      }
    }
  },
  "required": ["setting_brief", "characters", "scenes"]
}
```

Add to the director system prompt (on top of the base rules above):

```
Also produce a `characters` roster: for every recurring character give a stable
`id`, a `name`, and a `descriptor` — a specific, physical, reusable signature
(approx age, build, hair, distinguishing features, default wardrobe). Reuse each
descriptor VERBATIM wherever the character appears.

For each scene, list `characters_present` (the character ids visible in it) and
embed each present character's descriptor verbatim in that scene's `prompt`.
```

### Image wrapper (generate vs. edit-with-references)

```python
import base64
from openai import OpenAI

client = OpenAI()                 # reads OPENAI_API_KEY
IMAGE_MODEL = "gpt-image-2"
SIZE = "1536x1024"

def generate_image(prompt: str, reference_paths: list[str] | None = None) -> bytes:
    """No refs -> images.generate. With refs -> images.edit (keeps identity)."""
    if reference_paths:
        files = [open(p, "rb") for p in reference_paths]
        try:
            resp = client.images.edit(
                model=IMAGE_MODEL, image=files, prompt=prompt, size=SIZE
            )
        finally:
            for f in files:
                f.close()
    else:
        resp = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=SIZE)
    return base64.b64decode(resp.data[0].b64_json)
```

### The bible + the two-pass flow

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Character:
    id: str
    name: str
    descriptor: str                       # stable, verbatim physical signature
    reference_path: str | None = None

@dataclass
class ScenePrompt:
    scene_id: str
    prompt: str                           # per-moment body (no style preamble yet)
    characters_present: list[str] = field(default_factory=list)

@dataclass
class Bible:
    setting_brief: str
    characters: dict[str, Character]
    scenes: list[ScenePrompt]

# --- Pass 1: build the bible (one LLM call over the whole work) ---------------
def build_bible(work, scenes_text, model, call_llm) -> Bible:
    raw = call_llm(system=DIRECTOR_SYSTEM_V2,
                   user=render_context(work, scenes_text),
                   model=model, json_schema=DIRECTOR_SCHEMA_V2)
    data = parse_json(raw)
    chars = {c["id"]: Character(c["id"], c["name"], c["descriptor"])
             for c in data["characters"]}
    scenes = [ScenePrompt(s["scene_id"], s["prompt"], s.get("characters_present", []))
              for s in data["scenes"]]
    return Bible(data["setting_brief"], chars, scenes)

# --- Build one canonical portrait per character (run once, then persist) ------
PORTRAIT = ("{style}\n\nHead-and-shoulders character portrait, neutral plain "
            "background, front-facing, even lighting. {descriptor} "
            "Setting context: {setting}.")

def build_character_refs(bible: Bible, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for char in bible.characters.values():
        prompt = PORTRAIT.format(style=STYLE_PREAMBLE,
                                 descriptor=char.descriptor,
                                 setting=bible.setting_brief)
        path = out_dir / f"char_{char.id}.png"
        path.write_bytes(generate_image(prompt))          # no refs: establishing shot
        char.reference_path = str(path)

# --- Pass 2: render each scene, passing present characters' portraits ----------
def render_scene(scene: ScenePrompt, bible: Bible, out_dir: Path) -> Path:
    present = [bible.characters[cid] for cid in scene.characters_present
              if cid in bible.characters]
    refs = [c.reference_path for c in present if c.reference_path]
    prompt = f"{STYLE_PREAMBLE}\n\n{scene.prompt}"
    if present:                                            # re-state descriptors too
        prompt += "\n\nCharacters present: " + " ".join(c.descriptor for c in present)
    path = out_dir / f"scene_{scene.scene_id}.png"
    path.write_bytes(generate_image(prompt, reference_paths=refs or None))
    return path

# --- Orchestration ------------------------------------------------------------
bible = build_bible(work, scenes_text, model="claude-sonnet-4-6", call_llm=my_llm)
build_character_refs(bible, Path("refs"))                 # once per work
for scene in bible.scenes:
    render_scene(scene, bible, Path("images"))
```

### Why it's shaped this way

- **Descriptors AND references, together.** Pixels (reference images) lock identity
  best; the verbatim text descriptor is the belt-and-suspenders fallback and steers
  pose/wardrobe in the new scene.
- **Portraits generated once, then persisted.** Save the bible (as JSON) and the
  portrait PNGs so re-runs — and future sessions — reuse the *same* faces. This is
  what gives continuity across a long work, not just within one batch.
- **Pass only the present characters' references** (cap ~3–4 per scene). Throwing
  every character's portrait at every scene blends identities and muddies results.
- **Location continuity bonus:** you can also pass a *previous scene's image* as an
  extra reference when two scenes share a location, to carry the room/landscape over.
- **Cost:** 1 director call + 1 portrait per character + 1 image per scene. The edit
  calls cost the same ballpark as generate; the director is negligible.
- **When it still drifts:** re-roll just that scene (decoupled generation makes this
  cheap), tighten the descriptor, or add a second reference angle for that character.

---

## Origin

Extracted from the scenario engine's `image_prompts.build_prompts_llm`
(`services/api/scripts/scenario_gen/image_prompts.py`) in this repo, generalized for
reuse in other multi-scene image pipelines.
