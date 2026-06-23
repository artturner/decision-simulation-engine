"""Generate a validated ``scenario_json`` for a chosen subject."""

from __future__ import annotations

from collections.abc import Callable

from . import GENERATOR_PROMPT_PATH, PEDAGOGY_SKILL_PATH, llm


class GenerationError(Exception):
    """Raised when generation fails to produce valid JSON after retries."""


def _load_system_prompt() -> str:
    generator = GENERATOR_PROMPT_PATH.read_text(encoding="utf-8")
    pedagogy = PEDAGOGY_SKILL_PATH.read_text(encoding="utf-8")
    return (
        f"{generator}\n\n"
        "---\n\n"
        "# Design Best Practices (reference)\n\n"
        f"{pedagogy}"
    )


def _default_validate(scenario_json: dict) -> list[str]:
    from engine.validator import validate_scenario

    return validate_scenario(scenario_json)


def _subject_brief(subject: dict) -> str:
    lines = [f"Subject: {subject.get('title', '')}", "", subject.get("summary", "")]
    dps = subject.get("decision_points") or []
    if dps:
        lines += ["", "Key decision points:", *(f"- {d}" for d in dps)]
    sh = subject.get("stakeholders") or []
    if sh:
        lines += ["", "Stakeholders:", *(f"- {s}" for s in sh)]
    if subject.get("suggested_complexity"):
        lines += ["", f"Target complexity: {subject['suggested_complexity']}"]
    return "\n".join(lines)


def generate_scenario(
    pdf_blocks: list[dict],
    subject: dict,
    model: str,
    *,
    max_repairs: int = 3,
    call_fn: Callable[..., str] | None = None,
    validate_fn: Callable[[dict], list[str]] | None = None,
) -> dict:
    """Generate ``scenario_json`` and self-repair until it passes validation.

    ``call_fn`` and ``validate_fn`` are injectable for testing; they default to
    the Anthropic conversation call and the engine's ``validate_scenario``.
    """
    call = call_fn or llm.call_conversation
    validate = validate_fn or _default_validate
    system = _load_system_prompt()

    instruction = (
        "Using the source document and the subject below, write the branching "
        "scenario as a single JSON `scenario_json` object that conforms exactly to "
        "the Output Format Specification. Output ONLY the JSON object.\n\n"
        f"{_subject_brief(subject)}"
    )
    messages: list[dict] = [
        {"role": "user", "content": [*pdf_blocks, {"type": "text", "text": instruction}]}
    ]

    last_errors: list[str] = []
    for attempt in range(max_repairs + 1):
        text = call(system=system, messages=messages, model=model)
        try:
            scenario_json = llm.extract_json(text)
        except ValueError as exc:
            last_errors = [f"Output was not valid JSON: {exc}"]
            scenario_json = None

        if isinstance(scenario_json, dict):
            errors = validate(scenario_json)
            if not errors:
                return scenario_json
            last_errors = errors

        if attempt < max_repairs:
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The JSON failed validation with these errors:\n"
                        + "\n".join(f"- {e}" for e in last_errors)
                        + "\n\nFix every error and output the corrected, complete "
                        "scenario_json object only."
                    ),
                }
            )

    raise GenerationError(
        "Could not produce valid scenario_json after "
        f"{max_repairs + 1} attempts. Last errors:\n"
        + "\n".join(f"- {e}" for e in last_errors)
    )
