# Security

This document separates implemented controls from deployment assumptions. The
security code lives mainly in `backend/engineverse/security/`, `backend/main.py`,
and the route handlers. Tests exercise these controls, but a green suite is not
a penetration test, a production deployment, or proof that a remote judge is safe.

## Reporting a vulnerability

Please report security problems privately. When the repository's
[private vulnerability reporting](https://github.com/sauravprivatelimited369-byte/Engine_Verse/security/advisories/new)
form is available, use it. It is a repository setting the maintainer must turn
on (Settings > Code security > Private vulnerability reporting). If it is not on
yet, open an issue that only asks for a private contact, with no technical
details and no real learner data.

Include the affected page or file, steps to reproduce and the impact you
expect. This is a volunteer project, so there is no bounty and no guaranteed
response time, but reports are taken seriously and fixes are credited in the
changelog if you wish.

## Threat model

The assets are learner identities, sessions, progress, submissions, private notes,
and staff controls. The threat model includes credential theft and long-password
DoS, session/factor replay, CSRF and stolen cookies, SQL/XSS/SSTI injection,
regex/request resource exhaustion, arbitrary code execution, privilege
escalation, secret disclosure, spam and enumeration. File-upload exposure is
currently reduced because there is no user file-upload endpoint; adding one
requires a separate storage, scanning, size-limit and access-control design.

## Passwords

`security/passwords.py`.

- **scrypt**, `N=16384, r=8, p=1`, 64-byte key, 16-byte random salt. The
  work factor is configurable only by code; stored parameters are validated
  against hard resource ceilings before verification.
- Stored as `scrypt$16384$8$1$<saltB64>$<hashB64>` (130 characters). The
  parameters travel with the hash, so the cost can be raised later without
  invalidating existing credentials. `needs_rehash()` reports any hash that is
  not current, and the login path transparently upgrades it.
- **NFKC normalisation** before hashing, so a password typed with combining
  characters verifies identically to the precomposed form. Without this, two
  visually identical passwords would be two different credentials.
- Constant-time comparison via `hmac.compare_digest`.
- Length capped at 256 characters, which bounds the scrypt input and prevents a
  CPU-exhaustion request.
- Password fields are capped at 256 characters before authentication or hashing;
  the KDF verifier independently rejects longer values. Policy is length-first:
  minimum 10 characters, a character-mix check only below 16 characters, a
  local exact-match common-password blocklist, repeated-character detection,
  and rejection of passwords containing account identity text. The blocklist is
  a modest local list, not a breach-password service.

## Sessions

`security/sessions.py`.

- The cookie holds `<ulid>.<random token>`. **Only an HMAC-SHA-256 digest
  under `ENGINEVERSE_SECRET` is stored**, so a database disclosure does not yield
  usable sessions and rotating the root secret invalidates existing cookies.
  The first release that switches legacy unkeyed session hashes to HMAC also
  signs existing sessions out once.
- Cookie `ev_session`: `HttpOnly`, `SameSite=Lax`, `Secure` when the deployment
  is HTTPS, `Path=/`, `Max-Age` from configuration.
- Every request touches `last_seen_at`; `prune_sessions()` removes expired rows.
- `revoke_session()` and `revoke_all_sessions()` support logout and
  "sign out everywhere", and changing a password revokes every other session.
- No session id appears in a URL, which removes the fixation and
  referrer-leakage vectors.

## Password reset

`auth.issue_password_reset()` / `auth.consume_password_reset()`, backed by the
`password_resets` table.

- The token is 32 bytes from `secrets.token_urlsafe`. **Only its SHA-256 is
  stored**, so reading the table does not yield a working link.
- The token is matched by **exact hash equality**, never by pattern.
- Tokens expire after 30 minutes and are single use; consuming one marks it used
  in the same step that returns the user id, so it cannot be replayed.
- Issuing a token deletes any outstanding one for that user, so there is never a
  choice of live links and an older emailed link stops working.
- A weak new password costs the user their token rather than being retryable, so
  the form cannot be used as a password-strength oracle.
- The normal response is the same for known and unknown addresses. With a mail
  transport configured, the address lookup, token creation and SMTP delivery
  all run after the generic response body is sent, keeping account-dependent
  database work and relay latency out of the response-time path. Requests are
  limited to 5 per hour per source IP and 3 per hour per normalized address,
  including across application workers. The shared address bucket is a keyed
  digest, not the email itself.

### Why this is a table and not an audit row

Reset tokens were originally written into `audit_logs` and recovered with
`meta LIKE '%"<token>"%'`. Because the submitted token was interpolated straight
into the `LIKE` pattern, posting a single `%` matched the most recent row and
reset that account's password - a complete account takeover requiring no
credential and no access to anyone's email. The fix is not escaping the pattern;
a token is a secret and must be looked up by equality, so it now has a table of
its own with a hashed primary key. The old code also deleted from `audit_logs`,
which contradicts that table being append-only.

### Where the link goes

The link is delivered by `engineverse/notify.py` over the standard library's
`smtplib` — no third-party mail service. Configure it with `ENGINEVERSE_SMTP_URL`
and `ENGINEVERSE_MAIL_FROM`. Sending runs after the generic response body is
sent; a failed delivery consumes the unused token and records only the failure
class, never the address or reset URL.

With no relay configured, the default public route does not create a live
reset token or look up the submitted address. It returns the same generic
message for every address: if an account exists and this site can send email, a
link will be sent; otherwise contact the administrator. This avoids both the
old token-in-response takeover and the earlier “reset unavailable” message that
revealed whether a submitted address belonged to an account.

`ENGINEVERSE_REVEAL_RESET_TOKEN=1` is available only in development/test when no
mail transport is configured. Staging and production ignore it. A configured
but unreachable relay never triggers a reveal fallback; a form that starts
revealing tokens during an SMTP outage would be a takeover endpoint that switches
itself on at exactly
the wrong moment.

## CSRF

`security/csrf.py`.

- The token is `nonce.HMAC-SHA256(secret, "<subject>:<nonce>")`. Authenticated
  requests bind the subject to the session id. Anonymous pages use a random
  per-browser HttpOnly, SameSite=Strict cookie (`__Host-ev_csrf` over HTTPS,
  `ev_csrf` for local HTTP) as the subject, so a token copied from an attacker's
  own browser cannot be replayed in a victim's browser. EngineVersery requires
  `ENGINEVERSE_SECRET`; cross-browser replay also requires the victim's cookie.
- Every mutation requires a valid token, including login, registration, and
  reset flows. Tokens are accepted from the `x-csrf-token` header (JavaScript)
  or the `csrf_token` form field (server-rendered forms, which cannot set a
  header). The cookie is not exposed to JavaScript; pages carry the separate
  HMAC token.
- When the body must be read in middleware, `request.body()` is awaited before
  `request.form()`. Under Starlette's `BaseHTTPMiddleware` the request is a
  `_CachedRequest`, and caching the body is what lets the downstream handler read
  it again.

## Factor replay, practice attempts, and browser clipboard

Replay protection is applied to authentication factors and tokens, where a
replayed proof must not create another authenticated action:

- A TOTP seal stores the last accepted time-step; older or same-step codes are
  refused. The update uses compare-and-set so concurrent requests cannot both
  consume one factor. Recovery-code hashes are removed on use.
- Login and enrollment challenges are short-lived, stored as hashes, and
  consumed once. Password-reset tokens are also hashed, expire, and are single
  use. Rotating `ENGINEVERSE_SECRET` invalidates session-bound proofs and makes
  existing TOTP seals unreadable.
- **Practice answers are intentionally not one-time tokens.** A valid answer
  records a new attempt every time - history, mistake notebook and mastery all
  see every attempt, and attempts must not be deduplicated.
  `/api/practice/answer` is rate-limited to 120 attempts per minute per client IP
  and validates question/set membership and answer shape. **XP is separate
  from attempt recording and is knowledge-based** (owner decision, 19 October
  2026, reversing the earlier "every attempt earns 1 XP" rule this section used
  to mandate): a question pays its difficulty value on its first correct answer
  only, wrong answers and repeats pay 0, a coding problem pays on its first
  accepted solution, and a topic's view XP pays on first view. The reason is
  integrity of the competitive signal - under attempt XP, a loop of wrong
  answers or page refreshes minted leaderboard XP without any knowledge being
  demonstrated. This is an anti-farming product rule enforced server-side in
  `practice`/`coding`/`progress`; it is not a replay defense and must not be
  used to argue for deduplicating the attempts themselves.
- **Project build XP is different from practice XP.** A learner can explicitly
  log a given project build once; a partial unique index makes simultaneous
  retries idempotent. Merely viewing a project never awards XP.
- The browser client does not read from or write to the clipboard. Any future
  clipboard feature should require a direct user gesture, show the destination,
  and never poll or silently replace copied content.

## Sign-in factors

The default is password-only sign-in: a successful password check creates the
session directly. Two opt-in factors exist. An enrolled TOTP authenticator
(Settings -> Security) is per account and needs no outbound transport. Setting
`ENGINEVERSE_LOGIN_OTP=required` instead adds a delivered six-digit code to every
account's password sign-in, and production refuses to start in that mode without
a transport to deliver it.

When `ENGINEVERSE_LOGIN_OTP=required`, a successful password
match for an account without an enrolled TOTP authenticator starts a second,
short-lived six-digit challenge. The site remains publicly readable; this is a
sign-in control, not a site-wide gate. An enrolled TOTP authenticator satisfies
the same every-login verification and does not cause a delivered code to be
stacked on top of it.

- Email is the default delivery channel. A phone is offered only after it has
  been saved, verified and the operator-run `ENGINEVERSE_SMS_URL` gateway is
  configured. The settings page can switch the channel when both are available.
- The code is generated with `secrets`, expires after five minutes, is consumed
  once, and is replaced when a new code is issued. The database stores only an
  HMAC-SHA-256 of the canonical code inside a `totp.seal()` payload, keyed by
  `ENGINEVERSE_SECRET`; rotating that secret makes live codes unusable.
- Five wrong codes consume the challenge. Wrong attempts also feed the existing
  account lockout and login-attempt audit trail without putting the code in an
  audit row. Resends are limited to five issues per fifteen minutes and one
  resend per sixty seconds; a cooldown does not kill the still-live challenge.
- In a demo-enabled, non-production environment with neither transport
  configured, the code is revealed once to make a first local run usable. A
  configured-but-failing transport and every production environment fail
  closed; production never renders a code.
- `disabled` is an explicit password-only mode for an operator that has chosen
  not to require delivered codes. It must not be confused with a working
  transport: production checks the setting and refuses invalid values, and a
  required mode with neither SMTP nor SMS transport.

## Authentication and authorisation

Authentication establishes which account a request belongs to; it does not
make that account an administrator. Authorization is checked separately at the
server for each protected action. Hiding a button or serving a page is never a
substitute for the capability check. Session validity, MFA and CSRF answer
separate questions: who is signed in, whether a required factor was proven, and
whether this state-changing request came from the expected site.

`security/rbac.py` implements the authorization policy.

- 8 roles × 10 capabilities, expressed as an explicit allow-list. `can()` returns
  `False` for any role/capability pair that is not listed, and for any capability
  the module does not know about — the check **fails closed**.
- Roles: `student`, `mentor`, `moderator`, `subject_expert`, `project_reviewer`,
  `analytics_admin`, `content_admin`, `super_admin`. `student` holds no
  capabilities at all.
- `assert_can()` raises `Forbidden`, which the web layer turns into a 403.
  `/admin` is verified to return 403 for a student and 200 for a super admin.
- The seeder is tested against `rbac.ROLES`, because minting an undefined role
  silently produces an account with zero capabilities and a misleading label —
  a real defect this caught.

## Contact details: which email and which number

Sign-up used to accept `anything@gmail` and `12345` because one regex per field
counted as validation. The check is now layered, in `security/email_rules.py`
and `security/phone_rules.py`, and every layer is a separate decision:

1. **Syntax** (`parse`) — one `@`, a local part that is not empty and does not
   start or end with a dot, labels that are LDH, a TLD of letters. Address case
   is folded here, once, because lookups are.
2. **Policy** (`policy_check`) — the burner-inbox list and the near-miss table
   (`gmial.com`, `gmai.com`, …). This layer costs nothing and never touches the
   network, so it is always on, including in tests and on the exported pages.
3. **Deliverability** (`verify`) — an MX query, built with `socket` and `struct`
   rather than a DNS library, with a per-process cache. `off` / `fallback` / `mx`
   via `ENGINEVERSE_EMAIL_DELIVERABILITY`; `auto` picks `off` for test and CI and
   `fallback` elsewhere. **Fallback fails open**: a resolver that does not answer
   must not be able to lock a school out of signing up.

Phone numbers are checked against the numbering plan of the country whose dialling
code was selected — 30 codes in the table, 15 offered in the selector, all read
from the same structure by the templates and by the export. A number that matches
no plan is refused with that country's example (`India numbers look like
+91 98765 43210`), and a run of one repeated digit is refused as a placeholder.
`1234567890` is *not* refused: it is a valid, assignable shape, and ownership is
the OTP's job, not the format check's. US 555 numbers stay valid for the same
reason — they are fiction, not an invalid range.

Sign-in validates **shape only** (`validate_signin_identifier`), before the
lookup, and never reports an account as absent because of a format problem: an
unparseable identifier is answered with the rule it broke, which leaks nothing,
while "no such account" must stay vague. The exported GitHub Pages copy has no
server, so `static/js/pages-live.js` mirrors these rules; `backend/tests/
test_identity_validation.py` (see below) runs the same fixtures through both and compares
verdicts, and the exported pages are given the tables themselves inside the
`#ev-live` boot blob so the algorithm is the only thing duplicated.

## Input bounds and injection

- **Request size** — `RequestBoundsMiddleware` rejects targets over 8,192 bytes
  and bodies over 512 KiB, including chunked bodies without `Content-Length`,
  before form/JSON parsing. Oversize responses do not echo request data. Password
  fields are capped at 256 characters before KDF work; the verifier checks again.
  API handlers impose smaller limits on code, answer text, notes, search fields,
  IDs and similar inputs.
- **SQL injection** — values go through query parameters in `db.query/execute/scalar`.
  A few table names are interpolated only after selecting from fixed, local
  allowlists; request values are never treated as SQL identifiers. Foreign keys
  are enforced. The app uses SQL, not a NoSQL query engine, so there is no
  operator-object API that accepts user-provided query selectors.
- **SSTI** — template names are selected by route code, not by request/content
  values. Jinja autoescaping is on; user content is passed as data and is never
  compiled as a template.
- **Regex/CPU exhaustion** — all regular expressions are application-defined;
  learners cannot supply patterns for execution. Markdown rendering has a
  200,000-character input cap, API search and answer fields have narrower caps,
  and the whole request is bounded. These are resource bounds, not a claim that
  every future pattern is immune to ReDoS; new regexes need adversarial tests.
- **XSS** — Jinja2 runs with `autoescape=True`. Deliberate markup output is
  limited to rendered markdown, which passes through `markdown.py`'s escaping,
  and diagram SVG, which is rebuilt from an allowlist.
- **Stored SVG** — a diagram *is* markup, so `topic.html` emits `diagram.spec`
  with `| safe`. The spec is therefore run through `sanitize_svg()` where it is
  read, not in the template, so the clean version is the only one any caller can
  reach — including a future admin form. It allowlists elements and attributes
  rather than blocking known-bad ones, drops `on*` handlers and `javascript:`/
  `data:`/`vbscript:` URLs, and returns an empty string for input that is not SVG
  at all. A test asserts all six seeded diagrams survive with every element
  intact, because a sanitiser that mangles real diagrams is not a fix. CSP's
  nonce already stops an injected script; this is the layer that does not depend
  on a header being present.
- **Open redirect** — `is_safe_url()` allows only same-site paths and the
  `http`, `https` and `mailto` schemes. It explicitly rejects **protocol-relative
  URLs** (`//evil.com`, `/\evil.com`), which every browser resolves against the
  current scheme and which would otherwise turn any `next` parameter into an
  off-site redirect.
- **CSP** — a per-request nonce is generated for every response and the policy is
  `default-src 'self'` plus that nonce. A reused nonce would defeat the policy,
  so a test asserts two consecutive responses differ.
- **Error and information leakage** — request-validation errors are normalized
  instead of returning framework internals. Unexpected API errors return a
  generic 500 body; the server-rendered error page is generic as well. The
  corresponding audit event records a route label and exception type, not the
  exception message, submitted body, query string or traceback. Operators still
  need protected process logs and monitoring for diagnosis; never enable a
  debug traceback page on a public deployment. Sitemap canonical links use the
  configured `ENGINEVERSE_SITE_URL`, not the untrusted request `Host` header.

## Transport and headers

`SecurityHeadersMiddleware` sets, on every response:

| Header | Value |
|---|---|
| `Content-Security-Policy` | `default-src 'self'` + per-request nonce |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | camera, microphone and geolocation disabled |
| `Cross-Origin-Opener-Policy` / `Cross-Origin-Resource-Policy` | `same-origin` |
| `Strict-Transport-Security` | sent when the request arrives over HTTPS |
| `Cache-Control` | Signed-in pages are `private, no-store`; anonymous HTML is `private, max-age=0` because it carries a browser-bound CSRF token |

### Offline caching and shared devices

The service worker keeps a copy of fetched pages so the app works offline. Its
`cacheable()` check refuses non-GET requests, other origins, `/api/`, `/settings`
and `/admin` — but that is a denylist, and most pages render the viewer's own
data: `/today`, `/profile`, `/notifications`, `/mistakes`, `/streaks`. Cached on
a library machine or a sibling's phone, those would have been waiting for the
next person to open the app offline.

So `render()` marks signed-in pages `private, no-store`. Anonymous pages are
also `private` to HTTP caches because they contain a browser-bound CSRF token;
they carry `X-Offline-Cache: anonymous` so the service worker may keep only
those generic pages in that browser's local offline cache. The worker refuses
`no-store` responses and any `private` response without that explicit marker.
The decision comes from the response rather than a path denylist, so a new
personalised route cannot silently expose a user's dashboard offline.

### Public hosting, Android and off-site learner data

Pages is a static reading copy until a full HTTPS application origin is
configured. It cannot be the authority for accounts or progress; never put
learner rows, database dumps, `.env` files or signing keys in this public
repository or Pages artifact. On a live instance, PostgreSQL holds account data
and cookies stay on that instance's origin.

The reading copy has **no accounts**. Earlier versions offered a browser-side
"account" with a fast password digest, an on-page six-digit code and an optional
push of progress snapshots to a public learner registry
(`data/learners/registry.json`) via a GitHub token kept in the browser. That
design put learner data in a public repository (see
[the issue #39 incident](INCIDENT_ISSUE_39_REDACTION.md)) and could not protect a
password, so it was removed rather than patched:

- `backend/static/js/pages-live.js` keeps one device-local profile
  (`ev:local-profile:v1`): display name, branch, progress, bookmarks and the
  mistake notebook. It holds no password, email, phone or token, and nothing is
  uploaded. On load it migrates progress out of the old store and deletes the
  old keys, the IndexedDB mirror and any stored GitHub token.
- Imported JSON is validated field by field (`sanitizeProfile`); unknown keys
  are dropped and lengths are capped.
- The registry file, `github_storage.py`, the sync script, the sync workflow and
  the `/api/sync/*` routes are deleted. Tests in
  `backend/tests/test_audit_2026_10_19.py` keep them deleted.
- Pages that only make sense with an account (sign-in, OTP, password reset)
  are not exported; personal pages carry `noindex`.

The native Android app (`android/`) stores its own progress and planner in
app-private storage. Only that small preferences file is included in the user's
own Android backup and device transfer; WebView cookies, storage and cache are
not. Its web
viewer loads only this site's HTTPS pages, adds no JavaScript bridge and refuses
mixed content; see [android/README.md](../android/README.md). Release signing
keys are supplied to CI as repository secrets and never committed. The optional
TWA builder (`android/build-twa.cjs`) is for self-hosters with their own
origin, where the certificate must match Digital Asset Links.

An operator may opt in to `deploy/github-backups.yml`: it streams a Postgres
dump through `age` before writing a temporary **ciphertext** archive and
uploads it only to a *separate private* GitHub repository after checking
visibility. The token has access to that repo alone; the private recovery key
is kept offline. This does not make GitHub the live database or make hosting
safe by itself. Keep backups under a retention policy and rehearse restoring;
previous backups can still contain rows after a live account deletion. Review
[Backups](BACKUPS.md) before enabling this service. A leaked age identity,
GitHub token or Postgres credential requires incident response.

## Rate limiting and lockout

- `RateLimitMiddleware` keys abuse limits by the resolved client IP: 10 login
  posts per 5 minutes, 5 registrations/hour, 5 reset-link requests/hour/IP plus
  3 reset-link requests/hour per keyed address, 10 reset-token checks per
  5 minutes, 5 feedback submissions/hour, 120 answer
  attempts/min for `/api/practice/answer`, 30 run/submit requests/min for the
  coding judge, 30 tutor requests/hour, and 300 requests/min for other `/api`
  routes. Password changes, MFA setup/confirmation/removal, confirmation-email
  sends, and community posting, replying, reporting and voting also have
  per-account limits. IP budgets check an in-process sliding window and a
  database-backed window anchored at the first hit, not a wall-clock boundary;
  the stricter applies. A missing rate table reuses the
  already-counted local result, avoiding a double count; other database errors
  are not silently ignored. Rejections return 429 with `Retry-After`.
- `register_login_attempt()` records every credential check in `login_attempts`
  with the identifier, IP, outcome and reason. `auth_blocked()` consults it to
  lock an account after repeated failures, which is the defence against
  credential stuffing that a per-IP limit alone cannot provide.
- The failed-attempt counter and `locked_until` live on `users`, so lockout
  survives a process restart.

## The judge

Learner code is untrusted input that must execute. It never runs in the web
process.

- A child process with a scrubbed environment — a test asserts
  `os.environ.get('ENGINEVERSE_SECRET')` is `None` inside a submission.
- Resource ceilings applied with `setrlimit` **in the child**, not with `ulimit`
  in the generated script: process count, address space, CPU seconds, file size,
  open files and core dumps. A test reads each limit back from inside a
  submission and asserts it is bounded.
- A wall-clock deadline. The submission runs in its own session, so on timeout
  the **whole process group** is killed, not just the direct child. A test
  asserts a fork bomb is contained and leaves no processes behind.
- The local provider requires working network, PID and mount namespaces.
  Startup probes the network namespace, a PID namespace with a private procfs,
  and an actual tmpfs mount, not just the presence of `unshare`. Private procfs
  prevents code from enumerating host PIDs and reading same-UID application
  process environments. An empty tmpfs is mounted over the checkout and account
  home (when present); mount failure aborts the run. Tests exercise these
  boundaries, including a synthetic host-process environment canary. If any
  namespace is unavailable, the provider reports unavailable and does not
  execute learner code; it never downgrades to rlimits alone.
- Privileges are dropped to `nobody` where the parent is allowed to do so.
- `PR_SET_NO_NEW_PRIVS` is set in the child before `exec`, so no setuid/setgid
  binary or file capability a submission can reach may raise its privileges.
  A test reads `NoNewPrivs` back from `/proc/self/status` inside a submission.
- Outbound network is blocked: a test opens a socket to `1.1.1.1:80` and asserts
  it does not connect.
- Output is truncated, so a submission cannot exhaust memory by printing.
- The Java path runs in a **second** JVM (see `sandbox-java/README.md`) so a
  `System.exit`, a thread that never stops, or an exhausted heap cannot reach the
  sandbox itself.

### Why the limits are set in Python

They were originally `ulimit` lines inside the generated shell script. `/bin/sh`
is dash on Debian-family images, and dash implements neither `ulimit -u` nor
`ulimit -t`. Both lines failed with `Illegal option`, the `2>/dev/null || true`
suffix swallowed the error, and every submission ran with an unbounded
`RLIMIT_NPROC` and `RLIMIT_CPU` of `0`. A submitted fork bomb then exhausted the
host and the application server was killed alongside it. `setrlimit` cannot fail
silently in the same way, and the tests read the limits back from inside the
sandbox rather than trusting that they were set.

### What the built-in provider does not contain

The mount namespace hides the checkout and the network namespace removes
outbound access. A private PID namespace hides host process entries from procfs.
This is still process isolation, not full OS containment:

- Everything outside the mounted-over checkout and home directory may remain
  visible to a submission. `/etc/passwd`, the interpreter and the standard
  library are readable, as they must be for the code to run. This is not a
  general-purpose hostile multi-tenant boundary.
- Privilege dropping to `nobody` only happens when the parent is privileged
  enough to do it. Running the application as an unprivileged user means the
  drop is unavailable; namespace, tmpfs and rlimit controls still apply, but
  this is another reason to use a separately operated judge for production.
- The network, PID and mount namespaces depend on unprivileged user namespaces
  and mount permissions being enabled. That is why support is **probed at
  startup** rather than assumed; `provider_info()` reports the result, so an
  operator can see what the host actually provides.

### The container in `deploy/` is not a boundary either

An earlier revision of this document said the hardening lived in
`deploy/docker-compose.yml`, which ran a separate `sandbox` container with
`network_mode: none`, `cap_drop: [ALL]` and a read-only root filesystem. That was
wrong, and the service has been removed. The judge bridge invokes the sandbox
with `subprocess.run`, which cannot cross a container boundary, and the service
had no network and no published port, so nothing could reach it by any other
route either. Its `ENTRYPOINT` reads one JSON request from stdin, so with no
stdin attached it exited immediately and `restart: unless-stopped` looped it.

In production Compose, `ENGINEVERSE_JUDGE=disabled`, so learner code is not
executed. If an operator selects a local mode for development, the subprocess
runs inside the web container, where the toolchains have to be for that bridge
to work - which is why `deploy/Dockerfile.web` installs them only when built
with `--build-arg INSTALL_JUDGE_TOOLCHAINS=1`. The default (production) image
contains no compilers and no JDK: a process that refuses to run learner code
should not ship the machinery to run it. Containment includes the list above — rlimits, tmpfs mounts over the
checkout and home, network and PID namespaces with private procfs, a scrubbed
environment, a private process group, and an unprivileged UID when the parent
can drop privileges — plus the container's `read_only` root, `cap_drop: [ALL]`
and `no-new-privileges`.

Those controls are real and the judge tests verify them when the host supports
the required namespaces. They are not separation from the web container or a
full OS sandbox. A separately operated judge needs a socket protocol and its
own filesystem; `deploy/Dockerfile.sandbox` can build an image, but nothing in
this repository currently talks to it. Treat local execution as development-only.

### PHP2Shell and the runtime allowlist

On 21 October 2026 the PHP project shipped emergency fixes for PHP2Shell
(CVE-2026-109618 and CVE-2026-109619, CVSS 9.2): two flaws in the PHP core
giving an unauthenticated remote attacker code execution on any PHP install
that serves web requests (PHP-FPM, mod_php, php-cgi, FrankenPHP, LiteSpeed).
Fixed versions are 8.5.12, 8.4.27, 8.3.36 and 8.2.35, and exploitation was
reported in the wild within days.

**EngineVerse was not vulnerable, and is not.** The site is Python (FastAPI)
end to end; the repository contains no `.php` file, no PHP interpreter is
installed by any image or script, and no PHP SAPI has ever served a request
here. A test (`test_php2shell_hardening.py`) asserts the tree stays that way.

The audit PHP2Shell triggered still found four things to fix, because this
site's equivalent of "a runtime that executes other people's input" is the
judge:

1. **PHP was executable through a side door.** The Judge0 language map
   included PHP (and Kotlin), neither of which is in the runnable catalogue.
   No editor offered them, but `POST /api/run` passed the caller's language
   string straight through, so any signed-in learner could have PHP executed
   on the Judge0 host. Both mappings are deleted. Executable languages are
   now governed by one allowlist - `judge.KNOWN_LANGUAGES` - enforced at
   the judge facade (`run_custom`/`evaluate` refuse anything outside it
   before a provider is asked), again inside the Judge0 provider, and by
   `scripts/verify_hosted_app.py`, which now fails a deployment that reports
   PHP as runnable. Teaching *about* PHP or Kotlin in lesson text is
   unaffected; only executing them is governed. Operators running a stock
   Judge0 should still patch or rebuild that host (Judge0 images bundle a
   PHP CLI) - EngineVerse simply no longer sends it PHP.
2. **The Java bridge leaked the server's environment.** It copied
   `os.environ` and removed three variable names, handing the sandbox JVM -
   which compiles submissions in-process - the Judge0 key, the AI key, the
   SMTP URL (often containing a password) and any deployment token. The
   bridge now builds the child's environment from nothing (PATH, HOME,
   locale, and the sandbox-policy switch), and it turns the JVM security
   policy on itself instead of relying on an operator remembering to. The
   learner's own JVM already received a cleared environment from the
   sandbox; that part was correct and is unchanged.
3. **An end-of-life runtime was kept alive as a "fallback".**
   `scripts/setup_toolchains.py` provisioned .NET Core 3.1 (end-of-life
   December 2022) and vendored OpenSSL 1.1 libraries (end-of-life September
   2023) so it could keep executing learner C#. That is precisely the
   PHP2Shell failure mode - an unpatchable runtime executing untrusted
   input. The download, the vendored libraries and the `netcoreapp3.1`
   targeting are deleted. C# runs on the Roslyn-on-WASM bundle, or on a
   system .NET SDK 8+; an older SDK is refused by the judge and reported as
   missing by the installer. The rule going forward: **only a runtime that
   still receives security fixes may execute learner code.**
4. **Compilers shipped in the production image by default.** They are now
   behind `--build-arg INSTALL_JUDGE_TOOLCHAINS=1` (see above).

Two related notes, because they are the questions PHP2Shell usually prompts:

- **Adding more server-side languages would not have helped.** Security did
  not come from the site being written in Python rather than PHP; it came
  from the vulnerable runtime not being present. Every additional runtime
  that executes input is another emergency-patch obligation like this one.
  Ruby is already supported the safe way - CRuby compiled to WebAssembly,
  running inside the same sandbox/browser boundaries as everything else -
  and further languages will be added only behind the same allowlist and
  isolation, never as new in-process interpreters.
- **Patching speed is the control.** `.github/dependabot.yml` now opens
  weekly update PRs for every ecosystem in the repo (pip, GitHub Actions,
  Compose/container images, Maven, npm). The one surface Dependabot cannot
  see is the host judge toolchains pinned in `scripts/setup_toolchains.py`;
  review those pins on the same cadence, and rebuild `deploy/` images
  regularly so the floating base tags pick up distribution fixes.

### Browser execution on the static copy

The GitHub Pages copy has no server judge. Two languages execute there, in
the learner's own browser, and the boundary is drawn accordingly:

- **JavaScript runs in a dedicated Web Worker** (Blob-created), not in the
  page. An earlier revision used `new Function` in the page origin, where
  submitted code could read the vault profile from localStorage or rewrite
  the DOM, and an infinite loop froze the tab. The worker has no DOM and no
  handle on page state; the main thread only exchanges arguments/results by
  message and calls `terminate()` past the time budget. This is isolation
  *from the page*, not a boundary against the machine's owner - the code is
  the learner's own, equivalent to running it in devtools.
- **Python runs on real CPython (Pyodide/WebAssembly)** in a worker, loaded
  from same-origin files the Pages workflow pins and fetches
  (`scripts/fetch_pyodide.py`); no third-party CDN is contacted at runtime,
  and if the files are missing Python reports NOT RUN rather than falling
  back to an approximation. Problem judging appends the exact driver source
  the server judge appends, exported per problem.
- TypeScript, SQL and the compiled languages execute on the static copy
  inside dedicated Web Workers running their real toolchains compiled to
  WebAssembly (Clang, OpenJDK/TeaVM, rustc/Miri, Roslyn, the TypeScript
  compiler, SQLite, GopherJS), vendored pinned and same-origin by
  `scripts/fetch_browser_runtimes.py` — no third-party CDN is contacted at
  runtime. Worker code has no DOM and no handle on page state; the main
  thread exchanges only program text/stdin and results by message and
  terminates a worker past its time budget, so a runaway program costs a
  respawn, not the tab. If a language's runtime files are missing from a
  deployment it reports NOT RUN rather than falling back to an
  approximation. The hosted judge above remains the execution path
  whenever a server is present.

The hosted `/compiler` terminal executes through the same judge providers
and isolation as judged submissions (`POST /api/coding/run` with no problem
attached); it adds no new execution surface, only a new caller.

## Audit

`audit_logs` is append-only and records the action, actor, entity, IP and a JSON
detail blob. Security-relevant events — rejected CSRF, failed logins, role
changes, application errors — are written there. It is the largest table on the
platform, so in Postgres it is hash-partitioned 256 ways.

## Secrets

`ENGINEVERSE_SECRET` is the root of trust: it keys the session-token HMAC,
CSRF HMAC, signed flash cookie and authenticator seal. It is read from the
process environment, never from a request or database, and is omitted from the
local judge child's explicit environment. Store it in the deployment platform's
secret facility where available; `.env` is git-ignored and `.env.example` has no
real value. Rotating it invalidates session cookies and makes existing
authenticator seals unreadable; affected MFA accounts need an administrator to
clear the seal before they can sign in and enrol again. The first release that
adopts keyed session hashes also invalidates pre-existing legacy session hashes.

## Production startup

`ENGINEVERSE_ENV=production` refuses to serve until the secret, the Postgres
URL, the HTTPS origin and the judge mode are acceptable. The web process does
not migrate and does not seed. `scripts/release.py` does, with the bootstrap
role. The web role is `engineverse_app`: DML, no `CREATE`. Demo passwords are
not created and are not shown on the login page.

The local judge is unchanged for development. Production will not select it.
`judge0` is a URL you operate. This process does not verify that host. See
`docs/DEPLOYMENT.md`.

## Authenticator

Enrolment is optional for a learner and required, in production, before a staff
account can `POST` to `/admin`. `GET /admin` still works, so an operator can
read the page and then enrol under Settings. The check runs after CSRF, so a
forged admin post is rejected rather than turned into a settings change.

The factor is TOTP (SHA-1, 30 seconds, 6 digits) plus eight one-time recovery
codes. The secret is sealed with `ENGINEVERSE_SECRET` before it is stored.
That is application-level encryption, not a hardware module: anyone who can
read both the database and the secret can open it. Rotating the secret makes
existing seals unreadable. `scripts/create_admin.py --replace` clears the super
administrator's seal and says so, without printing it. Other accounts need an
administrator to clear `users.totp_secret`. No QR code is fetched from a remote
host. The settings page shows the secret and an `otpauth://` URI.

A matching password does not create a session when a factor is enrolled. The
second step is a short-lived signed token plus a code. A failed code increments
`failed_login_count`. A recovery code is removed from the seal when it is used.

## Client address

The address used for limits and the audit log is the TCP peer.
`X-Forwarded-For` is ignored unless `ENGINEVERSE_TRUST_PROXY` is on, and even
then only when that peer is loopback or private. A public peer that sends the
header is still the client. The compose file does not set the flag: its
published port is `127.0.0.1` and it does not run a proxy. Leave the flag off
unless the only path to the process is a proxy that overwrites the header.

## Honest limitations

- **A second factor is not universal.** Learners can sign in with a password
  alone until they enrol. Do not describe a deployment as MFA-protected unless
  the accounts that matter have actually enrolled.
- **The password blocklist is a modest local exact-match list** of common
  passwords. It catches exact matches such as `password` and `123456`; it is not
  a breach-password service and does not reject a long passphrase merely because
  it contains a common word.
- **Shared API limits count what reaches this database.** They do not fix a
  proxy that hides every learner behind one address. Login lockout was already
  stored in `login_attempts` and still is.
- **A well-formed fake address cannot be refused offline.** `someone@gmail.com`
  is indistinguishable from `someoneelse@gmail.com` without sending mail, and a
  static page cannot send any. The exported copy therefore checks syntax,
  near-miss domains and burner lists, and nothing more; the MX layer exists only
  on the hosted app, and only at sign-up. The 6-digit code is the one thing that
  actually proves the learner can read that inbox — on the exported pages it is
  shown in the page instead, which proves only that someone can read the screen.
- **Email confirmation needs a mail transport.** When `ENGINEVERSE_SMTP_URL`
  is set, Settings can email a one-time link. The link is stored as a hash and
  is not rendered into the page. With no transport, the address stays
  unconfirmed and sign-in still works. That is not proof the person controls
  the address.
- **The Java sandbox cannot be built in this workspace** — no JDK is installed
  here, and none can be fetched. It is not unverified, though:
  `.github/workflows/java.yml` compiles it, runs its unit tests, and smoke-tests
  the built jar on JDK 21 and JDK 25 on every change to `sandbox-java/`.
- **The Java sandbox's policy file does nothing on JDK 24 or later.** JEP 486
  permanently disabled the Security Manager, so `-Djava.security.policy` is
  inert and the file is never read. The policy is opt-in
  (`ENGINEVERSE_SANDBOX_POLICY=1`) and off by default, and `Runner` now prints a
  warning and omits the flags rather than implying the control is active. What
  actually contains a submission is the separate child JVM, the heap and stack
  ceilings and the hard deadline — those hold on every JDK. Consequence: on a
  modern JDK a Java submission is not blocked from opening a socket, so the
  network egress control must come from the container or host, not from the
  sandbox. Whether the JVM warns or errors on `-Djava.security.manager=allow`
  under JDK 25 is unverified here (no JVM to run), which is exactly why the
  flags are no longer passed at all.
