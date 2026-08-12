"""
Unit tests for the scenario generator CLI (scripts.scenario_gen).

These are network-free: the Anthropic/OpenAI calls and the engine validator are
injected as stubs. Pure helpers (slug, assembly, prompts, JSON extraction) are
tested directly.
"""

from __future__ import annotations

import json

import pytest

from scripts.scenario_gen import assemble, depth, generate, image_prompts, llm, quality


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestAssemble:
    def test_slugify(self):
        assert assemble.slugify("A Nation Divided: The Cherokee Choice") == (
            "a-nation-divided-the-cherokee-choice"
        )
        assert assemble.slugify("  Spaces & Symbols!! ") == "spaces-symbols"
        assert assemble.slugify("") == "scenario"

    def test_slug_to_media_folder(self):
        assert assemble.slug_to_media_folder("cherokee-nation") == "cherokee_nation"

    def test_build_import_shape(self):
        obj = assemble.build_import("s", "T", "D", {"scenes": {}})
        assert set(obj) == {"slug", "title", "description", "status", "scenario_json"}
        assert obj["status"] == "draft"
        assert obj["scenario_json"] == {"scenes": {}}


class TestExtractJson:
    def test_plain(self):
        assert llm.extract_json('{"a": 1}') == {"a": 1}

    def test_fenced(self):
        assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_prose_around(self):
        assert llm.extract_json('Here:\n{"a": [1,2]}\nThanks') == {"a": [1, 2]}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            llm.extract_json("no json here")


class TestImagePrompts:
    def test_skips_absolute_urls_and_none(self):
        sj = {
            "scenes": {
                "1": {"title": "Start", "description": "A room", "image": "scene_1.png"},
                "2": {"title": "Hosted", "image": "https://cdn/x.png"},
                "3": {"title": "No image"},
            }
        }
        prompts = image_prompts.build_prompts(sj)
        assert set(prompts) == {"1"}
        assert prompts["1"]["filename"] == "scene_1.png"
        assert "A room" in prompts["1"]["prompt"]
        assert image_prompts.STYLE_PREAMBLE.split(".")[0] in prompts["1"]["prompt"]

    def test_filename_synthesized_for_dotted_id(self):
        sj = {"scenes": {"5.yea": {"title": "End", "image": "scene_5_yea.png"}}}
        prompts = image_prompts.build_prompts(sj)
        assert prompts["5.yea"]["filename"] == "scene_5_yea.png"


class TestArtDirectorPrompts:
    SJ = {
        "metadata": {"title": "Redistricting", "description": "A commission redraws maps"},
        "scenes": {
            "1": {"title": "Office", "description": "A modern office", "image": "scene_1.png"},
            "2": {"title": "Proposal", "narration": "A reform-minded staffer", "image": "scene_2.png"},
            "3": {"title": "Hosted", "image": "https://cdn/x.png"},
        },
    }

    def _stub(self, *, system, content, model, max_tokens, json_schema):
        # The full scenario description and every target scene_id reach the model.
        ut = content[0]["text"]
        assert "A commission redraws maps" in ut and "[1]" in ut and "[2]" in ut
        return json.dumps(
            {
                "setting_brief": "present-day state capitol",
                "prompts": [
                    {"scene_id": "1", "prompt": "A contemporary office, two officials."}
                ],
            }
        )

    def test_uses_model_prompt_and_prepends_style(self):
        out = image_prompts.build_prompts_llm(self.SJ, "m", call_fn=self._stub)
        assert set(out) == {"1", "2"}  # hosted scene skipped
        assert out["1"]["prompt"].startswith(image_prompts.STYLE_PREAMBLE)
        assert "contemporary office" in out["1"]["prompt"]

    def test_falls_back_to_template_for_omitted_scene(self):
        out = image_prompts.build_prompts_llm(self.SJ, "m", call_fn=self._stub)
        # Scene 2 was omitted by the model → deterministic template fallback.
        assert out["2"]["filename"] == "scene_2.png"
        assert image_prompts.STYLE_PREAMBLE.split(".")[0] in out["2"]["prompt"]

    def test_no_targets_returns_empty(self):
        assert image_prompts.build_prompts_llm({"scenes": {}}, "m", call_fn=self._stub) == {}


# ---------------------------------------------------------------------------
# Generation: validate -> repair loop
# ---------------------------------------------------------------------------

VALID = {
    "metadata": {"title": "T"},
    "start_scene_id": "1",
    "scenes": {"1": {"type": "end", "outcome": "done"}},
}


