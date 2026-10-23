# The study assistant (Meridian × n8n)

The assistant is an AI chat panel on Meridian, backed by an n8n workflow. This
document describes what was built, what it will and will not do, how to configure
it, and the manual steps that only the repository owner can perform.

It is deliberately **not** described as "connected" anywhere in the product until
a request has actually been answered. The code and the UI both have an honest
"not configured" state, and that is the state the repository ships in.

---

## 1. What exists in the application

| Surface | File | What it does |
|---|---|---|
| Floating launcher on every page | `backend/templates/_assistant.html`, `backend/static/js/assistant.js` | Opens a dialog panel with the conversation. Hidden entirely when the assistant is not configured, so no dead bubble appears. |
| Full page | `backend/templates/assistant.html`, route `GET /assistant` | Same component at page scale, plus capabilities, limits, privacy and a "how this works" section. |
| Navigation entry | `backend/engineverse/navigation.py` → *Study assistant* under **Learn** | Appears in the top bar, mobile menu, footer, breadcrumb trail, `/search` and the sitemap automatically, because those are all generated from that table. |
| Server-side client | `backend/engineverse/assistant.py` | Validates the question, calls the Chat Trigger, parses the answer, maps failures to safe messages, derives the session id. |
| JSON API | `backend/web/api.py` → `POST /api/assistant/chat`, `GET /api/assistant/status` | Proxy, rate limits and audit metadata. |
| Configuration | `backend/engineverse/config.py` | `ENGINEVERSE_ASSISTANT_*` variables, validated at startup in production. |
| Widget checks | `scripts/check_assistant.js` | 29 behaviour checks under jsdom against the exported site. |
| Server checks | `backend/tests/test_assistant.py` | 45 checks: validation, transport, failure states, CSRF, limits, privacy, export. |
| Local stand-in | `scripts/mock_n8n.py` | Speaks the Chat Trigger contract so the widget can be exercised without credentials. It is not a model. |
| End-to-end probe | `scripts/verify_assistant.py` | Sends exactly one real message and prints the result. |

### Two transports, chosen by the server

```
Self-hosted Meridian (proxy mode)

  browser ──POST /api/assistant/chat──▶ FastAPI ──POST──▶ n8n Chat Trigger ──▶ model
     ▲                                   │                  │
     └──────────── answer ───────────────┘                  └─ per-session memory

GitHub Pages (direct mode, only if ENGINEVERSE_ASSISTANT_PUBLIC_URL is set)

  browser ──POST (CORS)──────────────────────────────────▶ n8n Chat Trigger ──▶ model
                                                              │
                                              Allowed Origins must list the Pages site
```

**Proxy mode** is the default and the safer one. The n8n webhook URL never reaches
the browser, the Content-Security-Policy can stay `connect-src 'self'`, and the
server can enforce per-IP and per-session limits before spending an execution.

**Direct mode** exists only because GitHub Pages cannot run Python. The browser
calls n8n itself, so the workflow's *Allowed Origins* and its own budget are the
only controls. It is opt-in, and the page says which mode it is in.

### What is never sent to the browser

- The webhook URL in proxy mode (asserted by a test: `CHAT_URL not in html`).
- Any API key, n8n credential, execution id or upstream error body.
- The student's question or the assistant's answer in the audit log. Only
  `question_chars`, `answer_chars`, `latency_ms` and an outcome are recorded.

### Session continuity

n8n's Chat Trigger keeps context per `sessionId`. Meridian computes it as
`HMAC-SHA256(instance secret, "assistant:" + subject + ":" + UTC date)`, truncated
to 32 hex characters. The subject is the signed-in user id or the anonymous
browser's CSRF subject.

Consequences, stated plainly:

- The id is stable for one UTC day, so a conversation continues across pages and
  reloads.
- Another browser cannot derive it from a username.
- Server memory is the workflow's, not Meridian's. Enabling it requires the
  agent variant of the workflow (`n8n/workflows/01b-student-copilot-agent.json`).
