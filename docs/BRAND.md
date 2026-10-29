# MERIDIAN — brand, name and design system

**MERIDIAN. Engineering, studied properly.**

This document records why the product is called Meridian, what the mark and the
"Meridian Glass" theme mean, and the rules that keep every surface — website,
GitHub Pages copy, Android app — recognisably the same product.

## Why "Meridian"

A meridian is the line you draw to fix your position: the reference you measure
everything else against. It is also the highest point a thing reaches. Both
readings are the product, not a metaphor bolted onto it:

| In navigation | In Meridian | Where it lives |
|---|---|---|
| **Fix your position** | Know exactly where you stand | Progress, streaks, leaderboard, mistake notebook |
| **Read the line** | Learn the concept properly | Notes at four depths, formulas, diagrams, 3D models |
| **Hold the bearing** | Practise until it holds | DPP, question banks, judged coding, CodeLab |
| **Re-cross to confirm** | Review on a schedule | Flashcards (SM-2), revision, formula centre |

The name was chosen against five tests — aura and confidence, how it sounds said
aloud in a classroom, engineering relevance, ownability, and logo potential:

| Name | Verdict |
|---|---|
| **Meridian** ✅ | Confident without shouting. A real navigating and surveying word, so it belongs to every branch, not just computing. One mark: an M inside a ring. "The meridian line", "off the meridian" — the language writes itself. |
| Forge | The previous identity. Strong verb, but it reads as a blacksmith theme rather than a study product, and ember-on-black pulled the interface toward a game. |
| Prism | Beautiful optics story, but it reads as an optics tool and excludes the civil, mechanical and chemical benches. |
| Vector | Magnitude and direction is a good study line, but it is cold and maths-only. |
| Axiom | Intellectual aura, but abstract — it sounds like a theorem, not a working product. |
| Apex / Titan | Powerful, but borrowed: a game and a watch brand. Borrowed aura is not aura. |

### Name check (read this before printing anything)

"Meridian" is a real word used by real companies. A search in October 2026 found
**Meridian Knowledge Solutions** (a US enterprise LMS) and **Meridian Ed-Tech
Global** (STEM labs in Pakistan and the US), plus an unrelated
location-services company of the same name. None of them does what this project
does — a free, open-source study workspace for engineering students — and a
student project is unlikely to be confused with an enterprise LMS. Still, if this
is ever going commercial, get a proper trademark search first, or rename: the
product name lives in `site_config`, so a rename is a data change plus the
wordmark, mark and copy described below.

## The mark

An **M inside a meridian ring**, with the orbit's signal dot on the ring
(`backend/static/icons/favicon.svg` is the source of truth; run
`scripts/gen_brand_icons.py` to regenerate every PNG, mipmap and the store
listing art).

- The M is the study path: up, over, up.
- The ring is the line of reference — the thing you measure against.
- The blue dot is the signal on the line: the one topic you are working on now.
- The glyph is drawn on a 64-unit grid from straight lines and one arc; it stays
  legible at 16 px and works in one colour.
- The wordmark is set in the reading serif, uppercase, with a signal-blue
  full-stop: **MERIDIAN.** The full-stop is the confidence. It ends the sentence.

## Colour — "Meridian Glass"

Warm paper, deep navy ink, one signal blue. Nothing else competes with the
reading.

| Token | Value | Job |
|---|---|---|
| `--accent` | `#1d5bd6` signal blue | Primary actions, focus, the line |
| `--accent-3` | `#0c3c8f` deep blue | Pressed states, emphasis |
| `--text` | `#10243d` navy ink | Body and headings |
| `--bg` | `#f5f2ea` warm paper | The page |
| `--surface` | `#fbf9f4` paper white | Glass fallback |
| `--ok` / `--warn` / `--bad` | `#147a49` / `#9a5a07` / `#ae2338` | Status only, never decoration |
| dark canvas / surface | `#0a1522` / `#101f30` | The same glass at night |

The accent stops remain white-label configurable (`site_config`), exactly as
before; the values above are the Meridian defaults in `seed_data`/`brand.py`.

Rules that are not negotiable:

1. **Glass has a job.** Frosted glass marks *floating chrome* (the top bar, its
   menus, the mobile panel) and *working surfaces* (the daily plan, the
   workspace preview, forms, cards). Long-form reading sits on quiet paper. If a
   surface is glass for no reason, it is decoration — remove it.
2. **Blur is spent, not sprinkled.** `backdrop-filter` only on chrome and the
   larger panels. The canvas underneath is squared paper (a 36 px grid); that is
   what the blur blurs, which is what makes the glass read as glass rather than
   as grey.
