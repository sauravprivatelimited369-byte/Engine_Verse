# Growth, discoverability and measurement

Meridian's growth goal is that a student who needs it can find it. This
document records what the code now does, what it deliberately does not do, and a
practical plan a single maintainer can run.

Two rules run through everything here:

1. **Do not manufacture numbers.** No fake testimonials, no invented user counts,
   no "12,000 students" badges, no engagement bait, no bot traffic.
2. **Do not measure what you have not disclosed.** Meridian loads no
   third-party analytics. That means some metrics below are *not available*, and
   this document says so instead of estimating them.

---

## 1. What is implemented in the code

| Item | Status | Where |
|---|---|---|
| Page titles and meta descriptions | Present on catalogue pages; every page has a title, most have a description | `base.html`, page templates |
| Canonical URLs | Every response | `web/deps.py` → `_canonical_url` |
| `og:title`, `og:description`, `og:type`, `og:site_name`, `og:url` | Present | `base.html` |
| `og:image`, `og:image:alt`, `twitter:card`, `twitter:*` | **Added** — a 512 px icon on every page | `base.html`, `_public_url()` |
| Structured data | **Added** — `WebSite` + `SearchAction` on the home page only, because that is the page that qualifies | `home.html` |
| `sitemap.xml` | Generated from the navigation table, so a new page is never omitted | `navigation.py`, `pages.py` |
| `robots.txt` | Generated for the deployed copy | `scripts/export_pages.py` |
| Descriptive URLs | `/topics/<slug>`, `/practice/problems/<slug>`, `/projects/<slug>` | `pages.py` |
| Internal links | Every destination is reachable from menus; the navigation table is asserted against the app by tests | `navigation.py`, `test_navigation.py` |
| Native share / copy link | **Added** on topic, project, problem and assistant pages; no tracking parameter | `_share.html`, `app.js` |
| Mobile layout | Existing; the assistant panel becomes a sheet above the bottom bar | `assistant.css` |
| Reduced motion | Respected by the assistant; existing app behaviour unchanged | `assistant.css` |
| Accessibility | Skip link, landmarks, `aria-live` log, focus management, `Escape` to close, visible labels | `_assistant.html`, `assistant.js` |
| Legal pages | `/privacy`, `/terms` exist; the assistant adds a disclosure and a "how this works" section | `assistant.html` |

Deliberately **not** added: a cookie banner (there are no tracking cookies to
consent to beyond the session/CSRF cookies already documented), pop-ups, exit
intent, a "live activity" ticker, or referral links (nothing tracks referrals, so
a `?ref=` would be decoration).

Sitemap caveat: on a **project** Pages site the site is served under
`/Engine_Verse/`, and crawlers only read `robots.txt` at an origin root. The
generated `robots.txt` therefore matters mainly when the site is deployed on its
own domain. It is not harmful in either case.

---

## 2. Measurement: what can actually be known

| Question | Can Meridian answer it? | How |
|---|---|---|
| Is the assistant working? | **Yes** | `audit_logs` actions `assistant.asked` / `assistant.failed` / `assistant.limited`, with `latency_ms` in `meta`. Workflow `06-analytics-rollup.json` queries it. |
| How many questions were answered / failed? | **Yes**, on a self-hosted instance | As above. On the static Pages copy there is no server, so **no**. |
| Assistant latency | **Yes** self-hosted | `meta.latency_ms` |
| Registrations, feedback, subscribers | **Yes** self-hosted | `users`, plus the optional n8n tables |
| Website visits and unique visitors | **No** | No analytics script is loaded. GitHub Pages reports its own traffic to the repository owner (insights), which is aggregate and outside this code. |
| Referral sources | **No** | Not measured, and not guessed. Add a privacy-respecting, disclosed analytics tool only if you decide the trade-off is worth it — and then update `/privacy`. |
| Returning users / retention cohorts | **No** (aggregate only via GitHub Pages if enabled) | Self-hosted accounts can approximate with `users.created_at` and activity, but that is a cohort query, not implemented here. |
| Assistant launch rate (launcher opened) | **No** | Not instrumented on purpose. Instrumenting it means collecting interaction events; decide and disclose before adding. |

The rule the analytics workflow follows: it prints `notMeasured` explicitly
rather than filling gaps with plausible numbers.

---

## 3. Content strategy that fits the actual product

Each of these is buildable from features that already work. The pattern is:
**one page, one problem a student can finish in ten minutes, link it into the
catalogue, share it once.**

