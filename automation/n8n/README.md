# n8n templates

Importable workflow JSON for the automation described in
[docs/N8N_AUTOMATION.md](../../docs/N8N_AUTOMATION.md). They are **inactive on
import** and contain **no credentials and no webhook URLs**. Every node that
needs an account says so in its note.

| File | What it does | What you must supply |
|---|---|---|
| `01-student-copilot.json` | Webhook → validate → AI Agent (+ window memory) → Respond. This is the contract `backend/engineverse/assistant.py` calls. | A chat-model credential; a Header Auth credential named to match `ENGINEVERSE_ASSISTANT_AUTH_HEADER` |
| `02-feedback-intake.json` | Webhook → validate/consent → Postgres insert → Respond | A Postgres credential for the database in `feedback.sql` |
| `03-student-onboarding.json` | Webhook → consent check → idempotent insert → welcome email with unsubscribe link | Postgres + SMTP credentials; set the `engineverse_url` variable |
| `05-monitoring.json` | Error Trigger → redact → email the administrator | SMTP credential; the admin address |
| `06-uptime-check.json` | Every 15 min → GET `/health` → email on a non-200 | SMTP credential; the `engineverse_url` variable |

## Import

1. In n8n: **Workflows → Add workflow → Import from File**.
2. Open each node flagged with a note and attach the credential it names.
3. Set the workflow variable `engineverse_url` (n8n: **Variables**) to the
   public EngineVerse origin, with no trailing slash, e.g.
   `https://engineverse.example.org`.
4. Run **Test workflow** with a real request before activating.
5. Activate only the workflows you have budgeted for. Every AI call is a paid
   model call on your account.

## Database

`feedback.sql` creates two tables and one reporting view. Run it with an owner
role against the automation database, not with the EngineVerse runtime role:

```bash
psql "$AUTOMATION_DB_URL" -v ON_ERROR_STOP=1 -f automation/n8n/feedback.sql
```

The unique index on `engineverse_subscribers.email` is what makes repeated
subscriptions a no-op instead of a second welcome email.

## Boundaries

- These templates do not scrape private accounts, bypass platform limits or send
  unsolicited bulk messages. Onboarding only emails addresses that submitted
  explicit consent, and every message carries an unsubscribe link.
- `02-feedback-intake.json` stores a rating, a fixed category, an optional
  contact address **only when consent was given**, and an optional message. It
  never receives the assistant's answer text.
- `05-monitoring.json` redacts URLs and query-string secrets before emailing.
- The JSON is checked for structure by `backend/tests/test_n8n_automation.py`.
  That test cannot prove a specific n8n version imports it cleanly; the first
  manual import is the real test.
