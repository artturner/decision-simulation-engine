"""Pure-function tests for the student dashboard engine and source mappers."""

from __future__ import annotations

import random
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from app.services.course_plan import CoursePlan, PlanItem, load_plans, norm_title
from app.services.dashboard import (
    ALMOST,
    DONE,
    IN_PROGRESS,
    PENDING,
    ItemRecord,
    build_dashboard,
    compute_grade,
)
from app.services.dashboard_sources import (
    _swap_origin,
    essay_records_from,
    video_grade,
    video_records_from,
)


def _plan(items: list[tuple[str, str, str, str]]) -> CoursePlan:
    """items: (key, type, source, target-iso)."""
    return CoursePlan(
        id="t", course="Test", term="T", owner_emails=("t@example.com",),
        weights={"video": 0.2, "scenario": 0.35, "frq": 0.45},
        type_labels={"video": "V", "scenario": "S", "frq": "F"},
        units={1: "One", 2: "Two"}, term_end=date(2026, 12, 11),
        late_policy="Late ok.", ahead_min_early=3, slightly_behind_max=3,
        items=tuple(
            PlanItem(key=k, title=k.title(), type=t, source=s, match_title=k,
                     chapter=1, unit=1 if i < len(items) // 2 else 2,
                     target=date.fromisoformat(d), flexible=False)
            for i, (k, t, s, d) in enumerate(items)
        ),
    )


PLAN = _plan([
    ("v1", "video", "video", "2026-09-01"),
    ("v2", "video", "video", "2026-09-02"),
    ("s1", "scenario", "scenario", "2026-09-03"),
    ("f1", "frq", "essay", "2026-09-10"),
    ("v3", "video", "video", "2026-10-06"),
    ("s2", "scenario", "scenario", "2026-10-08"),
    ("v4", "video", "video", "2026-11-20"),
    ("f2", "frq", "essay", "2026-11-25"),
])
AS_OF = date(2026, 10, 4)


def done(score, when="2026-09-01", **kw):
    return ItemRecord(state=DONE, score=score, completed_at=datetime.fromisoformat(when),
                      available=True, link="/x", **kw)


# ---------------------------------------------------------------------------
# Grade parity with the counselor report (tools/unit-reports/student_report.py)
# ---------------------------------------------------------------------------

TOOLS = Path(__file__).resolve().parents[3] / "tools"


@pytest.fixture(scope="module")
def student_report():
    sys.path.insert(0, str(TOOLS / "d2l-import"))
    sys.path.insert(0, str(TOOLS / "unit-reports"))
    try:
        import student_report as sr  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover — tooling not importable here
        pytest.skip(f"student_report not importable: {exc}")
    return sr


@pytest.mark.parametrize("seed", range(6))
def test_grade_and_pace_match_counselor_report(student_report, seed):
    plan = next(p for p in load_plans() if p.id == "psci2305-fall-2026")
    rng = random.Random(seed)
    as_of = date(2026, 10, 1 + seed)
    records = {}
    for it in plan.items:
        if rng.random() < 0.6:
            records[it.key] = done(round(rng.uniform(40, 100), 1))
    # The report keys grades by D2L item; map through its ITEMS (same order/titles).
    by_title = {i[1]: i[0] for i in student_report.ITEMS}
    grades = {by_title[it.title]: records[it.key].score for it in plan.items if it.key in records}

    expected = student_report.analyze(grades, as_of)
    dash = build_dashboard(plan, records, as_of)["summary"]

    def r(v):
        return None if v is None else round(v, 1)

    assert dash["grade"] == r(expected["grade"])
    assert dash["grade_submitted"] == r(expected["grade_submitted"])
    assert dash["pace_label"] == expected["pace"][1]
    assert dash["missing_count"] == len(expected["missing"])
    assert dash["done_count"] == expected["done_count"]
    assert dash["due_count"] == expected["due_count"]


def test_plan_items_match_report_items(student_report):
    plan = next(p for p in load_plans() if p.id == "psci2305-fall-2026")
    assert len(plan.items) == 60
    assert [it.title for it in plan.items] == [i[1] for i in student_report.ITEMS]


# ---------------------------------------------------------------------------
# Grade math details
# ---------------------------------------------------------------------------


def test_missing_counts_zero_but_pending_does_not():
    recs = {"v1": done(100), "s1": ItemRecord(state=PENDING)}
    g, gs, by_type = compute_grade(PLAN, recs, AS_OF)
    assert by_type["video"]["missing"] == 1  # v2 past due
    assert by_type["scenario"]["missing"] == 0  # s1 pending, not missing
    assert by_type["frq"]["missing"] == 1
    # video avg counted = (100 + 0) / 2 = 50; only video+frq counted (frq 0)
    assert g == pytest.approx((0.2 * 50 + 0.45 * 0) / 0.65)
    assert gs == pytest.approx(100.0)


