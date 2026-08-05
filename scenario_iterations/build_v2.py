"""Build v2 (scope counterfactual branch) on top of v1 (state-gated endings).

Change #2 — counterfactual scope branch:
  * 2d ("reject removal entirely") no longer silently rejoins the removal rail.
    It routes to a new CHOICE "2d.pressure" ("Holding the Line"):
      - HOLD FIRM  -> new END "6.removal_averted" ("The Road Not Taken"): no mass
        removal, no Korematsu case, historically vindicated. (NEW image)
      - CONCEDE    -> Scene 3 (removal proceeds) as a now-MOTIVATED override.
  * 2b, 2c keep routing to removal (per chosen design) but their narration is
    edited (TEXT ONLY, no new image) to acknowledge the program expanded past the
    line the advisor drew — removing the silent contradiction with the citizen-
    inclusive Korematsu climax.
  * 2a unchanged.

New images required: 2  (scene "2d.pressure", scene "6.removal_averted").
Everything else (v1 resolver + reframed tier endings) is inherited unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "fdr-korematsu" / "v1_state_gated-import.json"
DST = HERE / "fdr-korematsu" / "v2_scope_branch-import.json"

# Media folder convention matches the rest of the scenario (fdr_korematsu/1/…).
MEDIA_BASE = "https://media.cruxlabs.academy/fdr_korematsu/1"

PRESSURE_ID = "2d.pressure"
AVERTED_ID = "6.removal_averted"

# ---- New scene: the pressure decision after advising outright rejection -------
PRESSURE_SCENE = {
    "title": "Holding the Line",
    "description": "Your counsel to refuse removal collides with the pressure to act.",
    "image": f"{MEDIA_BASE}/scene_2d_pressure.png",  # NEW asset
    "narration": (
        "Your advice to refuse removal hangs in the air, and the President does "
        "not answer at once. General DeWitt's liaison makes the threat plain: if "
        "no order comes from Washington, the Western Defense Command may impose "
        "exclusion on its own military authority. Secretary Stimson warns that the "
        "press and Congress will brand the President reckless for leaving the coast "
        "'defenseless.' Attorney General Biddle holds with you—there is no factual "
        "basis for the fifth-column claims—but he cannot promise the politics will "
        "survive it.\n\n"
        "President Roosevelt: 'You have told me what is lawful. Now tell me whether "
        "you will hold to it—knowing what it may cost.'"
    ),
    "type": "choice",
    "choices": [
        {
            "text": (
                "Hold firm: urge the President to refuse mass removal and meet any "
                "genuine threat through targeted, evidence-based security measures"
            ),
            "next": AVERTED_ID,
            "effects": {
                "CivilLiberties": 3,
                "ConstitutionalLegitimacy": 3,
                "MilitarySupport": -3,
                "PresidentialPower": -1,
            },
        },
        {
            "text": (
                "Concede: the military and political cost of refusal is too high—"
                "support proceeding with removal after all"
            ),
            "next": "3",
            "effects": {
                "CivilLiberties": -3,
                "MilitarySupport": 2,
                "PresidentialPower": 1,
                "ConstitutionalLegitimacy": -2,
            },
        },
    ],
}

# ---- New end: the counterfactual "road not taken" ----------------------------
AVERTED_SCENE = {
    "title": "The Road Not Taken",
    "description": "Restraint holds, and the internment—and its precedent—never come.",
    "image": f"{MEDIA_BASE}/scene_6_removal_averted.png",  # NEW asset
    "narration": (
        "The President holds. No mass exclusion order is signed. DeWitt is reined "
        "in and told the coast will be defended through surveillance and "
        "individualized arrests where evidence warrants—and no invasion ever "
        "comes.\n\n"
        "The political storm is real: the President is accused of gambling with "
        "national security, and for a season the decision looks like recklessness. "
        "But no hundred thousand people are uprooted, no citizen is imprisoned for "
        "ancestry, and there is no Korematsu case to climb toward the Supreme "
        "Court. Decades later, when other nations' wartime detentions are "
        "condemned and America weighs what it nearly did, historians point to this "
        "moment as the restraint that might have been—and, here, was. The "
        "Constitution was not made to sleep in war, and you did not let it."
    ),
    "type": "end",
    "outcome": "removal_averted",
    "outcome_message": (
        "By refusing mass removal outright, you averted the internment and the "
        "precedent it created—at real political risk, and with history's "
        "vindication."
    ),
}

# ---- Text-only reconciliation appended to 2b and 2c narration ----------------
APPEND_2B = (
    "\n\nIn the weeks that follow, the military reads the exclusion broadly. The "
    "line you drew between citizen and alien does not hold against DeWitt's "
    "insistence, and the program that takes shape sweeps in American-born citizens "
    "as well—over your objection."
)
APPEND_2C = (
    "\n\nThe President's tone leaves little doubt: the individualized, evidence-"
    "based course you urged will not survive the pressure for mass action. What "
    "proceeds is a sweeping removal by ancestry, the very thing you argued "
    "against—your caution noted, and set aside."
)


def build() -> dict:
    obj = json.loads(SRC.read_text(encoding="utf-8"))
    sj = obj["scenario_json"]
    scenes = sj["scenes"]

    # 1) Reroute 2d into the pressure decision instead of straight to Scene 3.
    scenes["2d"]["next"] = PRESSURE_ID

    # 2) Add the two new scenes.
    scenes[PRESSURE_ID] = PRESSURE_SCENE
    scenes[AVERTED_ID] = AVERTED_SCENE

    # 3) Reconcile 2b / 2c narration with the citizen-inclusive reality (no image).
    scenes["2b"]["narration"] = scenes["2b"]["narration"] + APPEND_2B
    scenes["2c"]["narration"] = scenes["2c"]["narration"] + APPEND_2C

    return obj


def main() -> int:
    obj = build()
    DST.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
