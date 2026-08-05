# How We Make Sure Every Scenario Is Worth Playing

*A plain-language guide to the scenario quality system — for teachers,
reviewers, and anyone curious about what happens before a scenario reaches a
student.*

---

## What our scenarios promise

Our learning scenarios put a student inside a real historical or civic
dilemma — advising President Roosevelt in wartime, brokering a compromise at
the Constitutional Convention, deciding how to vote on a controversial bill.
At every step the student makes a choice, and the story responds.

That format makes an implicit promise to the student:

1. **Your choices matter.** Picking differently should be able to lead
   somewhere genuinely different.
2. **The ending you get is earned.** It should reflect the whole arc of your
   decisions, not just the last button you happened to press.
3. **The story never contradicts you.** If you refused a policy in chapter
   one, the story shouldn't later act as if you approved it — unless it
   openly shows you being overruled.

When any of these breaks, the scenario stops being a decision simulation and
becomes an illustrated slideshow. A student clicks, but nothing they decide
actually changes anything — and students notice.

## The problem we found

Our scenarios are drafted by an AI author working from source documents. When
we systematically checked the existing library, the drafts turned out to be
inconsistent. Many were excellent. But roughly a third had hidden defects that
are invisible when you read the story casually:

- **Choices that silently didn't matter.** Every path funneled to the same
  ending no matter what the student picked.
- **Scorekeeping that was never used.** The scenario dutifully tracked things
  like "public trust" going up and down with each choice — and then never
  looked at the score. It was a gradebook nobody opened.
- **Only one ending you could actually reach.** Other endings existed on
  paper but no combination of choices led to them.
- **Endings that misdescribed the journey.** One ending congratulated the
  student for preventing an event that, on some routes to that ending,
  clearly happened.

These flaws were only findable by exhaustively tracing every route through
the story — something a human reviewer rarely has time to do. One scenario
has 243 distinct routes.

## The fix: prevent first, then inspect and repair

We added two layers of protection. Think of them as better training for the
author, plus an editorial department that checks every manuscript.

### Layer 1 — Better instructions to the author (prevention)

The AI author's standing instructions now *require* the qualities we care
about: the scorekeeping must actually decide something, early choices must
have visible consequences later, at least two genuinely different endings
must be reachable, and every ending's text must be true for every route that
can arrive at it. Fixing the instructions is the cheapest fix there is: most
scenarios now come out right the first time. In our tests, freshly generated
scenarios were born sound — one perfectly, one with a single small defect
that the next layer caught and repaired automatically.

### Layer 2 — Automated inspection and repair (the quality loop)

Every new scenario now goes through a quality check *before* any artwork is
commissioned. It works in three steps, ordered from cheapest to most
expensive:

**Step 1: Play every possible route.** A computer program plays the scenario
the way thousands of students eventually will — every choice, every
combination, every route from first scene to final ending. This is exact,
instant, and free. It answers factual questions: Do choices change outcomes?
Is the scorekeeping actually consulted? How many endings can really be
reached? A scenario that passes all checks moves on immediately.

**Step 2: A continuity editor reads every route.** Some flaws aren't
structural — the plumbing is fine, but the *story* cheats. For these we use a
second, independent AI acting as a continuity editor. It reads the exact
sequence of scenes a student would experience on each route and asks: does
any later scene contradict a choice the student made earlier? Because a
single reading can be erratic — the same editor can flag different things on
different days — we have it **read each route five times and only trust
complaints it raises consistently**. Consistent complaints are treated as
real defects; one-off complaints are treated as noise and ignored. This
"read five times, take the majority" rule came directly from testing: it's
the difference between a trustworthy editor and a jumpy one.

**Step 3: An automated reviser fixes what was found.** The findings — written
in concrete terms, like "these two choices can never change the ending" or
"this ending claims the student prevented the removal, but on two routes it
happened" — go to a reviser AI, which rewrites the scenario to fix them. The
revision is then **re-inspected from scratch**. This repeats, with strict
safety rails:

- **Every revision is re-verified.** Nothing is taken on faith; the revised
  version replays every route and faces the continuity editor again.
- **We always keep the best version.** If a revision makes things worse, it's
  discarded. The system can never turn a good scenario into a bad one.
- **There's a budget.** After a set number of attempts, the loop stops and
  reports honestly rather than spinning forever.
- **A full report is written every time** — what was checked, what was found,
  what was changed, and whether the final version passed. A human can always
  audit the trail.

## Why this happens *before* the artwork

Scene illustrations are the most expensive part of producing a scenario.
Fixing a story after its images exist means paying for images twice. The
quality loop runs first, and the repairs themselves are thrifty: when the
system restructures a story, it reuses the existing scene images wherever
possible. In our benchmark repairs, badly broken scenarios were fully fixed
with **zero new images required**.

By default the gate is *advisory* — a failing scenario still moves forward,
but with a clear warning and a report attached. For anyone who wants a hard
guarantee, a strict mode refuses to commission artwork until the scenario
passes.

## Does it work? The evidence

We tested the system against the two worst scenarios in our library and
against a case we had previously repaired carefully by hand.

- **The worst scenario in the library** (a legislative drama where *none* of
  the three choice points affected the ending, and only one ending was
  reachable): the loop rebuilt it automatically — all four choice points now
  matter, four distinct endings are reachable, the scorekeeping now decides
  the finale, and the continuity editor's consistent complaints went from
  several down to **zero**. No new artwork was needed.
- **A second broken scenario** (one choice, one reachable ending): repaired
  automatically in a single run.
- **The hand-repaired case**: the automatic fix reproduced the same repair
  our expert made manually — the same kind of structural change, arrived at
  independently. Its story-consistency complaints fell from thirteen to one
  minor note across successive rounds. Along the way the system also proved
  its most important safety rail in live use: when one revision made the
  story *worse*, the system detected the regression and threw that revision
  away rather than accepting it.
- **A freshly written scenario with one small defect** was carried through
  the entire journey automatically: the defect was caught, the structure
  repaired, the story polished — and it now passes every check, including a
  unanimous clean bill from the continuity editor.
- **The healthy scenarios**: just as important, the system left our good
  scenarios completely untouched — they passed inspection immediately, at no
  extra cost.

One pattern from testing is worth knowing: structural problems (choices that
don't matter, unreachable endings) are usually fixed in a **single**
revision. Story-consistency problems take longer, but they improve steadily
with each pass — in the hardest case, complaints fell from four, to three,
to two, to one, to zero across successive rounds.

## What this means for you

- **Students** get scenarios where exploring different choices is genuinely
  rewarded — replaying a scenario differently leads somewhere different, and
  the ending they receive reflects the record they built.
- **Teachers** can trust that the debrief holds up: when a student says "I
  never supported the removal," the story will agree with them.
- **Reviewers** get a written quality report with every scenario instead of
  having to trace hundreds of routes by hand.
- **The budget** is protected: expensive artwork is only produced for
  stories that have already proven sound.

In short: the author now knows the rules, an inspector replays every possible
playthrough, a five-vote continuity editor reads every storyline, a reviser
fixes what they find, and nothing gets expensive artwork — or reaches a
student — until the story keeps its promises.