def test_pace_tiers():
    all_due = {k: done(90) for k in ("v1", "v2", "s1", "f1")}
    assert build_dashboard(PLAN, all_due, AS_OF)["summary"]["pace"] == "ok"
    ahead = {**all_due, **{k: done(90) for k in ("v3", "s2", "v4")}}
    assert build_dashboard(PLAN, ahead, AS_OF)["summary"]["pace"] == "ahead"
    assert build_dashboard(PLAN, {}, AS_OF)["summary"]["pace"] == "behind"
    one_missing = {k: done(90) for k in ("v1", "v2", "s1")}
    assert build_dashboard(PLAN, one_missing, AS_OF)["summary"]["pace"] == "slight"


def test_catch_up_projection():
    recs = {k: done(90) for k in ("v1", "v2", "s1")}
    s = build_dashboard(PLAN, recs, AS_OF)["summary"]
    assert s["catch_up"]["items"] == 1
    assert s["catch_up"]["grade_after"] > s["grade"]


# ---------------------------------------------------------------------------
# Next moves
# ---------------------------------------------------------------------------


def test_next_moves_prioritize_quick_wins_then_past_due():
    recs = {
        "v1": done(90),
        "v2": ItemRecord(available=True, link="/v2"),  # past due, not started
        "s1": ItemRecord(state=ALMOST, available=True, link="/s1", almost_label="Reflection not submitted"),
        "f1": ItemRecord(available=True, link="/f1"),  # past due FRQ
        "v3": ItemRecord(available=True, link="/v3"),  # due in 2 days
        "v4": ItemRecord(available=True, link="/v4"),  # far future → excluded
        "s2": ItemRecord(available=False),  # not assigned yet → excluded
    }
    moves = build_dashboard(PLAN, recs, AS_OF)["next_moves"]
    keys = [m["key"] for m in moves]
    assert keys[0] == "s1" and moves[0]["kind"] == "finish"
    assert set(keys[1:3]) == {"v2", "f1"}
    assert "v4" not in keys and "s2" not in keys
    assert keys[-1] == "v3"
    f1 = next(m for m in moves if m["key"] == "f1")
    assert f1["grade_delta"] > 0 and f1["past_due"]


def test_revise_move_only_below_threshold():
    recs = {k: done(90) for k in ("v1", "v2", "f1")}
    recs["s1"] = done(70, can_revise=True, revisions_left=2)
    moves = build_dashboard(PLAN, recs, AS_OF)["next_moves"]
    rev = [m for m in moves if m["kind"] == "revise"]
    assert [m["key"] for m in rev] == ["s1"] and rev[0]["label"] == "2 revisions left"
    recs["s1"] = done(85, can_revise=True, revisions_left=2)
    assert not [m for m in build_dashboard(PLAN, recs, AS_OF)["next_moves"] if m["kind"] == "revise"]


# ---------------------------------------------------------------------------
# Game layer + tips
# ---------------------------------------------------------------------------


def test_streak_counts_on_time_weeks_and_skips_empty_weeks():
    recs = {
        "v1": done(90, "2026-09-01"), "v2": done(90, "2026-09-02"), "s1": done(90, "2026-09-03"),
        "f1": done(90, "2026-09-09"),
    }
    st = build_dashboard(PLAN, recs, AS_OF)["game"]["streak"]
    assert st == {"current_weeks": 2, "best_weeks": 2, "weeks_counted": 2}
    recs["f1"] = done(90, "2026-09-20")  # late → week of Sep 7 fails
    st = build_dashboard(PLAN, recs, AS_OF)["game"]["streak"]
    assert st["current_weeks"] == 0 and st["best_weeks"] == 1


def test_xp_level_and_badges():
    recs = {
        "v1": done(100, "2026-08-30", detail={"total_questions": 4, "first_try_correct": 4}),
        "v2": done(90, "2026-08-30"),
        "s1": done(95, "2026-09-01", detail={"dimensions": {"insight": {"level": "full"}},
                                            "improved_by_revision": True}),
        "f1": done(92, "2026-09-12"),
    }
    game = build_dashboard(PLAN, recs, AS_OF)["game"]
    assert game["xp"] > 0 and game["level"]["number"] >= 2
    earned = {b["id"] for b in game["badges"] if b["earned"]}
    assert {"early_bird", "sharpshooter", "deep_thinker", "revision_pro", "frq_ace", "comeback"} <= earned
    assert "unit_1" in earned and "unit_2" not in earned