- In direct mode the browser generates its own random id per tab session.

---

## 2. Configuration

Set these on the host that runs FastAPI:

```bash
# Required to enable the assistant. The "Chat URL" from the n8n Chat Trigger.
ENGINEVERSE_ASSISTANT_URL=https://your-n8n.example/webhook/engineverse/chat

# Optional, with their defaults:
ENGINEVERSE_ASSISTANT_ENABLED=true          # kill switch
ENGINEVERSE_ASSISTANT_TIMEOUT_MS=25000      # 2s–120s
ENGINEVERSE_ASSISTANT_SESSION_LIMIT=20      # questions per browser session per hour
```

For the static GitHub Pages copy, set the repository **variable**
`ENGINEVERSE_ASSISTANT_PUBLIC_URL` to the same Chat URL. It is a variable, not a
secret: the value is published in the page by design. Leaving it unset keeps the
launcher off and the page honest.

Validation happens in `Settings.production_problems()`:

- must be `https://` (plain `http://` only for `localhost`/`127.0.0.1`);
- no embedded username/password;
- must be a webhook path, not the n8n root (a root URL is almost always a
  mistake, and it redirects to a sign-in page);
- timeout between 2 s and 120 s; session limit between 1 and 500.

An invalid value is reported at startup in production and treated as
"unconfigured" in development, so a typo never silently routes questions to an
unexpected host.

---

## 3. Behaviour a student sees

- **Launcher**: a labelled button (`Ask AI`) that reports `aria-expanded`, opens
  a dialog, focuses the textarea and closes on `Escape`, returning focus to the
  button. It never auto-opens, never covers the mobile bottom navigation, and is
  removed from the DOM when unconfigured.
- **Page-aware prompts**: three suggestions chosen from the page the student is
  on — debugging prompts on `/codelab` and problem pages, revision prompts on
  practice pages, planning prompts on `/planner`, project prompts on `/projects`.
- **Loading**: the Send button is disabled and says "Sending…", the input becomes
  read-only, prompt chips are disabled, and `aria-busy` is set. A repeated click
  or a double submit cannot send twice.
- **Errors**: a `role="alert"` message with a specific sentence for timeout, 429,
  5xx, empty answer, offline and unconfigured. Nothing internal leaks.
- **Retry**: "Try again" re-sends the last question once, without duplicating it in
  the transcript.
- **Offline**: detected before a request is made, with an explanation and a retry.
- **Reduced motion**: the panel's short reveal is disabled under
  `prefers-reduced-motion`.
- **Screen readers**: the transcript is a `role="log"` with `aria-live="polite"`;
  messages are labelled "You" and "Assistant"; output is text, never a rendering
  of raw HTML.
- **Formatting**: a small markdown subset — fenced code, `inline code`, **bold**,
  `-` bullets — is rendered from escaped text. Links are *not* turned into
  anchors: an AI-generated URL is not a source we can vouch for.
- **Disclosure**: every surface says "AI-generated · may be wrong" and "not a
  person", and the page lists what the assistant cannot do.

---

## 4. Abuse and cost controls

| Layer | Where | Limit |
|---|---|---|
| Per-IP burst | `main.RateLimitMiddleware`, `ai` bucket | 30 requests/hour, shared through the database |
| Per-session | `web/api.py` | `ENGINEVERSE_ASSISTANT_SESSION_LIMIT` (default 20/hour) |
| Question size | `assistant.sanitise_question` | 2–800 characters, control characters removed |
| Upstream timeout | `assistant.ask` | 25 s by default, plus a short connect timeout |
| n8n side | `01-student-copilot.json` → *Guard question* | 20 questions/hour per session, stored in workflow static data |
| Provider side | Your n8n/OpenAI settings | Set a spend cap; see §7 |

Direct mode loses the first two layers. If that matters for your traffic, use the
self-hosted site instead of the Pages copy, or keep the Pages copy without the
assistant.

