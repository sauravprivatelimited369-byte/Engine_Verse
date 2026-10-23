# EngineVerse OTP service — self-hosted, run with Git Bash

Real email/SMS one-time codes with **no third-party OTP service**: no Render,
no Twilio/MSG91 cloud accounts, no Supabase, no analytics. The service runs on
**your own machine or your own server**, started from Git Bash with one script.

The public website (`https://authorsauravkushwaha.github.io/EngineVerse/`) is a
static GitHub Pages copy. A static page **cannot** send an OTP: sending needs a
mail credential, and anything shipped to the browser would be public for anyone
to steal. That is why the page used to *show* the code. This service is the
small server half you run yourself:

```
Browser (GitHub Pages) ──POST /otp/send──▶  this service (YOUR machine)
                       ◀─ {masked} ──────        │ your own SMTP login
Browser ──POST /otp/verify {code}──▶ checks      ▼
                                     HMAC hash   user's inbox / phone
```

## Where your users' data lives (all on your disk)

| Data | Where | Protection |
|---|---|---|
| Sender SMTP password | `services/otp/.env` | typed hidden in Git Bash, `chmod 600`, git-ignored (setup verifies this), never committed |
| Codes | `services/otp/otp.sqlite3` | only HMAC-SHA256 **hashes** — the plaintext exists only in memory and in the delivered message; DB file `chmod 600` |
| User emails/phones | same local SQLite file only | never sent to any OTP/analytics cloud; the only network call is delivering the message itself |
| Code rules | — | 6 digits from `secrets`, 10-min expiry, 5 attempts, single-use, 30 s resend cooldown, hourly caps, CORS locked to your site origin |

On any delivery failure the API fails closed (503) and **no usable code
exists** — it never falls back to returning the code in a response.

One unavoidable fact, stated plainly: delivering a code *to* a Gmail inbox or
*to* a phone necessarily travels through Google's / the carrier's network —
that is the destination you asked to reach. What this design removes is every
*extra* party: no OTP vendor stores your users' emails, numbers or codes.

## Run it — Git Bash (Windows) or any bash

Prerequisite: Python 3.11+ (`python --version` in Git Bash).

```bash
git clone https://github.com/authorsauravkushwaha/EngineVerse.git
cd EngineVerse
bash services/otp/gitbash_setup_run.sh
```

First run asks (password input is hidden):

1. **Sender email** — e.g. a Gmail address you control for the site.
2. **SMTP host/port** — defaults are Gmail (`smtp.gmail.com:465`). For Gmail,
   create an **App Password** (Google Account → Security → 2-Step Verification
   → App passwords) and type that, *not* your account password. Any SMTP server
   you own (your domain/host's mail) works the same way — it is your account
   either way, not an OTP vendor. Gmail's free ~500 mails/day covers OTP use.
3. **Site origin** — default is your Pages URL; only that origin may call the
   service from a browser.
4. **Port** — default `8010`.

It writes `services/otp/.env` (600, git-ignored — it checks), then starts the
service. Later runs skip setup and just start it:

```bash
bash services/otp/gitbash_setup_run.sh            # setup (once) + run
bash services/otp/gitbash_setup_run.sh --run-only # just run
curl http://127.0.0.1:8010/health                 # {"ok": true, "email": true, "sms": false}
```

For the public Pages site to reach it, the service must be reachable over
HTTPS from the internet on **your own infrastructure** — e.g. run it on a VPS
you control (same script over SSH) behind your own Caddy/Nginx TLS, or on a
home server with your router's port-forward + your own domain. Then set one
GitHub **repository variable** (no secrets involved — just the URL):

Repo → Settings → Secrets and variables → Actions → **Variables** →
`ENGINEVERSE_OTP_API_URL` = `https://otp.yourdomain.example` → re-run the
Pages workflow. To test first without redeploying, in the site's browser
console: `localStorage.setItem('ev:otp_api_url', 'https://otp.yourdomain.example')`
and reload.

> Running it only on your laptop works for local testing; a laptop that is off
> or behind NAT cannot serve codes to visitors. That's a hosting fact, not a
> software lock-in — the same one script is the whole deployment.

## SMS without an SMS company (optional)

Email OTP needs nothing beyond the above. SMS inherently needs *something*
that can put a message on the phone network. The vendor-free options, both
supported via `SMS_WEBHOOK_URL` (the service POSTs `{"to","body"}` to any URL
**you** control):

- **Your own Android phone as the gateway**: run an open-source SMS-gateway
  app on a spare phone with your own SIM, point `SMS_WEBHOOK_URL` at it on
  your network. The service's message goes browser→your server→your phone→SMS.
- **A USB GSM modem + Gammu** (or similar) on your server, behind a tiny local
  webhook.

Until one of those exists, choose the email channel; SMS requests honestly
answer “SMS delivery is not configured” rather than pretending. (If you later
prefer a paid carrier anyway, Twilio/MSG91 env vars remain supported in
`app.py` — your choice, not a requirement.)

## Also: the hosted (non-Pages) app

The full FastAPI app already sends real codes itself under the same rules —
set `ENGINEVERSE_SMTP_URL` and `ENGINEVERSE_LOGIN_OTP=signup_only` in its
`.env`. This standalone service exists for the static Pages site, which has
no backend of its own.

## Tests

```bash
python -m pytest services/otp -q   # transports are faked; no real mail/SMS sent
```
