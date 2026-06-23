"""
Admin API router — prefix ``/admin``, mounted under ``/api/v1``.

Every route requires a valid ``X-Admin-Key`` header enforced at router level.

Endpoints
---------
POST   /scenarios/import
    Import a new scenario (creates the scenario record + version 1).
    Validates scenario_json with the engine validator before persisting.
    Returns 400 with error list if validation fails.

GET    /scenarios/{scenario_id}
    Return a scenario with all its versions.

POST   /scenarios/{scenario_id}/versions
    Create an additional version (auto-increments version_number).

POST   /scenarios/{scenario_id}/versions/{version_number}/publish
    Transition a version to published status, archiving any previously
    published version for the same scenario.

GET    /scenarios/{scenario_id}/analytics?version_number=
    Aggregated play analytics for a scenario (optionally scoped to a
    specific version number).

GET    /scenarios/{scenario_id}/export.csv?version_number=
    Download play data as a CSV file (one row per play).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from csv import DictWriter
from io import StringIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, verify_admin_key
from app.models.scenario import VersionStatus
from app.models.user import User
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.schemas.admin import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    ClassRollCreate,
    ClassRollOut,
    ClassRollUpdate,
    GradebookOut,
    GradebookAttempt,
    GradebookReflection,
    GradebookStudent,
    PublishedScenarioOut,
    PublishResponse,
    RollGradebookAttempt,
    RollGradebookOut,
    RollGradebookReflection,
    RollGradebookStudent,
    RollScenarioOut,
    ScenarioImportRequest,
    ScenarioImportResponse,
    ScenarioOut,
    VersionCreateRequest,
    VersionCreateResponse,
)
from app.services.analytics import get_analytics
from app.services.export import export_csv
from engine.validator import validate_scenario

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin_key)],
)

# Teacher-authenticated router — uses JWT instead of the legacy API key.
teacher_router = APIRouter(
    prefix="/teacher",
    tags=["teacher"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_status(raw: str) -> VersionStatus:
    """Convert a string to VersionStatus or raise 422."""
    try:
        return VersionStatus(raw)
    except ValueError:
        valid = ", ".join(s.value for s in VersionStatus)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status {raw!r}. Valid values: {valid}",
        )


def _validate_or_400(scenario_json: dict) -> None:
    """Run engine validation; raise HTTP 400 if errors found."""
    errors = validate_scenario(scenario_json)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid scenario JSON", "errors": errors},
        )


# ---------------------------------------------------------------------------
# POST /admin/scenarios/import
# ---------------------------------------------------------------------------


@router.post(
    "/scenarios/import",
    response_model=ScenarioImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a new scenario",
)
def import_scenario(
    body: ScenarioImportRequest,
    db: Session = Depends(get_db),
) -> ScenarioImportResponse:
    """Validate *scenario_json*, persist the scenario and its first version.

    Returns ``HTTP 400`` with a list of validation errors if the JSON is
    structurally or semantically invalid.
    Returns ``HTTP 409`` if the slug is already taken.
    """
    _validate_or_400(body.scenario_json)
    version_status = _parse_status(body.status)

    repo = ScenarioRepository(db)
    try:
        scenario = repo.create_scenario(body.slug, body.title, body.description)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug {body.slug!r} is already taken.",
        )

    version = repo.create_version(scenario.id, body.scenario_json, version_status)
    db.commit()

    return ScenarioImportResponse(
        scenario_id=scenario.id,
        version_id=version.id,
        version_number=version.version_number,
        status=version.status.value,
    )


# ---------------------------------------------------------------------------
# GET /admin/scenarios/{scenario_id}
# ---------------------------------------------------------------------------


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioOut,
    summary="Get a scenario with its versions",
)
def get_scenario(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ScenarioOut:
    """Return the scenario and all its versions.

    Returns ``HTTP 404`` if no scenario exists for *scenario_id*.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.scenario import Scenario

    scenario = db.scalar(
        select(Scenario)
        .options(selectinload(Scenario.versions))
        .where(Scenario.id == scenario_id)
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found.",
        )
    return ScenarioOut.model_validate(scenario)


# ---------------------------------------------------------------------------
# POST /admin/scenarios/{scenario_id}/versions
# ---------------------------------------------------------------------------


