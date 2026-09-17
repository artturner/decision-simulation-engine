#!/usr/bin/env python
"""Fetch rich Unit 1 (Ch 1-3) data from all three production apps.

Read-only: scenario gradebooks (3 scenarios), essay gradebook (UNIT 1 FRQ),
video assignment reports + per-question item stats (9 videos), most-missed.
Writes raw JSON to ./unit1_raw/ next to this script.
"""
import json
import ssl
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

TOOLS = Path(r"C:\Users\arttu\decision-simulation-engine\tools\d2l-import")
sys.path.insert(0, str(TOOLS))

from export_all_grades import (  # noqa: E402
    load_config, supabase_token, get_json, get_csv_rows, norm_title, request,
)


def windows_trust_context() -> ssl.SSLContext:
    """Default context plus every cert in the Windows ROOT/CA stores — needed
    because the district Palo Alto firewall re-signs some domains with an
    enterprise CA that Windows trusts but Python's bundle does not."""
    ctx = ssl.create_default_context()
    for store in ("ROOT", "CA"):
        for cert, enc, _trust in ssl.enum_certificates(store):
            if enc == "x509_asn":
                try:
                    ctx.load_verify_locations(cadata=cert)
                except ssl.SSLError:
                    pass
    return ctx


def video_opener_wintrust(cfg) -> urllib.request.OpenerDirector:
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=windows_trust_context()),
        urllib.request.HTTPCookieProcessor(CookieJar()))
    request(f"{cfg['VIDEO_API_BASE']}/api/admin/login",
            json_body={"email": cfg["VIDEO_TEACHER_EMAIL"],
                       "password": cfg["VIDEO_TEACHER_PASSWORD"]},
            opener=opener)
    return opener

HERE = Path(__file__).resolve().parent
OUT = HERE / "unit1_raw"
OUT.mkdir(exist_ok=True)

SCENARIO_TITLES = {
    "liberty park under threat": "ch1_liberty_park",
    "the philadelphia compromise": "ch2_philadelphia",
    "a nation divided the cherokee choice": "ch3_cherokee",
}
VIDEO_TITLES = {
    "what is government": ("ch1", "What is Government"),
    "who governs three theories of power": ("ch1", "Who Governs? Three Theories of Power"),
    "the modern citizen civic engagement": ("ch1", "The Modern Citizen: Civic Engagement"),
    "why america declared independence the broken contract": ("ch2", "Why America Declared Independence"),
    "america s rough draft": ("ch2", "America's Rough Draft"),
    "the great debate": ("ch2", "The Great Debate"),
    "the american tug of war": ("ch3", "The American Tug-of-War"),
    "the great power struggle": ("ch3", "The Great Power Struggle"),
    "federalism a tug of war": ("ch3", "Federalism: A Tug of War"),
}


def save(name: str, obj) -> None:
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    n = len(obj) if isinstance(obj, list) else "-"
    print(f"  wrote {p.name} ({n} rows)")


def main() -> None:
    cfg = load_config(TOOLS / ".env")

    if not (OUT / "scenarios.json").exists() or not (OUT / "essays.json").exists():
        token = supabase_token(cfg)
        auth = {"Authorization": f"Bearer {token}"}

        # ---- scenarios ---------------------------------------------------
        base = cfg["SCENARIO_API_BASE"]
        print("scenarios:")
        scen_out = []
        for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
            for sc in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/scenarios", headers=auth):
                key = SCENARIO_TITLES.get(norm_title(sc["title"]))
                if not key:
                    continue
                rows = get_csv_rows(
                    f"{base}/api/v1/teacher/rolls/{roll['id']}"
                    f"/scenarios/{sc['scenario_id']}/gradebook.csv", headers=auth)
                scen_out.append({"roll": roll.get("name", roll["id"]), "scenario": key,
                                 "title": sc["title"], "rows": rows})
                print(f"  {roll.get('name')}: {sc['title']} -> {len(rows)} students")
        save("scenarios", scen_out)

        # ---- essays ------------------------------------------------------
        base = cfg["ESSAY_API_BASE"]
        print("essays:")
        essay_out = []
        for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
            for a in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/assignments", headers=auth):
                nt = norm_title(a["title"])
                if "federalism" not in nt and "unit 1" not in nt:
                    continue
                rows = get_csv_rows(
                    f"{base}/api/v1/teacher/rolls/{roll['id']}"
                    f"/assignments/{a['assignment_id']}/gradebook.csv", headers=auth)
                essay_out.append({"roll": roll.get("name", roll["id"]),
                                  "title": a["title"], "rows": rows})
                print(f"  {roll.get('name')}: {a['title']} -> {len(rows)} students")
        save("essays", essay_out)

    # ---- videos ----------------------------------------------------------
    # The district Palo Alto firewall MITMs videos.cruxlabs.academy (school
    # network); the Railway service domain is not intercepted and serves the
    # same app with a valid cert.
    cfg["VIDEO_API_BASE"] = "https://app-production-a23d.up.railway.app"
    base = cfg["VIDEO_API_BASE"]
    print("videos:")
    opener = video_opener_wintrust(cfg)
    vid_out, seen_videos = [], {}
    for a in get_json(f"{base}/api/admin/assignments", opener=opener):
        if not a.get("className"):
            continue
        hit = VIDEO_TITLES.get(norm_title(a["videoTitle"]))
        if not hit:
            continue
        chapter, canon = hit
        rows = get_json(f"{base}/api/admin/reports/assignments/{a['id']}", opener=opener)
        vid_out.append({"class": a["className"], "chapter": chapter, "video": canon,
                        "app_title": a["videoTitle"], "rows": rows})
        seen_videos.setdefault(a["videoId"], canon)
        print(f"  {a['className']}: {a['videoTitle']} -> {len(rows)} students")
    save("videos", vid_out)

    q_out = []
    for vid, canon in seen_videos.items():
        rows = get_json(f"{base}/api/admin/reports/videos/{vid}/questions", opener=opener)
        q_out.append({"video": canon, "questions": rows})
    save("video_questions", q_out)

    save("most_missed", get_json(f"{base}/api/admin/reports/most-missed", opener=opener))
    print("done")


if __name__ == "__main__":
    main()
