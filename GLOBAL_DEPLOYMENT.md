# EngineVerse — Global Deployment Guide

EngineVerse is built so engineering students in every country can use it:
notes, practice, coding, projects, revision and placement prep — without
leaving the site. This guide documents every barrier that previously prevented
global use, the fix applied, and how to deploy a publicly accessible instance.

---

## 1. Barriers found and fixes applied

| # | Barrier | Why it blocked global use | Fix |
|---|---------|--------------------------|-----|
| 1 | Sign-in compulsory (ENGINEVERSE_SIGNIN=required) | Students could not browse content without an account — a privacy and access barrier. | Default changed to optional. Anonymous browsing of the public catalogue is allowed; set required for a gate. |
| 2 | English-only UI (lang="en" hardcoded, no i18n) | Billions of non-English students excluded; RTL scripts unsupported. | Full i18n layer: 10 locales (en, es, hi, ar, zh, fr, pt, bn, ru, ur), RTL support, footer language picker, browser-language detection, saved preference. |
| 3 | No password/SMS recovery | Without SMTP or SMS configured, password reset and OTP failed — students locked out. | Added ENGINEVERSE_SHOW_OTP_ON_PAGE: when no mail/SMS transport exists, recovery codes are shown on the page instead of 503. |
| 4 | Code execution disabled (ENGINEVERSE_JUDGE=disabled) | Judged coding practice did not run — students could not compile or submit code. | Documented Judge0 setup; production requires judge0 + ENGINEVERSE_JUDGE0_URL. |
| 5 | APK only on GitHub | GitHub blocked in China, Iran, North Korea, Syria, Crimea — no Android install. | Web app is installable on any phone via "Add to Home screen" (PWA). APK remains optional. |
| 6 | Hardcoded example domain | Not reachable; instances had no working public origin. | Documented real domain + HTTPS setup with Caddy. |
| 7 | Empty ENGINEVERSE_SECRET | Production refuses to start without a signing secret. | .env.example includes generation command; production validates length. |

---

## 2. Minimum viable deployment (any country)