@router.post(
    "/scenarios/{scenario_id}/versions",
    response_model=VersionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new version for an existing scenario",
)
def create_version(
    scenario_id: uuid.UUID,
    body: VersionCreateRequest,
    db: Session = Depends(get_db),
) -> VersionCreateResponse:
    """Add a new version to an existing scenario.

    Returns ``HTTP 400`` if scenario_json is invalid.
    Returns ``HTTP 404`` if *scenario_id* does not exist.
    """
    _validate_or_400(body.scenario_json)
    version_status = _parse_status(body.status)

    repo = ScenarioRepository(db)
    if repo.get_by_id(scenario_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found.",
        )

    version = repo.create_version(scenario_id, body.scenario_json, version_status)
    db.commit()

    return VersionCreateResponse(
        version_id=version.id,
        version_number=version.version_number,
        status=version.status.value,
    )


# ---------------------------------------------------------------------------
# POST /admin/scenarios/{scenario_id}/versions/{version_number}/publish
# ---------------------------------------------------------------------------


@router.post(
    "/scenarios/{scenario_id}/versions/{version_number}/publish",
    response_model=PublishResponse,
    summary="Publish a specific version",
)
def publish_version(
    scenario_id: uuid.UUID,
    version_number: int,
    db: Session = Depends(get_db),
) -> PublishResponse:
    """Publish *version_number* for *scenario_id*.

    Any previously published version for the same scenario is automatically
    archived so at most one version is live at a time.

    Returns ``HTTP 404`` if the scenario or version does not exist.
    """
    from sqlalchemy import select

    from app.models.scenario import ScenarioVersion

    version = db.scalar(
        select(ScenarioVersion).where(
            ScenarioVersion.scenario_id == scenario_id,
            ScenarioVersion.version_number == version_number,
        )
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Version {version_number} for scenario {scenario_id} not found."
            ),
        )

    repo = ScenarioRepository(db)
    updated = repo.publish_version(version.id)
    db.commit()

    return PublishResponse(
        version_id=updated.id,
        version_number=updated.version_number,
        status=updated.status.value,
    )


# ---------------------------------------------------------------------------
# GET /admin/scenarios/{scenario_id}/analytics
# ---------------------------------------------------------------------------


@router.get(
    "/scenarios/{scenario_id}/analytics",
    summary="Get aggregated analytics for a scenario",
)
def scenario_analytics(
    scenario_id: uuid.UUID,
    version_number: int | None = Query(None, description="Filter to a specific version"),
    db: Session = Depends(get_db),
) -> dict:
    """Return aggregated play analytics for *scenario_id*.

    Query parameters:
        ``version_number`` — restrict to a single version.  Omit to
        aggregate across all versions.

    Returns a JSON object with:
    - ``total_plays`` / ``completed_plays`` / ``completion_rate``
    - ``drop_off_by_scene`` — incomplete play counts per last scene
    - ``choice_distribution`` — per-scene, per-choice counts
    - ``reflection_count`` / ``reflection_rate``

    Returns ``HTTP 404`` if the scenario does not exist.
    """
    repo = ScenarioRepository(db)
    if repo.get_by_id(scenario_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found.",
        )

    return get_analytics(db, scenario_id, version_number)


# ---------------------------------------------------------------------------
# GET /admin/scenarios/{scenario_id}/export.csv
# ---------------------------------------------------------------------------


@router.get(
    "/scenarios/{scenario_id}/export.csv",
    summary="Export play data as CSV",
)
def scenario_export_csv(
    scenario_id: uuid.UUID,
    version_number: int | None = Query(None, description="Filter to a specific version"),
    db: Session = Depends(get_db),
) -> Response:
    """Download play data for *scenario_id* as a CSV file.

    Query parameters:
        ``version_number`` — restrict to a single version.  Omit to
        include all versions.

    Each row represents one play session.  Columns:
    ``play_id``, ``learner_label``, ``started_at``, ``completed``,
    ``outcome``, ``path``, ``reflection_1``, ``reflection_2``, …

    Returns ``HTTP 404`` if the scenario does not exist.
    """
    repo = ScenarioRepository(db)
    if repo.get_by_id(scenario_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found.",
        )

    content = export_csv(db, scenario_id, version_number)
    filename = f"scenario-{scenario_id}.csv"
    if version_number is not None:
        filename = f"scenario-{scenario_id}-v{version_number}.csv"

    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# POST /admin/media  — upload a media file to R2 (or local disk in dev)
