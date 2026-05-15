"""
Public API router — prefix ``/public``, mounted under ``/api/v1``.

No authentication required for these endpoints.

Endpoints
---------
GET  /scenarios/{slug}
    Return metadata for the latest published version of *slug*.

POST /plays/start
    Create a play session locked to a specific scenario_version_id.
    Returns the initial scene with media URLs resolved.

GET  /plays/{play_id}
    Return the full current play state (current scene, progress, done flag).
    Reconstructs engine state by replaying the immutable event log — no
    server-side state snapshots are stored.  Safe to call after browser
    refresh or on deep-link navigation.

POST /plays/{play_id}/step
    Advance a play by one step.
    For choice scenes ``choice_index`` is required in the request body.
    For auto_advance and conditional scenes no body is needed.
    Returns the new scene, updated progress, and a ``done`` flag.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.play import Event, EventType
from app.models.scenario import Scenario, ScenarioVersion, VersionStatus
from app.repositories.play_repo import PlayRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.schemas.public import (
    BackResponse,
    ChoiceOut,
    PlayStartRequest,
    PlayStartResponse,
    PlayViewResponse,
    ProgressOut,
    ReflectionRequest,
    ReflectionResponse,
    SceneDTO,
    ScenarioMetadataOut,
    ScenarioPublicResponse,
    StepRequest,
    StepResponse,
)
from engine.engine import ScenarioEngine
from engine.models import (
    AutoAdvanceScene,
    ChoiceScene,
    ConditionalScene,
    Scenario as EngineScenario,
)

router = APIRouter(
    prefix="/public",
    tags=["public"],
)


# ---------------------------------------------------------------------------
# Internal helpers — shared by start / step / back
# ---------------------------------------------------------------------------


def _compute_progress(events: list[Event]) -> ProgressOut:
    """Derive learner progress from the event log.

    ``step_count``   — number of choose / auto_advance / conditional_advance
                       events; reflects how many transitions the player made.
    ``choices_made`` — ordered list of choice texts from choose events.
    """
    step_types = {EventType.choose, EventType.auto_advance, EventType.conditional_advance}
    choices_made = [
        e.choice_text
        for e in events
        if e.event_type == EventType.choose and e.choice_text
    ]
    step_count = sum(1 for e in events if e.event_type in step_types)
    return ProgressOut(step_count=step_count, choices_made=choices_made)


def _build_scene_dto(
    raw: dict,
    slug: str,
    version_number: int,
) -> SceneDTO:
    """Convert an engine scene dict to a ``SceneDTO`` with a resolved image URL.

    The engine's ``_scene_to_dto`` returns a raw dict that includes:
    - ``scene_id``, ``type``, ``title``, ``narration``, ``description``
    - ``image`` — a relative path (or ``None``)
    - ``choices`` (list of {text, next, effects}) for choice scenes
    - ``outcome`` / ``outcome_message`` for end scenes

    This helper:
    - replaces ``image`` with an absolute ``image_url``
    - strips ``next`` and ``effects`` from choices (internal state machine
      fields the frontend doesn't need)
    """
    image: str | None = raw.get("image")
    image_url: str | None = (
        f"{settings.MEDIA_BASE_URL}/{slug}/{version_number}/{image}"
        if image
        else None
    )

    choices: list[ChoiceOut] | None = None
    if raw.get("choices") is not None:
        choices = [ChoiceOut(text=c["text"]) for c in raw["choices"]]

    return SceneDTO(
        scene_id=raw["scene_id"],
        type=raw["type"],
        title=raw.get("title", ""),
        narration=raw.get("narration", ""),
        description=raw.get("description", ""),
        image_url=image_url,
        choices=choices,
        outcome=raw.get("outcome"),
        outcome_message=raw.get("outcome_message"),
    )


# ---------------------------------------------------------------------------
# compute_play_view — reusable service function
# ---------------------------------------------------------------------------


def compute_play_view(play_id: uuid.UUID, db: Session) -> PlayViewResponse:
    """Reconstruct and return the full current state of a play session.

    Replays the immutable event log through the engine to derive the
    current scene and progress without any server-side state snapshots.

    Args:
        play_id: UUID of the play to reconstruct.
        db:      Active SQLAlchemy session.

    Returns:
        ``PlayViewResponse`` with the current scene, progress, and
        completion / reflection metadata.

    Raises:
        HTTPException 404: Play not found.
        HTTPException 500: Engine initialisation or replay failure
                           (fail-closed — internals are not exposed).
    """
    play_repo = PlayRepository(db)
    play = play_repo.get_play(play_id)
    if play is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Play not found.",
        )

    version: ScenarioVersion = db.get(ScenarioVersion, play.scenario_version_id)  # type: ignore[assignment]
    scenario_orm: Scenario = db.get(Scenario, version.scenario_id)  # type: ignore[assignment]

    # Parse scenario JSON for metadata / reflection fields
    engine_scenario = EngineScenario.model_validate(version.scenario_json)

    # Reconstruct engine state — fail-closed on any error
    try:
        engine = ScenarioEngine(version.scenario_json)
        initial_state, _ = engine.start()
        current_state, current_scene_raw = engine.rewind(
            initial_state, play_repo.events_for_engine(play_id)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reconstruct play state.",
        )

    all_events = play_repo.get_events(play_id)
    progress = _compute_progress(all_events)

    done = play.completed
    reflection_required = False
    reflection_questions: list[str] = []
    reflection_prompts: list[str] = []

    if done:
        reflection_required = engine_scenario.metadata.completion_tracking
        reflection_questions = engine_scenario.reflection_questions
        reflection_prompts = engine_scenario.reflection_prompts

    return PlayViewResponse(
        play_id=play_id,
        scene=_build_scene_dto(current_scene_raw, scenario_orm.slug, version.version_number),
        progress=progress,
        done=done,
        outcome=play.outcome if done else None,
        outcome_message=play.outcome_message if done else None,
        reflection_required=reflection_required,
        reflection_questions=reflection_questions,
        reflection_prompts=reflection_prompts,
    )


# ---------------------------------------------------------------------------
# GET /public/scenarios/{slug}
# ---------------------------------------------------------------------------


@router.get(
    "/scenarios/{slug}",
    response_model=ScenarioPublicResponse,
    summary="Get the latest published version of a scenario",
)
def get_scenario(
    slug: str,
    db: Session = Depends(get_db),
) -> ScenarioPublicResponse:
    """Return metadata for the highest-numbered published version of *slug*.

    Returns ``HTTP 404`` when:
    - the slug does not exist, or
    - the scenario exists but has no published version.
    """
    repo = ScenarioRepository(db)
    version = repo.get_published_version(slug)

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No published version found for scenario {slug!r}.",
        )

    scenario = EngineScenario.model_validate(version.scenario_json)

    meta = scenario.metadata
    cover_image_url: str | None = (
        f"{settings.MEDIA_BASE_URL}/{slug}/{version.version_number}/{meta.cover_image}"
        if meta.cover_image
        else None
    )
    metadata_out = ScenarioMetadataOut(
        **{k: v for k, v in meta.model_dump().items() if k != "cover_image"},
        cover_image_url=cover_image_url,
    )

    return ScenarioPublicResponse(
        slug=slug,
        scenario_version_id=version.id,
        version_number=version.version_number,
        metadata=metadata_out,
        start_scene_id=scenario.start_scene_id,
        reflection_questions=scenario.reflection_questions,
        reflection_prompts=scenario.reflection_prompts,
    )


# ---------------------------------------------------------------------------
# POST /public/plays/start
# ---------------------------------------------------------------------------


@router.post(
    "/plays/start",
    response_model=PlayStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new play session",
)
def start_play(
    body: PlayStartRequest,
    db: Session = Depends(get_db),
) -> PlayStartResponse:
    """Create a play session locked to *scenario_version_id*.

    Workflow:
    1. Verify the version exists and is published.
    2. Create a ``Play`` record (``PlayRepository.create_play`` also records
       a ``start`` event at seq=0).
    3. Use the engine to obtain the initial scene.
    4. Append a ``view_scene`` event at seq=1 for the start scene.
    5. Return the play ID, serialised scene (with image URL), and initial
       progress counters.

    Returns:
        ``HTTP 201`` with ``PlayStartResponse`` on success.
        ``HTTP 404`` if the version doesn't exist or is not published.
    """
    # 1. Verify version
    version: ScenarioVersion | None = db.get(ScenarioVersion, body.scenario_version_id)
    if version is None or version.status != VersionStatus.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Published scenario version {body.scenario_version_id} not found.",
        )

    # 2. Create play (start event at seq=0 is implicit)
    play_repo = PlayRepository(db)
    play = play_repo.create_play(version.id, learner_label=body.learner_label)

    # 3. Engine: initialise state and get start scene
    engine = ScenarioEngine(version.scenario_json)
    _state, scene_raw = engine.start()

    # 4. Record view_scene for the start scene (seq=1)
    play_repo.append_event(
        play.id,
        EventType.view_scene,
        scene_id=scene_raw["scene_id"],
    )

    db.commit()

    # 5. Resolve slug for image URL construction
    scenario: Scenario = db.get(Scenario, version.scenario_id)  # type: ignore[assignment]
    scene_dto = _build_scene_dto(scene_raw, scenario.slug, version.version_number)

    return PlayStartResponse(
        play_id=play.id,
        scenario_version_id=version.id,
        scene=scene_dto,
        progress=ProgressOut(step_count=0, choices_made=[]),
    )


# ---------------------------------------------------------------------------
# GET /public/plays/{play_id}
# ---------------------------------------------------------------------------


@router.get(
    "/plays/{play_id}",
    response_model=PlayViewResponse,
    summary="Get the current state of a play session",
)
def get_play(
    play_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PlayViewResponse:
    """Return the full current state of *play_id* by replaying its event log.

    Safe to call after a browser refresh or when navigating to a deep link —
    the backend is the single source of truth for play state.

    Returns:
        ``HTTP 200`` with ``PlayViewResponse``.
        ``HTTP 404`` if *play_id* does not exist.
        ``HTTP 500`` if event replay fails (fail-closed).
    """
    return compute_play_view(play_id, db)


# ---------------------------------------------------------------------------
# POST /public/plays/{play_id}/step
# ---------------------------------------------------------------------------


@router.post(
    "/plays/{play_id}/step",
    response_model=StepResponse,
    summary="Advance a play by one step",
)
def step_play(
    play_id: uuid.UUID,
    body: StepRequest,
    db: Session = Depends(get_db),
) -> StepResponse:
    """Execute the current scene and advance the play state.

    Workflow:
    1. Load and validate the play (404 if missing, 400 if already complete).
    2. Reconstruct current engine state by replaying the event log.
    3. Validate ``choice_index`` against the current scene type.
    4. Call ``engine.step()`` to execute the scene transition.
    5. Log the appropriate event (``choose`` / ``auto_advance`` /
       ``conditional_advance``).
    6. If the new scene is an end scene: call ``complete_play()``.
       Otherwise: append a ``view_scene`` event for the next scene.
    7. Return the new scene, updated progress, and ``done`` flag.

    Returns:
        ``HTTP 200`` with ``StepResponse``.
        ``HTTP 400`` if the play is completed or ``choice_index`` is invalid.
        ``HTTP 404`` if *play_id* does not exist.
        ``HTTP 422`` if ``choice_index`` is missing for a choice scene or
                     supplied for a non-choice scene.
    """
    play_repo = PlayRepository(db)

    # 1. Load and validate play
    play = play_repo.get_play(play_id)
    if play is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Play not found.")
    if play.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Play is already completed.")

    # 2. Load scenario version and reconstruct engine state
    version: ScenarioVersion = db.get(ScenarioVersion, play.scenario_version_id)  # type: ignore[assignment]
    scenario_orm: Scenario = db.get(Scenario, version.scenario_id)  # type: ignore[assignment]

    engine = ScenarioEngine(version.scenario_json)
    initial_state, _ = engine.start()
    current_state, _ = engine.rewind(initial_state, play_repo.events_for_engine(play_id))

    # 3. Validate choice_index against scene type
    current_scene_id = current_state.current_scene_id
    current_scene = engine.scenario.scenes[current_scene_id]

    if isinstance(current_scene, ChoiceScene) and body.choice_index is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="choice_index is required for choice scenes.",
        )

    # 4. Execute the step
    try:
        new_state, new_scene_raw, _done, _outcome_info = engine.step(
            current_state, body.choice_index
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # 5. Log the transition event for the scene we just left
    if isinstance(current_scene, ChoiceScene):
        choice = current_scene.choices[body.choice_index]  # type: ignore[index]
        play_repo.append_event(
            play_id=play_id,
            event_type=EventType.choose,
            scene_id=current_scene_id,
            choice_index=body.choice_index,
            choice_text=choice.text,
            next_scene_id=new_state.current_scene_id,
            delta_json=dict(choice.effects) if choice.effects else None,
        )
    elif isinstance(current_scene, AutoAdvanceScene):
        play_repo.append_event(
            play_id=play_id,
            event_type=EventType.auto_advance,
            scene_id=current_scene_id,
            next_scene_id=new_state.current_scene_id,
        )
    elif isinstance(current_scene, ConditionalScene):
        play_repo.append_event(
            play_id=play_id,
            event_type=EventType.conditional_advance,
            scene_id=current_scene_id,
            next_scene_id=new_state.current_scene_id,
        )

    # 6. Handle end scene or log view_scene
    done: bool
    outcome_info: dict | None

    if new_scene_raw["type"] == "end":
        # Execute the end scene to extract done=True and outcome fields
        _, _, done, outcome_info = engine.step(new_state)
        play_repo.complete_play(
            play_id=play_id,
            outcome=outcome_info["outcome"] if outcome_info else None,
            outcome_message=outcome_info["outcome_message"] if outcome_info else None,
            scene_id=new_state.current_scene_id,
        )
    else:
        done = False
        outcome_info = None
        play_repo.append_event(
            play_id=play_id,
            event_type=EventType.view_scene,
            scene_id=new_state.current_scene_id,
        )

    db.commit()

    # 7. Compute progress and return
    all_events = play_repo.get_events(play_id)
    return StepResponse(
        play_id=play_id,
        scene=_build_scene_dto(new_scene_raw, scenario_orm.slug, version.version_number),
        progress=_compute_progress(all_events),
        done=done,
        outcome=outcome_info["outcome"] if outcome_info else None,
        outcome_message=outcome_info["outcome_message"] if outcome_info else None,
    )


# ---------------------------------------------------------------------------
# POST /public/plays/{play_id}/back
# ---------------------------------------------------------------------------


@router.post(
    "/plays/{play_id}/back",
    response_model=BackResponse,
    summary="Undo the last step of a play",
)
def back_play(
    play_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BackResponse:
    """Remove the last step transition and return the previous scene.

    Strategy:
    1. Load and validate the play (404 if missing).
    2. Find the last step event (choose / auto_advance / conditional_advance).
       Return 400 if there are no step events (already at start).
    3. Truncate the last step event and all events that follow it.
    4. If the play was marked completed, reset that flag so the play can
       continue.
    5. Reconstruct engine state from the surviving events.
    6. Commit and return the previous scene with updated progress.

    Returns:
        ``HTTP 200`` with ``BackResponse`` (``done`` is always ``False``).
        ``HTTP 400`` if the play is already at the start scene.
        ``HTTP 404`` if *play_id* does not exist.
        ``HTTP 500`` if event replay fails (fail-closed).
    """
    play_repo = PlayRepository(db)

    # 1. Load play
    play = play_repo.get_play(play_id)
    if play is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Play not found.")

    # 2. Find the last step event
    step_types = {EventType.choose, EventType.auto_advance, EventType.conditional_advance}
    all_events = play_repo.get_events(play_id)
    step_events = [e for e in all_events if e.event_type in step_types]

    if not step_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already at the start of the scenario.",
        )

    last_step = step_events[-1]

    # 3. Truncate the last step and everything after it
    #    (keep all events with seq < last_step.seq)
    play_repo.truncate_events_after(play_id, seq=last_step.seq - 1)

    # 4. Reset completion state if the play was marked done
    if play.completed:
        play.completed = False
        play.outcome = None
        play.outcome_message = None
        play.ended_at = None
        db.flush()

    # 5. Reconstruct engine state from surviving events — fail-closed
    version: ScenarioVersion = db.get(ScenarioVersion, play.scenario_version_id)  # type: ignore[assignment]
    scenario_orm: Scenario = db.get(Scenario, version.scenario_id)  # type: ignore[assignment]

    try:
        engine = ScenarioEngine(version.scenario_json)
        initial_state, _ = engine.start()
        current_state, current_scene_raw = engine.rewind(
            initial_state, play_repo.events_for_engine(play_id)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reconstruct play state.",
        )

    remaining_events = play_repo.get_events(play_id)
    progress = _compute_progress(remaining_events)

    db.commit()

    return BackResponse(
        play_id=play_id,
        scene=_build_scene_dto(current_scene_raw, scenario_orm.slug, version.version_number),
        progress=progress,
        done=False,
    )


# ---------------------------------------------------------------------------
# POST /public/plays/{play_id}/reflection
# ---------------------------------------------------------------------------


@router.post(
    "/plays/{play_id}/reflection",
    response_model=ReflectionResponse,
    summary="Submit a learner reflection for a completed play",
)
def submit_reflection(
    play_id: uuid.UUID,
    body: ReflectionRequest,
    db: Session = Depends(get_db),
) -> ReflectionResponse:
    """Record a learner's reflection responses after play completion.

    Workflow:
    1. Load the play (404 if missing).
    2. Verify the play is completed (400 if not).
    3. Guard against duplicate submission (409 if a reflection already exists).
    4. Persist the reflection via ``PlayRepository.add_reflection``.
    5. Commit and return confirmation.

    Returns:
        ``HTTP 200`` with ``ReflectionResponse`` on success.
        ``HTTP 400`` if the play is not yet completed.
        ``HTTP 404`` if *play_id* does not exist.
        ``HTTP 409`` if a reflection has already been submitted for this play.
    """
    play_repo = PlayRepository(db)

    # 1. Load play
    play = play_repo.get_play(play_id)
    if play is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Play not found.",
        )

    # 2. Play must be completed
    if not play.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reflection can only be submitted for a completed play.",
        )

    # 3. Guard against duplicate submission
    if play_repo.get_reflection(play_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A reflection has already been submitted for this play.",
        )

    # 4. Persist — store responses dict directly as provided
    play_repo.add_reflection(
        play_id=play_id,
        responses_json=body.responses,
        student_name=body.student_name,
    )

    db.commit()

    return ReflectionResponse(ok=True)
