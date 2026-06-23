"""Thin Anthropic helpers for the scenario generator.

Heavy SDK imports are deferred into functions so the pure helpers
(``extract_json``) can be imported and unit-tested without the SDK installed.
"""

from __future__ import annotations

import json
from typing import Any


def get_client():
    import anthropic

    from app.core.config import settings

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — required for scenario generation."
        )
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def call_text(
    *,
    system: str,
    content: list[dict],
    model: str,
    max_tokens: int = 16000,
    json_schema: dict | None = None,
) -> str:
    """Call the Messages API and return the first text block.

    ``content`` is the user message content (a list of blocks — e.g. a PDF
    document block plus a text block). ``json_schema`` (optional) constrains
    the reply to JSON via structured output. Thinking is disabled for speed.
    """
    client = get_client()
    extra_body: dict[str, Any] = {"thinking": {"type": "disabled"}}
    if json_schema is not None:
        extra_body["output_config"] = {
            "format": {"type": "json_schema", "schema": json_schema}
        }

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        extra_body=extra_body,
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


def call_conversation(
    *,
    system: str,
    messages: list[dict],
    model: str,
    max_tokens: int = 16000,
) -> str:
    """Multi-turn variant used by the validate -> repair loop."""
    client = get_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


def extract_json(text: str) -> Any:
    """Parse a JSON object/array from model output, tolerating prose/fences."""
    t = text.strip()

    # Strip a ```json ... ``` (or bare ```) fence if present.
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass

    # Fall back: decode from the first opening bracket.
    start = min(
        (i for i in (t.find("{"), t.find("[")) if i != -1),
        default=-1,
    )
    if start == -1:
        raise ValueError("No JSON object/array found in model output.")
    obj, _end = json.JSONDecoder().raw_decode(t[start:])
    return obj
