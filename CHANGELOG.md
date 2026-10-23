# Changelog

Notable changes to EngineVerse (formerly Forge). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are not yet
tagged, so everything below is listed under **Unreleased** until the first
release.

## Unreleased

### Added

- **The Adaptive Lab (`/lab`) — the flagship feature.** A DC circuit the
  learner drives themselves (voltage 1-24 V, resistance 1-100 Ω, live
  `I = V / R` and `P = V x I`, an SVG circuit whose labels read from the same
  solved state as the numbers), three predict-then-verify challenges that lock
  the prediction before the reveal, and a personalised challenge mode over a
  16-question bank tagged by difficulty (5 easy / 7 medium / 4 hard) and by
  concept (formula, units, series, parallel, power). Correct answers move the
  learner up a level; wrong answers drop a level *and* stay on the concept that
  was missed. A rule-based mistake detector (no model, no API) names the actual
  arithmetic slip — "you multiplied voltage by resistance", "you divided the
  wrong way round", "that is the right number in milliamps" — with a generic
  working-out fallback. Progress goes to `localStorage` and is labelled
  "saved on this device"; blocked storage degrades to a session with a warning
  instead of throwing. The curriculum links are resolved from the real
  catalogue at request time, so the page cannot link to a notes page that does
  not exist.
- **`scripts/check_lab.js` and `scripts/check_lab_page.js`**, wired into
  `pages.yml`: 222 assertions on the physics, the mistake rules, the sequencing
  and the storage, plus 108 that boot the exported pages with the shipped
  `lab.js` under jsdom and drive them.
- **Status chips on every feature** — `Working now`, `Demo data` or
  `Coming next` — so nothing on the site claims more than it is.

### Changed

- **The product is EngineVerse**, matching the repository, the Android package
  and the Pages URL, with the tagline "Don't just learn engineering.
  Experiment with it." Replaces the previous FORGE identity. URLs, storage
  keys, the `engineverse` package and the `ENGINEVERSE_*` settings are
  unchanged; the Android app still carries the old label and launcher mark
  because its build is a separate workflow.
- **The design system is "WORKSHOP", not glass.** Warm off-white canvas
  (`#faf8f4`), deep-navy ink (`#16202c`), one blue accent (`#1f5fd6`), hairline
  borders, one short contact shadow, and small deliberately uneven radii.
  `backdrop-filter` is disabled site-wide; gradient headline text, decorative
  glows, animated backgrounds and floating chips are gone. Dark mode is a
  designed flat-navy palette rather than an inverted guess. Every text pair is
  WCAG AA and every interactive boundary clears 1.4.11's 3:1.
- **The homepage hero is the product, not a collage.** "Learn. Experiment.
  Practise.", two CTAs that both go somewhere real, and a live Adaptive Lab
  simulator on the right instead of floating glass cards. Below it: a real
  catalogue table (subject, item, type, time, status chip), the
  Learn -> Experiment -> Practise -> Review loop, four features with status
  chips, and an honest "Why EngineVerse?" that says plainly this is a focused
  prototype rather than a competitor to large tutorial platforms.
- **The Adaptive Lab takes CodeLab's top-bar slot.** The bar has a fixed budget
  of seven entries; CodeLab moves into the Code menu and keeps the mobile bar,
  the PWA shortcut and the service-worker precache.
- The mark is flat — navy tile, off-white anvil, one blue spark — and the PWA
  icons are rasterised from it. The service-worker cache version bumped to
  `engineverse-v14` so returning visitors drop the old stylesheet.
- Light is the default theme. Readers on a dark OS still get the night palette
  from the pre-paint script.

### Changed

- **The product is now FORGE — "Where engineers are made."** A full identity
  rebuild (see [docs/BRAND.md](docs/BRAND.md) for the naming rationale and the
  runner-up names): new name and tagline everywhere a learner looks, a new
  anvil-and-spark mark (favicon, PWA icons, Android launcher/splash, store
  listing — regenerate with `scripts/gen_brand_icons.py`), and a new
  "Obsidian EngineVerse" tempered-glass design system across the website, the
  GitHub Pages copy and the Android app: smoked/frosted glass over warm
  charcoal (dark) or warm paper (light), one ember accent family
  (`#f97316` / `#fbbf24` / `#f43f5e`), machined corners, and a rebuilt
  homepage ("Where engineers are forged", the Heat → Strike → Temper cycle,
  and a short "Why EngineVerse?" manifesto). The Android release asset is now
  `EngineVerse.apk`. Deliberately unchanged, so nothing breaks: all URLs and the
  Pages base path, the `engineverse` package and `ENGINEVERSE_*` settings,
  stored-progress formats and storage keys (old exports still import), the
  Android application id, and acceptance of legacy `EngineVerse.apk` links.

