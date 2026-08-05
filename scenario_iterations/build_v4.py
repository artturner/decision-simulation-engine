"""Build v4 (fix the principled_restraint ending overclaim) on top of v3.

The LLM contradiction judge (claude-sonnet-4-6) flagged 3 paths — all on the
`6.retreat` / principled_restraint ending — where my v1 legacy-tier rewrite
overclaimed. Two collisions caused it:

  1. The rewrite said the learner's counsel "bent consistently toward restraint"
     and that "the nation was spared its deepest self-inflicted wound." But this
     ending is reached by paths where mass removal DID happen (the rail), and on
     2d->concede paths the learner explicitly REVERSED and supported removal.
  2. v2 added `6.removal_averted` — now the true "internment avoided" ending — so
     "spared the wound" language in `6.retreat` collides with a different outcome.

Fix (TEXT ONLY, 0 new images, reuses scene_6_retreat.png): re-scope the ending
from "prevented the internment" to "couldn't prevent it — sometimes came to
support it — but kept it lawful, honest, and narrow, and blunted the precedent."
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "fdr-korematsu" / "v3_unilateral_and_dedup-import.json"
DST = HERE / "fdr-korematsu" / "v4_ending_fix-import.json"

RETREAT_NARRATION = (
    "You could not always prevent the removal—on some paths you argued against "
    "it from the first, on others you came to support it under the weight of the "
    "pressure. But once it was in motion, the decisions that followed bent toward "
    "principle: the military-necessity claim was tested rather than trusted, the "
    "exculpatory record was not buried to win the case, and the idea that ancestry "
    "alone can justify detention was contested at every step.\n\n"
    "The human cost was real, and it was not undone. Yet the program was kept "
    "narrower and more honest than it might have been, the courts were not taught "
    "that the Constitution sleeps in war, and the episode did not harden into the "
    "unqualified precedent for the worst that it could have become. When later "
    "generations look back, they find—inside a grave injustice—a thread of "
    "restraint and candor that mattered, and a model of how leadership in a system "
    "of shared powers pulls back toward the Constitution when it counts most."
)

RETREAT_OUTCOME_MSG = (
    "You bore heavy political costs to defend constitutional rights—unable to "
    "stop the removal, but keeping a grave injustice from hardening into an "
    "unqualified precedent."
)


def build() -> dict:
    obj = json.loads(SRC.read_text(encoding="utf-8"))
    scenes = obj["scenario_json"]["scenes"]
    scenes["6.retreat"]["narration"] = RETREAT_NARRATION
    scenes["6.retreat"]["outcome_message"] = RETREAT_OUTCOME_MSG
    return obj


def main() -> int:
    obj = build()
    DST.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
