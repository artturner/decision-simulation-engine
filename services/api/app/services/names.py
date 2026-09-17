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


def student_name_key(value: str | None) -> str:
    """Reduce a student name to a cross-app comparison key.

    Casefolds, collapses whitespace, and folds ``"Last, First"`` to
    ``"first last"`` so the same student matches across apps whose rosters
    disagree only on name order or case.  Shared by copy with the
    essay-grader repo — keep the two implementations identical.

    Limitation: a comma-suffixed name ("Smith, Jr., John") folds wrong;
    acceptable under the identical-roster-spellings convention.
    """
    s = normalize_student_name(value).casefold()
    if "," in s:
        last, _, first = s.partition(",")
        s = f"{first.strip()} {last.strip()}"
    return " ".join(s.split())


def names_equivalent(a: str | None, b: str | None) -> bool:
    """True when two spellings identify the same student (never for blanks)."""
    ka, kb = student_name_key(a), student_name_key(b)
    return bool(ka) and ka == kb
