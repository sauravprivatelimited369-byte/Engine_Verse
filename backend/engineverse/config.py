"""Runtime configuration.

Every knob is an environment variable so the same image runs on a laptop and
in production. Nothing here reaches out to a third-party service.
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A conservative HTTP header-name test, used for the assistant credential header.
_AUTH_HEADER_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,62}")


def _load_dotenv() -> None:
    """Minimal .env loader - avoids a dependency for something this small."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

#: The value ``effective_secret()`` invents when nothing is configured. It is
#: fine for a laptop. It must never be accepted as a production signing key.
DEV_SECRET = "engineverse-development-secret-not-for-production"
MIN_SECRET_LENGTH = 32

#: Judges that execute learner code inside this process's machine. Production
#: refuses them. ``disabled`` runs nothing. ``judge0`` delegates to a URL the
#: operator deployed separately; this process does not verify that host.
LOCAL_JUDGES = frozenset({"", "auto", "python", "java", "local"})

#: The login role the web process uses. It must not own the schema. The
#: official Postgres image makes the first user a superuser, so that user is
#: the migration role and this one is created beside it.
RUNTIME_DB_ROLE = "engineverse_app"

# Older deploy files used these names. They are copied into the names the
# application actually reads, and only when the canonical variable is unset,
# so an explicit ENGINEVERSE_* value always wins.
_ENV_ALIASES = {
    "ENGINEVERSE_SITE_URL": ("SITE_URL",),
    "ENGINEVERSE_JUDGE": ("JUDGE",),
    "ENGINEVERSE_JAVA_SANDBOX_JAR": ("JAVA_SANDBOX_JAR",),
}