```bash
# 1. Clone
git clone https://github.com/sauravprivatelimited369-byte/Engine_Verse.git
cd Engine_Verse

# 2. Configure
cp .env.example .env
# Edit .env: set ENGINEVERSE_SECRET, ENGINEVERSE_SITE_URL, ENGINEVERSE_DB_URL

# 3. Install Python deps
pip install -r requirements.txt

# 4. Seed the database
python scripts/seed.py --fresh --stats

# 5. Run
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Required .env values for a public instance

```
ENGINEVERSE_SECRET=<32+ random chars: python3 -c "import secrets;print(secrets.token_hex(32))">
ENGINEVERSE_SITE_URL=https://your-domain.com
ENGINEVERSE_DB_URL=postgresql://engineverse_app:password@localhost:5432/engineverse
ENGINEVERSE_SIGNIN=optional
ENGINEVERSE_JUDGE=judge0
ENGINEVERSE_JUDGE0_URL=http://your-judge0-host:2358
HOST=0.0.0.0
PORT=8000
```

### Optional but recommended

```
ENGINEVERSE_SMTP_URL=smtps://user:pass@smtp.example.com:465/?starttls=0
ENGINEVERSE_MAIL_FROM=EngineVerse <no-reply@your-domain.com>
ENGINEVERSE_SMS_URL=https://gateway.internal/messages
ENGINEVERSE_SHOW_OTP_ON_PAGE=1
ENGINEVERSE_APK_URL=https://github.com/sauravprivatelimited369-byte/Engine_Verse/releases/download/android-v1.0.0/EngineVerse.apk
```

---

## 3. HTTPS / public domain (Caddy)

EngineVerse must run behind HTTPS for cookies, service workers and PWA install. The deploy/ directory includes a Caddyfile:

```
your-domain.com {
    reverse_proxy localhost:8000
}
```

Run Caddy in front of the web process. It handles automatic Let's Encrypt certificates.

---

## 4. Code execution (judge)

Production refuses auto, python and java (they run learner code on the server). Use:

- **disabled** — no code execution (default; coding practice won't run).
- **judge0** — forward submissions to a self-hosted Judge0 instance:
  ```
  ENGINEVERSE_JUDGE=judge0
  ENGINEVERSE_JUDGE0_URL=http://your-judge0-host:2358
  ENGINEVERSE_JUDGE0_KEY=<api-key>
  ```

See backend/engineverse/judge/ for the judge integration.

---

## 5. Android app distribution

### Web app (works everywhere, including where GitHub is blocked)

Every EngineVerse instance is a PWA:
- Android (Chrome): Open the site → menu → "Add to Home screen" / "Install app".
- iPhone (Safari): Share → "Add to Home Screen".
- Desktop: Browser install icon.

No app store, no GitHub, no APK download needed.

### Native Android app

The repository's native app (`android/`) is built by `.github/workflows/android-build.yml`. Every Android change produces a debug APK as a workflow artifact. A maintainer can publish a signed release APK to GitHub Releases by adding the signing secrets and running the workflow manually; see [android/README.md](android/README.md). Operators who run the full website on their own domain can instead build a Trusted Web Activity with `android/build-twa.cjs` ([docs/ANDROID_TWA.md](docs/ANDROID_TWA.md)).

Note: GitHub Releases are unreachable in some countries. The web-app install path is the recommended global distribution method.

---

## 6. Internationalisation (i18n)

Supported UI languages (10):

| Code | Language | Script |
|------|----------|--------|
| en | English | LTR |
| es | Español | LTR |
| hi | हिन्दी | LTR |
| ar | العربية | RTL |
| zh | 中文 | LTR |
| fr | Français | LTR |
| pt | Português | LTR |
| bn | বাংলা | LTR |
| ru | Русский | LTR |
| ur | اردو | RTL |

- Language detected from browser and saved in localStorage.
- Footer language picker lets users switch at any time.
- Content remains in the author's language but is browsable everywhere.
- RTL layouts mirrored via html[dir="rtl"] CSS.

Add a new locale: create backend/static/locales/<code>.json (copy en.json).

---

## 7. Security notes for public instances

- Never commit .env — contains ENGINEVERSE_SECRET and database passwords (.env is git-ignored).
- Production requires PostgreSQL — SQLite is refused in production.
- Production requires HTTPS — ENGINEVERSE_SITE_URL must start with https://.
- Cookie Secure follows ENGINEVERSE_SITE_URL (https → secure cookies).
- If you enable ENGINEVERSE_SHOW_OTP_ON_PAGE, recovery codes are visible on screen — use only when no mail/SMS transport exists.

---

## 8. CI / CD

Pushes to main run:
- CI — Python test suite (requirements.txt pins).
- GitHub Pages — publishes the static public site.
- Android APK — builds, signs and releases EngineVerse.apk (requires repo secrets/vars).

Required GitHub variables for APK: ENGINEVERSE_APP_URL, ENGINEVERSE_TWA_PACKAGE, ENGINEVERSE_TWA_ALIAS, ANDROID_SIGNING_KEYSTORE.

---

## 9. What was changed (code)

- backend/engineverse/config.py — signin default required → optional; added recovery_show_on_page setting.
- backend/engineverse/auth.py — OTP/recovery code shown on page when no transport + opt-in flag.
- backend/web/deps.py — recovery_show_on_page exposed to templates.
- backend/static/js/i18n.js — new: client-side i18n, language persistence, picker builder.
- backend/static/locales/*.json — 10 locale files (en, es, hi, ar, zh, fr, pt, bn, ru, ur).
- backend/static/css/app.css — RTL overrides, language picker styles.
- backend/templates/base.html — i18n script tag, dynamic lang/dir, footer language picker.
- backend/templates/_footer.html — language picker widget.
- backend/templates/home.html — data-i18n attributes on all UI strings.
- .env — local development defaults.
