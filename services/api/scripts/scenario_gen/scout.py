"""Propose candidate branching-scenario subjects from a source PDF."""

from __future__ import annotations

from . import llm

_SCOUT_SYSTEM = """\
You are an instructional designer scouting a source document for the most
promising subjects to turn into educational *branching decision scenarios*.

A good subject has: a decision-maker the learner can inhabit, a moment of genuine
uncertainty or competing stakeholder interests, 3+ defensible courses of action,
and consequences that teach. Avoid topics that are purely factual recall or have
one obviously-correct answer.

Return the strongest candidates grounded in THIS document. Be specific to its
content — name the actual people, events, and tensions it describes.
"""

_SCOUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subjects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "why_good": {"type": "string"},
                    "decision_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "stakeholders": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "suggested_complexity": {
                        "type": "string",
                        "enum": ["simple", "medium", "complex"],
                    },
                },
                "required": [
                    "title",
                    "summary",
                    "why_good",
                    "decision_points",
                    "stakeholders",
                    "suggested_complexity",
                ],
            },
        }
    },
    "required": ["subjects"],
}


def scout_subjects(pdf_blocks: list[dict], n: int, model: str) -> list[dict]:
    """Return up to *n* candidate subjects grounded in the document."""
    content = [
        *pdf_blocks,
        {
            "type": "text",
            "text": (
                f"Propose the {n} most promising branching-scenario subjects from "
                "this document. Respond with JSON matching the required schema."
            ),
        },
    ]
    text = llm.call_text(
        system=_SCOUT_SYSTEM,
        content=content,
        model=model,
        max_tokens=4000,
        json_schema=_SCOUT_SCHEMA,
    )
    data = llm.extract_json(text)
    subjects = data.get("subjects", []) if isinstance(data, dict) else []
    return subjects[:n]
