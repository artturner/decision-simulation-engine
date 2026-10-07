#!/usr/bin/env python
"""D2L grade-import file that puts each student's access code in a Text item.

Delivers access codes privately through D2L (each student sees only their
own, under Grades) instead of email. Create a Text grade item in D2L first,
then:

    python fetch_unit2.py              # refresh codes (claims.json)
    python access_code_import.py       # -> OneDrive 2026 Fall/grade-imports/

    python access_code_import.py --item "Dashboard Access Code" --suffix " Text Grade"

--item must match the D2L grade item name exactly; --suffix is the column
suffix D2L uses for that item type (check a fresh grade export/template if
the import complains). Includes every rostered student with a code, claimed
or not. The file contains access codes: delete it after importing.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import checklist_unit2 as ck  # noqa: E402  (loads rosetta + claims; renders nothing)

OUT_DIR = Path(os.environ.get("ACCESS_CODE_OUT_DIR")
               or r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\grade-imports")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--item", default="Dashboard Access Code", help="D2L grade item name")
    ap.add_argument("--suffix", default=" Text Grade", help="D2L column suffix for the item type")
    args = ap.parse_args()

    recs = sorted((r for r in ck.students.values() if r.get("oid") and r.get("claim")),
                  key=lambda r: (r["last"].lower(), r["first"].lower()))
    missing = [f"{r['first']} {r['last']}" for r in ck.students.values()
               if r.get("oid") and not r.get("claim")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"access_codes_import_{date.today().isoformat()}.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["OrgDefinedId", "Last Name", "First Name", f"{args.item}{args.suffix}",
                    "End-of-Line Indicator"])
        for r in recs:
            w.writerow([r["oid"], r["last"], r["first"], r["claim"]["code"], "#"])
    print(f"wrote {out} ({len(recs)} students)")
    if missing:
        print(f"  NOTE: {len(missing)} rostered students have no access code: {missing}")


if __name__ == "__main__":
    main()
