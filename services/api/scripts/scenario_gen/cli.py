"""Scenario generator CLI orchestrator.

Run from services/api:

    python -m scripts.scenario_gen --pdf path/or/url.pdf
    python -m scripts.scenario_gen --pdf source.pdf --images
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import REPO_ROOT, assemble, generate, image_prompts, images, ingest, scout


def _select_subject(subjects: list[dict], non_interactive: bool) -> dict:
    print("\nCandidate subjects:\n")
    for i, s in enumerate(subjects, start=1):
        print(f"  [{i}] {s.get('title', '(untitled)')}  ({s.get('suggested_complexity', '?')})")
        if s.get("summary"):
            print(f"      {s['summary']}")
    if non_interactive:
        print("\n(non-interactive) selecting [1]")
        return subjects[0]
    raw = input(f"\nSelect subject [1-{len(subjects)}] (default 1): ").strip()
    idx = int(raw) - 1 if raw.isdigit() and 1 <= int(raw) <= len(subjects) else 0
    return subjects[idx]


def _derive_meta(scenario_json: dict, subject: dict) -> tuple[str, str]:
    meta = scenario_json.get("metadata", {}) if isinstance(scenario_json, dict) else {}
    title = meta.get("title") or subject.get("title") or "Untitled Scenario"
    description = meta.get("description") or subject.get("summary") or ""
    return title, description


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a branching scenario from a PDF.")
    parser.add_argument("--pdf", required=True, help="Local path or http(s) URL to a PDF.")
    parser.add_argument("--out", default=str(REPO_ROOT), help="Output directory.")
    parser.add_argument("--subjects", type=int, default=5, help="How many subjects to propose.")
    parser.add_argument("--slug", default=None, help="Override the derived slug.")
    parser.add_argument("--images", action="store_true", help="Generate + upload scene images.")
    parser.add_argument("--gen-model", default=None, help="Override scenario generation model.")
    parser.add_argument("--scout-model", default=None, help="Override subject scout model.")
    parser.add_argument(
        "--non-interactive", action="store_true", help="Auto-pick subject #1; no prompts."
    )
    args = parser.parse_args(argv)

    from app.core.config import settings

    gen_model = args.gen_model or settings.SCENARIO_GEN_MODEL
    scout_model = args.scout_model or settings.SCENARIO_SCOUT_MODEL
    out_dir = Path(args.out)

    print(f"→ Loading PDF: {args.pdf}")
    try:
        pdf_blocks = ingest.load_pdf_blocks(args.pdf)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not load PDF: {exc}", file=sys.stderr)
        return 1

    print(f"→ Scouting subjects ({scout_model}) …")
    subjects = scout.scout_subjects(pdf_blocks, args.subjects, scout_model)
    if not subjects:
        print("✗ No candidate subjects found.", file=sys.stderr)
        return 1
    subject = _select_subject(subjects, args.non_interactive)

    print(f"\n→ Generating scenario ({gen_model}) …")
    try:
        scenario_json = generate.generate_scenario(pdf_blocks, subject, gen_model)
    except generate.GenerationError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    title, description = _derive_meta(scenario_json, subject)
    slug = args.slug or assemble.slugify(title)
    if not args.non_interactive:
        raw = input(f"Slug [{slug}]: ").strip()
        if raw:
            slug = assemble.slugify(raw)

    # Image prompts (always produced). Use the art-director pass (full-scenario
    # context, one inferred setting) and fall back to the template on any failure.
    try:
        prompts = image_prompts.build_prompts_llm(scenario_json, scout_model)
    except Exception as exc:  # noqa: BLE001
        print(f"  (art-director prompts unavailable: {exc}; using template prompts)")
        prompts = image_prompts.build_prompts(scenario_json)

    if args.images:
        print(f"→ Generating {len(prompts)} images ({settings.SCENARIO_IMAGE_MODEL}) "
              "and uploading to R2 …")
        try:
            urls = images.generate_and_upload(
                scenario_json, slug, prompts, settings.SCENARIO_IMAGE_MODEL
            )
        except Exception as exc:  # noqa: BLE001
            print(f"✗ Image step failed: {exc}", file=sys.stderr)
            return 1
        print(f"  uploaded {len(urls)} images")

    # Validate the final scenario_json before writing.
    from engine.validator import validate_scenario

    errors = validate_scenario(scenario_json)
    if errors:
        print("✗ Final scenario failed validation:", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        return 1

    import_obj = assemble.build_import(slug, title, description, scenario_json)
    import_path = assemble.write_json(out_dir / f"{slug}-import.json", import_obj)
    prompts_path = assemble.write_json(out_dir / f"{slug}-image-prompts.json", prompts)

    print("\n✓ Done.")
    print(f"  Scenario : {import_path}")
    print(f"  Prompts  : {prompts_path}")
    if not args.images and prompts:
        print(f"  ({len(prompts)} scene image prompts — run again with --images to "
              "auto-generate and upload them)")
    print(
        "\nNext: POST the import file to /api/v1/admin/scenarios/import "
        "(X-Admin-Key header) via Postman."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
