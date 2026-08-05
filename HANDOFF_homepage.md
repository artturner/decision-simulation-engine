# Homepage Task Handoff

## Objective

Create a highly polished homepage for the Branching Scenarios application, informed by `SCENARIO_QUALITY_EXPLAINED.md`, with animated imagery based on randomly selected prompts from the repository's `*image-prompts*.json` files.

## Current status

The homepage implementation is complete in the working tree and the production build passes. It has not been committed or deployed.

The most recent local-preview attempt started successfully and returned HTTP 200 for the homepage, but the background development process did not remain alive after the tool session ended. At the time of this handoff, nothing is listening on port 3000. This is why `http://localhost:3000` currently refuses connections; it is not a page compilation failure.

To run the preview reliably, open a persistent PowerShell terminal and keep it open:

```powershell
cd C:\Users\arttu\decision-simulation-engine\apps\web
npm run dev
```

Wait for the `Ready` message, then open:

```text
http://localhost:3000
```

## What was implemented

### Homepage content and structure

`apps/web/app/page.tsx` was replaced with a full editorial landing page containing:

- A full-viewport cinematic hero headed “What will you choose?”
- Layered scenario artwork with animated camera drift and floating choice labels
- Navigation to scenario exploration, the quality explanation, class joining, and teacher sign-in
- A three-scenario showcase:
  - The Marshall Gambit
  - Strength in Numbers
  - The Quiet Transfer
- A plain-language explanation of the three-stage quality system:
  - Every route is played
  - Continuity is reviewed five times
  - Repairs are re-tested from scratch
- Benchmark proof drawn from `SCENARIO_QUALITY_EXPLAINED.md`, including four distinct endings, zero continuity defects, and zero replacement images in the repaired worst-case scenario
- A closing call to action and site footer

The homepage copy is derived from the promises, process, and evidence in `SCENARIO_QUALITY_EXPLAINED.md`; it is not generic landing-page filler.

### Visual design and animation

`apps/web/app/globals.css` now contains the complete visual system:

- Deep teal, parchment, coral, and gold editorial palette
- Georgia-based display typography with restrained system sans-serif supporting type
- Layered image frames and archival publication styling
- Slow Ken Burns-style image movement
- Floating choice chips
- Pulsing decision nodes and branching-line motifs
- Animated proof orbits and closing-image drift
- Responsive layouts for desktop, tablet, and mobile
- A `prefers-reduced-motion` mode that effectively disables animation

The animations are CSS-driven. The generated source images are still raster images; CSS supplies their motion on the page.

### Generated scene artwork

Three original 16:9 painterly editorial illustrations were generated with the built-in image generator. Their base concepts were selected randomly from repository prompt JSON files:

1. `the-marshall-gambit-image-prompts.json`, key `4b`
   - An 1803 basement courtroom beneath the Capitol
   - Saved as `apps/web/public/scenes/courtroom-1803.png`

2. `shaping-the-aca-image-prompts.json`, key `6a`
   - A present-day healthcare coalition press conference
   - Saved as `apps/web/public/scenes/healthcare-coalition.png`

3. `scenario_iterations/benchmark/regen-check-2-image-prompts.json`, key `2a`
   - A tense late-night Oval Office meeting
   - Saved as `apps/web/public/scenes/oval-office-night.png`

The prompts were normalized for a consistent painterly, cinematic editorial style and constrained to avoid text, captions, logos, interface elements, and watermarks.

### Social sharing image and metadata

A dedicated social card was generated and saved as:

- `apps/web/public/og.png`

It uses the homepage palette, courtroom imagery, branching-path motif, and the exact text:

- “WHAT WILL YOU CHOOSE?”
- “BRANCHING SCENARIOS”

`apps/web/app/layout.tsx` was updated to:

- Use the page title `Branching Scenarios — What Will You Choose?`
- Add a site-specific description
- Generate Open Graph and X/Twitter metadata
- Build the absolute `og.png` URL from the incoming request host

## Files changed by this task

Modified:

- `apps/web/app/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/app/layout.tsx`

Added:

- `apps/web/public/og.png`
- `apps/web/public/scenes/courtroom-1803.png`
- `apps/web/public/scenes/healthcare-coalition.png`
- `apps/web/public/scenes/oval-office-night.png`
- `HANDOFF_homepage.md`

Temporary preview logs may also exist and are not part of the product:

- `apps/web/.dev-server.log`
- `apps/web/.dev-server.err.log`

They can be deleted after troubleshooting or added to the local ignore file. Do not include them in a product commit.

## Verification completed

The production build was run from `apps/web`:

```powershell
npm run build
```

Result:

- Next.js 16.1.6 production compilation succeeded
- TypeScript checking succeeded
- Page-data collection succeeded
- All application routes were generated successfully
- The homepage is a dynamic server-rendered route because its metadata reads the incoming host

The development server also started successfully in the last attempt and served `GET /` with HTTP 200 before its background process was terminated.

No screenshot-based visual QA, browser interaction testing, commit, push, or deployment was performed.

## Working-tree cautions

The repository already contains numerous unrelated modified and untracked files. Those changes belong to the user and must not be reverted, overwritten, or included in a homepage-only commit.

When committing this task, stage only the homepage files listed above. In particular, do not stage unrelated scenario-generation, API, import, benchmark, or handoff files merely because they appear in `git status`.

## Recommended next steps

1. Start `npm run dev` in a persistent foreground terminal and keep that terminal open.
2. Review the homepage at desktop and mobile widths.
3. Confirm whether the three showcase cards should eventually link to real scenario slugs. They currently link to the quality section because the selected image-prompt sources do not establish three known published scenario routes.
4. Remove or ignore the temporary `.dev-server` log files.
5. If the visual review passes, run `npm run build` once more after any edits.
6. Stage and commit only the homepage files.
7. Deploy through the application's existing hosting workflow if desired. No deployment was attempted during this task.

## Known non-blocking considerations

- The generated images are high-quality PNG files of roughly 2.1–2.4 MB each. Next.js image optimization mitigates initial delivery, but WebP or AVIF source conversion could further reduce repository and deployment size.
- The homepage contains meaningful links for class joining and teacher sign-in. The showcase cards are intentionally informational until actual scenario slug mappings are selected.
- The local preview refusal is environmental/process-lifetime related. The successful production build and prior HTTP 200 response indicate the homepage source itself is operational.
