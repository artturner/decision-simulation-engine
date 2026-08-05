"""Re-run the image pipeline on an EXISTING scenario — no PDF, no regeneration.

Use this to refresh scene images for a scenario that was created before (or without)
the art-director prompt pass, or whose images have drifted from the text. It loads a
scenario from its ``<slug>-import.json``, re-runs the art-director pass over the whole
scenario (one inferred setting, literal/consistent prompts), and renders new images.

By default it is a DRY RUN: images are written to a local preview folder and nothing is
uploaded or overwritten. Pass ``--upload`` to push the new PNGs to R2 (replacing the
existing objects at the same keys) and write an updated import file you can re-import.

Run from services/api:

    # 1) Preview only (safe): render PNGs locally, write the fresh prompts
    python -m scripts.scenario_gen.redo_images --scenario shaping-the-aca

    # 2) Happy with the preview? Upload to R2 and write the updated import file
    python -m scripts.scenario_gen.redo_images --scenario shaping-the-aca --upload

Other flags:
    --scenes 1,2a,3   Only redo these scene ids (default: all scenes with an image).
    --force           Also redo scenes whose image is already a hosted URL.
    --prompts-file P  Use prompts from P instead of re-running the art director.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import REPO_ROOT, assemble, image_prompts, images


def _resolve_import_path(scenario: str, out_dir: Path) -> Path:
    """Accept a path to an ``-import.json`` file, or a bare slug/title that maps to
    ``<slug>-import.json`` in the output dir."""
    p = Path(scenario)
    if p.is_file():
        return p
    slug = assemble.slugify(scenario.removesuffix("-import.json").removesuffix(".json"))
    candidate = out_dir / f"{slug}-import.json"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Could not find a scenario for '{scenario}'. Looked for a file at that path "
        f"and at {candidate}."
    )


def _load(import_path: Path) -> tuple[dict, str, str, str]:
    """Return (scenario_json, slug, title, description) from an import file.

    Tolerates a bare scenario_json (no import envelope) by deriving fields from metadata.
    """
    obj = json.loads(import_path.read_text(encoding="utf-8"))
    if isinstance(obj, dict) and "scenario_json" in obj:
        scenario_json = obj["scenario_json"]
        meta = scenario_json.get("metadata", {})
        slug = obj.get("slug") or assemble.slugify(obj.get("title") or meta.get("title", ""))
        title = obj.get("title") or meta.get("title") or "Untitled Scenario"
        description = obj.get("description") or meta.get("description") or ""
    else:
        scenario_json = obj
        meta = scenario_json.get("metadata", {})
        title = meta.get("title") or "Untitled Scenario"
        description = meta.get("description") or ""
        slug = assemble.slugify(title)
    return scenario_json, slug, title, description


def _force_relative_images(scenario_json: dict, scene_ids: set[str] | None) -> None:
    """Rewrite hosted-URL ``image`` values back to their bare filename so the prompt
    builder (which skips http URLs) will treat them as regenerate targets. Mutates in
    place. If ``scene_ids`` is given, only those scenes are affected."""
    for scene_id, scene in scenario_json.get("scenes", {}).items():
        if scene_ids is not None and scene_id not in scene_ids:
            continue
        image = scene.get("image")
        if isinstance(image, str) and image.startswith(("http://", "https://")):
            scene["image"] = image.rsplit("/", 1)[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-run the image pipeline on an existing scenario (no PDF)."
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="Path to a <slug>-import.json, or a bare slug resolved in --out.",
    )
    parser.add_argument("--out", default=str(REPO_ROOT), help="Output/lookup directory.")
    parser.add_argument(
        "--preview-dir",
        default=None,
        help="Where to write preview PNGs (default: <out>/image_previews/<slug>).",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload new images to R2 (replaces existing keys) and write an updated "
        "import file. Without this, the tool only previews locally.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Also redo scenes whose image is already a hosted URL.",
    )
    parser.add_argument(
        "--scenes",
        default=None,
        help="Comma-separated scene ids to redo (default: all with an image).",
    )
    parser.add_argument(
        "--prompts-file",
        default=None,
        help="Reuse prompts from this JSON file instead of re-running the art director.",
    )
    parser.add_argument("--prompt-model", default=None, help="Override art-director model.")
    parser.add_argument("--image-model", default=None, help="Override image model.")
    args = parser.parse_args(argv)

    from app.core.config import settings

    out_dir = Path(args.out)
    prompt_model = args.prompt_model or settings.SCENARIO_SCOUT_MODEL
    image_model = args.image_model or settings.SCENARIO_IMAGE_MODEL
    scene_filter = (
        {s.strip() for s in args.scenes.split(",") if s.strip()} if args.scenes else None
    )

    try:
        import_path = _resolve_import_path(args.scenario, out_dir)
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    scenario_json, slug, title, description = _load(import_path)
    print(f"→ Loaded '{title}' (slug: {slug}) from {import_path}")

    if args.force:
        _force_relative_images(scenario_json, scene_filter)

    # Build fresh prompts (art director over the whole scenario) unless reusing a file.
    if args.prompts_file:
        prompts = json.loads(Path(args.prompts_file).read_text(encoding="utf-8"))
        print(f"→ Reusing {len(prompts)} prompts from {args.prompts_file}")
    else:
        print(f"→ Running art-director prompt pass ({prompt_model}) …")
        try:
            prompts = image_prompts.build_prompts_llm(scenario_json, prompt_model)
        except Exception as exc:  # noqa: BLE001
            print(f"  (art-director unavailable: {exc}; using template prompts)")
            prompts = image_prompts.build_prompts(scenario_json)

    if scene_filter is not None:
        prompts = {sid: spec for sid, spec in prompts.items() if sid in scene_filter}

    if not prompts:
        print(
            "✗ No scenes to redo. Scenes may already use hosted URLs — pass --force to "
            "regenerate those, or check --scenes.",
            file=sys.stderr,
        )
        return 1

    # Always write the fresh prompts alongside for inspection/editing (non-destructive).
    prompts_out = assemble.write_json(out_dir / f"{slug}-image-prompts.redo.json", prompts)
    print(f"  wrote fresh prompts: {prompts_out}")

    if not args.upload:
        preview_dir = Path(args.preview_dir) if args.preview_dir else out_dir / "image_previews" / slug
        preview_dir.mkdir(parents=True, exist_ok=True)
        print(f"→ Preview (dry run): rendering {len(prompts)} images ({image_model}) → {preview_dir}")
        for scene_id, spec in prompts.items():
            png = images.render_png(spec["prompt"], image_model)
            (preview_dir / spec["filename"]).write_bytes(png)
            print(f"    {scene_id} → {spec['filename']}")
        print("\n✓ Preview done. Review the PNGs, then re-run with --upload to publish.")
        print(f"  Previews : {preview_dir}")
        print(f"  Prompts  : {prompts_out}  (edit + pass via --prompts-file if desired)")
        return 0

    # Upload path: generate + push to R2 (replaces existing keys), rewrite image URLs.
    print(f"→ Uploading {len(prompts)} images ({image_model}) to R2 (replaces existing keys) …")
    try:
        urls = images.generate_and_upload(scenario_json, slug, prompts, image_model)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Image step failed: {exc}", file=sys.stderr)
        return 1
    print(f"  uploaded {len(urls)} images")

    from engine.validator import validate_scenario

    errors = validate_scenario(scenario_json)
    if errors:
        print("✗ Updated scenario failed validation:", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        return 1

    # Write a NEW import file (don't clobber the original) for re-import.
    import_obj = assemble.build_import(slug, title, description, scenario_json)
    updated_path = assemble.write_json(out_dir / f"{slug}-import.updated.json", import_obj)

    print("\n✓ Done.")
    print(f"  Updated import : {updated_path}")
    print(f"  Prompts        : {prompts_out}")
    print(
        "\nNext: POST the updated import file to /api/v1/admin/scenarios/import "
        "(X-Admin-Key header) to publish a new version."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
