# Contributing to Meridian

Thanks for helping. Meridian is a free study platform for engineering
students: a FastAPI website, a static reading copy published to GitHub Pages,
and a native Android app. Corrections to notes are as welcome as code.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Report security problems privately as described in
[docs/SECURITY.md](docs/SECURITY.md#reporting-a-vulnerability), not in an issue.

## Ground rules

These keep the project honest. Pull requests that break them are not merged.

- **No pretend features.** A button either works or is not shown. No fake
  sign-in, payment, notification, sync, statistic, testimonial or partner.
- **No secrets or learner data in the repository**: no `.env` files, tokens,
  keystores, database dumps or real names, emails or phone numbers. The static
  site and the Android app store progress on the device only.
- **Say what runs where.** Do not describe a programming language as runnable
  unless a test runs it, and keep the "not executed" messages accurate.
- **Link, don't copy.** Third-party books, videos and articles are linked, never
  re-hosted. See the [content policy](docs/CONTENT.md).
- **Verify links and opportunities.** Anything listed on the opportunities page
  needs an official URL you have opened yourself.

## Set up the website

Python 3.11 or newer.

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env            # then set ENGINEVERSE_SECRET (see README)
python scripts/seed.py --fresh --no-demo
uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

`--fresh` wipes the development database. Open <http://127.0.0.1:8000>.

## Run the checks

Run the tests from the repository root, as CI does. Some tests use paths
relative to the root.

```bash
python -m pytest backend/tests -q                  # the full suite (about 11 minutes)
python -m pytest backend/tests -q -m "not slow"    # skips real compile/run tests
```

To check the static GitHub Pages copy:

```bash
npm install --prefix .toolchain/jsdom jsdom@26
python scripts/export_pages.py --out site --reading-copy
node scripts/check_static_site.js site
node scripts/check_planner.js site/planner/index.html site/static/js/planner.js
```

`export_pages.py` reads the repository name from `GITHUB_REPOSITORY` or from
the `origin` remote. In a fork it builds URLs for your fork.

The Android app is built with Gradle; see [android/README.md](android/README.md).
A pull request that touches `android/` runs unit tests, lint and a debug build in
the **Android app** workflow.

## Making a change

1. Open an issue first for anything larger than a fix, so we can agree on the
   approach.
2. Branch from `main` and keep the change focused. Follow `.editorconfig`.
3. Add or update tests. Every route and page has tests in `backend/tests/`.
   Static-site behaviour is covered by `scripts/check_static_site.js`.
4. Update the docs and add a line to [CHANGELOG.md](CHANGELOG.md) under
   **Unreleased**.
5. Open a pull request and fill in the template. CI must pass.

### Content corrections

For a wrong formula, a broken example or a dead link, open a
**Content correction** issue with the page URL, or edit the seed data under
`seed_data/` and open a pull request. Notes follow
[docs/NOTE_TEMPLATE.md](docs/NOTE_TEMPLATE.md).

## Licence

Code you contribute is released under the [MIT License](LICENSE).
