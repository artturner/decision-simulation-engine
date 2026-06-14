"""
Pydantic request / response schemas for the public API.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared: scene representation
# ---------------------------------------------------------------------------


class ChoiceOut(BaseModel):
    """A single choice option visible to the learner."""

    text: str


class SceneDTO(BaseModel):
    """Serialisable scene returned by start / step / back / get-play.

    ``image_url`` replaces the engine's raw ``image`` relative path —
    resolution happens in the API layer using ``MEDIA_BASE_URL``.

    Optional fields are ``None`` when not applicable to the scene type:
    - ``choices``         — only for ``type="choice"`` scenes
    - ``outcome``         — only for ``type="end"`` scenes
    - ``outcome_message`` — only for ``type="end"`` scenes
    """

    scene_id: str
    type: str
    title: str
    narration: str
    description: str
    image_url: str | None
    choices: list[ChoiceOut] | None = None
    outcome: str | None = None
    outcome_message: str | None = None


class ProgressOut(BaseModel):
    """Learner progress summary included with every play response."""

    step_count: int
    choices_made: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# GET /public/class/{roll_id}  — class picker
# ---------------------------------------------------------------------------


class ClassPickerScenarioOut(BaseModel):
    """One scenario entry in the class picker list."""

    scenario_version_id: uuid.UUID
    slug: str
    title: str
    description: str
    sort_order: int | None


class ClassPickerResponse(BaseModel):
    """Response for GET /public/class/{roll_id}.

    Returns the roll's student list and the visible scenarios so the
    frontend can render a name picker and scenario chooser in one request.
    """

    roll_id: uuid.UUID
    roll_name: str
    join_code: str
    student_names: list[str]
    scenarios: list[ClassPickerScenarioOut]


class StudentScenarioStatus(BaseModel):
    """Scenario plus this student's attempt summary for the class picker."""

    scenario_version_id: uuid.UUID
    slug: str
    title: str
    description: str
    sort_order: int | None
    in_progress_play_id: uuid.UUID | None
    submitted_count: int
    latest_submitted_play_id: uuid.UUID | None


class StudentClassStatusResponse(BaseModel):
    """Visible class assignments with attempt state for one student name."""

    roll_id: uuid.UUID
    roll_name: str
    join_code: str
    student_name: str
    scenarios: list[StudentScenarioStatus]


# ---------------------------------------------------------------------------
# GET /public/scenarios/{slug}
# ---------------------------------------------------------------------------


class ScenarioMetadataOut(BaseModel):
    """Subset of scenario_json.metadata surfaced to the public API."""

    title: str = ""
    description: str = ""
    page_title: str = ""
    page_icon: str = ""
    author: str = ""
    version: str = ""
    completion_tracking: bool = False
    cover_image_url: str | None = None


class ScenarioPublicResponse(BaseModel):
    """Response for GET /public/scenarios/{slug}.

    Returns everything the frontend needs to render the landing page and
    know which reflection fields to collect at the end of the play.
    """

    slug: str
    scenario_version_id: uuid.UUID
    version_number: int
    metadata: ScenarioMetadataOut
    start_scene_id: str
    reflection_questions: list[str] = Field(default_factory=list)
    reflection_prompts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# POST /public/plays/start
# ---------------------------------------------------------------------------


class PlayStartRequest(BaseModel):
    """Body for starting a new play session.

    When started via the class picker, supply ``class_roll_id`` and a
    ``learner_label`` that exactly matches one of the roll's student names.
    The API validates membership server-side and returns ``422`` on mismatch.
    """

    scenario_version_id: uuid.UUID
    learner_label: str | None = None
    class_roll_id: uuid.UUID | None = None


class PlayStartResponse(BaseModel):
    """Response after successfully starting a play."""

    play_id: uuid.UUID
    scenario_version_id: uuid.UUID
    scene: SceneDTO
    progress: ProgressOut


# ---------------------------------------------------------------------------
# POST /public/plays/{play_id}/step
# ---------------------------------------------------------------------------


class StepRequest(BaseModel):
    """Body for advancing a play by one step.

    ``choice_index`` is required when the current scene is a choice scene
    and must be ``None`` (or omitted) for all other scene types.
    """

    choice_index: int | None = None


class StepResponse(BaseModel):
    """Response after a successful step."""

    play_id: uuid.UUID
    scene: SceneDTO
    progress: ProgressOut
    done: bool
    outcome: str | None = None
    outcome_message: str | None = None


# ---------------------------------------------------------------------------
# GET /public/plays/{play_id}
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# POST /public/plays/{play_id}/back
# ---------------------------------------------------------------------------


class BackResponse(BaseModel):
    """Response after successfully going back one step.

    ``done`` is always ``False`` — going back always leaves the play
    in an in-progress state.
    """

    play_id: uuid.UUID
    scene: SceneDTO
    progress: ProgressOut
    done: bool = False


# ---------------------------------------------------------------------------
# POST /public/plays/{play_id}/reflection
# ---------------------------------------------------------------------------


class ReflectionRequest(BaseModel):
    """Body for submitting a learner reflection after play completion.

    ``responses`` maps question keys (e.g. ``"reflection_1"``) to the
    learner's free-text answer.  At least one entry is required.

    ``student_name`` is optional; passed through to analytics exports.
    """

    responses: dict[str, str] = Field(min_length=1)
    student_name: str | None = None


class ReflectionResponse(BaseModel):
    """Confirmation returned after a reflection is successfully recorded."""

    ok: bool = True


# ---------------------------------------------------------------------------
# GET /public/plays/{play_id}
# ---------------------------------------------------------------------------


class PlayViewResponse(BaseModel):
    """Full play state — returned by GET /public/plays/{play_id}.

    Mirrors the start / step / back response shape so the frontend can use
    one type for all play state updates.

    When ``done`` is ``True`` the reflection fields are populated from the
    scenario's ``metadata.completion_tracking`` and
    ``reflection_questions`` / ``reflection_prompts`` arrays so the frontend
    can render the reflection form immediately without a second request.
    """

    play_id: uuid.UUID
    scene: SceneDTO
    progress: ProgressOut
    done: bool
    outcome: str | None = None
    outcome_message: str | None = None
    reflection_required: bool = False
    reflection_questions: list[str] = Field(default_factory=list)
    reflection_prompts: list[str] = Field(default_factory=list)
