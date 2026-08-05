"""Narrative-contradiction judge for branching scenarios.

Quantifies Finding #2: paths where an EARLIER choice is contradicted by LATER
narration that presupposes a policy the choice rejected or narrowed, with no
bridging beat acknowledging the reversal. This is what change #2 fixes, and it
is invisible to the purely structural metrics in ``analyze.py``.

Two judge backends, same interface ``judge_fn(path, transcript) -> verdict``:

* ``anthropic_judge_fn`` — the real metric. Mirrors ``app.services.ai_grader``
  exactly: ``anthropic.Anthropic``, ``messages.create`` with structured output
  via ``extra_body`` (``output_config`` json_schema, thinking disabled), model
  from ``settings.AI_GRADER_MODEL``. Requires the SDK + ANTHROPIC_API_KEY.

* ``heuristic_judge_fn`` — a deterministic OFFLINE stand-in. It does NOT read the
  narration with a model; it applies an explicit structural rule (narrower/opposed
  scope advice + reaches the removal rail + no bridging beat = contradiction). Use
  it to (a) run the pipeline with no API key, (b) as a free CI regression check,
  and (c) as ground truth to validate the LLM judge against. Its numbers are NOT
  an independent model judgment — label them as heuristic.

``judge_paths`` builds each learner transcript and aggregates verdicts into a
metrics block ready to merge into ``analyze.py`` output.
"""

from __future__ import annotations

import json
from typing import Callable

# verdict shape returned by any judge_fn
#   {"contradiction": bool, "severity": "none|minor|major",
#    "offending_scene": str, "earlier_choice": str, "explanation": str}
Verdict = dict
JudgeFn = Callable[[dict, str], Verdict]


class JudgeUnavailable(Exception):
    """Raised when the LLM judge is not configured (no SDK / no API key)."""


# ---------------------------------------------------------------------------
# Transcript construction — the exact sequence a learner experienced
# ---------------------------------------------------------------------------

def build_transcript(scenario_json: dict, path: dict) -> str:
    """Render one path as an ordered transcript: each scene's title + narration,
    and the option TEXT chosen at each choice scene."""
    scenes = scenario_json["scenes"]
    chosen_by_scene = {sid: idx for sid, idx in path["decisions"]}
    lines: list[str] = []
    for n, sid in enumerate(path["scene_seq"], 1):
        s = scenes[sid]
        title = s.get("title", sid)
        narration = (s.get("narration") or s.get("description") or "").strip()
        kind = s.get("type")
        lines.append(f"--- Beat {n}: {title} ({kind}) ---\n{narration}")
        if kind == "choice" and sid in chosen_by_scene:
            opt = s["choices"][chosen_by_scene[sid]]["text"]
            lines.append(f">> The learner CHOSE: \"{opt}\"")
        if kind == "end" and s.get("outcome_message"):
            lines.append(f"[OUTCOME] {s['outcome_message']}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Real LLM judge (Anthropic) — mirrors app.services.ai_grader
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_TEMPLATE = """\
You are a narrative-continuity checker for branching educational scenarios. You \
are given the EXACT ordered sequence a learner experienced: each scene's \
narration and, at each decision, the option TEXT the learner chose.
{premise}
Detect LOGICAL CONTRADICTIONS between a choice the learner made and LATER \
narration — specifically where later text asserts, presupposes, or depends on a \
state of affairs that an earlier choice REJECTED, FORBADE, or NARROWED, and the \
scenario never acknowledges the reversal. Also flag an ENDING whose narration \
over-claims or under-claims relative to what actually happened on THIS path \
(e.g. it congratulates the learner for preventing an event the path shows \
occurring, or condemns them for something this path avoided).

RULES:
- A contradiction requires an UNACKNOWLEDGED reversal. If a later beat explicitly \
bridges the gap (a superior overruled the learner, the learner conceded, events \
overtook the line the learner drew, etc.), it is NOT a contradiction — it is a \
resolved tension. Read the whole sequence before deciding.
- Only flag factual/logical inconsistency about what actually happened in the \
story: did an event occur that an earlier choice ruled out? does a later beat \
presuppose a decision, policy, or fact that this path's choices foreclosed? \
Do NOT flag tonal tension, hard tradeoffs, or merely bad outcomes.
- severity: "major" if a core plot fact contradicts the choice (the central \
event happened despite being ruled out, or the ending mischaracterizes what the \
path did); "minor" if a narrower detail conflicts; "none" if consistent.

Return the single most serious contradiction on the path (or none).
"""


def build_judge_system(scenario_json: dict | None = None) -> str:
    """Render the judge system prompt, injecting the scenario's OWN premise
    (title + description) so the judge is scenario-agnostic — no hardcoded
    facts about any particular scenario family."""
    premise = ""
    meta = (scenario_json or {}).get("metadata") or {}
    title = meta.get("title", "").strip()
    description = meta.get("description", "").strip()
    if title or description:
        premise = (
            "\nScenario premise (context only — judge the transcript, not the "
            f"premise): {title}. {description}\n"
        )
    return _JUDGE_SYSTEM_TEMPLATE.format(premise=premise)

_JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "contradiction": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]},
        "offending_scene": {"type": "string"},
        "earlier_choice": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": [
        "contradiction",
        "severity",
        "offending_scene",
        "earlier_choice",
        "explanation",
    ],
}