def test_tips_surface_reflection_and_review():
    recs = {
        "s1": ItemRecord(state=ALMOST, available=True, link="/s1"),
        "v1": done(80, detail={"total_questions": 4, "first_try_correct": 2,
                               "missed": [{"prompt": "What is federalism?"}]}),
    }
    kinds = [t["kind"] for t in build_dashboard(PLAN, recs, AS_OF)["tips"]]
    assert kinds[0] == "quick_win"
    assert "review" in kinds and "catch_up" in kinds


# ---------------------------------------------------------------------------
# Source mappers
# ---------------------------------------------------------------------------


def test_video_grade_rule():
    assert video_grade("completed", 3, 4) == pytest.approx(93.75)
    assert video_grade("completed", 0, 0) == 75.0
    assert video_grade("in_progress", 3, 4) is None


def test_video_records_from_maps_titles_and_fallback_link(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "VIDEO_WEB_FALLBACK_BASE", "https://alt.example.com")
    data = {"lessons": [
        {"video_title": "V1!", "status": "completed", "total_questions": 4, "first_try_correct": 4,
         "completed_at": "2026-09-01T20:00:00Z", "link": "https://videos.example.com/join?code=AB&lesson=t",
         "missed": [], "duration_seconds": 420},
        {"video_title": "v2", "status": "in_progress", "total_questions": 3, "first_try_correct": 1,
         "link": "https://videos.example.com/join?code=AB&lesson=u"},
        {"video_title": "Unrelated", "status": "completed"},
    ]}
    recs = video_records_from(PLAN, data).records
    assert set(recs) == {"v1", "v2"}
    assert recs["v1"].state == DONE and recs["v1"].score == 100.0
    assert recs["v1"].alt_link == "https://alt.example.com/join?code=AB&lesson=t"
    assert recs["v1"].effort_minutes == 10
    assert recs["v1"].completed_at == datetime(2026, 9, 1, 15, 0)  # UTC → Central
    assert recs["v2"].state == IN_PROGRESS and recs["v2"].score is None


def test_essay_records_from_scales_and_flags_revisions():
    data = {"assignments": [
        {"title": "F1", "join_code": "ABC123", "status": "graded", "score": 39.0, "max_total": 50.0,
         "attempts": 1, "max_attempts": 3, "overridden": False,
         "first_graded_at": "2026-09-09T15:00:00Z", "dimensions": [], "feedback": "Good."},
        {"title": "f2", "join_code": "ABC123", "status": "draft", "score": None, "max_total": 100.0},
    ]}
    recs = essay_records_from(PLAN, data).records
    assert recs["f1"].score == 78.0 and recs["f1"].can_revise and recs["f1"].revisions_left == 2
    assert recs["f1"].link.endswith("/join?code=ABC123")
    assert recs["f2"].state == ALMOST


def test_swap_origin():
    assert _swap_origin("https://a.com/x?y=1", "https://b.com") == "https://b.com/x?y=1"
    assert _swap_origin("https://a.com/x", "https://a.com") is None
    assert _swap_origin(None, "https://b.com") is None
    assert norm_title("Who Governs? Three Theories") == "who governs three theories"


def test_upcoming_frq_draft_outranks_cheap_past_due_video():
    plan = _plan([("v1", "video", "video", "2026-09-01")]
                 + [(f"w{i}", "video", "video", "2026-09-01") for i in range(9)]
                 + [("s1", "scenario", "scenario", "2026-09-03"),
                    ("f0", "frq", "essay", "2026-09-10"),
                    ("f1", "frq", "essay", "2026-10-08")])
    recs = {
        "v1": ItemRecord(available=True, link="/v1"),
        **{f"w{i}": done(90) for i in range(9)},
        "s1": done(90),
        "f0": done(85),
        "f1": ItemRecord(state=ALMOST, available=True, link="/f1"),
    }
    moves = build_dashboard(plan, recs, AS_OF)["next_moves"]
    assert [m["key"] for m in moves][:2] == ["f1", "v1"]
    assert moves[0]["grade_delta"] > 10  # skipping a 45%-weight FRQ is costly


def test_this_week_looks_ahead_on_weekends():
    sunday = build_dashboard(PLAN, {}, date(2026, 10, 4))["this_week"]
    assert sunday["start"] == "2026-10-05" and set(sunday["keys"]) == {"v3", "s2"}
    wednesday = build_dashboard(PLAN, {}, date(2026, 10, 7))["this_week"]
    assert wednesday["start"] == "2026-10-05"
