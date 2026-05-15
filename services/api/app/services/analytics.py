"""
Analytics aggregation service for admin reporting.

All functions accept an open SQLAlchemy ``Session`` and return plain
Python dicts / primitives so they are easy to test and serialise.

Filtering
---------
Pass ``version_number=None`` to aggregate across *all* versions of the
scenario.  Pass an integer to restrict to a single version.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.play import Event, EventType, Play, Reflection
from app.models.scenario import ScenarioVersion


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_version_ids(
    db: Session,
    scenario_id: uuid.UUID,
    version_number: int | None,
) -> list[uuid.UUID]:
    """Return the UUIDs of all matching ScenarioVersion rows.

    Returns an empty list when no matching rows exist (caller must handle).
    """
    stmt = select(ScenarioVersion.id).where(
        ScenarioVersion.scenario_id == scenario_id
    )
    if version_number is not None:
        stmt = stmt.where(ScenarioVersion.version_number == version_number)
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_analytics(
    db: Session,
    scenario_id: uuid.UUID,
    version_number: int | None = None,
) -> dict:
    """Compute analytics for a scenario (optionally filtered to one version).

    Returns a dict with the following keys:

    ``total_plays``
        Total number of play sessions started.

    ``completed_plays``
        Number of plays that reached an end scene.

    ``completion_rate``
        ``completed_plays / total_plays``, rounded to 4 decimal places.
        ``0.0`` when there are no plays.

    ``drop_off_by_scene``
        Mapping of ``scene_id -> count`` showing how many *incomplete*
        plays ended (abandoned) at each scene.  Plays that completed are
        excluded.

    ``choice_distribution``
        Nested mapping ``{scene_id: {choice_index_str: count}}``
        aggregated from all ``choose`` events.

    ``reflection_count``
        Total reflection submissions across all completed plays.

    ``reflection_rate``
        ``reflection_count / completed_plays``, rounded to 4 decimal places.
        ``0.0`` when there are no completed plays.
    """
    version_ids = _resolve_version_ids(db, scenario_id, version_number)

    if not version_ids:
        return {
            "total_plays": 0,
            "completed_plays": 0,
            "completion_rate": 0.0,
            "drop_off_by_scene": {},
            "choice_distribution": {},
            "reflection_count": 0,
            "reflection_rate": 0.0,
        }

    # ------------------------------------------------------------------
    # Play counts
    # ------------------------------------------------------------------
    plays_in_scope = select(Play.id).where(
        Play.scenario_version_id.in_(version_ids)
    )

    total_plays: int = db.scalar(
        select(func.count()).select_from(plays_in_scope.subquery())
    ) or 0

    completed_plays: int = db.scalar(
        select(func.count(Play.id)).where(
            Play.scenario_version_id.in_(version_ids),
            Play.completed.is_(True),
        )
    ) or 0

    completion_rate = (
        round(completed_plays / total_plays, 4) if total_plays > 0 else 0.0
    )

    # ------------------------------------------------------------------
    # Drop-off by scene (last view_scene of non-completed plays)
    # ------------------------------------------------------------------
    abandoned_ids = list(
        db.scalars(
            select(Play.id).where(
                Play.scenario_version_id.in_(version_ids),
                Play.completed.is_(False),
            )
        ).all()
    )

    drop_off_by_scene: dict[str, int] = {}
    for play_id in abandoned_ids:
        last_scene = db.scalar(
            select(Event.scene_id)
            .where(
                Event.play_id == play_id,
                Event.event_type == EventType.view_scene,
            )
            .order_by(Event.seq.desc())
            .limit(1)
        )
        if last_scene:
            drop_off_by_scene[last_scene] = drop_off_by_scene.get(last_scene, 0) + 1

    # ------------------------------------------------------------------
    # Choice distribution
    # ------------------------------------------------------------------
    choice_rows = db.execute(
        select(Event.scene_id, Event.choice_index, func.count().label("cnt"))
        .join(Play, Event.play_id == Play.id)
        .where(
            Play.scenario_version_id.in_(version_ids),
            Event.event_type == EventType.choose,
        )
        .group_by(Event.scene_id, Event.choice_index)
        .order_by(Event.scene_id, Event.choice_index)
    ).all()

    choice_distribution: dict[str, dict[str, int]] = {}
    for scene_id, choice_index, cnt in choice_rows:
        if scene_id not in choice_distribution:
            choice_distribution[scene_id] = {}
        choice_distribution[scene_id][str(choice_index)] = cnt

    # ------------------------------------------------------------------
    # Reflection rate
    # ------------------------------------------------------------------
    reflection_count: int = db.scalar(
        select(func.count(Reflection.id)).where(
            Reflection.play_id.in_(plays_in_scope)
        )
    ) or 0

    reflection_rate = (
        round(reflection_count / completed_plays, 4)
        if completed_plays > 0
        else 0.0
    )

    return {
        "total_plays": total_plays,
        "completed_plays": completed_plays,
        "completion_rate": completion_rate,
        "drop_off_by_scene": drop_off_by_scene,
        "choice_distribution": choice_distribution,
        "reflection_count": reflection_count,
        "reflection_rate": reflection_rate,
    }