def _apply_env_aliases() -> None:
    for canonical, aliases in _ENV_ALIASES.items():
        if os.environ.get(canonical, "").strip():
            continue
        for alias in aliases:
            value = os.environ.get(alias, "").strip()
            if value:
                os.environ[canonical] = value
                break


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    """Parses an integer environment variable, naming it when invalid.

    A bare ``int(os.environ[...])`` turns a typo such as
    ``ENGINEVERSE_JUDGE_TIMEOUT_MS=5s`` into an anonymous ValueError
    traceback at import time. Failing loudly is right - silently falling
    back would run with limits the operator did not choose - but the
    failure has to say which variable to fix.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise RuntimeError(
            f"{name} must be an integer (got a non-integer value). "
            f"Fix it or leave it unset to use the default of {default}."
        ) from None


@dataclass(frozen=True)
class Settings:
    # --- identity ---------------------------------------------------------
    site_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_SITE_URL", "http://localhost:8000").rstrip("/"))
    secret: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_SECRET", ""))
    env: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_ENV", "development"))

    # --- database ---------------------------------------------------------
    db_path: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_DB_PATH", "./data/engineverse.sqlite"))
    db_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_DB_URL", ""))

    # --- sessions ---------------------------------------------------------
    session_max_age_days: int = field(default_factory=lambda: _int("ENGINEVERSE_SESSION_DAYS", 30))
    session_idle_days: int = field(default_factory=lambda: _int("ENGINEVERSE_SESSION_IDLE_DAYS", 7))
    #: Lifetime of a sign-in where "keep me signed in" was left unticked. Short
    #: on purpose: a borrowed lab machine should not stay signed in for a month.
    session_short_hours: int = field(default_factory=lambda: _int("ENGINEVERSE_SESSION_SHORT_HOURS", 12))
    cookie_secure: bool = field(default_factory=lambda: _bool("ENGINEVERSE_COOKIE_SECURE", False))
    #: Trust X-Forwarded-For only from a private or loopback peer. Default off.
    trust_proxy: bool = field(default_factory=lambda: _bool("ENGINEVERSE_TRUST_PROXY", False))

    # --- code execution ---------------------------------------------------
    judge: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_JUDGE", "auto").lower())
    judge_timeout_ms: int = field(default_factory=lambda: _int("ENGINEVERSE_JUDGE_TIMEOUT_MS", 5000))
    judge_memory_kb: int = field(default_factory=lambda: _int("ENGINEVERSE_JUDGE_MEMORY_KB", 524288))
    judge0_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_JUDGE0_URL", ""))
    judge0_key: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_JUDGE0_KEY", ""))
    java_home: str = field(default_factory=lambda: os.environ.get("JAVA_HOME", ""))
    java_sandbox_jar: str = field(
        default_factory=lambda: os.environ.get(
            "ENGINEVERSE_JAVA_SANDBOX_JAR", "./sandbox-java/target/engineverse-sandbox.jar"
        )
    )

    # --- outbound mail and optional sign-in codes -------------------------
    # ``disabled`` is the default: sign-in is password-only, and an account
    # that wants a second factor enrols an authenticator under /settings (which
    # needs no outbound transport at all).
    #
    # ``required`` adds a delivered six-digit code to every password sign-in.
    # It is opt-in because it can only work on an instance that has a working
    # SMTP or SMS transport: an operator who copied the example .env without
    # configuring mail would otherwise lock every learner out of their own
    # account, and the production checks below exist to refuse exactly that.
    login_otp: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_LOGIN_OTP", "disabled").strip().lower())
    # This is an operator-run HTTP gateway, not a hosted SMS provider. Its
    # request contract lives in engineverse.notify.send_sms.
    sms_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_SMS_URL", "").strip())
    # Empty smtp_url means this instance has no mail transport. That is the
    # default, and it matters: without it a password reset link has nowhere to
    # go, so it must not be handed to the caller instead. See engineverse.notify.
    smtp_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_SMTP_URL", ""))
    mail_from: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_MAIL_FROM", "EngineVerse <no-reply@localhost>"))
    #: Shows the reset token in the page instead of emailing it. Development
    #: only, and refused outright when env is production. Default off: turning
    #: it on makes POST /forgot-password an account-takeover endpoint.
    reveal_reset_token: bool = field(default_factory=lambda: _bool("ENGINEVERSE_REVEAL_RESET_TOKEN", False))

    # --- identity checks ---------------------------------------------------
    # How hard sign-up interrogates the *domain* of a new address, before an
    # account that cannot be mailed exists. See email_rules.probe for the modes.
    #
    # ``auto`` (the default) probes with a bounded DNS lookup everywhere except
    # the test suite, and refuses only a domain that has neither an MX nor an A
    # record - the shape of a typed-in invention. An address is never refused
    # because this process could not reach port 53.
    email_deliverability: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_EMAIL_DELIVERABILITY", "auto").strip().lower())

    @property
    def email_deliverability_mode(self) -> str:
        """``off``, ``fallback`` or ``mx`` - the mode the code actually uses."""
        raw = self.email_deliverability or "auto"
        if raw == "auto":
            # The suite seeds @example.com accounts and runs on machines with no
            # outbound DNS, where a live probe would fail on the network instead
            # of on the code under test. Reserved domains are skipped anyway.
            return "off" if self.env.strip().lower() in {"test", "ci", ""} else "fallback"
        if raw in {"off", "none", "false", "0"}:
            return "off"
        if raw in {"on", "true", "1", "fallback"}:
            return "fallback"
        return raw


    # --- who may use the site ---------------------------------------------
    # ``required`` (the default) puts every page and API route behind an
    # account: a signed-out visitor is sent to /login and comes back to the page
    # they asked for once signed in. Only the sign-in, registration and
    # password-recovery pages, the legal pages, certificate verification and
    # the static assets stay open. ``optional`` restores anonymous browsing of
    # the public catalogue; it exists for operators who want that and for the
    # test suite's anonymous-page checks.
    signin: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_SIGNIN", "optional").strip().lower())

    # Advertise a signed Android release only after the operator has published
    # it and configured its exact URL. A missing APK never masquerades as one.
    apk_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_APK_URL", ""))

    @property
    def approved_apk_url(self) -> str:
        from engineverse.distribution import normalise_apk_url

        try:
            return normalise_apk_url(self.apk_url)
        except ValueError:
            return ""

    @property
    def signin_required(self) -> bool:
        # Anything other than an explicit "optional" keeps the gate closed, so
        # a typo in the variable fails safe rather than opening the site.
        return self.signin != "optional"

    @property
    def login_otp_required(self) -> bool:
        return self.login_otp == "required"

    @property
    def signup_otp_only(self) -> bool:
        return self.login_otp in {"signup_only", "new_user"}

    @property
    def sms_configured(self) -> bool:
        return bool(self.sms_url)

    # When no SMTP/SMS transport is configured, OTP and password-reset codes
    # cannot be delivered. Setting this to true shows the code on the page
    # instead. This is less secure than email/SMS delivery, but it keeps
    # learners from being permanently locked out of their accounts on
    # self-hosted instances that have no outbound transport. Refused in
    # production unless explicitly opted in.
    recovery_show_on_page: bool = field(
        default_factory=lambda: _bool("ENGINEVERSE_SHOW_OTP_ON_PAGE", False)
    )

    # --- AI tutor ---------------------------------------------------------
    # Used by engineverse.tutor only. Empty keeps the grounded-retrieval mode.
    ai_key: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_AI_KEY", ""))
    ai_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_AI_URL", ""))

    # --- Student copilot (operator's n8n workflow) ------------------------
    # The browser never talks to n8n. It posts to /api/assistant/chat on this
    # origin, and this process forwards a bounded request to the URL below.
    # That keeps the workflow URL, its credential and its CORS settings off the
    # client, and lets the strict CSP stay connect-src 'self'.
    #
    # Empty is a supported state: the assistant page then says plainly that no
    # workflow is connected and points at the grounded in-app tutor instead.
    assistant_url: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_ASSISTANT_URL", "").strip())
    assistant_token: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_ASSISTANT_TOKEN", "").strip())
    # Header the token is sent in. n8n's Header Auth credential expects
    # whatever name was configured there; `Authorization: Bearer <token>` is
    # the other common choice. The value is sent verbatim.
    assistant_auth_header: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_ASSISTANT_AUTH_HEADER", "X-EngineVerse-Key").strip())
    assistant_timeout_s: int = field(default_factory=lambda: _int(
        "ENGINEVERSE_ASSISTANT_TIMEOUT_S", 45))
    assistant_display_name: str = field(default_factory=lambda: os.environ.get(
        "ENGINEVERSE_ASSISTANT_NAME", "EngineVerse copilot").strip()[:60])

    # --- hosting ----------------------------------------------------------
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("PORT", 8000))
    frame_preview: bool = field(default_factory=lambda: _bool("ENGINEVERSE_FRAME_PREVIEW", False))

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def sqlite_path(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    @property
    def uses_postgres(self) -> bool:
        return self.db_url.startswith(("postgresql://", "postgres://"))

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod"}

    @property
    def is_https(self) -> bool:
        return self.site_url.startswith("https://")

    def effective_secret(self) -> bytes:
        """Returns the configured secret, refusing to run unsafely in prod."""
        secret = self.secret.strip()
        if not secret:
            if self.is_production:
                raise RuntimeError(
                    "ENGINEVERSE_SECRET must be set in production. "
                    'Generate one with: python3 -c "import secrets;print(secrets.token_hex(32))"'
                )
            secret = DEV_SECRET
        return secret.encode("utf-8")

    def new_secret_hint(self) -> str:
        return secrets.token_hex(32)

    @property
    def allows_demo_accounts(self) -> bool:
        """Development and the test suite only. Never production, never staging."""
        return self.env.lower() in {"development", "test", "dev", ""}

    def production_problems(self) -> list[str]:
        """Reasons this process must not serve production traffic.

        The messages name the variable, never the secret itself. An empty list
        means the checks in this method passed. It does not mean the deployment
        has been reviewed, backed up, or isolated.
        """
        if not self.is_production:
            return []
        problems: list[str] = []
        secret = self.secret.strip()
        if not secret:
            problems.append("ENGINEVERSE_SECRET is empty")
        elif secret == DEV_SECRET:
            problems.append("ENGINEVERSE_SECRET is the development fallback")
        elif len(secret) < MIN_SECRET_LENGTH:
            problems.append(f"ENGINEVERSE_SECRET is shorter than {MIN_SECRET_LENGTH} characters")
        if not self.db_url:
            problems.append("ENGINEVERSE_DB_URL is required in production; SQLite is not a production database")
        elif not self.uses_postgres:
            problems.append("ENGINEVERSE_DB_URL must be a postgresql:// URL in production")
        from urllib.parse import urlparse

        parsed = urlparse(self.site_url)
        if parsed.scheme != "https" or not parsed.hostname:
            problems.append("ENGINEVERSE_SITE_URL must be an https:// origin in production")
        if self.reveal_reset_token:
            problems.append("ENGINEVERSE_REVEAL_RESET_TOKEN must not be set in production")
        if self.frame_preview:
            problems.append("ENGINEVERSE_FRAME_PREVIEW must not be set in production")
        if self.signin not in {"required", "optional"}:
            problems.append("ENGINEVERSE_SIGNIN must be either 'required' or 'optional'")
        from engineverse.distribution import normalise_apk_url

        try:
            normalise_apk_url(self.apk_url)
        except ValueError as exc:
            problems.append(str(exc))
        if self.email_deliverability_mode not in {"off", "fallback", "mx"}:
            problems.append(
                "ENGINEVERSE_EMAIL_DELIVERABILITY must be 'auto', 'off', 'fallback' or 'mx' "
                f"(got {self.email_deliverability!r})"
            )
        if self.login_otp not in {"required", "disabled", "signup_only", "new_user"}:
            problems.append(
                "ENGINEVERSE_LOGIN_OTP must be either 'required', 'signup_only', or 'disabled'"
            )
        elif self.login_otp in {"required", "signup_only", "new_user"} and not self.smtp_url.strip() and not self.sms_url.strip():
            problems.append(
                f"ENGINEVERSE_LOGIN_OTP={self.login_otp} needs ENGINEVERSE_SMTP_URL or "
                "ENGINEVERSE_SMS_URL for sign-in code delivery"
            )
        if self.session_max_age_days < 1 or self.session_idle_days < 1 or self.session_short_hours < 1:
            problems.append(
                "ENGINEVERSE_SESSION_DAYS, ENGINEVERSE_SESSION_IDLE_DAYS and "
                "ENGINEVERSE_SESSION_SHORT_HOURS must all be at least 1"
            )
        if self.judge_timeout_ms < 500 or self.judge_memory_kb < 65_536:
            problems.append(
                "ENGINEVERSE_JUDGE_TIMEOUT_MS must be at least 500 and "
                "ENGINEVERSE_JUDGE_MEMORY_KB at least 65536"
            )
        # The assistant is optional. When it is configured, its URL is a
        # server-side secret-bearing endpoint: plaintext would put the student's
        # question on the wire, and credentials in the URL would land in logs.
        if self.assistant_url:
            from urllib.parse import urlparse as _urlparse

            parsed_assistant = _urlparse(self.assistant_url)
            if parsed_assistant.scheme != "https":
                problems.append("ENGINEVERSE_ASSISTANT_URL must be an https:// URL in production")
            if parsed_assistant.username or parsed_assistant.password:
                problems.append(
                    "ENGINEVERSE_ASSISTANT_URL must not contain credentials; "
                    "use ENGINEVERSE_ASSISTANT_TOKEN and ENGINEVERSE_ASSISTANT_AUTH_HEADER"
                )
            if not _AUTH_HEADER_RE.fullmatch(self.assistant_auth_header or ""):
                problems.append(
                    "ENGINEVERSE_ASSISTANT_AUTH_HEADER must be a valid HTTP header name "
                    "(letters, digits and hyphens)"
                )
            if not 5 <= self.assistant_timeout_s <= 120:
                problems.append("ENGINEVERSE_ASSISTANT_TIMEOUT_S must be between 5 and 120")
        judge = (self.judge or "").lower()
        if judge in LOCAL_JUDGES:
            shown = judge or "auto"
            problems.append(
                f"ENGINEVERSE_JUDGE={shown} would run learner code on this server; "
                "production requires 'disabled' or 'judge0' with ENGINEVERSE_JUDGE0_URL"
            )
        elif judge == "judge0" and not self.judge0_url.strip():
            problems.append("ENGINEVERSE_JUDGE=judge0 requires ENGINEVERSE_JUDGE0_URL")
        elif judge not in {"disabled", "judge0"}:
            problems.append(f"ENGINEVERSE_JUDGE={judge} is not a known production mode")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _apply_env_aliases()
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
