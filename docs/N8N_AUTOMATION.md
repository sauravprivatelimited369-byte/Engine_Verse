# n8n automation: what exists, what is designed, what needs you

This page separates three things that are easy to blur together: workflows that
ship as importable JSON, workflows specified here but not built because they
need an account or a decision from the operator, and the manual steps only the
owner of the n8n instance can perform.

Nothing here was activated, and no private n8n workflow was edited by this
change. The instance this repository's owner runs was not reachable from the
environment where the work was done.

## Status at a glance

| Workflow | Purpose | Shipped as JSON | Verified end to end |
|---|---|---|---|
| **A. Student copilot** | Question → validate → AI answer → return | `01-student-copilot.json` | Bridge verified against a local stand-in; **your workflow not tested** |
| **B. Feedback intake** | Vote/category → consent → store → aggregate view | `02-feedback-intake.json` + `feedback.sql` | JSON structure only |
| **C. Learning content distribution** | Draft → human review → platform versions → publish | Not shipped — see the design below | Nothing |
| **D. Student onboarding** | Opt-in → idempotent insert → welcome → unsubscribe | `03-student-onboarding.json` + `feedback.sql` | JSON structure only |
| **E. Growth analytics** | Aggregate the measurements the app can actually produce | Not shipped — see the design below | Nothing |
| **F. Operational monitoring** | Failed executions and unhealthy endpoint → administrator | `05-monitoring.json`, `06-uptime-check.json` | JSON structure only |

"JSON structure only" means `backend/tests/test_n8n_automation.py` asserts the
document is coherent (unique nodes, resolvable connections, no embedded
credentials) and that the safety rules the docs claim are present. It is not an
import test.

---

## A. Student copilot

Contract, setup, error codes and privacy: [ASSISTANT.md](ASSISTANT.md). In short:

```
Webhook (Header Auth, responseNode)
  → Code: bound the body (2–1200 chars, session shape, page shape)
    → IF valid
      → AI Agent (system prompt, English/Hindi) ← chat model ← window memory keyed by sessionId
        → Respond to Webhook { output }
      → else → Respond 422
```

Operational notes:

- Set the model yourself. The template names `gpt-4o-mini` as a placeholder
  because it is cheap; it is not an endorsement and no cost figure is claimed
  here.
- `contextWindowLength: 12` bounds memory per session. A larger window costs
  more per turn and does not help a student who asks one question.
- The system prompt forbids claiming to execute code, browse the web, read the
  student's account, or be a human. `test_n8n_automation.py` fails if those
  sentences are removed, so the UI's disclosure cannot drift from the prompt.

## B. Feedback intake

```
Webhook (Header Auth) → Code (validate; store contact only with consent)
  → IF acceptable → Postgres INSERT → Respond { recorded: true }
                  → else → Respond 422
```

The EngineVerse UI's own "Was this useful?" control already records an aggregate
vote in the audit log without free text. This workflow is for **longer** feedback
the operator chooses to collect. If you enable it, host the form yourself, set
`contactConsent` from an unchecked box, and link the privacy page. The database
view `engineverse_feedback_weekly` gives a weekly count and the most common
reason; it does not estimate anything about people who did not respond.

## C. Learning content distribution — design only

This is deliberately **not** shipped as JSON. Publishing to GitHub, YouTube,
Instagram, Telegram or WhatsApp requires accounts, API credentials, and a
decision about which channels you own. A template that guessed at those would
either fail on import or, worse, publish something unreviewed.

The pipeline to build, once you have decided the channels:

1. **Source.** A schedule or manual trigger reads *approved* EngineVerse content
   — a published topic, a project brief, a solved problem — through the REST API
   (`/api/...`) or a read-only database replica. Never scrape your own site.
2. **Draft.** An AI node produces a platform-shaped draft: a 60-second video
   script, a carousel outline, a Telegram post, a repository README section.
   Pass the source text as context and require citations back to the topic URL.
3. **Human review — mandatory.** A Wait node or an approval email. The draft is
   not publishable until a named person approves it. This is the step that keeps
   the account from becoming an auto-generated content farm.
4. **Adapt.** Separate branches per channel, each with its own length and format
   rules. Never post identical text to five networks.
