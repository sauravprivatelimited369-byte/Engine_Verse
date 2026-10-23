# EngineVerse — brand, name and design system

**EngineVerse. Don't just learn engineering. Experiment with it.**

This document records what the product is called, what the "WORKSHOP" design
system is, and the rules that keep every surface — website, GitHub Pages copy,
Android app — recognisably the same product.

> The product was previously named FORGE and shipped a dark glass theme called
> "Obsidian Forge". Both are gone. The naming rationale below is the current
> one; the old forge metaphor is preserved only in this note so that older
> commits, screenshots and issue threads still make sense.

## Why "EngineVerse"

It names the audience and the scope in one word: engineering, and the whole of
it. It is also the name the repository, the Android package and the deployed
Pages URL already use, so the product, the code and the URL finally agree —
which matters more for a project a student has to find again than any amount of
naming ceremony.

The tagline is a claim about the workflow rather than a slogan:

> **Don't just learn engineering. Experiment with it.**

That sentence is the product's differentiator compressed: notes alone are a
commodity, and EngineVerse does not try to out-volume the platforms that
already do notes well. What it adds is the step between reading and practising
— a lab you can drive, a prediction you commit to before the answer is shown,
and feedback that names the mistake.

## The mark

An anvil and the spark of a strike, flat on a solid navy tile
(`backend/static/icons/favicon.svg` is the source of truth; the PWA icons under
`backend/static/icons/` are rasterised from it).

- Drawn on a 64-unit grid from straight lines, so it stays legible at 16 px.
- Two colours: the navy tile `#16202c`, the off-white anvil `#faf8f4`, and one
  blue spark `#5b93f5`. No gradient and no glow — the same restraint the
  stylesheet applies to every surface. The previous version of this mark used a
  diagonal obsidian gradient and an ember-gold spark; both were decoration.
- The wordmark is Sora ExtraBold, uppercase: **EngineVerse**.
- The Android launcher mipmaps and store listing art are still generated from
  the old mark; regenerating them is part of the next Android build.

## Colour — "WORKSHOP"

One confident accent, and nothing else is coloured. A study workspace should
read like a workbook, not a product landing page.

| Token | Value | Job |
|---|---|---|
| `--bg` | `#faf8f4` warm off-white | The canvas |
| `--text` | `#16202c` deep navy | Body copy — 15.5:1 on the canvas |
| `--text-2` | `#3d4a5c` | Secondary copy — 8.5:1 |
| `--muted` | `#667183` | Metadata — 4.65:1 |
| `--accent` | `#1f5fd6` | Primary actions, focus rings, the one thing that matters |
| `--accent-ink` | `#1a4fb0` | Links on light surfaces — 7.1:1 on the canvas |
| `--field-edge` | `rgba(22,32,44,.52)` | The outline of anything operable — 3.4:1 |
| Night canvas / surface | `#101720` / `#17202b` | Dark mode: the same layout, flat navy |

Rules that are not negotiable:

1. **No glass, no glow, no gradient.** `backdrop-filter` is disabled
   site-wide by one rule in `app.css`. Gradient headline text, decorative
   blobs, animated backgrounds and neon shadows are all gone. They were the
   single strongest reason the site read as a generated template.
2. **A border, not a shadow, separates two surfaces.** Shadows are one short
   contact shadow at most. Nothing lifts off the page.
3. **Radii are small and deliberately uneven** (4 / 6 / 10 px). One pillowy
   radius applied to every component is what makes a grid of cards look
   interchangeable.
4. **Spacing comes from an 8 px scale**: 4, 8, 12, 16, 24, 32, 48, 64.
5. **Contrast never depends on an effect.** Every text pair above is checked
   against WCAG AA; interactive boundaries against 1.4.11's 3:1. Dark mode is
   a first-class palette, not an inverted guess, and `forced-colors` and print
   guards are kept.
6. **Code stays dark in both themes.** A code block is a different material
   from the page; a navy slab (`#16202c`) is readable on paper.

The accent stops remain white-label configurable (`site_config`); the values
above are the defaults in `seed_data/library_data.py`. Note that
`accent_color_3` is set equal to `accent_color` on purpose: `base.html` derives
`--grad` from accent → accent-3, so keeping them equal makes every leftover
gradient in older templates resolve to a flat colour.

## Voice

Short. Certain. No motivational wallpaper.

- Say what the thing *does*: "Start practising", not "Begin your journey".
- Numbers on the page come from the catalogue. No invented user counts,
  ratings, testimonials or partner logos — ever.
- **Every feature carries a status chip.** `Working now`, `Demo data` or
  `Coming next`. A leaderboard backed by hard-coded rows says `Demo data`; a
  feature that does not exist yet says `Coming next` rather than rendering a
  button that goes nowhere. Confidence that needs fake proof is not confidence.
- Progress kept in the browser is described as **saved on this device**, never
  as saved progress or cross-device sync.

## The site, as one workflow

EngineVerse is a study workspace, not a library. The organising idea is the
loop the Adaptive Lab makes explicit, and every other area is one step of it:

| Step | Area | Where it lives |
|---|---|---|
| **Learn** | Notes, topics, formulas, books, videos | `/explore`, `/formulas` |
| **Experiment** | Interactive labs — predict before the answer is shown | `/lab` |
| **Practise** | Daily sets, question bank, judged coding | `/practice`, `/dpp`, `/sheets` |
| **Review** | Spaced repetition and the mistake notebook | `/revision`, `/mistakes` |
| **Prove it** | Progress, streaks, portfolio | `/dashboard`, `/streaks` |
| **Plan** | Study plans, exam countdowns, opportunities | `/planner`, `/opportunities` |

Navigation labels stay plain (Learn, Practice, Lab, Code, Revise) because
clarity beats cleverness in a menu.

## Honesty rules for anything new

These are the rules the homepage, the Adaptive Lab and the docs already follow.
A new feature that breaks them should not ship.

- No fabricated user counts, ratings, testimonials, partner logos,
  certifications or success claims.
- No dead buttons, no fake search boxes, no fake sign-in flows, no links to
  pages that do not exist. Mark it `Coming next` or remove it.
- A page may only claim it was tested or that data is real when it was.
- Nothing new may require a backend, a database, an auth provider or an AI API
  to work on the static Pages copy.

## What deliberately did NOT change

A rename changes what learners see, not the load-bearing identifiers other
systems depend on:

- The Python package `engineverse`, `ENGINEVERSE_*` environment variables and
  database names (renaming them breaks every existing deployment).
- The Pages progress format `engineverse-local-progress`, `ev-*` storage keys
  and the IndexedDB name (renaming them deletes learner progress on the public
  copy). Exports from before the rename still import.
- All URLs and the `/Engine_Verse/` Pages base path (derived from the
  repository name by `project.py`).
- The Android application id and package name, and the `Forge` app label in
  `android/`. The Android build is a separate workflow and was not part of the
  rename; it is the one place the old name still shows.
