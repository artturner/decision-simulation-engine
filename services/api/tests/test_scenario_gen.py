"""
Unit tests for the scenario generator CLI (scripts.scenario_gen).

These are network-free: the Anthropic/OpenAI calls and the engine validator are
injected as stubs. Pure helpers (slug, assembly, prompts, JSON extraction) are
tested directly.
"""

from __future__ import annotations

import json

import pytest

from scripts.scenario_gen import assemble, generate, image_prompts, llm


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
