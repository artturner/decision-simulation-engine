"""
Scenario generator CLI.

Turns a source PDF into a ready-to-import branching scenario:
PDF -> candidate subjects -> (pick one) -> generate scenario_json (validated
against the engine) -> write <slug>-import.json + per-scene image prompts, and
optionally generate images (OpenAI gpt-image-1) and upload them to R2.

Run from services/api:

    python -m scripts.scenario_gen --pdf path/or/url.pdf [--images]
"""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path

# services/api/scripts/scenario_gen/__init__.py
#   parents[0]=scenario_gen [1]=scripts [2]=api [3]=services [4]=repo root
SERVICE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]

# Source design docs used to steer generation (kept at repo root).
GENERATOR_PROMPT_PATH = REPO_ROOT / "branching_scenario_generator_system_prompt_1.md"
PEDAGOGY_SKILL_PATH = REPO_ROOT / "SCENARIO_SKILL.md"


def _ensure_internal_packages_on_path() -> None:
    """Make `engine` and `expr` importable when not pip-installed locally.

    In the Docker image these are installed (services/api/Dockerfile); for local
    CLI runs we fall back to the in-repo `packages/<pkg>/src` source layout.
    Installed versions take precedence — we only append when not already found.
    """
    for pkg in ("engine", "expr"):
        if find_spec(pkg) is not None:
            continue
        src = REPO_ROOT / "packages" / pkg / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.append(str(src))


_ensure_internal_packages_on_path()
