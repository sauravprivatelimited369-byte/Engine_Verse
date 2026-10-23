# Changelog

Notable changes to EngineVerse. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are not yet
tagged, so everything below is listed under **Unreleased** until the first
release.

## Unreleased

### Added

- **AI student copilot** (`/assistant` plus a floating launcher): questions go to
  the operator's n8n workflow through a server-side bridge
  (`backend/engineverse/assistant.py`), so the webhook URL and its credential are
  never in the browser and the page keeps `connect-src 'self'`. The UI labels the
  assistant as AI, shows an honest "not connected" state instead of a dead
  composer, offers page-aware suggestions, retry and rate-limit recovery, and
  keeps the transcript in `sessionStorage` only. `scripts/check_assistant.py`
  verifies a real answer. See [docs/ASSISTANT.md](docs/ASSISTANT.md).
- **n8n automation templates** (`automation/n8n/`): student copilot, feedback
  intake, idempotent onboarding with consent and unsubscribe, error alerting and
  an uptime poll. Inactive on import, no credentials embedded, and validated for
  structure by `backend/tests/test_n8n_automation.py`. Design, costs and the
  remote steps are in [docs/N8N_AUTOMATION.md](docs/N8N_AUTOMATION.md).
- **Share controls** on topic and project pages: native share where available,
  copy-link with a fallback, and plain WhatsApp/Telegram links (no SDK).
- **Social metadata**: `og:image`, `twitter:card`, page-level descriptions, and
  JSON-LD (`WebSite` + `SearchAction` on the home page, `LearningResource` on
  topic pages) using only fields the page can evidence.
- **Growth plan** with the measurement limits stated plainly:
  [docs/GROWTH.md](docs/GROWTH.md).

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

- `/privacy` and `/terms` now describe the assistant: what is sent, what is not
  stored, that it is not a person, and that its answers are not advice.
- `/support` explains how to report a wrong or unsafe assistant answer, and
  `/tutor` points at the copilot for questions outside the catalogue.
- Rate-limit responses for the assistant carry a stable
  `assistant_rate_limited` code so the UI can show a recovery message.
- The home page gains one honest assistant entry point next to the grounded
  tutor.

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

### Fixed

- Open Graph and Twitter descriptions now use each page's own description
  instead of the site tagline.
- The social-preview image URL no longer contains a double slash in the static
  export.
