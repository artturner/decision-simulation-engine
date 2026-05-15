"""
Validator tests — structural errors, referential integrity, expression
parse checks, and multi-error collection.
"""

import pytest

from engine.validator import validate_scenario


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------


def minimal_valid() -> dict:
    """Smallest passing scenario: choice → auto_advance → end.
    Uses default start_scene_id so scene '1' must exist.
    """
    return {
        "metadata": {"title": "Minimal"},
        "scenes": {
            "1": {
                "type": "choice",
                "choices": [{"text": "Continue", "next": "mid"}],
            },
            "mid": {"type": "auto_advance", "next": "end"},
            "end": {"type": "end"},
        },
    }


def conditional_scenario() -> dict:
    """Scenario with a conditional scene, reused across several tests."""
    return {
        "metadata": {"title": "Conditional"},
        "scenes": {
            "1": {
                "type": "conditional",
                "conditions": [
                    {"condition": "confidence > 0", "next": "end"},
                ],
                "default": "end",
            },
            "end": {"type": "end"},
        },
    }


def full_valid() -> dict:
    """Four-scene scenario exercising all scene types."""
    return {
        "metadata": {"title": "Full", "completion_tracking": True},
        "reflection_questions": ["What did you learn?"],
        "variables": {"confidence": 0},
        "start_scene_id": "intro",
        "scenes": {
            "intro": {
                "type": "choice",
                "choices": [
                    {"text": "A", "next": "branch", "effects": {"confidence": 1}},
                ],
            },
            "branch": {
                "type": "conditional",
                "conditions": [{"condition": "confidence > 0", "next": "end"}],
                "default": "end",
            },
            "auto": {"type": "auto_advance", "next": "end"},
            "end": {"type": "end", "outcome": "success"},
        },
    }


# ---------------------------------------------------------------------------
# Valid scenarios
# ---------------------------------------------------------------------------


class TestValidScenarios:
    def test_minimal_returns_empty(self):
        assert validate_scenario(minimal_valid()) == []

    def test_full_returns_empty(self):
        assert validate_scenario(full_valid()) == []

    def test_conditional_returns_empty(self):
        assert validate_scenario(conditional_scenario()) == []

    def test_explicit_start_scene_id_valid(self):
        data = minimal_valid()
        data["start_scene_id"] = "mid"
        assert validate_scenario(data) == []

    def test_choice_with_effects_valid(self):
        data = minimal_valid()
        data["scenes"]["1"]["choices"][0]["effects"] = {"confidence": 1}
        assert validate_scenario(data) == []

    def test_readme_expression_valid(self):
        """Full README conditional expression passes parse check."""
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"][0]["condition"] = (
            "LargeStateFavor >= -2 && LargeStateFavor <= 2"
            " && SouthernStateFavor >= -2 && SouthernStateFavor <= 2"
        )
        assert validate_scenario(data) == []

    def test_end_scene_only_no_refs_valid(self):
        data = {
            "metadata": {"title": "X"},
            "scenes": {"1": {"type": "end"}},
        }
        assert validate_scenario(data) == []


# ---------------------------------------------------------------------------
# Phase 1 — structural (Pydantic) errors
# ---------------------------------------------------------------------------


class TestStructuralErrors:
    def test_missing_scenes_field(self):
        errs = validate_scenario({"metadata": {"title": "X"}})
        assert len(errs) > 0
        assert any("scenes" in e for e in errs)

    def test_missing_metadata_field(self):
        errs = validate_scenario({"scenes": {}})
        assert len(errs) > 0
        assert any("metadata" in e for e in errs)

    def test_unknown_scene_type(self):
        data = minimal_valid()
        data["scenes"]["1"] = {"type": "telepathy"}
        errs = validate_scenario(data)
        assert len(errs) > 0

    def test_choice_missing_choices_field(self):
        data = minimal_valid()
        data["scenes"]["1"] = {"type": "choice"}  # choices required
        errs = validate_scenario(data)
        assert len(errs) > 0

    def test_auto_advance_missing_next_field(self):
        data = minimal_valid()
        data["scenes"]["mid"] = {"type": "auto_advance"}  # next required
        errs = validate_scenario(data)
        assert len(errs) > 0


# ---------------------------------------------------------------------------
# Phase 2 — start_scene_id
# ---------------------------------------------------------------------------


class TestStartSceneId:
    def test_explicit_missing_target(self):
        data = minimal_valid()
        data["start_scene_id"] = "99"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "start_scene_id" in errs[0]
        assert "'99'" in errs[0]

    def test_default_one_not_in_scenes(self):
        """Default start_scene_id='1' but '1' is not a scene key."""
        data = {
            "metadata": {"title": "X"},
            "scenes": {"intro": {"type": "end"}},
        }
        errs = validate_scenario(data)
        assert any("start_scene_id" in e and "'1'" in e for e in errs)


