"""
Pydantic request / response schemas for the admin API.

All UUIDs are returned as strings (Pydantic serialises uuid.UUID to str
automatically when ``model_config = ConfigDict(from_attributes=True)``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# AI reflection grading leniency for an assignment.
GradingDifficulty = Literal["strict", "standard", "lenient"]


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------


class VersionOut(BaseModel):
    """A single scenario version as returned by admin endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scenario_id: uuid.UUID
    version_number: int
    status: str
    created_at: datetime


class ScenarioOut(BaseModel):
    """A scenario with its version list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    versions: list[VersionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# POST /admin/scenarios/import
# ---------------------------------------------------------------------------


class ScenarioImportRequest(BaseModel):
    """Body for importing a new scenario (creates scenario + version 1)."""

    slug: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    status: str = Field(
        default="draft",
        description="Initial version status: draft | published | archived",
    )
    scenario_json: dict = Field(..., description="Full scenario definition object")


class ScenarioImportResponse(BaseModel):
    """Response after a successful import."""

    scenario_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    status: str


# ---------------------------------------------------------------------------
# POST /admin/scenarios/{scenario_id}/versions
# ---------------------------------------------------------------------------


class VersionCreateRequest(BaseModel):
    """Body for creating an additional version of an existing scenario."""

    status: str = Field(default="draft")
    scenario_json: dict = Field(..., description="Full scenario definition object")


class VersionCreateResponse(BaseModel):
    """Response after creating a new version."""

    version_id: uuid.UUID
    version_number: int
    status: str


# ---------------------------------------------------------------------------
# POST /admin/scenarios/{scenario_id}/versions/{version_number}/publish
# ---------------------------------------------------------------------------


class PublishResponse(BaseModel):
    """Response after publishing a version."""

    version_id: uuid.UUID
    version_number: int
    status: str


# ---------------------------------------------------------------------------
# Teacher rolls schemas
# ---------------------------------------------------------------------------


class ClassRollCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    student_names: list[str] = Field(default_factory=list)


class ClassRollUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    student_names: list[str] | None = None


class ClassRollOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    join_code: str
    student_names: list
    created_at: datetime


# ---------------------------------------------------------------------------
# Teacher scenario-roll assignment schemas
# ---------------------------------------------------------------------------


class AssignmentCreate(BaseModel):
    scenario_id: uuid.UUID
    visible: bool = False
    sort_order: int | None = None
    grading_difficulty: GradingDifficulty = "standard"


class AssignmentUpdate(BaseModel):
    visible: bool | None = None
    sort_order: int | None = None
    grading_difficulty: GradingDifficulty | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scenario_id: uuid.UUID
    class_roll_id: uuid.UUID
    visible: bool
    sort_order: int | None
    grading_difficulty: str
    created_at: datetime


class PublishedScenarioOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    published_version_id: uuid.UUID
    version_number: int


class RollScenarioOut(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID
    class_roll_id: uuid.UUID
    visible: bool
    sort_order: int | None
    grading_difficulty: str
    created_at: datetime
    slug: str
    title: str
    description: str


# ---------------------------------------------------------------------------
# Gradebook schemas
# ---------------------------------------------------------------------------


class GradebookReflection(BaseModel):
    student_name: str | None
    submitted_at: datetime
    responses: dict
    grade_total: int | None = None
    feedback: str | None = None
    accepted: bool = False
    needs_human_review: bool = False
    graded_at: datetime | None = None


class GradebookAttempt(BaseModel):
    play_id: uuid.UUID
    started_at: datetime
    completed: bool
    outcome: str | None
    reflection: GradebookReflection | None


class GradebookStudent(BaseModel):
    learner_label: str | None
    attempts: list[GradebookAttempt]


class GradebookOut(BaseModel):
    scenario_id: uuid.UUID
    scenario_title: str
    students: list[GradebookStudent]


class RollGradebookReflection(BaseModel):
    student_name: str | None
    submitted_at: datetime
    responses: dict
    grade_total: int | None = None
    feedback: str | None = None
    accepted: bool = False
    needs_human_review: bool = False
    graded_at: datetime | None = None
    # Difficulty this attempt was actually graded under (from the stored
    # breakdown); may differ from the assignment's current setting if the
    # teacher changed it after grading. None for ungraded/legacy reflections.
    difficulty: str | None = None


class RollGradebookAttempt(BaseModel):
    play_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    completed: bool
    outcome: str | None
    reflection: RollGradebookReflection | None


class RollGradebookStudent(BaseModel):
    student_name: str
    status: str
    in_progress_play_id: uuid.UUID | None
    submitted_count: int
    latest_submitted_at: datetime | None
    best_attempt: RollGradebookAttempt | None
    attempts: list[RollGradebookAttempt]


class RollGradebookOut(BaseModel):
    roll_id: uuid.UUID
    scenario_id: uuid.UUID
    scenario_title: str
    grading_difficulty: str
    students: list[RollGradebookStudent]
