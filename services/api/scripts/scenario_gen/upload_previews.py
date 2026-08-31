"""Upload the REVIEWED preview PNGs from an image-redo pass to R2 — no re-render.

``redo_images --upload`` re-renders every image from its prompt, so what ships is
not what you reviewed. This tool closes that gap: it takes the preview PNGs from a
prior ``redo_images`` dry run (the ones you actually looked at), uploads them to R2
at the standard keys, rewrites each scene's ``image`` to the hosted URL, and writes
``<slug>-import.updated.json`` ready for import. Same move as the fdr-korematsu
image refresh (reviewed previews pushed via the storage module), made repeatable.

Run from services/api:

    python -m scripts.scenario_gen.upload_previews --scenario shaping-the-aca

Flags:
    --preview-dir P   Where the reviewed PNGs live (default <out>/image_previews/<slug>).
    --prompts-file P  Scene-id → filename map from the redo pass
                      (default <out>/<slug>-image-prompts.redo.json).
    --scenes 1,2a     Only upload these scene ids.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import REPO_ROOT, assemble, images
from .redo_images import _load, _resolve_import_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload reviewed redo-preview PNGs to R2 and write an updated import file."
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
        help="Directory of reviewed PNGs (default: <out>/image_previews/<slug>).",
    )
    parser.add_argument(
        "--prompts-file",
        default=None,
        help="Redo prompts JSON mapping scene ids to filenames "
        "(default: <out>/<slug>-image-prompts.redo.json).",
    )
    parser.add_argument(
        "--scenes",
        default=None,
        help="Comma-separated scene ids to upload (default: all in the prompts file).",
    )
    args = parser.parse_args(argv)

    from app.services.storage import upload_media

    out_dir = Path(args.out)
    try:
        import_path = _resolve_import_path(args.scenario, out_dir)
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    scenario_json, slug, title, description = _load(import_path)
    print(f"→ Loaded '{title}' (slug: {slug}) from {import_path}")

    preview_dir = (
        Path(args.preview_dir) if args.preview_dir else out_dir / "image_previews" / slug
    )
    prompts_path = (
        Path(args.prompts_file)
        if args.prompts_file
        else out_dir / f"{slug}-image-prompts.redo.json"
    )
    if not prompts_path.is_file():
        print(
            f"✗ No prompts file at {prompts_path} — run redo_images first (its dry run "
            "writes this file alongside the previews).",
            file=sys.stderr,
        )
        return 1
    prompts: dict[str, dict] = json.loads(prompts_path.read_text(encoding="utf-8"))

    scene_filter = (
        {s.strip() for s in args.scenes.split(",") if s.strip()} if args.scenes else None
    )
    folder = assemble.slug_to_media_folder(slug)
    uploaded = 0
    missing: list[str] = []
    for scene_id, spec in prompts.items():
        if scene_filter is not None and scene_id not in scene_filter:
            continue
        if scene_id not in scenario_json.get("scenes", {}):
            print(f"    (skipping {scene_id}: not in scenario)", file=sys.stderr)
            continue
        png_path = preview_dir / spec["filename"]
        if not png_path.is_file():
            missing.append(f"{scene_id} ({spec['filename']})")
            continue
        key = f"{folder}/{images.MEDIA_VERSION}/{spec['filename']}"
        url = upload_media(images.optimize_png(png_path.read_bytes()), key, "image/png")
        scenario_json["scenes"][scene_id]["image"] = url
        uploaded += 1
        print(f"    {scene_id} → {url}")

    if missing:
        print(f"⚠ No preview PNG for: {', '.join(missing)}", file=sys.stderr)
    if not uploaded:
        print(f"✗ Nothing uploaded — no reviewed PNGs found in {preview_dir}.", file=sys.stderr)
        return 1

    from engine.validator import validate_scenario

    errors = validate_scenario(scenario_json)
    if errors:
        print("✗ Updated scenario failed validation:", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        return 1

    import_obj = assemble.build_import(slug, title, description, scenario_json)
    updated_path = assemble.write_json(out_dir / f"{slug}-import.updated.json", import_obj)

    print(f"\n✓ Uploaded {uploaded} reviewed images.")
    print(f"  Updated import : {updated_path}")
    print(
        "\nNext: POST the updated import file to /api/v1/admin/scenarios/import "
        "(X-Admin-Key header), then publish the created version."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
