"""EngineVerse OTP delivery service — real email/SMS one-time codes.

Why this exists
---------------
The public site (``authorsauravkushwaha.github.io/EngineVerse``) is a *static*
GitHub Pages copy. A browser page cannot send email or SMS: doing so needs a
mail/SMS account credential, and any credential shipped to the browser is
public. This small service is the missing server half. The static page calls
it, it generates a 6-digit code, **sends it to the user's own email inbox or
phone**, and stores only an HMAC hash of the code. The code is never returned
in an HTTP response.

It uses only the Python standard library (the same choice as the main
backend's ``engineverse/notify.py``), so it runs anywhere Python 3.11+ runs:
your own machine or server (see gitbash_setup_run.sh), or next to the main app.

Endpoints
---------
``GET  /health``     -> {"ok": true, "email": bool, "sms": bool}
``POST /otp/send``   {"purpose","channel":"email"|"phone","destination"}
                     -> {"ok": true, "masked", "expires_in"}   (code is SENT,
                        never returned)
``POST /otp/verify`` {"purpose","destination","code"}
                     -> {"ok": true} / 401 {"ok": false, "error": ...}

Configuration (environment variables — never commit real values)
----------------------------------------------------------------
OTP_SECRET            HMAC key for hashing codes (required, 32+ chars).
SMTP_URL              e.g. Gmail: smtps://you%40gmail.com:APP_PASSWORD@smtp.gmail.com:465/
                      (use a Gmail *App Password*, not your account password)
MAIL_FROM             e.g. "EngineVerse <you@gmail.com>"
TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM   (+1... sender number)
MSG91_AUTH_KEY / MSG91_TEMPLATE_ID                     (India SMS, DLT template)
SMS_WEBHOOK_URL / SMS_WEBHOOK_TOKEN   generic gateway: POST {"to","body"}
OTP_ALLOWED_ORIGINS   comma-separated browser origins allowed to call this
                      service, e.g. https://authorsauravkushwaha.github.io
OTP_DB                SQLite path (default ./otp.sqlite3)
PORT                  listen port (default 8000)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env sitting next to this file (created by gitbash_setup_run.sh).

    Real environment variables win. The file is git-ignored and chmod 600 by
    the setup script: credentials live only on the operator's own machine.
    """
    for candidate in (Path(__file__).with_name(".env"), Path.cwd() / ".env"):
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        break


_load_dotenv()

TTL_SECONDS = 600
RESEND_COOLDOWN = 30
MAX_ATTEMPTS = 5
MAX_SENDS_PER_DESTINATION_HOUR = 5
MAX_SENDS_PER_IP_HOUR = 30
PURPOSES = {"signup_verify", "password_reset", "password_change", "login_verify"}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


# --------------------------------------------------------------------------
# Configuration / storage
# --------------------------------------------------------------------------

def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _db() -> sqlite3.Connection:
    db_path = env("OTP_DB", "./otp.sqlite3")
    conn = sqlite3.connect(db_path)
    try:  # codes (hashed) and destinations stay readable only by the owner
        os.chmod(db_path, 0o600)
    except OSError:
        pass
    conn.execute(
        "CREATE TABLE IF NOT EXISTS challenges ("
        " purpose TEXT, destination TEXT, code_hash TEXT, expires_at REAL,"
        " attempts INTEGER, last_sent REAL, PRIMARY KEY (purpose, destination))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sends (destination TEXT, ip TEXT, at REAL)"
    )
    return conn


def _hash(code: str, purpose: str, destination: str) -> str:
    secret = env("OTP_SECRET")
    if len(secret) < 16:
        raise RuntimeError("OTP_SECRET must be set (32+ random characters).")
    msg = f"{purpose}:{destination}:{code}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def mask(destination: str, channel: str) -> str:
    if channel == "phone":
        digits = re.sub(r"\D", "", destination)
        return "•" * max(4, len(digits) - 4) + digits[-4:]
    local, _, domain = destination.partition("@")
    shown = local[0] + "•••" + (local[-1] if len(local) > 2 else "")
    return f"{shown}@{domain}"


# --------------------------------------------------------------------------
# Transports (real delivery; each raises on failure so we fail closed)
# --------------------------------------------------------------------------

def email_configured() -> bool:
    return bool(env("SMTP_URL"))


def sms_configured() -> bool:
    return bool(
        (env("TWILIO_ACCOUNT_SID") and env("TWILIO_AUTH_TOKEN") and env("TWILIO_FROM"))
        or (env("MSG91_AUTH_KEY") and env("MSG91_TEMPLATE_ID"))
        or env("SMS_WEBHOOK_URL")
    )


