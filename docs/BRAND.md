# FORGE — brand, name and design system

**FORGE. Where engineers are made.**

This document records why the product is called Forge, what the mark and the
"Obsidian Forge" glass theme mean, and the rules that keep every surface —
website, GitHub Pages copy, Android app — recognisably the same product.

## Why "Forge"

A forge is where raw metal becomes a tool that holds an edge. That is not a
metaphor pasted onto a study app; it is the study method the app already
enforced, given its proper name:

| In the forge | In Forge | Where it lives |
|---|---|---|
| **Heat** — make the metal workable | **Learn** the concept properly | Notes, topics, 3D models, formulas |
| **Strike** — shape it with repeated blows | **Practise** under pressure | DPP, question bank, judged coding, CodeLab |
| **Temper** — reheat so it holds its edge | **Review** until it sticks | Flashcards (spaced repetition), mistake notebook |
| **Inspect** — check the finished piece | **Prove it** | Progress, streaks, leaderboard, portfolio, certificates |

The name was chosen against five tests — aura/power, how it sounds said aloud
by a student in any Indian classroom, engineering relevance, ownability, and
logo potential:

| Name | Verdict |
|---|---|
| **Forge** ✅ | A verb *and* a place. Five letters, impossible to mispronounce, and it explains the product in one word: raw effort in, real engineer out. "Forge ahead", "forged in fire", "where engineers are made" — the language writes itself. |
| Prism | Beautiful glass/optics story (one light in, the whole spectrum of branches out) and runner-up. Less raw power, and it reads as an optics tool, not a workshop. |
| Vector | Magnitude + direction is a great study line, but it is cold and maths-only — it excludes the mechanical/civil/electrical benches. |
| Axiom | Intellectual aura, but abstract; it sounds like a theorem, not effort. |
| Titan / Apex | Powerful, but Titan is a household watch brand in India and Apex is a game. Borrowed aura is not aura. |
| Kinetic / Torque | Real engineering energy, but hard to spell from hearing and narrow (mechanics only). |
| Ignis / Vulcan | Latin fire and the god of the forge — maximum aura, minimum instant meaning. A name you must explain has already lost. |

## The mark

An **anvil struck by a spark** on an obsidian-glass tile
(`backend/static/icons/favicon.svg` is the source of truth; run
`scripts/gen_brand_icons.py` to regenerate every PNG, mipmap and the store
listing art).

- The anvil is where the work happens — the student's bench.
- The four-point spark is the moment of the strike: daily effort, visible.
- The wordmark is Sora ExtraBold, uppercase, with an ember full-stop:
  **FORGE.** — the full-stop is the confidence. It ends the sentence.
- The glyph is drawn on a 64-unit grid from straight machined lines; it stays
  legible at 16 px and works in one colour.

## Colour — "Obsidian Forge"

One confident accent family: heat. Everything else is warm charcoal or warm
paper so the ember does the talking.

| Token | Value | Job |
|---|---|---|
| `--accent` | `#f97316` ember | Primary actions, focus, heat |
| `--accent-2` | `#fbbf24` spark gold | Highlights, the spark in the mark |
| `--accent-3` | `#f43f5e` heat rose | Far end of gradients, hot states |
| Dark bg / surface | `#0b0908` / `#171310` | The forge at night |
| Light bg / surface | `#faf6f0` / `#fffdf9` | The workshop in daylight |
| Light link ink | `#b44a0c` burnt ember | Ember is luminance-heavy; this fixed ink holds ≥ 4.9:1 on paper where a tint of `#f97316` fails |

Rules that are not negotiable:

1. **Glass has a job.** Frosted glass = tempered glass over the fire. It marks
   *floating chrome* (top bar, menus, bottom nav) and *today's workspace*
   (hero, plan, bench panel). Reading surfaces stay quiet tints. If a surface
   is glass for no reason, it is decoration — remove it.