3. **Contrast never depends on the effect.** Every glass surface has a solid
   fallback (`@supports`), plus `prefers-reduced-transparency`, `forced-colors`
   and print guards.
4. **Hairlines, not shadows.** One pixel borders; soft, neutral, shallow shadows.
   No coloured or glowing shadows.
5. **Small radii.** 8 / 11 / 16 px. Corners are cut, not pillowed; nothing is a
   26 px blob.
6. **No gradient type.** Headlines are one ink colour. Emphasis is italic serif
   in the signal blue, not a rainbow.

## Type

- **Headings: Newsreader** (variable, self-hosted, SIL OFL — see
  `backend/static/fonts/LICENSE-Newsreader.txt`). It is a reading serif: this is
  a place people read for an hour, and the page should look like it expects
  that. Italic is kept for emphasis inside headlines.
- **Interface and body: Inter** (variable, self-hosted, already in the build).
- **Numbers and code:** tabular figures in the interface face; the system mono
  stack for code, so no extra download.
- No CDN, no third-party origin: both families ship from `/static/fonts` and are
  covered by the strict `font-src 'self'` CSP.

## Layout language

- An editorial grid: one reading column, a rail for context and figures, hairline
  rules to separate rows.
- Sections change shape when their content does — a two-column library, a
  checklist plan, a three-step loop, a table of branches. No wall of identical
  cards.
- A spacing scale of 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- Every number on a page comes from the catalogue. No invented user counts,
  ratings or testimonials — ever.

## Voice

Short. Specific. No motivational wallpaper.

- Tagline: **Engineering, studied properly.**
- Homepage: "Learn with purpose. Practise with confidence."
- Say what the thing does: "Start today's practice", not "Begin your journey".
- Say what it is not: certificates are completion records, not qualifications;
  seeded topics are starter material and drafts are labelled as drafts.

## The full website

The rebrand renames no URLs (bookmarks and the Pages export keep working):

- **The library** (Learn) — 45 branches, 93 subjects, 406 topics with notes at
  four depths, 3D models, formulas, books and videos.
- **Practice** — daily sets (DPP), question banks, judged coding sheets and the
  mistake notebook.
- **CodeLab** (+ programming paths) — 14 language toolchains that run in the
  browser on the public copy.
- **Revision** — flashcards on a spaced-repetition clock.
- **Progress** — streak, XP, leaderboard, portfolio and completion certificates.
- **Planner and opportunities** — study plans, exam countdowns, internships,
  scholarships and hackathons from official sources.
- **The app** — the Android build: offline catalogue and planner, opening the
  website for full notes and code.

## What deliberately did NOT change

A rebrand changes what learners see, not the load-bearing identifiers other
systems depend on:

- The Python package `engineverse`, `ENGINEVERSE_*` environment variables and
  database names (renaming them breaks every existing deployment).
- The Pages progress format `engineverse-local-progress`, `ev-*` storage keys
  and the `MeridianVaultDB` database (renaming them deletes learner progress on
  the public copy). Exports from before the rebrand still import.
- The `EngineVerseAndroid/` user-agent token, and legacy `Forge.apk` /
  `EngineVerse.apk` release-name acceptance (the app now ships `Meridian.apk`;
  old links still validate).
- The Android application id / package (changing it orphans installed apps).
- All URLs and the `/Engine_Verse/` Pages base path (derived from the repository
  name by `project.py` — see below).
- The browser namespace `window.EngineVerse` (an API name, not a name a reader
  sees). It publishes `window.EngineVerse.siteName`, which is the product name
  the deployment is configured with, so the browser-side features that used to
  hard-code "EngineVerse" in a sentence — the voice reader, the voice tutor —
  say the right name on a white-label deployment instead.

## Renaming the GitHub repository (optional, when ready)

The product no longer needs the old name anywhere user-facing. To rename the
repository itself — e.g. `Engine_Verse` → `Meridian`:

1. GitHub → repository **Settings → General → Repository name** → `Meridian`.
   GitHub redirects the old git and web URLs.
2. Nothing in the code hardcodes the old name: Pages URL, base path and release
   links are derived from the repository by `backend/engineverse/project.py`, so
   the next Pages build publishes to `https://<owner>.github.io/Meridian/`
   automatically.
3. Update the two links in `README.md` (badges use workflow file names, so they
   follow automatically) and any bookmarks you have shared.
4. Existing clones: `git remote set-url origin <new-url>`.