def send_email(to: str, code: str, purpose: str) -> None:
    parsed = urllib.parse.urlparse(env("SMTP_URL"))
    host = parsed.hostname or "localhost"
    use_ssl = parsed.scheme == "smtps"
    port = parsed.port or (465 if use_ssl else 587)
    user = urllib.parse.unquote(parsed.username or "")
    password = urllib.parse.unquote(parsed.password or "")
    query = urllib.parse.parse_qs(parsed.query)
    starttls = query.get("starttls", ["1"])[0] not in ("0", "false", "no")

    msg = EmailMessage()
    msg["From"] = env("MAIL_FROM", "EngineVerse <no-reply@localhost>")
    msg["To"] = to
    msg["Subject"] = "Your EngineVerse verification code"
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(
        f"Your EngineVerse verification code is {code}.\n\n"
        f"It expires in {TTL_SECONDS // 60} minutes and works once. "
        "If you did not request this code, ignore this email — "
        "your account has not been changed."
    )
    context = ssl.create_default_context()
    if use_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    with client:
        if starttls and not use_ssl:
            client.starttls(context=context)
        if user:
            client.login(user, password)
        client.send_message(msg)


def _http_post(url: str, data: bytes, headers: dict, timeout: float = 15) -> int:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (operator-configured URL)
        return int(resp.status)


def send_sms(to: str, code: str, purpose: str) -> None:
    body = (
        f"Your EngineVerse verification code is {code}. "
        f"It expires in {TTL_SECONDS // 60} minutes and works once."
    )
    if env("TWILIO_ACCOUNT_SID"):
        sid, token = env("TWILIO_ACCOUNT_SID"), env("TWILIO_AUTH_TOKEN")
        data = urllib.parse.urlencode(
            {"To": to, "From": env("TWILIO_FROM"), "Body": body}
        ).encode()
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        status = _http_post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data,
            {"Authorization": f"Basic {auth}",
             "Content-Type": "application/x-www-form-urlencoded"},
        )
    elif env("MSG91_AUTH_KEY"):
        # MSG91 OTP API v5 — needs a DLT-approved template id (operator's).
        mobile = to.lstrip("+")
        url = (
            "https://control.msg91.com/api/v5/otp?"
            + urllib.parse.urlencode(
                {"template_id": env("MSG91_TEMPLATE_ID"), "mobile": mobile,
                 "authkey": env("MSG91_AUTH_KEY"), "otp": code}
            )
        )
        # MSG91 takes the code itself (it does not compose from our body).
        status = _http_post(url, b"", {})
    else:
        headers = {"Content-Type": "application/json"}
        if env("SMS_WEBHOOK_TOKEN"):
            headers["Authorization"] = f"Bearer {env('SMS_WEBHOOK_TOKEN')}"
        status = _http_post(
            env("SMS_WEBHOOK_URL"),
            json.dumps({"to": to, "body": body}).encode(),
            headers,
        )
    if status < 200 or status >= 300:
        raise RuntimeError(f"SMS provider returned HTTP {status}")


# --------------------------------------------------------------------------
# Core logic (kept transport-injectable for tests)
# --------------------------------------------------------------------------

class OtpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def send_code(purpose: str, channel: str, destination: str, ip: str,
              *, mailer=None, texter=None) -> dict:
    mailer = mailer or send_email
    texter = texter or send_sms
    if purpose not in PURPOSES:
        raise OtpError(422, "Unknown verification purpose.")
    destination = (destination or "").strip()
    if channel == "email":
        destination = destination.lower()
        if not EMAIL_RE.match(destination):
            raise OtpError(422, "Enter a valid email address.")
        if not email_configured():
            raise OtpError(503, "Email delivery is not configured on the server.")
    elif channel == "phone":
        destination = re.sub(r"[\s\-()]", "", destination)
        if not PHONE_RE.match(destination):
            raise OtpError(422, "Enter a mobile number with country code, e.g. +919876543210.")
        if not sms_configured():
            raise OtpError(503, "SMS delivery is not configured on the server.")
    else:
        raise OtpError(422, "Channel must be 'email' or 'phone'.")

    now = time.time()
    with _db() as conn:
        row = conn.execute(
            "SELECT last_sent FROM challenges WHERE purpose=? AND destination=?",
            (purpose, destination),
        ).fetchone()
        if row and now - row[0] < RESEND_COOLDOWN:
            raise OtpError(429, "Please wait a few seconds before requesting a new code.")
        sent_dest = conn.execute(
            "SELECT COUNT(*) FROM sends WHERE destination=? AND at > ?",
            (destination, now - 3600),
        ).fetchone()[0]
        sent_ip = conn.execute(
            "SELECT COUNT(*) FROM sends WHERE ip=? AND at > ?", (ip, now - 3600)
        ).fetchone()[0]
        if sent_dest >= MAX_SENDS_PER_DESTINATION_HOUR or sent_ip >= MAX_SENDS_PER_IP_HOUR:
            raise OtpError(429, "Too many codes requested. Try again later.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    # Deliver FIRST. Only a successfully sent code is stored/usable, and the
    # plaintext leaves this process only via the mail/SMS transport.
    try:
        (mailer if channel == "email" else texter)(destination, code, purpose)
    except Exception as exc:  # fail closed: no usable code, no code in response
        raise OtpError(503, "We could not deliver your code. Try again later.") from exc

    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO challenges VALUES (?,?,?,?,?,?)",
            (purpose, destination, _hash(code, purpose, destination),
             now + TTL_SECONDS, 0, now),
        )
        conn.execute("INSERT INTO sends VALUES (?,?,?)", (destination, ip, now))
        conn.execute("DELETE FROM sends WHERE at < ?", (now - 7200,))
    return {"ok": True, "masked": mask(destination, channel),
            "expires_in": TTL_SECONDS, "channel": channel}


