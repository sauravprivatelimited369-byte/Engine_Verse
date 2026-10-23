# Changelog

Notable changes to Meridian (formerly EngineVerse). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are not yet
tagged, so everything below is listed under **Unreleased** until the first
release.

## Unreleased

### Changed

- **The product is now MERIDIAN — "Engineering, studied properly."** This
  replaces the previous name and theme completely (see
  [docs/BRAND.md](docs/BRAND.md) for the naming rationale and the runner-up
  names). New name and tagline everywhere a learner looks; a new mark (an M
  inside a meridian ring with the orbit's signal dot: favicon, PWA icons,
  Android launcher/splash, store listing — regenerate with
  `scripts/gen_brand_icons.py`); and a rebuilt **"Meridian Glass"** identity
  across the website, the GitHub Pages copy and the Android app.
- **The homepage was rebuilt, not repainted.** It now leads with a reading
  serif headline, a warm-paper canvas and a real workspace preview (today's
  plan, with the actual topic and problem the catalogue picked), followed by a
  library list with figures, the interactive four-step plan, the
  Learn → Practise → Review loop, three feature rows showing real interface
  previews, and a branch index. Every number comes from the catalogue; the
  invented-proof patterns (floating glass chip collage, six-count stat strip,
  gradient headline, "why our name" manifesto) are gone.
- **New palette and type.** Warm paper (`#f5f2ea`), navy ink (`#10243d`) and one
  signal blue (`#1d5bd6`) replace ember-on-obsidian; headings are now
  **Newsreader**, a self-hosted reading serif (SIL OFL), with Inter retained for
  interface and body copy. Glass is now light, hairline-bordered and reserved
  for chrome and working surfaces, with solid, reduced-transparency,
  forced-colors and print fallbacks. The new visual layer lives in
  `backend/static/css/meridian.css` and re-skins every existing page through
  the components `app.css` already defines.
- **Course pages no longer paint headings in a language's brand colour.** The
  catalogue stores a colour per language; it was applied to the `<h1>` and the
  card titles, which failed contrast for several stored values and broke the
  one-accent rule. The colour is now a short rule above the title (a marker,
  not ink), so the text stays navy and every language still reads as distinct.
- **Page headers got a measure.** The intro paragraph on every `page-hero`
  (explore, practice, planner, programming, and the rest) is capped at 64
  characters and set as a lede instead of stretching the full card width.
- The Android release asset is now `Meridian.apk` (legacy `Meridian.apk` /
  `EngineVerse.apk` links still validate), the Compose entry points are
  `MeridianApp` / `MeridianTheme`, and the app palette matches the website.
- **Deliberately unchanged, so nothing breaks:** all URLs and the Pages base
  path, the `engineverse` package and `ENGINEVERSE_*` settings, the stored
  progress format and `ev-*` storage keys (old exports still import), and the
  Android application id.

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