---

## 5. Privacy

- Meridian stores **no transcript** and no per-message row. The audit log gets
  a metadata entry (`assistant.asked` / `assistant.failed` / `assistant.limited`)
  with character counts, outcome and latency.
- The question and answer travel to your n8n instance and then to the model
  provider you selected in the workflow. That provider's retention terms apply
  and are outside Meridian's control — the assistant page says so.
- The page asks students not to paste passwords, API keys, identity numbers or
  information about other people.
- Workflow settings default to `saveDataSuccessExecution: none`, so successful
  executions do not store the conversation in n8n. Failures are saved
  (`saveDataErrorExecution: all`) so an operator can debug them; tighten this if
  your policy requires it.
- Meridian's own privacy notice is at `/privacy`. The assistant adds a
  disclosure beside the chat and a "How this works" section on `/assistant`.

---

## 6. Verifying it (in order)

```bash
# 1. Unit, transport (against the local mock) and API checks
python -m pytest backend/tests/test_assistant.py -q

# 2. The widget, against the exported site
python scripts/export_pages.py --out site --reading-copy
node scripts/check_assistant.js site

# 3. The real webhook, once, after configuration
python scripts/verify_assistant.py            # or --url ... --dry-run first
```

`verify_assistant.py` exits 0 only if the assistant returned text. It sends one
message and does not retry.

Then in a browser: sign in (or use an instance with `ENGINEVERSE_SIGNIN=optional`),
open `/assistant`, ask a question, and check the answer and its sources of truth.
On the Pages copy, check the launcher's `Ready (direct)` state and the browser
console for CORS errors.

---

## 7. What is *not* done, and why

These are stated rather than implied:

1. **The owner's n8n workspace was not modified.** Its `/assistant` URL is the
   n8n editor route: it redirects to `/signin`, so it is a private workflow view,
   not a public chat endpoint. It cannot be embedded, and no public Chat Trigger
   URL exists until the workflow is made public in *Embedded Chat* mode (see
   `docs/N8N_AUTOMATION.md` §2).
2. **No message has been sent to that workspace.** This environment can reach
   GitHub and package registries only, not `*.n8n.cloud`. The transport is
   verified against a local server implementing the documented contract
   (`scripts/mock_n8n.py`); the claim "a real answer arrived from n8n Cloud" is
   therefore *unverified* until `scripts/verify_assistant.py` is run with a real
   URL.
3. **No production deployment was performed.** GitHub Pages rebuilds on push;
   whether it published is checked by `scripts/verify_pages.py` in CI, not here.
4. **No model is bundled.** Choosing a model, its cost and its data-handling
   terms is the operator's decision, made in n8n.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "The study assistant is not configured on this server." | `ENGINEVERSE_ASSISTANT_URL` empty or invalid | Set it; restart the process; check `GET /api/assistant/status` |
| Launcher missing on the Pages copy | `ENGINEVERSE_ASSISTANT_PUBLIC_URL` not set, or the last build predates it | Set the repository variable and re-run *GitHub Pages* |
| Browser console: CORS error (direct mode) | Pages origin not in the workflow's *Allowed Origins* | Add `https://sauravprivatelimited369-byte.github.io` to the Chat Trigger options |
| 503 with `reason: refused` | Workflow inactive, wrong path, or Chat Trigger not public | Activate it; copy the *Chat URL* again; set *Make Chat Publicly Available* |
| 504 timeouts | Model slow, or n8n queue saturated | Raise `ENGINEVERSE_ASSISTANT_TIMEOUT_MS`, or reduce `max_tokens` |
| 429 in the panel | Per-session or per-IP budget exhausted | Wait, or raise `ENGINEVERSE_ASSISTANT_SESSION_LIMIT` |
| Assistant answers in the wrong language | Workflow prompt | Edit the system message in the workflow (it is a Code/Agent field) |