2. **Blur is spent, not sprinkled.** `backdrop-filter` only on chrome and big
   chambers. Repeating cards use the translucent tint without blur (they sit
   on the glowing graph-paper canvas, so they still read as glass) — a
   ₹8,000 phone must scroll at 60 fps.
3. **Contrast never depends on the effect.** Every glass surface has a solid
   fallback with identical contrast (`@supports not (backdrop-filter)`),
   plus `prefers-reduced-transparency`, `forced-colors` and print guards.
4. **Machined, not pillowy.** Radii are 9/13/19 px. Corners get a bright
   `--glass-edge` and a top highlight `--glass-hi`, like a cut plate.
5. **The canvas is graph paper.** The faint 44 px grid + ember glows are the
   engineer's notebook under the glass. That is what the blur blurs.

The accent stops remain white-label configurable (`site_config`), exactly as
before; the values above are the Forge defaults in `seed_data`/`brand.py`.

## Voice

Short. Certain. No motivational wallpaper.

- Tagline: **Where engineers are made.**
- Homepage: "Engineers aren't born. They're forged — one honest hour at a time."
- Say what the thing *does*: "Start today's practice", not "Begin your journey".
- Numbers on the page come from the catalogue. No invented user counts,
  ratings or testimonials — ever. Confidence that needs fake proof is not
  confidence.

## The full website, as one forge

The rebrand renames no URLs (bookmarks and the Pages export keep working);
it gives the existing rooms one story a judge can repeat after 30 seconds:

- **The Library** (Learn) — raw material, refined: 45 branches, 93 subjects,
  406 topics at four depths, 3D models, formulas, books and videos.
- **The Hammer Room** (Practice) — daily sets (DPP), question banks, judged
  coding sheets and the mistake notebook.
- **The Bench** (CodeLab + programming paths) — 14 language toolchains that
  run in the browser on the public copy.
- **The Tempering Shelf** (Revise) — flashcards on a spaced-repetition clock.
- **The Inspection Record** (Progress) — streak, XP, leaderboard, portfolio
  and completion certificates (records, not qualifications — we say so).
- **The Order Book** (Planner + Opportunities) — study plans, exam countdowns,
  internships, scholarships and hackathons from official sources.
- **The Forge in your pocket** — the Android app: offline catalogue and
  planner, opening the website for full notes and code.

Room names are copy flavour in headings; navigation labels stay plain
(Notes, Practice, Progress…) because clarity beats cleverness in a menu.

## What deliberately did NOT change

A rebrand changes what learners see, not the load-bearing identifiers other
systems depend on. These keep the original codename on purpose — the same way
large products keep internal names long after a public rename:

- The Python package `engineverse`, `ENGINEVERSE_*` environment variables and
  database names (renaming them breaks every existing deployment).
- The Pages progress format `engineverse-local-progress`, `ev-*` storage keys
  and the `ForgeVaultDB` database (renaming them deletes learner
  progress on the public copy). Exports from before the rebrand still import.
- The `EngineVerseAndroid/` user-agent token and legacy `EngineVerse.apk`
  release-name acceptance (the app now ships `Forge.apk`; old links still
  validate).
- The Android application id / package (changing it orphans installed apps).
- All URLs and the `/Engine_Verse/` Pages base path (derived from the
  repository name by `project.py` — see below).

## Renaming the GitHub repository (optional, when ready)

The product no longer needs the old name anywhere user-facing. To rename the
repository itself — e.g. `Engine_Verse` → `Forge`:

1. GitHub → repository **Settings → General → Repository name** → `Forge`.
   GitHub redirects the old git and web URLs.
2. Nothing in the code hardcodes the old name: Pages URL, base path and
   release links are derived from the repository by
   `backend/engineverse/project.py`, so the next Pages build publishes to
   `https://<owner>.github.io/Forge/` automatically.
3. Update the two links in `README.md` (badges use workflow file names, so
   they follow automatically) and any bookmarks/short-links you have shared.
4. Existing clones: `git remote set-url origin <new-url>`.
