#!/usr/bin/env python
"""Fetch Unit 2 (Ch 4-7) status data from all three production apps.

Like fetch_unit1.py, plus per-student claim-code status (for the
"enter your access code" checklist item). Read-only against production.
Writes raw JSON to ./unit2_raw/ (gitignored - contains student data).
"""
import json
import ssl
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "d2l-import"
sys.path.insert(0, str(TOOLS))

from export_all_grades import (  # noqa: E402
    load_config, supabase_token, get_json, get_csv_rows, norm_title, request,
)

OUT = HERE / "unit2_raw"
OUT.mkdir(exist_ok=True)

SCENARIO_TITLES = {
    "probable cause traffic stop investigation": "ch4_probable_cause",
    "the motor voter decision": "ch7_motor_voter",
}
# normalized app title -> (chapter, canonical display title)
VIDEO_TITLES = {
    "civil liberties": (4, "Civil Liberties"),
    "applying our freedoms": (4, "Applying Our Freedoms"),
    "the rights of suspects": (4, "The Rights of Suspects"),
    "unwritten rights": (4, "Unwritten Rights"),
    "civil rights rules of equality": (5, "Civil Rights: Rules of Equality"),
    "the struggle for equality": (5, "The Struggle for Equality"),
    "wider struggle for rights": (5, "Wider Struggle for Rights"),
    "the polling puzzle": (6, "The Polling Puzzle"),
    "demystifying the polls": (6, "Demystifying the Polls"),
    "what is public opinion": (6, "What Is Public Opinion"),
    "effects of public opinion": (6, "Effects of Public Opinion"),
    "voter registration and turnout": (7, "Voter Registration and Turnout"),
    "elections campaigns and voting": (7, "Elections, Campaigns and Voting"),
    "direct democracy": (7, "Direct Democracy"),
}


def windows_trust_context() -> ssl.SSLContext:
    """See fetch_unit1.py — needed when the district firewall intercepts."""
    ctx = ssl.create_default_context()
    for store in ("ROOT", "CA"):
        for cert, enc, _trust in ssl.enum_certificates(store):
            if enc == "x509_asn":
                try:
                    ctx.load_verify_locations(cadata=cert)
                except ssl.SSLError:
                    pass
    return ctx


def video_opener(cfg) -> urllib.request.OpenerDirector:
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=windows_trust_context()),
        urllib.request.HTTPCookieProcessor(CookieJar()))
    request(f"{cfg['VIDEO_API_BASE']}/api/admin/login",
            json_body={"email": cfg["VIDEO_TEACHER_EMAIL"],
                       "password": cfg["VIDEO_TEACHER_PASSWORD"]},
            opener=opener)
    return opener


def save(name: str, obj) -> None:
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    n = len(obj) if isinstance(obj, list) else "-"
    print(f"  wrote {p.name} ({n} rows)")


def main() -> None:
    cfg = load_config(TOOLS / ".env")
    token = supabase_token(cfg)
    auth = {"Authorization": f"Bearer {token}"}

    # ---- scenarios + claim codes -----------------------------------------
    base = cfg["SCENARIO_API_BASE"]
    print("scenarios:")
    scen_out, claims_out = [], []
    for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
        roll_name = roll.get("name", "")
        if roll_name.endswith("_F26"):  # fall rolls only; skip pilot/test rolls
            codes = get_json(
                f"{base}/api/v1/teacher/rolls/{roll['id']}/claim-codes", headers=auth)
            claims_out.append({"roll": roll_name, "codes": codes})
            print(f"  {roll_name}: {len(codes)} claim codes "
                  f"({sum(1 for c in codes if c['last_claimed_at'])} claimed)")
        for sc in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/scenarios",
                           headers=auth):
            key = SCENARIO_TITLES.get(norm_title(sc["title"]))
            if not key:
                continue
            rows = get_csv_rows(
                f"{base}/api/v1/teacher/rolls/{roll['id']}"
                f"/scenarios/{sc['scenario_id']}/gradebook.csv", headers=auth)
            scen_out.append({"roll": roll_name or roll["id"], "scenario": key,
                             "title": sc["title"], "rows": rows})
            print(f"  {roll_name}: {sc['title']} -> {len(rows)} students")
    save("scenarios", scen_out)
    save("claims", claims_out)

    # ---- essays ----------------------------------------------------------
    base = cfg["ESSAY_API_BASE"]
    print("essays:")
    essay_out = []
    for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
        for a in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/assignments",
                          headers=auth):
            nt = norm_title(a["title"])
            if "unit 2" not in nt and "equal protection" not in nt:
                continue
            rows = get_csv_rows(
                f"{base}/api/v1/teacher/rolls/{roll['id']}"
                f"/assignments/{a['assignment_id']}/gradebook.csv", headers=auth)
            essay_out.append({"roll": roll.get("name", roll["id"]),
                              "title": a["title"], "rows": rows})
            print(f"  {roll.get('name')}: {a['title']} -> {len(rows)} students")
    save("essays", essay_out)

    # ---- videos ----------------------------------------------------------
    # District firewall intercepts the custom domain; Railway domain is clean.
    cfg["VIDEO_API_BASE"] = "https://app-production-a23d.up.railway.app"
    base = cfg["VIDEO_API_BASE"]
    print("videos:")
    opener = video_opener(cfg)
    vid_out, matched = [], set()
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
        matched.add(norm_title(a["videoTitle"]))
        print(f"  {a['className']}: {a['videoTitle']} -> {len(rows)} students")
    save("videos", vid_out)
    missing = set(VIDEO_TITLES) - matched
    if missing:
        print(f"  WARNING: no live assignment matched: {sorted(missing)}")
    print("done")


if __name__ == "__main__":
    main()