# ---------------------------------------------------------------------------


@router.post(
    "/media",
    summary="Upload a media file (image or video)",
)
async def upload_media(
    key: str = Form(
        ...,
        description="Relative path in the media store, e.g. cherokee-choice/1/scene_1.png",
    ),
    file: UploadFile = File(...),
) -> dict:
    """Upload *file* and store it at *key*.

    In production (R2 configured), the file is written to the R2 bucket and
    the R2 public URL is returned.  In development, the file is saved to the
    local ``media/`` directory.

    Returns ``{"url": "<public URL>", "key": "<key>"}``
    """
    from app.services.storage import upload_media as _upload

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    url = _upload(content, key, content_type)
    return {"url": url, "key": key}


# ===========================================================================
# Teacher endpoints — JWT auth via get_current_user
# ===========================================================================


# ---------------------------------------------------------------------------
# POST /teacher/rolls
# ---------------------------------------------------------------------------


@teacher_router.post(
    "/rolls",
    response_model=ClassRollOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a class roll",
)
def create_roll(
    body: ClassRollCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClassRollOut:
    repo = RollRepository(db)
    roll = repo.create(current_user.id, body.name, body.student_names)
    db.commit()
    db.refresh(roll)
    return ClassRollOut.model_validate(roll)


# ---------------------------------------------------------------------------
# GET /teacher/rolls
# ---------------------------------------------------------------------------


@teacher_router.get(
    "/rolls",
    response_model=list[ClassRollOut],
    summary="List class rolls owned by the current teacher",
)
def list_rolls(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClassRollOut]:
    repo = RollRepository(db)
    rolls = repo.list_for_owner(current_user.id)
    return [ClassRollOut.model_validate(r) for r in rolls]


# ---------------------------------------------------------------------------
# GET /teacher/rolls/{roll_id}
# ---------------------------------------------------------------------------


@teacher_router.get(
    "/rolls/{roll_id}",
    response_model=ClassRollOut,
    summary="Get a class roll",
)
def get_roll(
    roll_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClassRollOut:
    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")
    return ClassRollOut.model_validate(roll)


# ---------------------------------------------------------------------------
# PATCH /teacher/rolls/{roll_id}
# ---------------------------------------------------------------------------


@teacher_router.patch(
    "/rolls/{roll_id}",
    response_model=ClassRollOut,
    summary="Update a class roll's name or student list",
)
def update_roll(
    roll_id: uuid.UUID,
    body: ClassRollUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClassRollOut:
    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")
    roll = repo.update(roll, name=body.name, student_names=body.student_names)
    db.commit()
    db.refresh(roll)
    return ClassRollOut.model_validate(roll)


# ---------------------------------------------------------------------------
# DELETE /teacher/rolls/{roll_id}
# ---------------------------------------------------------------------------


@teacher_router.delete(
    "/rolls/{roll_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a class roll",
)
def delete_roll(
    roll_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")
    repo.delete(roll)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# GET /teacher/scenarios/published
# ---------------------------------------------------------------------------


@teacher_router.get(
    "/scenarios/published",
    response_model=list[PublishedScenarioOut],
    summary="List published scenarios available for assignment",
)
def list_published_scenarios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PublishedScenarioOut]:
    from sqlalchemy import select

    from app.models.scenario import Scenario, ScenarioVersion

    stmt = (
        select(Scenario, ScenarioVersion)
        .join(ScenarioVersion, ScenarioVersion.scenario_id == Scenario.id)
        .where(
            ScenarioVersion.status == VersionStatus.published,
            (Scenario.owner_id.is_(None)) | (Scenario.owner_id == current_user.id),
        )
        .order_by(Scenario.title, ScenarioVersion.version_number.desc())
    )

    seen: set[uuid.UUID] = set()
    scenarios: list[PublishedScenarioOut] = []
    for scenario, version in db.execute(stmt):
        if scenario.id in seen:
            continue
        seen.add(scenario.id)
        scenarios.append(
            PublishedScenarioOut(
                id=scenario.id,
                slug=scenario.slug,
                title=scenario.title,
                description=scenario.description,
                published_version_id=version.id,
                version_number=version.version_number,
            )
        )
    return scenarios


# ---------------------------------------------------------------------------
# GET /teacher/rolls/{roll_id}/scenarios
# ---------------------------------------------------------------------------


def _roll_scenario_out(assignment: object, db: Session) -> RollScenarioOut | None:
    from app.models.assignment import ScenarioRollAssignment
    from app.models.scenario import Scenario

    typed = assignment
    if not isinstance(typed, ScenarioRollAssignment):
        return None
    scenario = db.get(Scenario, typed.scenario_id)
    if scenario is None:
        return None
    return RollScenarioOut(
        id=typed.id,
        scenario_id=typed.scenario_id,
        class_roll_id=typed.class_roll_id,
        visible=typed.visible,
        sort_order=typed.sort_order,
        created_at=typed.created_at,
        slug=scenario.slug,
        title=scenario.title,
        description=scenario.description,
    )


def _attempt_grade(play: object) -> int:
    """Return a play's graded score for best-attempt ranking.

    Ungraded completed plays sort below any graded attempt (-1).
    """
    reflection = getattr(play, "reflection", None)
    if reflection is not None and reflection.grade_total is not None:
        return reflection.grade_total
    return -1


def _roll_gradebook_attempt(play: object) -> RollGradebookAttempt:
    from app.models.play import Play

    typed = play
    if not isinstance(typed, Play):
        raise TypeError("Expected Play")

    reflection = None
    if typed.reflection is not None:
        r = typed.reflection
        needs_review = bool((r.grade_breakdown or {}).get("needs_human_review", False))
        reflection = RollGradebookReflection(
            student_name=r.student_name,
            submitted_at=r.submitted_at,
            responses=r.responses_json,
            grade_total=r.grade_total,
            feedback=r.feedback,
            accepted=bool(r.accepted),
            needs_human_review=needs_review,
            graded_at=r.graded_at,
        )
    return RollGradebookAttempt(
        play_id=typed.id,
        started_at=typed.started_at,
        ended_at=typed.ended_at,
        completed=typed.completed,
        outcome=typed.outcome,
        reflection=reflection,
    )


def _get_owned_roll_assignment(
    roll_id: uuid.UUID,
    scenario_id: uuid.UUID,
    current_user: User,
    db: Session,
):
    from app.models.scenario import Scenario

    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")

    assignment = repo.get_assignment(scenario_id, roll_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")

    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")

    return roll, assignment, scenario


def _build_roll_gradebook(
    roll_id: uuid.UUID,
    scenario_id: uuid.UUID,
    current_user: User,
    db: Session,
) -> RollGradebookOut:
    from app.models.play import Play

    roll, _assignment, scenario = _get_owned_roll_assignment(
        roll_id,
        scenario_id,
        current_user,
        db,
    )

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Play)
        .join(Play.scenario_version)
        .where(
            Play.class_roll_id == roll_id,
            Play.scenario_version.has(scenario_id=scenario_id),
        )
        .options(selectinload(Play.reflection))
        .order_by(Play.learner_label, Play.started_at)
    )
    plays = list(db.scalars(stmt))
    plays_by_student: dict[str, list[Play]] = defaultdict(list)
    for play in plays:
        if play.learner_label:
            plays_by_student[play.learner_label].append(play)

    students: list[RollGradebookStudent] = []
    for student_name in roll.student_names:
        student_plays = plays_by_student.get(student_name, [])
        attempts: list[RollGradebookAttempt] = []
        in_progress_play_id: uuid.UUID | None = None
        latest_submitted_at = None
        latest_completed_play = None
        submitted_count = 0

        for play in student_plays:
            if play.completed:
                submitted_count += 1
                if play.ended_at and (
                    latest_submitted_at is None or play.ended_at > latest_submitted_at
                ):
                    latest_submitted_at = play.ended_at
                # Best attempt = highest graded score among completed plays,
                # ties broken by most recent. Exploring branches is never
                # penalized. Ungraded completed plays rank below any graded one.
                if latest_completed_play is None:
                    latest_completed_play = play
                else:
                    best_grade = _attempt_grade(latest_completed_play)
                    play_grade = _attempt_grade(play)
                    best_at = latest_completed_play.ended_at or latest_completed_play.started_at
                    play_at = play.ended_at or play.started_at
                    if play_grade > best_grade or (
                        play_grade == best_grade
                        and (best_at is None or (play_at is not None and play_at >= best_at))
                    ):
                        latest_completed_play = play
            elif in_progress_play_id is None:
                in_progress_play_id = play.id

            attempts.append(_roll_gradebook_attempt(play))

        if submitted_count > 0:
            status_label = "completed"
        elif in_progress_play_id is not None:
            status_label = "in_progress"
        else:
            status_label = "not_started"

        students.append(
            RollGradebookStudent(
                student_name=student_name,
                status=status_label,
                in_progress_play_id=in_progress_play_id,
                submitted_count=submitted_count,
                latest_submitted_at=latest_submitted_at,
                best_attempt=(
                    _roll_gradebook_attempt(latest_completed_play)
                    if latest_completed_play is not None
                    else None
                ),
                attempts=attempts,
            )
        )

    return RollGradebookOut(
        roll_id=roll_id,
        scenario_id=scenario_id,
        scenario_title=scenario.title,
        students=students,
    )


@teacher_router.get(
    "/rolls/{roll_id}/scenarios",
    response_model=list[RollScenarioOut],
    summary="List scenarios assigned to a class roll",
)
def list_roll_scenarios(
    roll_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RollScenarioOut]:
    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")

    rows: list[RollScenarioOut] = []
    for assignment in repo.list_assignments_for_roll(roll_id):
        row = _roll_scenario_out(assignment, db)
        if row is not None:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# POST /teacher/rolls/{roll_id}/scenarios  — assign a scenario to a roll
# ---------------------------------------------------------------------------


@teacher_router.post(
    "/rolls/{roll_id}/scenarios",
    response_model=RollScenarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a scenario to a class roll",
)
def assign_scenario(
    roll_id: uuid.UUID,
    body: AssignmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RollScenarioOut:
    from sqlalchemy.exc import IntegrityError

    from app.models.scenario import Scenario

    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")

    scenario = db.get(Scenario, body.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")

    try:
        assignment = repo.assign_scenario(
            body.scenario_id, roll_id, visible=body.visible, sort_order=body.sort_order
        )
        db.commit()
        db.refresh(assignment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario is already assigned to this roll.",
        )

    row = _roll_scenario_out(assignment, db)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")
    return row


# ---------------------------------------------------------------------------
# PATCH /teacher/rolls/{roll_id}/scenarios/{scenario_id}
# ---------------------------------------------------------------------------


@teacher_router.patch(
    "/rolls/{roll_id}/scenarios/{scenario_id}",
    response_model=RollScenarioOut,
    summary="Update visibility or sort order of a scenario in a roll",
)
def update_assignment(
    roll_id: uuid.UUID,
    scenario_id: uuid.UUID,
    body: AssignmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RollScenarioOut:
    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")

    assignment = repo.get_assignment(scenario_id, roll_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")

    assignment = repo.update_assignment(assignment, visible=body.visible, sort_order=body.sort_order)
    db.commit()
    db.refresh(assignment)
    row = _roll_scenario_out(assignment, db)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")
    return row


# ---------------------------------------------------------------------------
# DELETE /teacher/rolls/{roll_id}/scenarios/{scenario_id}
# ---------------------------------------------------------------------------


@teacher_router.delete(
    "/rolls/{roll_id}/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a scenario from a class roll",
)
def remove_assignment(
    roll_id: uuid.UUID,
    scenario_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    repo = RollRepository(db)
    roll = repo.get(roll_id)
    if roll is None or roll.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roll not found.")

    assignment = repo.get_assignment(scenario_id, roll_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")

    repo.remove_assignment(assignment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# GET /teacher/rolls/{roll_id}/scenarios/{scenario_id}/gradebook
# ---------------------------------------------------------------------------


@teacher_router.get(
    "/rolls/{roll_id}/scenarios/{scenario_id}/gradebook",
    response_model=RollGradebookOut,
    summary="Get roll-scoped student results for an assigned scenario",
)
def roll_gradebook(
    roll_id: uuid.UUID,
    scenario_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RollGradebookOut:
    return _build_roll_gradebook(roll_id, scenario_id, current_user, db)


@teacher_router.get(
    "/rolls/{roll_id}/scenarios/{scenario_id}/gradebook.csv",
    summary="Export roll-scoped best-attempt results as CSV",
)
def roll_gradebook_csv(
    roll_id: uuid.UUID,
    scenario_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Download one CSV row per roster student for the selected scenario.

    ``best_attempt`` is the highest-scoring completed attempt (ties broken by
    most recent), and includes the AI grade, accepted flag, review flag, and
    coaching feedback when present.  In-progress and not-started students are
    included with blank best-attempt fields so the roster remains complete.
    """
    gradebook = _build_roll_gradebook(roll_id, scenario_id, current_user, db)
    reflection_keys: list[str] = []
    seen_reflection_keys: set[str] = set()
    for student in gradebook.students:
        if student.best_attempt and student.best_attempt.reflection:
            for key in student.best_attempt.reflection.responses:
                if key not in seen_reflection_keys:
                    seen_reflection_keys.add(key)
                    reflection_keys.append(key)

    fieldnames = [
        "student_name",
        "status",
        "submitted_count",
        "latest_submitted_at",
        "best_attempt_play_id",
        "best_attempt_started_at",
        "best_attempt_submitted_at",
        "best_attempt_outcome",
        "grade_total",
        "grade_accepted",
        "needs_human_review",
        "feedback",
        "reflection_submitted_at",
        *reflection_keys,
    ]
    output = StringIO()
    writer = DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for student in gradebook.students:
        attempt = student.best_attempt
        reflection = attempt.reflection if attempt else None
        row = {
            "student_name": student.student_name,
            "status": student.status,
            "submitted_count": student.submitted_count,
            "latest_submitted_at": student.latest_submitted_at.isoformat()
            if student.latest_submitted_at
            else "",
            "best_attempt_play_id": str(attempt.play_id) if attempt else "",
            "best_attempt_started_at": attempt.started_at.isoformat()
            if attempt
            else "",
            "best_attempt_submitted_at": attempt.ended_at.isoformat()
            if attempt and attempt.ended_at
            else "",
            "best_attempt_outcome": attempt.outcome if attempt and attempt.outcome else "",
            "grade_total": reflection.grade_total
            if reflection and reflection.grade_total is not None
            else "",
            "grade_accepted": "yes" if reflection and reflection.accepted else "",
            "needs_human_review": "yes"
            if reflection and reflection.needs_human_review
            else "",
            "feedback": reflection.feedback if reflection and reflection.feedback else "",
            "reflection_submitted_at": reflection.submitted_at.isoformat()
            if reflection
            else "",
        }
        for key in reflection_keys:
            row[key] = reflection.responses.get(key, "") if reflection else ""
        writer.writerow(row)

    filename = f"roll-{roll_id}-scenario-{scenario_id}-gradebook.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# GET /teacher/scenarios/{scenario_id}/gradebook
# ---------------------------------------------------------------------------


@teacher_router.get(
    "/scenarios/{scenario_id}/gradebook",
    response_model=GradebookOut,
    summary="Get all student plays for a scenario, grouped by student name",
)
def gradebook(
    scenario_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GradebookOut:
    """Return every recorded play for a scenario, expanded by student.

    Only returns plays that were started via a class picker (plays.class_roll_id
    is not null) so the teacher sees roll-validated names, not free-text entries.

    Plays are grouped by learner_label; within each group they are ordered
    oldest-first so attempts read chronologically.
    """
    from collections import defaultdict

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.play import Play, Reflection
    from app.models.scenario import Scenario

    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")
    if scenario.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your scenario.")

    stmt = (
        select(Play)
        .join(Play.scenario_version)
        .where(
            Play.scenario_version.has(scenario_id=scenario_id),
            Play.class_roll_id.isnot(None),
        )
        .options(selectinload(Play.reflection))
        .order_by(Play.learner_label, Play.started_at)
    )
    plays = list(db.scalars(stmt))

    groups: dict[str | None, list[GradebookAttempt]] = defaultdict(list)
    for play in plays:
        ref = play.reflection
        reflection_out = None
        if ref is not None:
            reflection_out = GradebookReflection(
                student_name=ref.student_name,
                submitted_at=ref.submitted_at,
                responses=ref.responses_json,
            )
        groups[play.learner_label].append(
            GradebookAttempt(
                play_id=play.id,
                started_at=play.started_at,
                completed=play.completed,
                outcome=play.outcome,
                reflection=reflection_out,
            )
        )

    students = [
        GradebookStudent(learner_label=label, attempts=attempts)
        for label, attempts in sorted(groups.items(), key=lambda x: (x[0] or ""))
    ]

    return GradebookOut(
        scenario_id=scenario_id,
        scenario_title=scenario.title,
        students=students,
    )