def make_anthropic_judge_fn(
    model: str | None = None,
    scenario_json: dict | None = None,
) -> JudgeFn:
    """Build the real judge. Raises JudgeUnavailable if SDK/key are missing.

    Pass ``scenario_json`` so the judge prompt carries the scenario's own
    premise; without it the prompt is still valid but premise-free.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise JudgeUnavailable("anthropic SDK is not installed.") from exc

    try:
        from app.core.config import settings

        api_key = settings.ANTHROPIC_API_KEY
        model = model or settings.AI_GRADER_MODEL
    except Exception:  # noqa: BLE001 — allow running outside the app too
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        model = model or "claude-sonnet-4-6"

    if not api_key:
        raise JudgeUnavailable("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    system = build_judge_system(scenario_json)

    def judge_fn(_path: dict, transcript: str) -> Verdict:
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": transcript}],
            extra_body={
                "thinking": {"type": "disabled"},
                "output_config": {
                    "format": {"type": "json_schema", "schema": _JUDGE_SCHEMA}
                },
            },
        )
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            raise RuntimeError("Judge returned no content.")
        return json.loads(text)

    judge_fn.model = model  # type: ignore[attr-defined]
    return judge_fn


# ---------------------------------------------------------------------------
# Deterministic offline stand-in (NOT an LLM judgment) — FDR-KOREMATSU ONLY.
# Its rules encode that scenario's specific scene graph; on any other scenario
# it is vacuously clean (and says so on stderr). Use it for fdr CI regression,
# never as a generic gate.
# ---------------------------------------------------------------------------

# Scene-1 scope options that advise something NARROWER than the citizen-inclusive
# removal the Korematsu climax requires (by choice index at the start scene).
_NARROWER_SCOPE = {1: "minor", 2: "major", 3: "major"}  # 2b, 2c, 2d
# Scenes whose narration presupposes that mass removal actually happened.
_REMOVAL_RAIL = {"4a", "4b", "4c", "5", "6.entrenched", "6.candid", "6.retreat"}
# Markers that a bridging/acknowledgment beat reconciled the reversal.
_BRIDGE_MARKERS = (
    "over your objection",
    "set aside",
    "will not survive",
    "does not hold",
    "conced",  # concede/conceded
    "overrul",
)


def make_heuristic_judge_fn(scenario_json: dict) -> JudgeFn:
    """Build the offline stand-in, closing over the scenario so it can inspect
    the SCOPE BEAT's own narration for a reconciliation marker. Scoping the marker
    scan to that beat (not the whole transcript) avoids false negatives from
    unrelated uses of words like 'concede' elsewhere in the story.

    FDR-KOREMATSU-SPECIFIC: the rail/scope rules name that scenario's scene ids.
    For any other scenario every verdict is vacuously clean."""
    scenes = scenario_json["scenes"]
    if not _REMOVAL_RAIL & set(scenes):
        import sys

        print(
            "[contradiction_judge] WARNING: the heuristic mock is "
            "fdr-korematsu-specific; this scenario shares none of its scene ids, "
            "so mock verdicts will be vacuously clean. Use the LLM judge.",
            file=sys.stderr,
        )

    def judge_fn(path: dict, _transcript: str) -> Verdict:
        seq = path["scene_seq"]
        scope_idx = next((idx for sid, idx in path["decisions"] if sid == "1"), None)
        sev = _NARROWER_SCOPE.get(scope_idx)
        reaches_rail = any(s in _REMOVAL_RAIL for s in seq)
        # The scope consequence beat is the scene right after the start choice.
        scope_beat = scenes.get(seq[1]) if len(seq) > 1 else None
        scope_narr = (scope_beat or {}).get("narration", "").lower()
        bridged = "2d.pressure" in seq or any(m in scope_narr for m in _BRIDGE_MARKERS)
        if sev and reaches_rail and not bridged:
            scope_txt = path["choice_texts"][0] if path["choice_texts"] else "scope"
            return {
                "contradiction": True,
                "severity": sev,
                "offending_scene": next(s for s in seq if s in _REMOVAL_RAIL),
                "earlier_choice": scope_txt,
                "explanation": "Narrower/opposed scope advice, yet later beats treat "
                "citizen-inclusive mass removal as fact with no acknowledged reversal.",
            }
        return {
            "contradiction": False,
            "severity": "none",
            "offending_scene": "",
            "earlier_choice": "",
            "explanation": "Consistent, or the reversal is explicitly acknowledged.",
        }

    return judge_fn


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def judge_paths(
    scenario_json: dict,
    paths: list[dict],
    judge_fn: JudgeFn,
    backend: str,
) -> dict:
    """Judge every path and aggregate. Caches by transcript so identical
    narratives cost one call."""
    cache: dict[str, Verdict] = {}
    flagged: list[dict] = []
    major = minor = 0
    for p in paths:
        transcript = build_transcript(scenario_json, p)
        if transcript not in cache:
            cache[transcript] = judge_fn(p, transcript)
        v = cache[transcript]
        if v.get("contradiction"):
            if v.get("severity") == "major":
                major += 1
            else:
                minor += 1
            flagged.append(
                {
                    "choices": p["choices"],
                    "outcome": p["outcome"],
                    "severity": v.get("severity"),
                    "offending_scene": v.get("offending_scene"),
                    "earlier_choice": v.get("earlier_choice"),
                    "explanation": v.get("explanation"),
                }
            )
    n = len(paths)
    return {
        "backend": backend,
        "model": getattr(judge_fn, "model", None),
        "judged_paths": n,
        "unique_transcripts": len(cache),
        "contradiction_paths": major + minor,
        "major": major,
        "minor": minor,
        "rate": round((major + minor) / n, 4) if n else 0.0,
        "examples": flagged[:8],
    }