### Fixed

- **CodeLab and the compiler page no longer look dead.** Four separate faults
  were behind "the compiler is not working at all, and CodeLab only runs one
  language":
  - `app.js` replaced the whole `window.EV` namespace, deleting `EV.i18n`
    (published by `i18n.js`, which loads first). Its init threw
    "Cannot set properties of undefined (setting 'picker')" on every page and
    the language picker was never built.
  - A rejected run (stale CSRF token, expired session, a proxy's HTML error
    page) carried no `status`, so the console showed "Idle" with three empty
    tabs and Run looked like a dead button. The client normalises any payload
    into a renderable result and, on a 403, fetches a fresh token from the new
    `GET /api/csrf` and retries once. The CSRF middleware's 403 body now
    carries `status`, `stderr` and `csrfTokenUrl` too.
  - `/compiler` took its language list only from the seeded catalogue, so an
    unseeded database gave an empty drop-down and a permanently disabled Run.
    It now falls back to CodeLab's static language registry.
  - Sandbox limits were sized as if nothing else ran on the host: a fixed
    `ulimit -u 32` (a JVM starts ~24 threads) and a javac JVM whose default
    1 GB compressed-class-space reservation did not fit under the
    address-space cap. Valid Java was reported as a compilation error. The
    task budget is measured in threads and shared by both limits, and javac
    runs with pinned `-J` flags.
- A program killed by a signal is reported as a crash, not as a timeout, and
  the Node/WASM host runners (C#, Ruby) are retried when the interpreter
  itself dies before producing output.
- Ruby is now a CodeLab language: the judge could run it, but `/api/execute`
  answered 400 "Unsupported language".
- Disabled languages now say which binary is missing and the exact
  `scripts/setup_toolchains.py` command, on `/codelab` and `/compiler`,
  instead of only "limited runtimes on this server".

### Added

- **Native Android app** (`android/`): Kotlin and Jetpack Compose with a native
  home screen, an offline subject catalogue (93 subjects and 406 topics, bundled
  from the seed data by `scripts/export_android_catalog.py`), a study planner,
  progress with streaks, settings, a splash screen and a hardened in-app viewer
  for full notes and the playground. It includes JVM unit tests.
- **Android app workflow**: unit tests, lint and a debug APK artifact on every
  Android change. A signed release APK is built only on manual dispatch, using
  repository secrets.
- **Study planner** (`/planner`): tasks, exam countdowns and a focus timer, kept
  in the browser, with JSON export and import.
- **Opportunities** (`/opportunities`): internships, scholarships, olympiads
  and hackathons, linked only to official pages. A weekly CI job checks them.
- **Help and feedback** (`/support`) and a `/api/me/export` download of your own
  data on the full website.
- `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and pull
  request templates, `.editorconfig` and this changelog.
- `robots.txt` and a sitemap for the GitHub Pages copy.

### Changed

- **GitHub Pages copy**: progress lives in one device-local profile with
  export and import. Pages that only work with a server (sign-in, codes,
  password reset) are no longer exported; personal pages are `noindex`.
- The Pages workflow targets this repository. Tests, jsdom checks of the
  exported site, and checks of every bundled browser runtime gate the deploy.
- Repository URLs come from one place (`backend/engineverse/project.py`)
  instead of being hard-coded to the old repository.
- CI uses Node 22 and syntax-checks every browser script.
- The website's export buttons explain that saving files does not work inside
  the Android app, instead of reporting a download that did not happen.

### Removed

- The browser-side "accounts" on the Pages copy: fast password hashes,
  on-page six-digit codes and a GitHub token in browser storage.
- The public learner registry (`data/learners/registry.json`), its sync script,
  its workflow and the `/api/sync/*` routes. Learner data no longer goes into
  the public repository.
- The generated Java WebView APK builder (`scripts/build_android_apk.py`) and
  its workflow, replaced by the native app.
- `scripts/check_auth_flow.js`, which tested the removed browser accounts.

### Security

- No credentials of any kind are stored by the static site or the app. Imported
  progress files are validated field by field.
- The Android viewer loads only this site's HTTPS pages, exposes no JavaScript
  bridge, blocks mixed content and file access, and enables Safe Browsing.
