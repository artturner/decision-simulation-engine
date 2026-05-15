"""
CSV export service for admin data download.

Produces a UTF-8 CSV string with one row per play.  Dynamic
``reflection_N`` columns are added based on the number of reflection
questions defined in the scenario JSON.

Column order
------------
play_id, learner_label, started_at, completed, outcome,
path, reflection_1, reflection_2, ...

``path``
    Scene IDs visited in order, joined by `` -> ``
    (e.g. ``s1 -> s2 -> s3``).  Derived from ``view_scene`` events.

``reflection_N``
    The Nth answer from ``responses_json["responses"]``, or ``""`` when
    the play has no reflection or fewer responses than questions.
"""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.play import Event, EventType, Play, Reflection
from app.models.scenario import ScenarioVersion
from app.services.analytics import _resolve_version_ids


def export_csv(
    db: Session,
    scenario_id: uuid.UUID,
    version_number: int | None = None,
) -> str:
    """Build and return a CSV string for all plays of *scenario_id*.

    Args:
        db:             Active SQLAlchemy session.
        scenario_id:    UUID of the scenario to export.
        version_number: If given, restrict to that version number only.
                        ``None`` exports all versions.

    Returns:
        A UTF-8 CSV string (including the header row).  Returns a
        header-only string when there are no matching plays.
    """
    version_ids = _resolve_version_ids(db, scenario_id, version_number)

    # ------------------------------------------------------------------
    # Determine max reflection columns from scenario JSON
    # ------------------------------------------------------------------
    max_reflection_cols = 0
    if version_ids:
        versions = db.scalars(
            select(ScenarioVersion).where(ScenarioVersion.id.in_(version_ids))
        ).all()
        for v in versions:
            qs = v.scenario_json.get("reflection_questions", [])
            max_reflection_cols = max(max_reflection_cols, len(qs))

    reflection_headers = [
        f"reflection_{i + 1}" for i in range(max_reflection_cols)
    ]
    headers = [
        "play_id",
        "learner_label",
        "started_at",
        "completed",
        "outcome",
        "path",
        *reflection_headers,
    ]

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)

    if not version_ids:
        return output.getvalue()

    # ------------------------------------------------------------------
    # Load plays ordered by start time
    # ------------------------------------------------------------------
    plays = db.scalars(
        select(Play)
        .where(Play.scenario_version_id.in_(version_ids))
        .order_by(Play.started_at)
    ).all()

    for play in plays:
        # Path: scene IDs in seq order from view_scene and complete events.
        # view_scene records every scene a learner reaches; complete records
        # the end scene (which never gets a view_scene event).
        scene_ids = list(
            db.scalars(
                select(Event.scene_id)
                .where(
                    Event.play_id == play.id,
                    Event.event_type.in_(
                        [EventType.view_scene, EventType.complete]
                    ),
                    Event.scene_id.is_not(None),
                )
                .order_by(Event.seq)
            ).all()
        )
        path = " -> ".join(scene_ids)

        # Reflection responses — keyed by "reflection_1", "reflection_2", …
        reflection = db.scalar(
            select(Reflection).where(Reflection.play_id == play.id)
        )
        responses: dict[str, str] = {}
        if reflection is not None and isinstance(reflection.responses_json, dict):
            responses = reflection.responses_json

        reflection_values = [
            responses.get(f"reflection_{i + 1}", "")
            for i in range(max_reflection_cols)
        ]

        writer.writerow(
            [
                str(play.id),
                play.learner_label or "",
                play.started_at.isoformat() if play.started_at else "",
                str(play.completed).lower(),
                play.outcome or "",
                path,
                *reflection_values,
            ]
        )

    return output.getvalue()
