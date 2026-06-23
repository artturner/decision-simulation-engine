"""Build image-generation prompts, one per scene.

Two builders:
- ``build_prompts`` — deterministic template (fallback; no LLM).
- ``build_prompts_llm`` — an "art-director" pass that reads the whole scenario and
  writes literal, visually-concrete prompts with a single inferred setting applied
  consistently. This avoids the image model latching onto abstract/political phrasing
  in learner-facing prose (e.g. "reform-minded", "party leadership").
"""

from __future__ import annotations

from collections.abc import Callable

from . import llm

# A shared style preamble prepended to every scene prompt keeps the set visually
# coherent (gpt-image-1 has no seed; consistency comes from the description).
STYLE_PREAMBLE = (
    "Editorial illustration for an educational decision scenario. Consistent across "
    "the set: painterly, cinematic lighting, muted realistic palette, period- and "
    "context-accurate detail, no text, no captions, no logos, no UI, no word bubbles. "
    "16:9 composition."
)

_ART_DIRECTOR_SYSTEM = """\
You are the art director for an educational decision scenario. You write prompts for an
AI image model — one per scene — that are LITERAL and VISUALLY CONCRETE.

You are given the scenario's title and description and every scene's text. First infer a
single consistent SETTING for the whole scenario: time period, geographic/cultural place,
the recurring people and their roles, their attire, and the locations. Infer this from the
content. Do NOT assume a default country, culture, or era, and do NOT force a modern or
American setting — let the scenario decide. Only if the scenario is genuinely ambiguous,
choose a neutral, realistic contemporary setting.

Then write one prompt per requested scene. For each prompt:
- Describe ONLY what is concretely visible: place, people (count, role, approximate age,
  attire), key objects, time of day, weather, and mood conveyed through lighting/composition.
- Anchor the era and place explicitly in EVERY prompt, identical across scenes.
- Keep recurring characters, wardrobe, and locations consistent scene to scene.
- Do NOT use abstract, political, ideological, or judgmental terms (e.g. "reform-minded",
  "party leadership", "progressive", "regime"). Translate any such idea into a neutral,
  concrete depiction of people and place.
- No text, captions, logos, UI, charts, or speech bubbles.

Return JSON matching the schema: a `setting_brief` string and a `prompts` array of
objects with `scene_id` (exactly as given) and `prompt`.
"""

_ART_DIRECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "setting_brief": {"type": "string"},
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scene_id": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["scene_id", "prompt"],
            },
        },
    },
    "required": ["setting_brief", "prompts"],
}


def _scene_filename(scene_id: str, scene: dict) -> str:
    image = scene.get("image")
    if isinstance(image, str) and image and not image.startswith(("http://", "https://")):
        return image.rsplit("/", 1)[-1]
    safe = scene_id.replace(".", "_").replace(" ", "_")
    return f"scene_{safe}.png"


def build_prompt_for_scene(scene: dict) -> str:
    """Compose one image prompt from a scene's title/description/narration."""
    title = (scene.get("title") or "").strip()
    description = (scene.get("description") or "").strip()
    # Narration can be long; the visual cue is usually the setting/description.
    narration = (scene.get("narration") or "").strip()
    subject = description or narration[:400] or title
    parts = [STYLE_PREAMBLE, "", f"Scene: {title}".strip(), subject]
    return "\n".join(p for p in parts if p).strip()


def _image_targets(scenario_json: dict) -> list[tuple[str, dict]]:
    """Scenes that need a prompt: have an ``image`` that isn't already a hosted URL."""
    targets: list[tuple[str, dict]] = []
    for scene_id, scene in scenario_json.get("scenes", {}).items():
        image = scene.get("image")
        if image is None:
            continue
        if isinstance(image, str) and image.startswith(("http://", "https://")):
            continue
        targets.append((scene_id, scene))
    return targets


def build_prompts(scenario_json: dict) -> dict[str, dict]:
    """Deterministic template builder: {scene_id: {filename, prompt}}."""
    return {
        scene_id: {
            "filename": _scene_filename(scene_id, scene),
            "prompt": build_prompt_for_scene(scene),
        }
        for scene_id, scene in _image_targets(scenario_json)
    }


def _art_director_user_text(scenario_json: dict, targets: list[tuple[str, dict]]) -> str:
    meta = scenario_json.get("metadata", {})
    lines = [
        f"Scenario title: {meta.get('title', '')}",
        f"Scenario description: {meta.get('description', '')}",
        "",
        "Write one image prompt for each of these scenes (use the exact scene_id):",
        "",
    ]
    for scene_id, scene in targets:
        body = (scene.get("description") or "").strip()
        narration = (scene.get("narration") or "").strip()
        text = body or narration[:500]
        lines.append(f"[{scene_id}] {(scene.get('title') or '').strip()}")
        if text:
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def build_prompts_llm(
    scenario_json: dict,
    model: str,
    *,
    call_fn: Callable[..., str] | None = None,
) -> dict[str, dict]:
    """Art-director builder: infer one setting from the whole scenario and write
    literal, consistent prompts. Falls back to the template for any scene the model
    omits. ``call_fn`` is injectable for testing.
    """
    targets = _image_targets(scenario_json)
    if not targets:
        return {}

    call = call_fn or llm.call_text
    text = call(
        system=_ART_DIRECTOR_SYSTEM,
        content=[{"type": "text", "text": _art_director_user_text(scenario_json, targets)}],
        model=model,
        max_tokens=4000,
        json_schema=_ART_DIRECTOR_SCHEMA,
    )
    data = llm.extract_json(text)
    by_id = {
        p["scene_id"]: p["prompt"]
        for p in (data.get("prompts", []) if isinstance(data, dict) else [])
        if isinstance(p, dict) and p.get("scene_id") and p.get("prompt")
    }

    out: dict[str, dict] = {}
    for scene_id, scene in targets:
        body = by_id.get(scene_id)
        prompt = (
            f"{STYLE_PREAMBLE}\n\n{body.strip()}"
            if body
            else build_prompt_for_scene(scene)  # per-scene fallback
        )
        out[scene_id] = {"filename": _scene_filename(scene_id, scene), "prompt": prompt}
    return out
