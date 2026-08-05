"""Build v1 (state-gated endings) from the archived v0 original.

Change set (#1 only):
  * Scene "5" choices keep their effects but now route to a new conditional
    resolver "5.verdict" instead of hardwiring an outcome.
  * "5.verdict" reads accumulated ConstitutionalLegitimacy + CivilLiberties and
    routes to one of the THREE EXISTING end scenes (images reused verbatim),
    now reframed as legacy TIERS rather than as the specific final action.
  * The three endings' narration is rewritten to be action-agnostic legacy
    verdicts so no path lands on a contradictory ending. Outcome codes,
    image URLs, and outcome_message valence are preserved.

Expression grammar has NO arithmetic, so tiers use per-variable thresholds.

Tunable thresholds below. Run analyze.py on the output to measure.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "fdr-korematsu" / "v0_original-import.json"
DST = HERE / "fdr-korematsu" / "v1_state_gated-import.json"

# --- Tunable tier thresholds (per-variable; no arithmetic in the grammar) ----
# restraint (best): strong on BOTH legitimacy and rights
R_CONLEG, R_CIVLIB = 4, 2
# failure (worst): weak on EITHER legitimacy or rights
F_CONLEG, F_CIVLIB = 0, -1
# else -> qualified (middle, the default)

RESOLVER_ID = "5.verdict"

RESOLVER_NARRATION = (
    "The Supreme Court will rule on whether what the administration did was "
    "lawful. But a second verdict—slower, and either harsher or kinder—"
    "is passed by history: by the scholars, jurists, and citizens who weigh not "
    "one decision but the whole arc of the counsel you gave. That verdict is now "
    "being written."
)

# Action-agnostic legacy-tier rewrites. Keys are existing end-scene ids.
ENDING_REWRITES = {
    "6.retreat": {
        "title": "Conscience Over Crisis",
        "description": "The cumulative arc of your counsel protected the Constitution.",
        "narration": (
            "Across the decisions that mattered—scope, mechanism, and the "
            "final reckoning before the Court—your counsel bent consistently "
            "toward restraint. The military-necessity claim was tested rather than "
            "trusted, and the principle that ancestry alone cannot justify "
            "detention was defended rather than surrendered.\n\n"
            "The political price was real: the administration was accused of "
            "vacillating in wartime, and the road you chose was never the easy "
            "one. Yet the nation was spared its deepest self-inflicted wound. When "
            "later generations look back, they find not a precedent for the worst "
            "but a model of the restraint that leadership in a system of shared "
            "powers sometimes demands. Attorney General Biddle's fear proved "
            "unfounded: you were not remembered as the men who taught the courts "
            "that the Constitution sleeps in war."
        ),
        "outcome_message": (
            "You bore heavy political costs to protect constitutional rights, "
            "avoiding one of history's gravest precedents."
        ),
    },
    "6.candid": {
        "title": "A Mixed Legacy",
        "description": "Neither the deepest failure nor a clean triumph.",
        "narration": (
            "The final record is mixed. On the decisions that mattered you neither "
            "fully surrendered the Constitution nor fully defended it—but "
            "enough legitimacy was preserved that the reckoning, when it came, had "
            "something honest to build on.\n\n"
            "The Court still defers heavily to the military in wartime, and the "
            "convictions may stand—but the dissents grow sharper and better "
            "grounded, and the full weight of the doubts is not lost to history. "
            "When later generations reexamine the case, that preserved integrity "
            "accelerates the reckoning; reform, apology, and acknowledgment of "
            "error come, and the precedent's authority erodes faster than it "
            "otherwise would. It was an imperfect navigation of an impossible "
            "moment—not a clean triumph, but not the deepest failure either."
        ),
        "outcome_message": (
            "Partial integrity limited the long-term damage and strengthened the "
            "constitutional reckoning that followed."
        ),
    },
    "6.entrenched": {
        "title": "A Precedent for the Worst",
        "description": "The whole arc of counsel had already set the outcome.",
        "narration": (
            "Whatever was argued in the final hour, the whole arc of your counsel "
            "had already set the outcome. Removal reached broadly, the machinery "
            "of exclusion moved on suspicion of ancestry alone, and by the time "
            "the case reached the Court the record you had built could not support "
            "the weight of the rights it displaced.\n\n"
            "In a 6–3 decision the convictions are upheld and the "
            "administration prevails—but the victory is hollow and corrosive. "
            "Korematsu becomes a precedent that, decades later, scholars and the "
            "Court itself will condemn. Forty-four years on, a President will issue "
            "a formal apology and compensation; the Justice Department will admit "
            "the government argued in error. Yet a justice will warn that such a "
            "thing 'could happen again.' By letting certainty and security "
            "override rights across the decisions that mattered, you secured a "
            "courtroom win at the cost of the nation's constitutional conscience."
        ),
        "outcome_message": (
            "The policy was upheld but became a notorious symbol of rights "
            "sacrificed to wartime fear, repudiated by history."
        ),
    },
}


def build() -> dict:
    obj = json.loads(SRC.read_text(encoding="utf-8"))
    sj = obj["scenario_json"]
    scenes = sj["scenes"]

    # 1) Reroute scene 5 choices -> resolver (effects preserved).
    for choice in scenes["5"]["choices"]:
        choice["next"] = RESOLVER_ID

    # 2) Insert the conditional resolver, reusing scene 5's image (no new asset).
    scenes[RESOLVER_ID] = {
        "title": "The Second Verdict",
        "description": "History weighs the whole arc of your counsel, not one choice.",
        "image": scenes["5"]["image"],
        "narration": RESOLVER_NARRATION,
        "type": "conditional",
        "conditions": [
            {
                "condition": f"ConstitutionalLegitimacy >= {R_CONLEG} && CivilLiberties >= {R_CIVLIB}",
                "next": "6.retreat",
            },
            {
                "condition": f"ConstitutionalLegitimacy <= {F_CONLEG} || CivilLiberties <= {F_CIVLIB}",
                "next": "6.entrenched",
            },
        ],
        "default": "6.candid",
    }

    # 3) Reframe the three endings as legacy tiers (image + outcome code kept).
    for sid, patch in ENDING_REWRITES.items():
        scenes[sid].update(patch)

    return obj


def main() -> int:
    obj = build()
    DST.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
