"""Build v3 (unilateral-military ending + Scene-5 reveal de-dup) on top of v2.

Change #3 — the road-not-taken can go wrong:
  * "2d.pressure" grows from 2 choices to 3. Alongside HOLD FIRM (-> averted) and
    CONCEDE (-> removal rail), a middle option lets the advisor keep the
    principled stance but decline to force a rupture with the Army — permitting
    General DeWitt to impose exclusion on his OWN military authority. That routes
    to a new END "6.unilateral" ("Rule of the General"): removal by military fiat,
    lawless and beyond any court. New outcome code: military_supremacy.
    (1 NEW image: scene_6_unilateral.png)

Change #4 — Scene-5 reveal de-dup (TEXT ONLY, 0 images):
  * The "intelligence surfaces" beat is reworded as VINDICATION of what Attorney
    General Biddle (present in every branch) argued from the outset, so it no
    longer reads as fresh news to a 2c/2d advisor who already made that case.

New images required by v3: 1  (scene "6.unilateral").
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "fdr-korematsu" / "v2_scope_branch-import.json"
DST = HERE / "fdr-korematsu" / "v3_unilateral_and_dedup-import.json"

MEDIA_BASE = "https://media.cruxlabs.academy/fdr_korematsu/1"
UNILATERAL_ID = "6.unilateral"

# ---- #3: the three-way pressure decision (replaces 2d.pressure choices) -------
PRESSURE_CHOICES = [
    {
        "text": (
            "Hold firm and assert civilian control: urge the President to refuse "
            "removal and rein General DeWitt in, whatever the cost to Army relations"
        ),
        "next": "6.removal_averted",
        "effects": {
            "CivilLiberties": 3,
            "ConstitutionalLegitimacy": 3,
            "MilitarySupport": -3,
            "PresidentialPower": -1,
        },
    },
    {
        "text": (
            "Hold to your principle but decline to force a rupture with the Army—"
            "let DeWitt act on his own military authority in the coastal zone"
        ),
        "next": UNILATERAL_ID,
        "effects": {
            "CivilLiberties": -3,
            "ConstitutionalLegitimacy": -3,
            "PresidentialPower": -2,
            "MilitarySupport": 1,
        },
    },
    {
        "text": (
            "Concede: the military and political cost of refusal is too high—"
            "support proceeding with an official removal after all"
        ),
        "next": "3",
        "effects": {
            "CivilLiberties": -3,
            "MilitarySupport": 2,
            "PresidentialPower": 1,
            "ConstitutionalLegitimacy": -2,
        },
    },
]

UNILATERAL_SCENE = {
    "title": "Rule of the General",
    "description": "Removal by military fiat—lawless, and beyond any court.",
    "image": f"{MEDIA_BASE}/scene_6_unilateral.png",  # NEW asset
    "narration": (
        "The President will not sign an order—but he will not force a breach with "
        "his commander in the field either. General DeWitt, unwilling to wait, "
        "imposes exclusion on his own military authority. Removal proceeds: not by "
        "statute, not by executive order, but by the command of a general "
        "answering, in practice, to no one.\n\n"
        "There is no clean law to challenge and no tidy test case; when suits come, "
        "the courts call the matter a political thicket and look away. The "
        "precedent is quieter than Korematsu, and in one way graver—that in a "
        "crisis a field commander can override civilian judgment and "
        "constitutional limits, and Washington will avert its eyes. You kept the "
        "President's hands clean and your own principles intact, and a hundred "
        "thousand people were removed anyway, with no one willing to own it. "
        "History records a wound that never had a name, because it never had a day "
        "in court."
    ),
    "type": "end",
    "outcome": "military_supremacy",
    "outcome_message": (
        "You averted a lawful internment only to permit an unlawful one—removal "
        "by military fiat, beyond the reach of courts or the President."
    ),
}

# ---- #4: Scene-5 reveal reworded as vindication (text only) -------------------
SCENE5_NARRATION = (
    "Fred Korematsu has been arrested and is challenging his conviction. His case "
    "is climbing toward the Supreme Court. The Solicitor General will argue the "
    "government's position, and your office must shape it.\n\n"
    "The government's own reports now confirm on paper what voices in this room—"
    "Attorney General Biddle foremost among them—warned from the outset: there is "
    "no evidence of Japanese American disloyalty, and the military-necessity claim "
    "DeWitt advanced rests on nothing. Some staff urge burying these findings to "
    "protect the case; others insist the Court must see them.\n\n"
    "President Roosevelt: 'The Court will decide whether what we did was lawful. "
    "How should we present our case—and how honest should we be about what we "
    "know?'"
)


def build() -> dict:
    obj = json.loads(SRC.read_text(encoding="utf-8"))
    scenes = obj["scenario_json"]["scenes"]

    # #3: expand the pressure decision and add the unilateral-military ending.
    scenes["2d.pressure"]["choices"] = PRESSURE_CHOICES
    scenes[UNILATERAL_ID] = UNILATERAL_SCENE

    # #4: reword the Scene 5 reveal (narration only).
    scenes["5"]["narration"] = SCENE5_NARRATION

    return obj


def main() -> int:
    obj = build()
    DST.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