5. **Publish.** Official integrations only: GitHub (content API), YouTube (Data
   API v3, quota-limited), Telegram Bot API, WhatsApp Business Cloud API
   (template messages, opt-in required), Instagram Graph API (business account).
6. **Record.** Write the published URL, channel, timestamp and approver to an
   `engineverse_content_log` table. Growth numbers are read from the platform's
   own analytics, not invented.

Do not: cross-post to groups you do not own, DM strangers, use unofficial
scrapers, or automate follows and likes. Those get accounts banned and are not
"growth".

## D. Student onboarding

```
Webhook (Header Auth) → Code (email shape, explicit consent, token)
  → IF opted in → Postgres INSERT … ON CONFLICT (email) DO NOTHING RETURNING id
      → IF a row came back → welcome email → Respond 200
      → else → Respond 200 "already subscribed"
  → else → Respond 422
```

Requirements the template implements:

- **Consent is a field, not an assumption.** `payload.consent === true` or no
  email is sent.
- **Idempotence.** The unique index plus `ON CONFLICT DO NOTHING` is what makes a
  second submission harmless. Do not replace it with a select-then-insert.
- **Withdrawal.** Every message carries an unsubscribe link with a random token,
  not the address. Set `revoked_at` when it is used, and exclude revoked rows
  from every send. A marketing email without a working unsubscribe is unlawful
  in most jurisdictions and, more simply, a bad way to treat students.

EngineVerse itself has no newsletter form. The workflow is the mechanism; you
decide whether to put a form on `/support` or keep sign-ups to GitHub Releases.

## E. Growth analytics — design only

Measure only what you can actually observe, and label everything else as an
estimate.

**Available from the application without new tracking:**

| Metric | Source | Notes |
|---|---|---|
| Questions asked, answered, failed, latency | `audit_logs` action `assistant.asked` / `assistant.answered` | `meta` has the outcome, character count and latency; no question text |
| Feedback trend | `audit_logs` action `assistant.feedback` | Boolean + fixed category |
| Registrations | `users` table, by `created_at` | Counts accounts, not people |
| Content engagement | `activity`, `submissions`, `user_flashcards` | Per-account, only with a lawful basis and a privacy notice |
| Uptime | `/health` polled by `06-uptime-check.json` | Polling is not a user measurement |

**Not available, and therefore not claimed:** unique visitors, referral sources,
campaign performance, retention cohorts for anonymous readers. The application
loads no analytics script by design (`docs/SECURITY.md`). If you add one, it must
be disclosed on `/privacy`, must not receive chat text, and should be
cookie-light. GitHub Pages provides no server-side visitor data.

A dashboard should be built only against a real source. A page of invented
"active users" numbers is worse than no dashboard.

## F. Operational monitoring

- `05-monitoring.json` runs on n8n's **Error Trigger**. It redacts URLs and
  query-string secrets, then emails the administrator the workflow name,
  execution id, last node, timestamp and a truncated message. It never includes
  a student question or answer.
- `06-uptime-check.json` polls `GET /health` every 15 minutes and emails on a
  non-200. `GET /health` is public in both sign-in modes and returns no private
  rows when `ENGINEVERSE_ENV=production`.
- Neither workflow retries. A retry storm against a down service is noise, and
  n8n already records the failed execution.
- Set a **budget alert** in your model provider and an **execution limit** in
  n8n. The bridge limits one address to 60 questions/hour; it cannot cap your
  total spend.

## Manual steps that remain

| # | Action | Why it cannot be done here |
|---|---|---|
| 1 | Create the Header Auth credential in n8n | Needs your n8n login |
| 2 | Set `ENGINEVERSE_ASSISTANT_URL` / `_TOKEN` on the server | Needs your host's secret store |
| 3 | Attach the model credential | Needs your provider account |
| 4 | Activate workflows and run `scripts/check_assistant.py` | Needs a reachable instance |
| 5 | Decide on channels and approval ownership for workflow C | Editorial decision |
| 6 | Choose an analytics source (or stay script-free) | Privacy decision |
| 7 | Confirm n8n execution limits and model budget | Cost decision |
