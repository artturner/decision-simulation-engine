"""
AI reflection grader.

Grades a learner's reflection against an outcome-neutral rubric using the
Anthropic API.  The grading philosophy is process- and effort-based, never
outcome-based: several scenarios are intentionally no-win, so which ending a
learner reached must never affect the score.

The AI scores three reflection dimensions (engagement, reasoning, insight).
Completion (20 pts) is computed deterministically by the caller from
``play.completed`` — the AI never decides it.  The AI returns a *level* per
dimension; point values are derived server-side from the level so scoring is
deterministic and the model cannot miscompute totals.

Usage
-----
    from app.services.ai_grader import grade_reflection, GradingUnavailable

    result = grade_reflection(
        reflection_questions=[...],
        responses={...},
        choice_path=[...],
        completed=True,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings

# ---------------------------------------------------------------------------
# Rubric definition
# ---------------------------------------------------------------------------

# Maximum points per AI-scored dimension (sum = 80; completion adds 20).
DIMENSION_POINTS: dict[str, int] = {
    "engagement": 25,
    "reasoning": 30,
    "insight": 25,
}

COMPLETION_POINTS = 20

# Anchored levels -> fraction of the dimension's max points.
LEVEL_FRACTION: dict[str, float] = {
    "full": 1.0,
    "solid": 0.8,
    "minimal": 0.4,
    "low_effort": 0.0,
}

_VALID_LEVELS = set(LEVEL_FRACTION)

DEFAULT_RUBRIC = """\
Grade this learner reflection on an outcome-neutral, effort-based rubric.

ABSOLUTE RULES:
- Do NOT consider whether the scenario outcome was good or bad. Several scenarios
  are intentionally no-win (e.g. historical tragedies). Never reward "success" or
  penalize "failure".
- Reward sincere effort and genuine engagement. Never penalize unconventional or
  uncomfortable opinions — only penalize non-answers.
- The LOW-EFFORT GATE: an answer that is empty, "idk"/"none"/"n/a", a single word,
  or a copy-paste of the prompt scores "low_effort" on every dimension it affects.

Score each of three dimensions with one level: full | solid | minimal | low_effort.

- engagement: Does the reflection show the learner understood the choice they made
  and the situation they were in? ("full" = specific and scenario-grounded;
  "solid" = on-topic and sincere but general; "minimal" = vague attempt;
  "low_effort" = non-answer.)
- reasoning: Does the learner give a *why* — weighing tradeoffs, acknowledging there
  was no clean answer, or referencing specifics from the scenario or their own
  decisions?
- insight: Does the learner connect to a bigger idea or articulate what they would
  reconsider / do differently?

For each dimension also give a one-sentence `evidence` quote or paraphrase
justifying the level.

Set `needs_human_review` to true (with a short `review_reason`) when answers are
borderline low-effort, contain possible distress, or look AI-generated.

Write `feedback_for_student`: 2-4 sentences of warm, specific coaching that helps
the learner deepen their reflection next time. Never mention scores or point values.
"""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GradingUnavailable(Exception):
    """Raised when AI grading is not configured (no API key)."""


class GradingError(Exception):
    """Raised when the grading API call fails after retries."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    level: str
    points: int
    max_points: int
    evidence: str


@dataclass
class GradeResult:
    grade_total: int
    completion_points: int
    dimensions: dict[str, DimensionScore]
    feedback: str
    needs_human_review: bool
    review_reason: str | None
    low_effort_flags: list[str]
    model: str
    graded_at: datetime

    def breakdown_dict(self) -> dict:
        """Serialize to the JSONB shape stored on the reflection."""
        return {
            "completion_points": self.completion_points,
            "dimensions": {
                name: {
                    "level": d.level,
                    "points": d.points,
                    "max_points": d.max_points,
                    "evidence": d.evidence,
                }
                for name, d in self.dimensions.items()
            },
            "needs_human_review": self.needs_human_review,
            "review_reason": self.review_reason,
            "low_effort_flags": self.low_effort_flags,
        }


# ---------------------------------------------------------------------------
# Structured-output schema for the Anthropic API
# ---------------------------------------------------------------------------

