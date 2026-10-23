# Student growth, honestly

EngineVerse is for students. Growth here means more students finding it and
finding it useful — not more sessions, more impressions, or a counter that goes
up because it was animated.

Two rules run through this page:

1. **Measure only what the system can observe.** The app loads no analytics
   script. GitHub Pages exposes no visitor counts. Anything described as
   "estimated" below is exactly that.
2. **Nothing requires spam.** No feature is locked behind inviting friends, no
   pop-up interrupts reading, and no unsolicited bulk messaging is part of the
   plan.

## What is already implemented (this change and before)

| Surface | What exists | Verify it |
|---|---|---|
| Titles and descriptions | Every page extends `base.html`, which supplies `<title>`, meta description, canonical URL, Open Graph and Twitter card metadata | `python -m pytest backend/tests/test_crawl.py backend/tests/test_navigation.py` |
| Canonical URLs | Absolute, generated from `ENGINEVERSE_SITE_URL` (never the `Host` header) or the Pages origin in the static export | `deps._canonical_url` |
| Sitemap | `/sitemap.xml`, generated from `navigation.indexable_paths()` plus every seeded slug and paginated shelf | `backend/tests/test_crawl.py` |
| robots.txt | Allows crawling only when anonymous browsing is on; disallows `/api/`, `/settings`; points at the sitemap | `main.create_app` |
| Structured data | `WebSite` + `SearchAction` on `/`, `LearningResource` on topic pages — only fields the page can evidence | `home.html`, `topic.html` |
| Social previews | `og:image` is the shipped 512px icon, absolute in both hosting modes; `summary` card | View source |
| Share controls | Native share sheet when available, copy-link with a fallback, WhatsApp and Telegram links (ordinary links, no SDK) on topic and project pages | `_share.html`, `app.js` |
| Internal links | One navigation table drives the top bar, mobile menu, footer, breadcrumbs, "everything" index, sitemap and the static export | `backend/tests/test_navigation.py` |
| Accessibility | Skip link, focus-visible styles, reduced-motion support, `role="log"` transcript, native dialog, labelled controls | `check_static_site.js`, manual keyboard pass |
| Speed | No CDN, no framework, self-hosted variable fonts, two CSS files, small vanilla scripts | `du -sh backend/static` |

## What is not implemented, and why

- **Referral tracking.** A referral link that cannot reliably attribute a sign-up
  is worse than none: it produces numbers nobody should trust. If referral codes
  are added later, they need a first-party endpoint, a privacy notice and a
  deduplication rule before any link is published.
- **A public analytics dashboard.** There is no traffic data source in this
  repository. Building a dashboard on seeded or estimated numbers would be
  inventing metrics.
- **Testimonials.** There are none. Do not add quotes from students who did not
  say them.
- **A newsletter form.** The onboarding workflow exists
  (`automation/n8n/03-student-onboarding.json`) but no form is published. Whether
  to collect email addresses is the operator's decision, and it needs an
  unsubscribe path that works before the form goes live.

## A 30-day plan

The plan assumes one maintainer with limited hours. It optimises for useful
content that can be checked, not for volume.

### Week 1 — make the front door honest and fast

- [ ] Deploy the current branch and run `scripts/check_assistant.py --app <url>`.
      Until it exits 0, the assistant is "configured", not "working".
- [ ] Enable GitHub Pages (Settings → Pages → Source: GitHub Actions) if it is
      not already on. `GET /repos/{owner}/{repo}/pages` currently returns 404
      from this environment, which is what "not enabled" looks like over the API.
- [ ] Submit the sitemap to Google Search Console and Bing Webmaster Tools.
      Record the verification date; do not guess at indexation.
- [ ] Run Lighthouse against the deployed home, a topic page and `/assistant`.
      Fix anything under 90 in Performance or Accessibility before adding
      content.
- [ ] Ask five students to complete one task each (find a topic, answer a DPP
      question, ask the assistant one question) and note where they hesitate.

### Week 2 — publish three genuinely useful pages

Pick from material that already exists, so the work is editing not invention:

- [ ] **"How to read a Python traceback"** — with a real error, the fix, and a
      link to `/codelab`.
- [ ] **"A 7-day revision plan for one engineering subject"** — the planner
      workflow, written out, linking `/planner` and `/flashcards`.
- [ ] **"Your first judged problem"** — one problem from `/practice/problems`,
      solved in two languages, with the test output shown.

Each page: one canonical URL, one description, a real example, internal links to
the tool it teaches. No keyword stuffing, no auto-generated filler.

### Week 3 — distribution that respects the audience

- [ ] Post each of the three pages once, where the students already are: your own
      Telegram channel or a college group you are a member of, with permission
      from its owner. Do not cross-post identical text to five networks.
- [ ] Create one short video from the traceback page. Publish it where you have
      an account; link it from `/videos`.
- [ ] Open three "good first issue" items on GitHub (typo, missing formula,
      mobile layout bug) and label them. A contribution route is growth too.
- [ ] Add the assistant's "Was this useful?" results to a weekly note. Read the
      bad answers; fix the system prompt or the content they reveal.

### Week 4 — review with real numbers

- [ ] Export `audit_logs` counts for `assistant.asked` by outcome and by day. This
      is measured, not estimated.
- [ ] Count registrations by week from the `users` table.
- [ ] Ask Search Console for impressions, clicks and queries. Anything not in
      Search Console or your own database is an estimate — label it as one.
- [ ] Decide the next three content pages from the questions students actually
      asked (they are not stored; use the patterns you saw in feedback and
      support issues).
- [ ] Write a public changelog entry that says what changed and what did not.

### What success looks like at day 30

Not a number of "users". A defensible answer to three questions:

1. Did any student complete a learning loop (read → practise → review) without
   help?
2. Did the assistant answer questions it was configured to answer, and fail
   visibly when it was not?
3. Is there a repeatable way to publish one useful page a week?

If the answer to any of those is no, more traffic will not fix it.

## Content standards

- Every claim about the platform must match the code. If the judge is disabled,
  the page says so.
- Every AI-generated surface is labelled as AI.
- Every external link points at an official source, and the weekly link check
  (`scripts/check_links.py`) is the maintenance path.
- No fake urgency, no fake counters, no fake testimonials, no "AI-powered"
  claims where no model is called.
