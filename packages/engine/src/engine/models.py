"""
Pydantic v2 models for the scenario JSON contract.

All models use ``extra="ignore"`` so that existing scenario files with
unfamiliar fields don't fail validation — semantic checks (dead-end
references, duplicate keys, etc.) are the job of the validator module.

Scene type hierarchy
--------------------
SceneBase
├── ChoiceScene       type="choice"
├── AutoAdvanceScene  type="auto_advance"
├── ConditionalScene  type="conditional"
└── EndScene          type="end"

Pydantic dispatches on the ``type`` discriminator field, so
``dict[str, Scene]`` deserialises each scene into the correct subclass.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared base — inherited by every model in this module
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Extra fields in JSON are silently ignored (forward-compat)."""

    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Choice and Condition leaf models
# ---------------------------------------------------------------------------

# Type alias: variable-name → numeric delta  (e.g. {"confidence": 1, "risk": -1})
ChoiceEffect = dict[str, float]


class Choice(_Base):
    """One selectable option inside a choice scene."""

    text: str
    next: str
    effects: ChoiceEffect = Field(default_factory=dict)


class Condition(_Base):
    """A single branch inside a conditional scene."""

    condition: str  # expression string — evaluated by expr.safe_evaluate
    next: str


# ---------------------------------------------------------------------------
# Scene base and subtypes
# ---------------------------------------------------------------------------


class SceneBase(_Base):
    """Fields common to every scene type."""

    title: str = ""
    image: str | None = None       # relative path resolved to URL by the API
    description: str = ""
    narration: str = ""


class ChoiceScene(SceneBase):
    type: Literal["choice"]
    choices: list[Choice]


class AutoAdvanceScene(SceneBase):
    type: Literal["auto_advance"]
    next: str


class ConditionalScene(SceneBase):
    type: Literal["conditional"]
    conditions: list[Condition]
    default: str | None = None     # fallback scene_id if no condition matches


class EndScene(SceneBase):
    type: Literal["end"]
    outcome: str | None = None
    outcome_message: str | None = None


# Discriminated union — Pydantic selects the correct subclass from ``type``.
Scene = Annotated[
    Union[ChoiceScene, AutoAdvanceScene, ConditionalScene, EndScene],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Scenario metadata
# ---------------------------------------------------------------------------


class ScenarioMetadata(_Base):
    title: str = ""
    description: str = ""
    page_title: str = ""
    page_icon: str = ""
    author: str = ""
    version: str = ""
    completion_tracking: bool = False
    cover_image: str | None = None  # relative path resolved to URL by the API


# ---------------------------------------------------------------------------
# Top-level Scenario
# ---------------------------------------------------------------------------


class Scenario(_Base):
    metadata: ScenarioMetadata
    reflection_questions: list[str] = Field(default_factory=list)
    reflection_prompts: list[str] = Field(default_factory=list)
    # Initial variable values; Pydantic coerces int → float for uniformity.
    variables: dict[str, float] = Field(default_factory=dict)
    # Which scene to start on; defaults to "1" to match legacy JSON files
    # that omit this field.
    start_scene_id: str = "1"
    scenes: dict[str, Scene]
