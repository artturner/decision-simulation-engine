"""
Pydantic request / response schemas for the admin API.

All UUIDs are returned as strings (Pydantic serialises uuid.UUID to str
automatically when ``model_config = ConfigDict(from_attributes=True)``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
