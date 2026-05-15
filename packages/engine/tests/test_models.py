"""
Model tests — Pydantic parsing, discriminated unions, defaults, and
coercion for the scenario JSON contract.
"""

import pytest
from pydantic import ValidationError

from engine.models import (
    AutoAdvanceScene,
    Choice,
    ChoiceScene,
    Condition,
    ConditionalScene,
    EndScene,
    Scenario,
    ScenarioMetadata,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_SCENARIO: dict = {
    "metadata": {"title": "Minimal"},
    "scenes": {
        "1": {
            "type": "choice",
            "title": "First Scene",
            "choices": [{"text": "Continue", "next": "end"}],
        },
        "end": {"type": "end"},
    },
}

FULL_SCENARIO: dict = {
    "metadata": {
        "title": "Cherokee Choice",
        "description": "A learning scenario",
        "page_title": "Cherokee Choice",
        "page_icon": "🌿",
        "author": "Test Author",
        "version": "1.0",
        "completion_tracking": True,
    },
    "reflection_questions": ["What did you learn?", "What would you do differently?"],
    "reflection_prompts": ["Think about the impact.", "Consider alternatives."],
    "variables": {"confidence": 0, "risk": 0},
    "start_scene_id": "intro",
    "scenes": {
        "intro": {
            "type": "choice",
            "title": "Introduction",
            "description": "You stand at a crossroads.",
            "narration": "Choose your path.",
            "image": "intro.png",
            "choices": [
                {"text": "Go left", "next": "middle", "effects": {"confidence": 1}},
                {"text": "Go right", "next": "branch", "effects": {"risk": 1}},
            ],
        },
        "middle": {
            "type": "auto_advance",
            "title": "Middle Scene",
            "next": "end",
        },
        "branch": {
            "type": "conditional",
            "title": "Branch Scene",
            "conditions": [
                {"condition": "confidence > 0", "next": "end"},
                {"condition": "risk > 0", "next": "middle"},
            ],
            "default": "end",
        },
        "end": {
            "type": "end",
            "title": "The End",
            "outcome": "success",
            "outcome_message": "You succeeded!",
        },
    },
}


# ---------------------------------------------------------------------------
# Scenario — top-level loading
# ---------------------------------------------------------------------------


class TestScenarioLoading:
    def test_minimal_scenario_loads(self):
        s = Scenario.model_validate(MINIMAL_SCENARIO)
        assert s.metadata.title == "Minimal"
        assert len(s.scenes) == 2

    def test_full_scenario_loads(self):
        s = Scenario.model_validate(FULL_SCENARIO)
        assert s.metadata.title == "Cherokee Choice"
        assert len(s.scenes) == 4

    def test_start_scene_id_default_is_one(self):
        s = Scenario.model_validate(MINIMAL_SCENARIO)
        assert s.start_scene_id == "1"

    def test_start_scene_id_explicit(self):
        s = Scenario.model_validate(FULL_SCENARIO)
        assert s.start_scene_id == "intro"

    def test_reflection_questions_default_empty(self):
        s = Scenario.model_validate(MINIMAL_SCENARIO)
        assert s.reflection_questions == []

    def test_reflection_questions_loaded(self):
        s = Scenario.model_validate(FULL_SCENARIO)
        assert len(s.reflection_questions) == 2
        assert s.reflection_questions[0] == "What did you learn?"

    def test_reflection_prompts_loaded(self):
        s = Scenario.model_validate(FULL_SCENARIO)
        assert len(s.reflection_prompts) == 2

    def test_variables_default_empty(self):
        s = Scenario.model_validate(MINIMAL_SCENARIO)
        assert s.variables == {}

    def test_variables_int_coerced_to_float(self):
        s = Scenario.model_validate(FULL_SCENARIO)
        # Pydantic coerces int 0 → float 0.0
        assert isinstance(s.variables["confidence"], float)
        assert s.variables["confidence"] == 0.0

    def test_extra_top_level_fields_ignored(self):
        data = {**MINIMAL_SCENARIO, "unknown_field": "should be ignored"}
        s = Scenario.model_validate(data)
        assert not hasattr(s, "unknown_field")

    def test_missing_scenes_raises(self):
        with pytest.raises(ValidationError):
            Scenario.model_validate({"metadata": {"title": "X"}})

    def test_missing_metadata_raises(self):
        with pytest.raises(ValidationError):
            Scenario.model_validate({"scenes": {}})


# ---------------------------------------------------------------------------
# Discriminated union — each scene type
# ---------------------------------------------------------------------------


class TestDiscriminatedUnion:
    def setup_method(self):
        self.scenario = Scenario.model_validate(FULL_SCENARIO)

    def test_choice_scene_type(self):
        scene = self.scenario.scenes["intro"]
        assert isinstance(scene, ChoiceScene)

    def test_auto_advance_scene_type(self):
        scene = self.scenario.scenes["middle"]
        assert isinstance(scene, AutoAdvanceScene)

    def test_conditional_scene_type(self):
        scene = self.scenario.scenes["branch"]
        assert isinstance(scene, ConditionalScene)

    def test_end_scene_type(self):
        scene = self.scenario.scenes["end"]
        assert isinstance(scene, EndScene)

    def test_invalid_type_raises(self):
        data = {
            **MINIMAL_SCENARIO,
            "scenes": {
                "1": {"type": "unknown_type", "title": "Bad"},
            },
        }
        with pytest.raises(ValidationError):
            Scenario.model_validate(data)


# ---------------------------------------------------------------------------
# ChoiceScene
# ---------------------------------------------------------------------------


class TestChoiceScene:
    def setup_method(self):
        self.scene = Scenario.model_validate(FULL_SCENARIO).scenes["intro"]
        assert isinstance(self.scene, ChoiceScene)

    def test_title(self):
        assert self.scene.title == "Introduction"

    def test_description(self):
        assert self.scene.description == "You stand at a crossroads."

    def test_narration(self):
        assert self.scene.narration == "Choose your path."

    def test_image(self):
        assert self.scene.image == "intro.png"

    def test_choice_count(self):
        assert len(self.scene.choices) == 2

    def test_choice_text(self):
        assert self.scene.choices[0].text == "Go left"
        assert self.scene.choices[1].text == "Go right"

    def test_choice_next(self):
        assert self.scene.choices[0].next == "middle"

    def test_choice_effects_present(self):
        assert self.scene.choices[0].effects == {"confidence": 1.0}

    def test_choice_effects_coerced_to_float(self):
        assert isinstance(self.scene.choices[0].effects["confidence"], float)

    def test_choice_effects_default_empty(self):
        scene_data = {
            "type": "choice",
            "choices": [{"text": "X", "next": "y"}],
        }
        scene = ChoiceScene.model_validate(scene_data)
        assert scene.choices[0].effects == {}

    def test_image_default_none(self):
        scene = ChoiceScene.model_validate(
            {"type": "choice", "choices": [{"text": "X", "next": "y"}]}
        )
        assert scene.image is None


# ---------------------------------------------------------------------------
# AutoAdvanceScene
# ---------------------------------------------------------------------------


class TestAutoAdvanceScene:
    def setup_method(self):
        self.scene = Scenario.model_validate(FULL_SCENARIO).scenes["middle"]
        assert isinstance(self.scene, AutoAdvanceScene)

    def test_next(self):
        assert self.scene.next == "end"

    def test_title(self):
        assert self.scene.title == "Middle Scene"


# ---------------------------------------------------------------------------
# ConditionalScene
# ---------------------------------------------------------------------------


class TestConditionalScene:
    def setup_method(self):
        self.scene = Scenario.model_validate(FULL_SCENARIO).scenes["branch"]
        assert isinstance(self.scene, ConditionalScene)

    def test_condition_count(self):
        assert len(self.scene.conditions) == 2

    def test_condition_expr(self):
        assert self.scene.conditions[0].condition == "confidence > 0"

    def test_condition_next(self):
        assert self.scene.conditions[0].next == "end"

    def test_default_present(self):
        assert self.scene.default == "end"

    def test_default_is_none_when_absent(self):
        scene = ConditionalScene.model_validate(
            {
                "type": "conditional",
                "conditions": [{"condition": "x > 0", "next": "a"}],
            }
        )
        assert scene.default is None


# ---------------------------------------------------------------------------
# EndScene
# ---------------------------------------------------------------------------


class TestEndScene:
    def setup_method(self):
        self.scene = Scenario.model_validate(FULL_SCENARIO).scenes["end"]
        assert isinstance(self.scene, EndScene)

    def test_outcome(self):
        assert self.scene.outcome == "success"

    def test_outcome_message(self):
        assert self.scene.outcome_message == "You succeeded!"

    def test_outcome_defaults_none(self):
        scene = EndScene.model_validate({"type": "end"})
        assert scene.outcome is None
        assert scene.outcome_message is None


# ---------------------------------------------------------------------------
# ScenarioMetadata
# ---------------------------------------------------------------------------


class TestScenarioMetadata:
    def setup_method(self):
        self.meta = Scenario.model_validate(FULL_SCENARIO).metadata

    def test_title(self):
        assert self.meta.title == "Cherokee Choice"

    def test_description(self):
        assert self.meta.description == "A learning scenario"

    def test_page_title(self):
        assert self.meta.page_title == "Cherokee Choice"

    def test_page_icon(self):
        assert self.meta.page_icon == "🌿"

    def test_author(self):
        assert self.meta.author == "Test Author"

    def test_version(self):
        assert self.meta.version == "1.0"

    def test_completion_tracking(self):
        assert self.meta.completion_tracking is True

    def test_all_fields_default_when_missing(self):
        meta = ScenarioMetadata.model_validate({})
        assert meta.title == ""
        assert meta.description == ""
        assert meta.page_title == ""
        assert meta.page_icon == ""
        assert meta.author == ""
        assert meta.version == ""
        assert meta.completion_tracking is False

    def test_extra_fields_ignored(self):
        meta = ScenarioMetadata.model_validate({"title": "X", "unknown": "y"})
        assert meta.title == "X"
        assert not hasattr(meta, "unknown")


# ---------------------------------------------------------------------------
# SceneBase shared fields
# ---------------------------------------------------------------------------


class TestSceneBaseDefaults:
    def test_title_defaults_empty(self):
        scene = EndScene.model_validate({"type": "end"})
        assert scene.title == ""

    def test_description_defaults_empty(self):
        scene = EndScene.model_validate({"type": "end"})
        assert scene.description == ""

    def test_narration_defaults_empty(self):
        scene = EndScene.model_validate({"type": "end"})
        assert scene.narration == ""

    def test_image_defaults_none(self):
        scene = EndScene.model_validate({"type": "end"})
        assert scene.image is None

    def test_extra_scene_fields_ignored(self):
        scene = EndScene.model_validate({"type": "end", "future_field": "value"})
        assert not hasattr(scene, "future_field")