| Week | Piece | Source material | Effort |
|---|---|---|---|
| 1 | "Data structures in 30 days" plan | `/roadmaps`, `/sheets` | 2 h |
| 1 | "Fix these five Python errors" | `/compiler`, the error messages the judge returns | 2 h |
| 2 | "How to read a stack trace" | `/codelab` | 2 h |
| 2 | "Your first judged problem" walkthrough | `/practice/problems` | 2 h |
| 3 | "Build a weather dashboard" project log | `/projects` brief, `/apis` directory | 3 h |
| 3 | "Semester exam revision in 7 days" | `/planner`, `/flashcards`, `/revision` | 2 h |
| 4 | "AI/ML from zero: what to learn first" | `/roadmaps`, `/topics` AI topics | 3 h |
| 4 | "How to prepare for a hackathon with 48 hours" | `/projects`, `/sheets` | 2 h |

Publishing: write once, adapt per channel using workflow `03` (which stops for
review), and post by hand. Telegram and a blog/updates page are the cheapest
channels to maintain; Instagram and YouTube need production work, so they are a
later step.

Rules that keep this from becoming spam:

- Every post links to a page that exists and works.
- Say "free and open source"; never claim accreditation, placement guarantees or
  a result nobody measured.
- One message per subscriber, with a working unsubscribe (workflow `04`/`05`).
- No automated DMs, no purchased lists, no scraping groups.

---

## 4. A 30-day student acquisition plan

Assumes one maintainer, a few hours a week, and no ad budget.

**Days 1–3 — make the site findable and honest.**
Set `ENGINEVERSE_ASSISTANT_URL` (or the Pages variable), run
`scripts/verify_assistant.py`, and confirm `/assistant` answers in a browser.
Claim the Pages site in Google Search Console and Bing Webmaster Tools for the
repository owner, submit `sitemap.xml`, and fix anything the coverage report
flags. Check `/privacy` and `/terms` describe the assistant's data flow.

**Days 4–7 — fix the first five minutes.**
Open the site on a mid-range Android phone over mobile data. Time the first
paint; check the hero, the "Start learning" path, and that the assistant loads
without blocking. Ask two students to try one task each and watch where they
stop. Fix those two things before writing any content.

**Days 8–14 — publish the first four pieces above.**
Post each to the channels you can maintain (a Telegram study group you already
belong to, LinkedIn, X, your college community). Answer questions in replies
with links to the page that actually answers them. Do not cross-post the same
text to ten groups.

**Days 15–21 — make contribution easy.**
Label 5 beginner-friendly issues (typos in notes, a missing formula, a better
error message). Open the repository's Discussions or point to the existing
`/community`. Publish a short release note for the assistant and the workflows.
Ask two classmates for a note correction; merging their PR is the best growth
loop a study platform has.

**Days 22–30 — measure, then decide.**
Look at Search Console queries, GitHub Pages traffic (aggregate), assistant
audit counts if self-hosted, and any feedback received. Write down three numbers
and three surprises. Decide the next month from those, not from vanity metrics.
If the assistant is getting real use, review its answers with a subject teacher
and adjust the system prompt — quality is what makes students return.

What this plan cannot promise: a specific traffic number. Anything quoted here
would be invented.

---

## 5. Community and contributions

- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue templates and a PR template
  already exist; `docs/SECURITY.md` is the vulnerability route.
- Beginner-friendly work that is genuinely useful: note corrections, formula
  typos, clearer error copy, an accessibility fix, a new flashcard deck, a
  translation in `backend/static/locales/`.
- Release notes should stay short and specific: what changed, what it affects,
  and what is still not done. The assistant's "not configured" state is a good
  example of documenting a limit rather than hiding it.

---

## 6. Next five improvements

1. **Verify the assistant against the real n8n workspace** and record the answer
   in the release notes (`scripts/verify_assistant.py`).
2. **Instrument the assistant honestly**: opt-in, disclosed counters for launcher
   opens and answer usefulness ("Was this helpful?"), stored server-side with the
   same metadata-only rule. Without this, quality improvements are guesses.
3. **Add subject-teacher review for the assistant's answers**: a weekly sample of
   20 answers, corrected in the system prompt. This is the highest-value quality
   work for a study tool.
4. **Faster first load on mobile**: measure Core Web Vitals on a throttled 3G
   profile and cut the largest blocking asset; the notes pages carry a lot of
   catalogue HTML.
5. **Widen the content moat**: the 30-day roadmap and error-message pieces above
   are the pages a student bookmarks and shares; they deserve screenshots, real
   examples and a printable version.
