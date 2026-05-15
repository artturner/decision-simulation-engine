"""
Scenario validator — semantic checks beyond Pydantic structural validation.

``validate_scenario`` runs in two phases:

1. **Structural** — Pydantic schema validation (wrong types, missing required
   fields, unknown discriminator values).  Returns Pydantic errors formatted
   as strings and exits early; semantic checks cannot run on a broken model.

2. **Semantic** — referential integrity and expression parse checks:
   - ``start_scene_id`` points to a real scene
   - Every ``choice.next`` points to a real scene
   - Every ``auto_advance.next`` points to a real scene
   - Every ``condition.next`` points to a real scene
   - Conditional expressions are syntactically valid (lex + parse, no eval)
   - Conditional ``default``, if present, points to a real scene
   - Conditional scenes have at least one condition

All errors are collected before returning so callers see the full picture
rather than just the first problem.
"""

from pydantic import ValidationError

from engine.models import (
    AutoAdvanceScene,
    ChoiceScene,
    ConditionalScene,
    Scenario,
)
from expr.lexer import LexError
from expr.parser import ParseError, parse


def validate_scenario(scenario_json: dict) -> list[str]:
    """Return a list of human-readable error strings for *scenario_json*.

    An empty list means the scenario is structurally and semantically valid.
    """
    # ------------------------------------------------------------------
    # Phase 1: structural validation via Pydantic
    # ------------------------------------------------------------------
    try:
        scenario = Scenario.model_validate(scenario_json)
    except ValidationError as exc:
        return [
            f"{' -> '.join(str(loc) for loc in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]

    errors: list[str] = []
    scene_ids = set(scenario.scenes.keys())

    # ------------------------------------------------------------------
    # Phase 2: semantic validation
    # ------------------------------------------------------------------

    # 2a. start_scene_id must reference an existing scene
    if scenario.start_scene_id not in scene_ids:
        errors.append(
            f"start_scene_id {scenario.start_scene_id!r} does not exist in scenes"
        )

    # 2b. Per-scene reference and expression checks
    for scene_id, scene in scenario.scenes.items():

        if isinstance(scene, ChoiceScene):
            for i, choice in enumerate(scene.choices):
                if choice.next not in scene_ids:
                    errors.append(
                        f"Scene {scene_id!r} choice {i} references"
                        f" unknown next {choice.next!r}"
                    )

        elif isinstance(scene, AutoAdvanceScene):
            if scene.next not in scene_ids:
                errors.append(
                    f"Scene {scene_id!r} auto_advance references"
                    f" unknown next {scene.next!r}"
                )

        elif isinstance(scene, ConditionalScene):
            if not scene.conditions:
                errors.append(
                    f"Scene {scene_id!r} conditional has no conditions"
                )

            for i, condition in enumerate(scene.conditions):
                # Expression syntax check — parse only, no variable context needed
                try:
                    parse(condition.condition)
                except (LexError, ParseError) as exc:
                    errors.append(
                        f"Scene {scene_id!r} condition {i}"
                        f" has invalid expression: {exc}"
                    )

                if condition.next not in scene_ids:
                    errors.append(
                        f"Scene {scene_id!r} condition {i} references"
                        f" unknown next {condition.next!r}"
                    )

            if scene.default is not None and scene.default not in scene_ids:
                errors.append(
                    f"Scene {scene_id!r} conditional default references"
                    f" unknown scene {scene.default!r}"
                )

        # EndScene: no outgoing references to validate

    return errors