_LEVEL_SCHEMA = {"type": "string", "enum": sorted(_VALID_LEVELS)}

_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "engagement_level": _LEVEL_SCHEMA,
        "engagement_evidence": {"type": "string"},
        "reasoning_level": _LEVEL_SCHEMA,
        "reasoning_evidence": {"type": "string"},
        "insight_level": _LEVEL_SCHEMA,
        "insight_evidence": {"type": "string"},
        "needs_human_review": {"type": "boolean"},
        "review_reason": {"type": "string"},
        "feedback_for_student": {"type": "string"},
    },
    "required": [
        "engagement_level",
        "engagement_evidence",
        "reasoning_level",
        "reasoning_evidence",
        "insight_level",
        "insight_evidence",
        "needs_human_review",
        "review_reason",
        "feedback_for_student",
    ],
}


def _build_user_prompt(
    reflection_questions: list[str],
    responses: dict[str, str],
    choice_path: list[str],
) -> str:
    qa_lines = []
    for i, question in enumerate(reflection_questions, start=1):
        key = f"reflection_{i}"
        answer = responses.get(key, "").strip()
        qa_lines.append(f"Q{i}: {question}\nA{i}: {answer or '(no answer)'}")
    # Include any extra response keys not matched by index.
    matched = {f"reflection_{i}" for i in range(1, len(reflection_questions) + 1)}
    for key, answer in responses.items():
        if key not in matched:
            qa_lines.append(f"{key}: {answer}")

    path_text = (
        "\n".join(f"- {c}" for c in choice_path)
        if choice_path
        else "(no recorded choices)"
    )

    return (
        "The learner's decisions during the scenario were:\n"
        f"{path_text}\n\n"
        "Their reflection answers:\n\n"
        + "\n\n".join(qa_lines)
    )


def grade_reflection(
    reflection_questions: list[str],
    responses: dict[str, str],
    choice_path: list[str],
    completed: bool,
) -> GradeResult:
    """Grade a reflection. Raises ``GradingUnavailable`` / ``GradingError``."""
    if not settings.ai_grading_enabled:
        raise GradingUnavailable("AI grading is not configured.")

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise GradingUnavailable("anthropic SDK is not installed.") from exc

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_prompt = _build_user_prompt(reflection_questions, responses, choice_path)

    try:
        response = client.messages.create(
            model=settings.AI_GRADER_MODEL,
            max_tokens=1024,
            system=DEFAULT_RUBRIC,
            messages=[{"role": "user", "content": user_prompt}],
            # Passed via extra_body so the request shape is independent of the
            # installed SDK version's typed kwargs. structured output constrains
            # the reply to valid JSON; thinking is disabled for a fast, cheap call.
            extra_body={
                "thinking": {"type": "disabled"},
                "output_config": {
                    "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - surface any API failure uniformly
        raise GradingError(f"Grading API call failed: {exc}") from exc

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise GradingError("Grading API returned no content.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GradingError("Grading API returned invalid JSON.") from exc

    return _build_result(data, completed)


def _build_result(data: dict, completed: bool) -> GradeResult:
    dimensions: dict[str, DimensionScore] = {}
    low_effort_flags: list[str] = []
    total = COMPLETION_POINTS if completed else 0

    for name, max_points in DIMENSION_POINTS.items():
        level = data.get(f"{name}_level")
        if level not in _VALID_LEVELS:
            level = "low_effort"
        points = round(LEVEL_FRACTION[level] * max_points)
        total += points
        if level == "low_effort":
            low_effort_flags.append(name)
        dimensions[name] = DimensionScore(
            level=level,
            points=points,
            max_points=max_points,
            evidence=str(data.get(f"{name}_evidence", "")),
        )

    return GradeResult(
        grade_total=total,
        completion_points=COMPLETION_POINTS if completed else 0,
        dimensions=dimensions,
        feedback=str(data.get("feedback_for_student", "")),
        needs_human_review=bool(data.get("needs_human_review", False)),
        review_reason=(data.get("review_reason") or None),
        low_effort_flags=low_effort_flags,
        model=settings.AI_GRADER_MODEL,
        graded_at=datetime.now(timezone.utc),
    )