def verify_code(purpose: str, destination: str, code: str) -> dict:
    destination = (destination or "").strip()
    if "@" in destination:
        destination = destination.lower()
    else:
        destination = re.sub(r"[\s\-()]", "", destination)
    code = re.sub(r"[\s.\-]", "", str(code or ""))
    if not re.fullmatch(r"\d{6}", code):
        raise OtpError(422, "Enter the 6-digit code.")
    now = time.time()
    # NOTE: do not raise inside `with _db()` — sqlite3 rolls the transaction
    # back on exception, which would resurrect a just-deleted challenge.
    outcome: OtpError | None = None
    attempts_left = 0
    with _db() as conn:
        row = conn.execute(
            "SELECT code_hash, expires_at, attempts FROM challenges"
            " WHERE purpose=? AND destination=?",
            (purpose, destination),
        ).fetchone()
        if not row or now > row[1]:
            outcome = OtpError(401, "That code has expired. Request a new one.")
        elif hmac.compare_digest(_hash(code, purpose, destination), row[0]):
            conn.execute(
                "DELETE FROM challenges WHERE purpose=? AND destination=?",
                (purpose, destination),
            )
            return {"ok": True}
        else:
            attempts = row[2] + 1
            attempts_left = MAX_ATTEMPTS - attempts
            if attempts >= MAX_ATTEMPTS:
                conn.execute(
                    "DELETE FROM challenges WHERE purpose=? AND destination=?",
                    (purpose, destination),
                )
                outcome = OtpError(401, "Too many incorrect attempts. Request a new code.")
            else:
                conn.execute(
                    "UPDATE challenges SET attempts=? WHERE purpose=? AND destination=?",
                    (attempts, purpose, destination),
                )
                outcome = OtpError(401, f"Incorrect code ({attempts_left} attempts left).")
    assert outcome is not None
    raise outcome


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "EngineVerseOTP/1.0"

    def log_message(self, *args):  # never log bodies/codes
        pass

    def _origin_allowed(self) -> str:
        origin = self.headers.get("Origin", "")
        allowed = [o.strip() for o in env(
            "OTP_ALLOWED_ORIGINS",
            "https://authorsauravkushwaha.github.io,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",") if o.strip()]
        if "*" in allowed:
            return origin or "*"
        return origin if origin in allowed else ""

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        origin = self._origin_allowed()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        origin = self._origin_allowed()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("/health", ""):
            self._reply(200, {"ok": True, "email": email_configured(),
                              "sms": sms_configured()})
        else:
            self._reply(404, {"ok": False, "error": "Not found."})

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 8192:
                raise OtpError(413, "Request too large.")
            data = json.loads(self.rfile.read(length) or b"{}")
            ip = self.client_address[0]
            if self.path.rstrip("/") == "/otp/send":
                self._reply(200, send_code(
                    str(data.get("purpose", "signup_verify")),
                    str(data.get("channel", "email")),
                    str(data.get("destination", "")), ip))
            elif self.path.rstrip("/") == "/otp/verify":
                self._reply(200, verify_code(
                    str(data.get("purpose", "signup_verify")),
                    str(data.get("destination", "")),
                    str(data.get("code", ""))))
            else:
                self._reply(404, {"ok": False, "error": "Not found."})
        except OtpError as exc:
            self._reply(exc.status, {"ok": False, "error": exc.message})
        except Exception:  # noqa: BLE001 — never leak internals/codes
            self._reply(500, {"ok": False, "error": "Server error."})


def main() -> None:
    if len(env("OTP_SECRET")) < 16:
        raise SystemExit("Set OTP_SECRET (32+ random chars) before starting.")
    port = int(env("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