class TestGenerateRepairLoop:
    def test_returns_on_first_valid(self):
        calls = {"n": 0}

        def call_fn(**kwargs):
            calls["n"] += 1
            return json.dumps(VALID)

        result = generate.generate_scenario(
            [], {"title": "S"}, "m",
            call_fn=call_fn,
            validate_fn=lambda sj: [],
        )
        assert result == VALID
        assert calls["n"] == 1

    def test_repairs_then_succeeds(self):
        outputs = ['{"bad": true}', json.dumps(VALID)]
        seen_errors = {"second_call_had_errors": False}

        def call_fn(*, system, messages, model):
            # On the repair turn, the prior errors must be in the conversation.
            if len(messages) > 1:
                seen_errors["second_call_had_errors"] = any(
                    "failed validation" in m["content"]
                    for m in messages
                    if isinstance(m.get("content"), str)
                )
            return outputs[len(messages) // 2]

        def validate_fn(sj):
            return [] if sj == VALID else ["scenes: bad"]

        result = generate.generate_scenario(
            [], {"title": "S"}, "m",
            call_fn=call_fn,
            validate_fn=validate_fn,
        )
        assert result == VALID
        assert seen_errors["second_call_had_errors"]

    def test_raises_after_max_repairs(self):
        def call_fn(**kwargs):
            return '{"still": "bad"}'

        with pytest.raises(generate.GenerationError):
            generate.generate_scenario(
                [], {"title": "S"}, "m",
                max_repairs=2,
                call_fn=call_fn,
                validate_fn=lambda sj: ["nope"],
            )


# ---------------------------------------------------------------------------
# Quality gate + reviser loop (network-free; real engine, injected LLMs)
# ---------------------------------------------------------------------------

# State-gated: variable is read by a conditional, the choice flips the outcome.
GOOD_SJ = {
    "metadata": {"title": "Good", "description": "A state-gated scenario"},
    "variables": {"Trust": 0},
    "start_scene_id": "1",
    "scenes": {
        "1": {
            "title": "Decide", "type": "choice",
            "choices": [
                {"text": "earn trust", "next": "2", "effects": {"Trust": 2}},
                {"text": "burn trust", "next": "2", "effects": {"Trust": -2}},
            ],
        },
        "2": {
            "title": "Reckoning", "type": "conditional",
            "conditions": [{"condition": "Trust >= 1", "next": "3.win"}],
            "default": "3.lose",
        },
        "3.win": {"title": "Win", "type": "end", "outcome": "win",
                  "outcome_message": "w"},
        "3.lose": {"title": "Lose", "type": "end", "outcome": "lose",
                   "outcome_message": "l"},
    },
}

# Broken like rio-grande: write-only variable, both branches converge on the
# single reachable ending, so the one choice point is inert.
BAD_SJ = {
    "metadata": {"title": "Bad", "description": "A write-only scenario"},
    "variables": {"Trust": 0},
    "start_scene_id": "1",
    "scenes": {
        "1": {
            "title": "Decide", "type": "choice",
            "choices": [
                {"text": "a", "next": "2a", "effects": {"Trust": 2}},
                {"text": "b", "next": "2b", "effects": {"Trust": -2}},
            ],
        },
        "2a": {"title": "A", "type": "auto_advance", "next": "3"},
        "2b": {"title": "B", "type": "auto_advance", "next": "3"},
        "3": {"title": "End", "type": "end", "outcome": "only",
              "outcome_message": "o"},
        "3.unreachable": {"title": "Never", "type": "end", "outcome": "never",
                          "outcome_message": "n"},
    },
}


class TestStructuralGate:
    def test_good_scenario_passes_every_check(self):
        gate = quality.structural_gate(GOOD_SJ)
        assert gate.ok
        assert all(c["ok"] for c in gate.checks.values())
        assert gate.metrics["variables_read_count"] == 1
        assert gate.metrics["inert_choice_scenes"] == []
        assert gate.metrics["outcomes_reachable"] == ["lose", "win"]

    def test_bad_scenario_fails_every_check(self):
        gate = quality.structural_gate(BAD_SJ)
        assert not gate.ok
        assert not gate.checks["variables_read"]["ok"]
        assert not gate.checks["all_choices_influential"]["ok"]
        assert not gate.checks["outcomes_reachable"]["ok"]
        assert gate.metrics["inert_choice_scenes"] == ["1"]
        assert gate.metrics["outcomes_declared"] == ["never", "only"]

    def test_no_variables_declared_is_not_a_write_only_failure(self):
        sj = json.loads(json.dumps(GOOD_SJ))
        del sj["variables"]
        sj["scenes"]["2"] = {"title": "Split", "type": "auto_advance", "next": "3.win"}
        sj["scenes"]["1"]["choices"][1]["next"] = "3.lose"
        gate = quality.structural_gate(sj)
        assert gate.checks["variables_read"]["ok"]


class TestQualityLoop:
    def test_pass_at_birth_accepted_without_judge_or_reviser(self):
        def no_call(**kwargs):
            raise AssertionError("reviser must not run on a passing scenario")

        def no_judge(sj):
            raise AssertionError("judge must not run on an as-generated pass")

        res = quality.run_quality_loop(
            GOOD_SJ, gen_model="m", call_fn=no_call, judge_factory=no_judge,
            log=lambda _m: None,
        )
        assert res.passed
        assert res.scenario_json == GOOD_SJ
        assert res.report["revisions_attempted"] == 0
        assert res.report["versions"][0]["accepted"]

    def test_reviser_repairs_failing_scenario(self):
        seen = {"findings": ""}

        def call_fn(*, system, messages, model, max_tokens):
            seen["findings"] = messages[0]["content"]
            assert "Revision Mode" in system
            return json.dumps(GOOD_SJ)

        res = quality.run_quality_loop(
            BAD_SJ, gen_model="m", call_fn=call_fn,
            judge_factory=lambda sj: None, log=lambda _m: None,
        )
        assert res.passed
        assert res.scenario_json == GOOD_SJ
        assert res.report["revisions_attempted"] == 1
        assert res.report["best_iteration"] == 1
        # The reviser saw the concrete structural findings.
        assert "FAIL variables_read" in seen["findings"]
        assert "inert" in seen["findings"]

    def test_keep_best_returns_original_when_reviser_never_improves(self):
        def call_fn(**kwargs):
            return json.dumps(BAD_SJ)  # reviser returns the same broken thing

        res = quality.run_quality_loop(
            BAD_SJ, gen_model="m", max_iters=2, call_fn=call_fn,
            judge_factory=lambda sj: None, log=lambda _m: None,
        )
        assert not res.passed
        assert res.scenario_json == BAD_SJ
        assert res.report["best_iteration"] == 0  # ties resolve to the original
        assert res.report["revisions_attempted"] == 2

    def test_revised_version_must_survive_the_judge(self):
        flagged = {
            "contradiction": True, "severity": "major",
            "offending_scene": "3.win", "earlier_choice": "a",
            "explanation": "ending contradicts the path",
        }

        def judge_factory(sj):
            def judge_fn(_path, _transcript):
                return dict(flagged)
            return judge_fn

        def call_fn(**kwargs):
            return json.dumps(GOOD_SJ)

        res = quality.run_quality_loop(
            BAD_SJ, gen_model="m", max_iters=1, judge_k=3,
            call_fn=call_fn, judge_factory=judge_factory, log=lambda _m: None,
        )
        # Revision fixed the structure but the judge stably flags every path →
        # the loop must NOT report a pass.
        assert not res.passed
        v1 = res.report["versions"][1]
        assert v1["gate_ok"] and not v1["accepted"]
        assert v1["stability"]["stable_total"] > 0

    def test_all_judge_samples_erroring_is_not_a_vacuous_pass(self):
        def judge_factory(sj):
            def judge_fn(_path, _transcript):
                raise RuntimeError("billing/outage")
            return judge_fn

        def call_fn(**kwargs):
            return json.dumps(GOOD_SJ)

        res = quality.run_quality_loop(
            BAD_SJ, gen_model="m", max_iters=2, judge_k=3,
            call_fn=call_fn, judge_factory=judge_factory, log=lambda _m: None,
        )
        # v0 fails structurally; the judge is fully erroring, so no version may
        # be reported as passed, and the loop must stop without crashing.
        assert not res.passed
        assert all(not v["accepted"] for v in res.report["versions"])

    def test_reviser_transport_error_returns_best_so_far(self):
        def call_fn(**kwargs):
            raise ConnectionError("api unreachable")

        res = quality.run_quality_loop(
            BAD_SJ, gen_model="m", call_fn=call_fn,
            judge_factory=lambda sj: None, log=lambda _m: None,
        )
        assert not res.passed
        assert res.scenario_json == BAD_SJ  # graceful keep-best, no crash

    def test_reviser_validation_failures_are_repaired_in_conversation(self):
        outputs = ['{"metadata": "broken"}', json.dumps(GOOD_SJ)]
        calls = {"n": 0}

        def call_fn(*, system, messages, model, max_tokens):
            out = outputs[calls["n"]]
            calls["n"] += 1
            if calls["n"] == 2:  # repair turn must carry the validator errors
                assert any(
                    isinstance(m.get("content"), str)
                    and "failed engine validation" in m["content"]
                    for m in messages
                )
            return out

        revised = quality.revise_scenario(BAD_SJ, "findings", "m", call_fn=call_fn)
        assert revised == GOOD_SJ

    def test_reviser_gives_up_after_max_repairs(self):
        def call_fn(**kwargs):
            return "not json at all"

        with pytest.raises(quality.ReviseError):
            quality.revise_scenario(BAD_SJ, "findings", "m",
                                    call_fn=call_fn, max_repairs=1)


# ---------------------------------------------------------------------------
# Decision depth (--min-decisions)
# ---------------------------------------------------------------------------

# Every route passes 2 choice scenes ("1", then "3" — reached directly, via
# the auto_advance bridge, or via the conditional's only condition).
DEEP_SJ = {
    "metadata": {"title": "Deep"},
    "start_scene_id": "1",
    "scenes": {
        "1": {
            "title": "First", "type": "choice",
            "choices": [
                {"text": "long way", "next": "2"},
                {"text": "short way", "next": "4"},
            ],
        },
        "2": {"title": "Bridge", "type": "auto_advance", "next": "3"},
        "3": {
            "title": "Second", "type": "choice",
            "choices": [{"text": "on", "next": "5"}],
        },
        "4": {
            "title": "Weigh", "type": "conditional",
            "conditions": [{"condition": "true", "next": "3"}],
        },
        "5": {"title": "End", "type": "end", "outcome": "o",
              "outcome_message": "m"},
    },
}


class TestMinDecisionDepth:
    def test_counts_choice_scenes_only(self):
        # choice → conditional → end: one decision beat.
        assert depth.min_decision_depth(GOOD_SJ) == 1

    def test_min_over_all_routes(self):
        assert depth.min_decision_depth(DEEP_SJ) == 2

    def test_conditional_default_is_a_route(self):
        # A default that skips the second choice scene shortens the minimum.
        sj = json.loads(json.dumps(DEEP_SJ))
        sj["scenes"]["4"]["default"] = "5"
        assert depth.min_decision_depth(sj) == 1

    def test_cycles_do_not_hang_or_shorten(self):
        sj = {
            "start_scene_id": "1",
            "scenes": {
                "1": {"type": "choice", "choices": [
                    {"text": "loop", "next": "2"},
                    {"text": "on", "next": "3"},
                ]},
                "2": {"type": "auto_advance", "next": "1"},
                "3": {"type": "end", "outcome": "o"},
            },
        }
        assert depth.min_decision_depth(sj) == 1

    def test_no_reachable_end_returns_zero(self):
        sj = {
            "start_scene_id": "1",
            "scenes": {
                "1": {"type": "auto_advance", "next": "2"},
                "2": {"type": "auto_advance", "next": "1"},
            },
        }
        assert depth.min_decision_depth(sj) == 0


class TestMinDecisionsValidator:
    def test_passes_when_floor_met(self):
        assert depth.min_decisions_validator(1)(GOOD_SJ) == []

    def test_depth_error_when_valid_but_shallow(self):
        errors = depth.min_decisions_validator(2)(GOOD_SJ)
        assert len(errors) == 1
        assert "only 1 choice scene" in errors[0]
        assert "at least 2" in errors[0]
        assert "EVERY branch" in errors[0]

    def test_engine_errors_come_first_without_depth_error(self):
        sj = json.loads(json.dumps(GOOD_SJ))
        sj["scenes"]["1"]["choices"][0]["next"] = "nowhere"
        errors = depth.min_decisions_validator(2)(sj)
        assert errors
        assert not any("Decision depth" in e for e in errors)

    def test_depth_shortfall_flows_through_the_repair_loop(self):
        outputs = [json.dumps(GOOD_SJ), json.dumps(DEEP_SJ)]
        seen = {"depth_error_in_repair_turn": False}

        def call_fn(*, system, messages, model):
            if len(messages) > 1:
                seen["depth_error_in_repair_turn"] = any(
                    isinstance(m.get("content"), str)
                    and "Decision depth too shallow" in m["content"]
                    for m in messages
                )
            return outputs[len(messages) // 2]

        result = generate.generate_scenario(
            [], {"title": "S"}, "m",
            call_fn=call_fn,
            validate_fn=depth.min_decisions_validator(2),
        )
        assert result == DEEP_SJ
        assert seen["depth_error_in_repair_turn"]

    def test_gate_metrics_surface_decisions_min(self):
        assert quality.structural_gate(GOOD_SJ).metrics["decisions_min"] == 1
