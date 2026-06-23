"""Wrap a scenario_json into the import envelope and write it to disk."""

from __future__ import annotations

import json
import re
from pathlib import Path


def slugify(title: str) -> str:
    """Kebab-case slug from a title (lowercase, alnum + hyphens)."""
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "scenario"


def slug_to_media_folder(slug: str) -> str:
    """Media folder convention: underscores (e.g. cherokee-nation -> cherokee_nation)."""
    return slug.replace("-", "_")


def build_import(
    slug: str,
    title: str,
    description: str,
    scenario_json: dict,
    status: str = "draft",
) -> dict:
    """Build the POST /admin/scenarios/import request body."""
    return {
        "slug": slug,
        "title": title,
        "description": description,
        "status": status,
        "scenario_json": scenario_json,
    }


def write_json(path: Path, obj: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
