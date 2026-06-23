"""
Unit tests for the AI reflection grader (app.services.ai_grader).

These tests are DB-free and SDK-free: the deterministic scoring logic is tested
directly, and the happy path injects a fake ``anthropic`` module so no network
call or real API key is needed.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from app.core.config import settings
from app.services import ai_grader


# ---------------------------------------------------------------------------
# Deterministic scoring (_build_result)
# ---------------------------------------------------------------------------


def _ai_payload(engagement, reasoning, insight, **extra):
    payload = {
        "engagement_level": engagement,
        "engagement_evidence": "e",
        "reasoning_level": reasoning,
        "reasoning_evidence": "r",
        "insight_level": insight,
        "insight_evidence": "i",
        "needs_human_review": False,
        "review_reason": "",
        "feedback_for_student": "Nice work.",
    }
    payload.update(extra)
    return payload


class TestBuildResult:
    def test_full_marks_with_completion(self):
        result = ai_grader._build_result(
            _ai_payload("full", "full", "full"), completed=True
        )
        # 20 completion + 25 + 30 + 25 = 100
        assert result.grade_total == 100
        assert result.completion_points == 20
        assert result.low_effort_flags == []

    def test_completion_excluded_when_not_completed(self):
        result = ai_grader._build_result(
            _ai_payload("full", "full", "full"), completed=False
        )
        assert result.completion_points == 0
        assert result.grade_total == 80

    def test_level_fractions_map_to_points(self):
        result = ai_grader._build_result(
            _ai_payload("solid", "minimal", "low_effort"), completed=True
        )
        dims = result.dimensions
        assert dims["engagement"].points == round(0.8 * 25)  # 20
        assert dims["reasoning"].points == round(0.4 * 30)  # 12
        assert dims["insight"].points == 0
        assert result.grade_total == 20 + 20 + 12 + 0

    def test_low_effort_gate_flags_dimension(self):
        result = ai_grader._build_result(
            _ai_payload("low_effort", "full", "full"), completed=True
        )
        assert "engagement" in result.low_effort_flags
        assert result.dimensions["engagement"].points == 0

    def test_invalid_level_defaults_to_low_effort(self):
        result = ai_grader._build_result(
            _ai_payload("amazing", "full", "full"), completed=True
        )
        assert result.dimensions["engagement"].level == "low_effort"
        assert "engagement" in result.low_effort_flags

    def test_needs_human_review_propagates(self):
        result = ai_grader._build_result(
            _ai_payload(
                "full", "full", "full",
                needs_human_review=True,
                review_reason="possible distress",
            ),
            completed=True,
        )
        assert result.needs_human_review is True
        assert result.review_reason == "possible distress"

    def test_breakdown_dict_shape(self):
        result = ai_grader._build_result(
            _ai_payload("full", "solid", "minimal"), completed=True
        )
        bd = result.breakdown_dict()
        assert set(bd["dimensions"]) == {"engagement", "reasoning", "insight"}
        assert bd["dimensions"]["engagement"]["max_points"] == 25
        assert "completion_points" in bd
        assert "low_effort_flags" in bd


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_user_prompt_includes_questions_answers_and_path(self):
        prompt = ai_grader._build_user_prompt(
            reflection_questions=["Why?", "What next?"],
            responses={"reflection_1": "Because.", "reflection_2": "More care."},
            choice_path=["Sued in court", "Negotiated"],
        )
        assert "Why?" in prompt
        assert "Because." in prompt
        assert "Sued in court" in prompt
        assert "Negotiated" in prompt

    def test_missing_answer_marked(self):
        prompt = ai_grader._build_user_prompt(
            reflection_questions=["Q1"],
            responses={},
            choice_path=[],
        )
        assert "(no answer)" in prompt
        assert "(no recorded choices)" in prompt

    def test_rubric_is_outcome_neutral(self):
        rubric = ai_grader.DEFAULT_RUBRIC.lower()
        assert "no-win" in rubric
        assert "outcome" in rubric
        # Must not reward success / penalize failure
        assert "never reward" in rubric


# ---------------------------------------------------------------------------
# grade_reflection orchestration
# ---------------------------------------------------------------------------


class TestGradeReflection:
    def test_raises_unavailable_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
        with pytest.raises(ai_grader.GradingUnavailable):
            ai_grader.grade_reflection([], {}, [], completed=True)

    def test_happy_path_with_fake_sdk(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(settings, "AI_GRADER_MODEL", "claude-sonnet-4-6", raising=False)

        payload = _ai_payload("full", "solid", "minimal")
        fake = _make_fake_anthropic(json.dumps(payload))
        monkeypatch.setitem(sys.modules, "anthropic", fake)

        result = ai_grader.grade_reflection(
            reflection_questions=["Q1", "Q2"],
            responses={"reflection_1": "a", "reflection_2": "b"},
            choice_path=["c1"],
            completed=True,
        )
        assert result.model == "claude-sonnet-4-6"
        assert result.dimensions["engagement"].level == "full"
        # 20 completion + 25 (full) + 24 (solid 0.8*30) + 10 (minimal 0.4*25)
        assert result.grade_total == 20 + 25 + 24 + 10

    def test_api_failure_raises_grading_error(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key", raising=False)
        fake = _make_fake_anthropic(None, raise_exc=RuntimeError("boom"))
        monkeypatch.setitem(sys.modules, "anthropic", fake)
        with pytest.raises(ai_grader.GradingError):
            ai_grader.grade_reflection(["Q"], {"reflection_1": "a"}, [], completed=True)

    def test_invalid_json_raises_grading_error(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key", raising=False)
        fake = _make_fake_anthropic("not json")
        monkeypatch.setitem(sys.modules, "anthropic", fake)
        with pytest.raises(ai_grader.GradingError):
            ai_grader.grade_reflection(["Q"], {"reflection_1": "a"}, [], completed=True)


# ---------------------------------------------------------------------------
# Fake Anthropic SDK
# ---------------------------------------------------------------------------


def _make_fake_anthropic(text: str | None, raise_exc: Exception | None = None):
    """Build a stand-in ``anthropic`` module with the surface grade_reflection uses."""

    class _Block:
        def __init__(self, text):
            self.type = "text"
            self.text = text

    class _Resp:
        def __init__(self, text):
            self.content = [_Block(text)]

    class _Messages:
        def create(self, **kwargs):
            if raise_exc is not None:
                raise raise_exc
            return _Resp(text)

    class _Client:
        def __init__(self, *args, **kwargs):
            self.messages = _Messages()

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client
    return module
