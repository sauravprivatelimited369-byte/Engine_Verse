# Changelog

Notable changes to Meridian (formerly EngineVerse). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are not yet
tagged, so everything below is listed under **Unreleased** until the first
release.

## Unreleased

### Added

- **Interactive 3D Observatory, Scroll Walkthrough and Live Study Workbench.**
  Upgraded `engine3d.js` with hemisphere ambient, Blinn-Phong specular and
  Fresnel rim lighting, indexed `gl.LINES` X-Ray wireframe mode, smooth
  `EngineVerse3D.setScene()` camera transitions, pointer micro-parallax,
  scroll-linked 3D rotation (`data-ev3d-scroll`) and declarative viewport
  toolbars (`data-ev3d-cmd`) across the homepage, signed-in dashboard and all
  406 topic pages. Added `models3d.meridian_instrument_scene()` for the
  Meridian Armillary hero scene, a sticky 3D scroll-storytelling walkthrough,
  a four-tab interactive workbench (four-depth note reader with browser speech,
  self-marking practice MCQs, 3D-flip spaced-repetition flashcards and
  multi-language judged code starters), a discipline-filterable 3D Atlas with
  in-stage model loading, instant 45-branch search, and `meridian-v16` offline
  service-worker caching.

- **The native apps are now real offline apps, and they are downloadable.**
  Every push publishes `Meridian.apk` to the
  [android-latest](https://github.com/sauravprivatelimited369-byte/Engine_Verse/releases/tag/android-latest)
  release and `Meridian-iOS.ipa` plus `Meridian-macOS.dmg` to
  [apple-latest](https://github.com/sauravprivatelimited369-byte/Engine_Verse/releases/tag/apple-latest),
  each with a SHA-256 sidecar, so a phone can install the app from a link
  without a GitHub login, an App Store account or a developer machine.
  `scripts/export_mobile_content.py` bundles the whole lesson library —
  406 topics at all four note depths, 350 formulas and the 534-question
  practice bank — into `content.json` for both apps (`android/app/src/main/assets/`,
  `apple/Resources/`). Markdown is parsed once, at export, into blocks and runs,
  so both apps render notes natively and need no web page to read them. Android
  gained a notes reader with a depth switcher, a practice tab with explanations
  and saved answers, and lost its "notes open in the browser" path; the Apple
  apps gained the same screens. The website is now used only for interactive
  diagrams, 3D models and the WebAssembly code playground.

### Fixed

- **Choosing a topic's MCQs in the question bank now works.** The bank's
  filter form offered Subject, Difficulty and Kind but no Topic at all: the
  handler honoured `?topic=` only when a link elsewhere supplied it, so "the
  MCQs for this part" could not be asked for on the page itself. Worse, on
  the GitHub Pages copy the whole form was decorative - the exported page is
  one static file, a static host ignores the query string, and nothing in
  the browser runtime filtered the list, so every selection submitted,
  reloaded and showed the same first screen. The form now has a real Topic
  selector (`practice.question_topics()`): every topic with at least one
  question, grouped under its subject, labelled with its MCQ count, plus the
  stem search the handler already supported. A chosen topic wins over a
  mismatched subject instead of AND-ing into an empty page, an unknown topic
  is named in the banner instead of leaving a hole in it, and every card
  shows (and links) its topic. With JavaScript the selects apply on change
  and choosing a subject narrows the topic list to that subject's topics
  (`app.js` hosted, `pages-live.js` static). On the static copy the bank now
  filters the exported `quiz-bank.json` in the browser - subject, topic,
  difficulty, kind, search and `?slug=` deep links, 24 at a time with Show
  more standing in for the server pager - and writes the choice back into
  the URL, so a filtered bank is a shareable link. `write_quiz_bank()`
  exports each question's `subjectId`/`subjectSlug` (the form submits ids;
  only the display name was exported, so a browser filter could never have
  matched) in the same order as `list_questions()`, whose ORDER BY gained
  the `q.id` tiebreak the shared seed timestamps need. Two neighbouring
  dead-ends went with it: static grading looked for `.option` where every
  card says `.opt`, so picking an answer never lit the right/wrong option
  up, and every practice card on a subject page linked to the whole subject
  list instead of the question it named (now `?slug=`); topic pages link to
  their topic's bank view. Covered by `test_question_bank_topics.py` and the
  new jsdom check `scripts/check_question_bank.js`, wired into CI and the
  Pages workflow next to `check_stream_filter.js`.

- **The Android app never produced an APK.** Two configuration bugs, both
  introduced in the wave-3 merge: the Gradle wrapper pinned 9.4.1 while AGP
  9.4.1 refuses to run below 9.6.0, and the AndroidX/Compose versions were
  compiled against API 37 while the app compiled against 36, so the AAR
  metadata check failed with 14 issues. The wrapper is now 9.6.0 and
  `compileSdk` is 37 (`targetSdk` stays 36 for Google Play). The backend test
  that pinned the old wrapper string now asserts the Gradle/AGP pair instead,
  and a new test keeps the workflow publishing an installable APK.

- **Depth wave 3 for the programming academy: thirty new modules, three per
  language.** `seed_data/language_book_wave3.py` (Python, Java),
  `language_book_wave3_web.py` (JavaScript, TypeScript),
  `language_book_wave3_native.py` (C, C++),
  `language_book_wave3_services.py` (C#, Go) and the existing
  `language_book_wave3_data.py` (Rust, SQL) give every path a semantics module,
  a standard-library-by-job module and a diagnostics module. The semantics
  modules cover the rules that decide behaviour (`==` versus identity, integer
  promotion, slicing and aliasing, nullability, coercion); the library modules
  map jobs to APIs with the traps named; the diagnostics modules teach
  tracebacks, stack traces, sanitizers, `pprof`, Miri and `EXPLAIN`. That is 275
  staged modules in total, up from 245, still across 30 stages and 90
  checkpoint questions, and every new module ends in an existing judged
  problem. Python and C/C++ examples were executed with CPython 3.11 and
  gcc/g++ 12.2; Java, C#, Go and Rust examples are authored and reviewed but not
  compiled in this environment, and SQL is written for PostgreSQL 16 with the
  SQLite/MySQL differences called out. See
  [docs/ACADEMY_VERIFICATION.md](docs/ACADEMY_VERIFICATION.md).

- **A deep language reference beside the course paths.** `/programming/reference`
  is a hub for ten languages, and `/programming/{language}/reference` is a
  lookup page with the execution model, the properties that decide design
  choices, syntax rules, the type system, the standard library by job, an
  error/cause/fix table, idioms, version history and official sources. The hub
  also renders ten cross-language tasks, each written in all ten languages with a
  note naming what does not translate. The content is 555 authored rows plus the
  comparison tasks, validated for shape and minimum depth at import and again
  before seeding, stored in `language_references` and
  `language_reference_tasks`, indexed for search, listed in the sitemap, and
  exported into the static reading copy. See
  [docs/LANGUAGE_REFERENCE.md](docs/LANGUAGE_REFERENCE.md).

- **Depth wave 2 for the programming academy: twenty new advanced modules.**
  `seed_data/language_book_wave2.py` adds two modules per language to the
  advanced stage of all ten paths (245 modules total, up from 225), covering
  runtime and systems material that a syntax reference only lists: Python's GIL
  with threads/processes/asyncio and typing/packaging/CI; the JVM heap and GC
  plus the Java Memory Model and executors; JavaScript's task and microtask
  queues plus ESM/bundling/supply-chain risk; TypeScript's type system and
  runtime validation; C undefined behaviour and the build/debug toolchain; C++
  RAII/value categories/moves and templates/concepts; C# `Span<T>`/GC and
  `async`/cancellation internals; Go's scheduler/channels/context and
  benchmark/profiling work; Rust borrowing/lifetimes and trait dispatch; SQL
  index/plan reading and transaction isolation anomalies. Every module ends in
  a judged problem that already exists in the bank. Examples were executed with
  the available toolchains (Python, JavaScript, TypeScript via Node type
  stripping, C, C++, SQLite); Java, C#, Go and Rust examples are authored and
  reviewed but not compiled in this environment. These are book-depth lessons,
  not A–O structured units, so the structured-unit count stays at fifteen. See
  [docs/ACADEMY.md](docs/ACADEMY.md) for the module table and the honest
  verification boundary.

- **Native macOS and iOS apps (`apple/`) and website downloads.** Added a Swift
  5.10 multiplatform SwiftUI + WebKit project targeting macOS 14+ (Universal
  `arm64` + `x86_64`) and iOS / iPadOS 17+ (`arm64`) with offline subject and
  topic search (`scripts/export_apple_catalog.py` → `apple/Resources/catalog.json`),
  study streaks, planner tasks, learning-record export, local-only privacy
  manifest (`PrivacyInfo.xcprivacy`), and a hardened `WKWebView` viewer with
  zero `WKScriptMessageHandler` bridges. `.github/workflows/apple-build.yml`
  runs `swift test`, builds `Meridian-macOS.dmg` and `Meridian-iOS.ipa` with
  SHA-256 digests, verifies archives via `scripts/verify_apple_release.py`, and
  publishes release assets. Both the FastAPI backend (`ENGINEVERSE_MACOS_URL`,
  `ENGINEVERSE_IOS_URL`, `/downloads/{filename}`) and static GitHub Pages export
  (`scripts/export_pages.py`) surface macOS, iOS, and Android downloads across
  the homepage hero, footer, OS-aware `/install` page (plus Safari Web App
  instructions), `/hosting`, and `/settings`. Details in
  [docs/APPLE.md](docs/APPLE.md); tests in `backend/tests/test_apple_project.py`,
  `backend/tests/test_public_delivery.py`, and
  `backend/tests/test_static_export_contract.py`.

- **Search-engine and social metadata for the public site.** Every public page
  now has one canonical URL (filter parameters dropped, `page` and `card` kept),
  a meta description taken from its navigation blurb, and a `robots` meta tag
  that keeps signed-in and error pages out of the index. `robots.txt` disallows
  the private pages listed in the navigation table. Open Graph and Twitter
  previews use a 1200x630 card (`/static/img/og-image.png`). The home page has
  Organization structured data and every trail has BreadcrumbList data that
  mirrors the visible breadcrumb. Retired and non-canonical addresses answer
  301 (`engineverse/redirects.py`); the static copy writes refresh pages for
  them. Images are served as WebP with a PNG fallback through a `<picture>`
  macro that requires alt text and lazy-loads by default. Tests are in
  `backend/tests/test_seo.py`. Regenerate the images with
  `scripts/gen_social_images.py`.

### Added

- **Optional ElevenLabs voice reader and spoken tutor.** Educational text
  (note sections, the formula centre, roadmaps, programming lessons, Study
  Tutor answers and checked practice explanations) can be read aloud, with
  Play/Pause, Stop, Replay and a speed control. On `/tutor`, students can hold
  a spoken conversation with a configured ElevenLabs agent. Both are off by
  default: the API key stays on the FastAPI backend, `/api/voice/speech` returns
  audio and `/api/voice/session` returns a short-lived signed Conversational AI
  URL. Requests are JSON-only, origin-allow-listed, size-capped and
  rate-limited; URLs and audio are released client-side. Setup, the agent
  instruction and cost limits are in
  [docs/ELEVENLABS_INTEGRATION.md](docs/ELEVENLABS_INTEGRATION.md).

- **The n8n study assistant.** A floating launcher on every page and a full page
  at `/assistant`, backed by an n8n Chat Trigger. The server proxies the request
  (`POST /api/assistant/chat`), so the webhook URL never reaches the browser and
  the CSP stays `connect-src 'self'`; the static Pages copy can call the trigger
  directly only when `ENGINEVERSE_ASSISTANT_PUBLIC_URL` is configured. Includes
  page-aware prompts, session continuity, timeouts, retry, offline detection,
  per-IP and per-session limits, safe error messages and an honest
  "not configured" state. See `docs/ASSISTANT.md`.
- **Eight importable n8n workflows** in `n8n/workflows/`: student copilot
  (HTTP model and agent+memory variants), feedback intake, content drafting with
  a mandatory human review stop, onboarding, unsubscribe, measured analytics
  rollup and operations monitoring. Generated by
  `scripts/build_n8n_workflows.py`, validated by
  `scripts/check_n8n_workflows.py`; setup and costs in
  `docs/N8N_AUTOMATION.md`.
- **`scripts/mock_n8n.py`** speaks the Chat Trigger contract so the integration
  can be exercised without credentials, and **`scripts/verify_assistant.py`**
  sends one real message once a webhook is configured.
- **Assistant tests**: 45 Python checks (`backend/tests/test_assistant.py`) and
  29 browser checks (`scripts/check_assistant.js`) covering transport, error and
  retry states, CSRF, rate limits, XSS escaping, duplicate mounting and the
  static export.
- **Sharing without tracking**: a copy-link / native-share control on topic,
  project, problem and assistant pages. No `?ref=` parameter is added because
  Meridian measures no referrals, so it would decorate the URL without
  measuring anything.
- **Open Graph and Twitter card images**, `og:image:alt`, a `twitter:*` block and
  `WebSite` + `SearchAction` structured data on the home page, where it applies.
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
- **Legacy lessons gained a course rail.** A module that predates the
  structured unit format rendered as one narrow card with half the page empty;
  it now sits in the same two-column layout as a structured lesson, with a rail
  carrying the course index, its stage, previous/next and the honest "nothing
  here is graded" note. Its content and wording are unchanged.
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

- **CodeLab no longer hides what you are typing.** The editor draws text with
  two layers: a syntax-highlighted mirror, and the textarea itself. While you
  edit, the mirror is hidden and the textarea paints the characters. Those two
  halves were driven by different mechanisms - JavaScript added an
  `.is-editing` class that hid the mirror, and a separate
  `.cl-textarea:focus` rule was the only thing that restored the text colour.
  On a soft keyboard, an IME or an Android WebView that misses or never
  repaints the pseudo-class, the mirror was hidden while the textarea text
  stayed transparent: the caret moved and the character count grew, but the
  slab looked empty. One state (the class, mirrored by `:focus` in CSS) now
  owns both halves, and every way an edit can start - focus, pointerdown,
  touchstart, keydown, IME input, the quick-symbol keys and autocomplete -
  sets it, so no combination can hide both layers. The editor slab also no
  longer inherits the site-wide form-field styling (12px radius, inner shadow,
  120px min-height) from `app.css`, which had been drawing a rounded opaque
  card over the code area, and a highlighter error now falls back to plain
  text instead of an empty mirror. On phones, the page lifts the editor clear
  of the on-screen keyboard when the visual viewport shrinks mid-edit.
- **The CodeLab mobile view switcher is a valid tablist again.** The Run button
  sat inside the element with `role="tablist"`, which is a child a tablist may
  not contain (axe `aria-required-children`, severity critical). The three tabs
  now live in their own `.cl-mobile-tabs` wrapper and Run is their sibling, with
  the same layout and keyboard behaviour.
- **The static-site import checks no longer race the file reader.** They slept
  for a fixed 50 ms after handing a file to the settings importer and then read
  the status line, which failed intermittently on a loaded CI runner and passed
  on a laptop. They now wait for the expected line, up to three seconds.
- The assistant's `X-EngineVerse-Page` header is reduced to printable ASCII
  before it is sent upstream, so a crafted page path cannot inject a header.
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