# ---------------------------------------------------------------------------
# Phase 2 — ChoiceScene references
# ---------------------------------------------------------------------------


class TestChoiceValidation:
    def test_unknown_next(self):
        data = minimal_valid()
        data["scenes"]["1"]["choices"][0]["next"] = "nonexistent"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "Scene '1'" in errs[0]
        assert "choice 0" in errs[0]
        assert "'nonexistent'" in errs[0]

    def test_correct_choice_index_in_message(self):
        data = minimal_valid()
        data["scenes"]["1"]["choices"] = [
            {"text": "OK", "next": "mid"},
            {"text": "Bad", "next": "missing"},
        ]
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "choice 1" in errs[0]

    def test_multiple_bad_choices_each_reported(self):
        data = minimal_valid()
        data["scenes"]["1"]["choices"] = [
            {"text": "A", "next": "gone_a"},
            {"text": "B", "next": "gone_b"},
        ]
        errs = validate_scenario(data)
        assert len(errs) == 2
        assert any("choice 0" in e for e in errs)
        assert any("choice 1" in e for e in errs)

    def test_valid_choice_no_error(self):
        data = minimal_valid()
        assert not any("choice" in e for e in validate_scenario(data))


# ---------------------------------------------------------------------------
# Phase 2 — AutoAdvanceScene references
# ---------------------------------------------------------------------------


class TestAutoAdvanceValidation:
    def test_unknown_next(self):
        data = minimal_valid()
        data["scenes"]["mid"]["next"] = "gone"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "'mid'" in errs[0]
        assert "auto_advance" in errs[0]
        assert "'gone'" in errs[0]

    def test_valid_next_no_error(self):
        assert validate_scenario(minimal_valid()) == []


# ---------------------------------------------------------------------------
# Phase 2 — ConditionalScene
# ---------------------------------------------------------------------------


class TestConditionalValidation:
    def test_no_conditions_error(self):
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"] = []
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "no conditions" in errs[0]

    def test_condition_unknown_next(self):
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"][0]["next"] = "gone"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "condition 0" in errs[0]
        assert "'gone'" in errs[0]

    def test_correct_condition_index_in_message(self):
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"] = [
            {"condition": "x > 0", "next": "end"},
            {"condition": "y > 0", "next": "missing"},
        ]
        errs = validate_scenario(data)
        assert any("condition 1" in e for e in errs)

    def test_invalid_expression_lex_error(self):
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"][0]["condition"] = "@@@"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "invalid expression" in errs[0]

    def test_invalid_expression_parse_error(self):
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"][0]["condition"] = "a &&"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "invalid expression" in errs[0]

    def test_valid_expression_no_error(self):
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"][0]["condition"] = "confidence >= -2"
        errs = validate_scenario(data)
        assert errs == []

    def test_unknown_variable_in_expression_is_ok(self):
        """Validator only parse-checks expressions; unknown variables are fine
        (they're detected at runtime via safe_evaluate fail-closed)."""
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"][0]["condition"] = "UnknownVar > 0"
        assert validate_scenario(data) == []

    def test_default_unknown_scene(self):
        data = conditional_scenario()
        data["scenes"]["1"]["default"] = "gone"
        errs = validate_scenario(data)
        assert len(errs) == 1
        assert "default" in errs[0]
        assert "'gone'" in errs[0]

    def test_no_default_no_error(self):
        data = conditional_scenario()
        del data["scenes"]["1"]["default"]
        assert validate_scenario(data) == []

    def test_multiple_condition_errors_collected(self):
        """Bad expression + unknown next on same condition both reported."""
        data = conditional_scenario()
        data["scenes"]["1"]["conditions"] = [
            {"condition": "@@@", "next": "gone"},
        ]
        errs = validate_scenario(data)
        # expression error AND unknown next
        assert len(errs) == 2


# ---------------------------------------------------------------------------
# Multi-error collection
# ---------------------------------------------------------------------------


class TestMultipleErrors:
    def test_all_errors_returned_not_just_first(self):
        data = {
            "metadata": {"title": "Many Errors"},
            "start_scene_id": "missing_start",
            "scenes": {
                "1": {
                    "type": "choice",
                    "choices": [{"text": "Bad", "next": "gone_a"}],
                },
                "mid": {"type": "auto_advance", "next": "gone_b"},
                "end": {"type": "end"},
            },
        }
        errs = validate_scenario(data)
        # start_scene_id + choice 0 + auto_advance = 3 errors
        assert len(errs) == 3

    def test_end_scenes_never_produce_errors(self):
        """EndScene has no outgoing refs; should never add errors."""
        data = minimal_valid()
        errs = validate_scenario(data)
        assert not any("'end'" in e for e in errs)
