"""
Student-name normalization.

Plays store ``learner_label`` as a plain string and the roll gradebook
groups plays by exact match against the current roster, so an invisible
whitespace difference (e.g. a double space pasted into the roster)
silently orphans a student's plays.  Every comparison between a
learner-supplied name and a roster name — and every stored
``learner_label`` — must go through :func:`normalize_student_name`.

Roster names themselves are stored as the teacher typed them; they are
normalized at comparison time only, so existing rolls keep working
without a data migration.
"""

from __future__ import annotations


def normalize_student_name(value: str | None) -> str:
    """Collapse internal whitespace runs to single spaces and trim.

    Returns ``""`` for ``None`` or whitespace-only input.
    """
    if not value:
        return ""
    return " ".join(value.split())
