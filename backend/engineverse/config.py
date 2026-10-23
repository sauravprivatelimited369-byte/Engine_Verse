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
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Hosts that may be reached over plain HTTP. Everything else in production
#: must be HTTPS: the assistant receives a student's question, and a plaintext
#: hop would expose it to anyone on the path.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

#: A chat webhook URL must not carry a username or password. Credentials in a
#: URL end up in proxy logs and browser history, and n8n's Chat Trigger needs
#: none: the workflow is identified by its own path.
_BAD_URL_CHARS = re.compile(r"[\s<>\"'\\]")


def normalise_assistant_url(value: str | None, *, allow_local_http: bool = False) -> str:
    """Validate an n8n Chat Trigger webhook URL, or return an empty string.

    The assistant is the one place where this application talks to a service it
    does not host, so the URL is treated as configuration that can be wrong:
    a typo must fail at startup, not silently send questions to a stranger's
    host. Raises ``ValueError`` with a message naming the variable; never
    echoes the rejected value, which may contain a token.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if _BAD_URL_CHARS.search(raw):
        raise ValueError(
            "ENGINEVERSE_ASSISTANT_URL contains whitespace, quotes or backslashes"
        )
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("ENGINEVERSE_ASSISTANT_URL must start with https:// (or http:// on localhost)")
    if not parts.hostname:
        raise ValueError("ENGINEVERSE_ASSISTANT_URL is missing a host name")
    if parts.username or parts.password:
        raise ValueError(
            "ENGINEVERSE_ASSISTANT_URL must not carry credentials; put them in the n8n workflow instead"
        )
    if parts.fragment:
        raise ValueError("ENGINEVERSE_ASSISTANT_URL must not contain a # fragment")
    if parts.scheme == "http" and not (allow_local_http and parts.hostname in LOCAL_HOSTS):
        raise ValueError(
            "ENGINEVERSE_ASSISTANT_URL must use https://; plain HTTP is only allowed for localhost"
        )
    # A bare origin is almost always a mistake: the n8n editor lives there,
    # not a chat webhook. Ask for the webhook path so the failure is visible
    # at configuration time rather than as a redirect to a sign-in page.
    if parts.path in {"", "/"}:
        raise ValueError(
            "ENGINEVERSE_ASSISTANT_URL must be the Chat Trigger webhook URL "
            "(for example https://your-n8n.example/webhook/engineverse/chat), not the n8n home page"
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


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
        "ENGINEVERSE_MAIL_FROM", "Meridian <no-reply@localhost>"))
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
    def assistant_webhook(self) -> str:
        """The validated server-side Chat Trigger URL, or ``""``.

        Invalid configuration yields an empty string rather than an exception:
        the page then reports the assistant as unavailable, which is true, and
        the reason is named by :meth:`production_problems` at startup.
        """
        try:
            return normalise_assistant_url(self.assistant_url, allow_local_http=not self.is_production)
        except ValueError:
            return ""

    @property
    def assistant_public_webhook(self) -> str:
        """The validated URL published to the static Pages copy, or ``""``."""
        try:
            return normalise_assistant_url(self.assistant_public_url, allow_local_http=False)
        except ValueError:
            return ""

    @property
    def assistant_mode(self) -> str:
        """``proxy`` on the server, ``off`` when unconfigured or switched off.

        The static export chooses ``direct`` separately (see export_pages.py);
        a Python process never asks the browser to reach n8n directly, so the
        Content-Security-Policy can stay ``connect-src 'self'``.
        """
        if not self.assistant_enabled:
            return "off"
        return "proxy" if self.assistant_webhook else "off"

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
    ai_key: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_AI_KEY", ""))
    ai_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_AI_URL", ""))

    # --- ElevenLabs voice reader and voice tutor --------------------------
    # Off by default: this is the only feature in the application that sends
    # educational text to a third-party service, and it costs money per
    # character. With the flag unset the written site is completely unchanged,
    # no request is made, and the reader reports "not configured".
    elevenlabs_enabled: bool = field(
        default_factory=lambda: _bool("ENGINEVERSE_ELEVENLABS_ENABLED", False)
    )
    # Server-side only. Never sent to a browser, never logged.
    elevenlabs_api_key: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", "").strip()
    )
    # Approved voices. Comma-separate to offer more than one; labels are
    # optional and only used for the picker.
    elevenlabs_voice_id_en: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_TTS_VOICE_ID_EN", "").strip()
    )
    elevenlabs_voice_id_hi: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_TTS_VOICE_ID_HI", "").strip()
    )
    elevenlabs_voice_name_en: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_TTS_VOICE_NAME_EN", "").strip()
    )
    elevenlabs_voice_name_hi: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_TTS_VOICE_NAME_HI", "").strip()
    )
    elevenlabs_tts_model_id: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_TTS_MODEL_ID", "eleven_multilingual_v2").strip()
    )
    # Conversational AI agent. Empty means the voice tutor explains that no
    # agent is configured instead of pretending a session exists.
    elevenlabs_agent_id: str = field(
        default_factory=lambda: os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    )
    #: Longest text accepted for one synthesis request (characters).
    voice_max_chars: int = field(
        default_factory=lambda: _int("ENGINEVERSE_VOICE_MAX_CHARS", 1200)
    )
    #: Upstream read/write timeout in seconds. A stuck ElevenLabs request must
    #: not pin a worker forever.
    voice_timeout_seconds: int = field(
        default_factory=lambda: _int("ENGINEVERSE_VOICE_TIMEOUT_SECONDS", 30)
    )
    #: Browser origins allowed to call the public voice API. The static GitHub
    #: Pages copy is a different origin from the FastAPI app, so exactly the
    #: deployment origins are listed - never "*".
    voice_origins: str = field(
        default_factory=lambda: os.environ.get("ENGINEVERSE_VOICE_ORIGINS", "").strip()
    )

    @property
    def allowed_voice_origins(self) -> list[str]:
        """The CORS allow list: configured origins plus this site's own.

        An empty list means the application refuses cross-origin voice calls
        entirely; the same-origin live app still works because a same-origin
        request sends no Origin header at all.
        """
        from urllib.parse import urlsplit

        candidates: list[str] = []
        for raw in (self.voice_origins or "").replace(" ", "").split(","):
            if not raw:
                continue
            try:
                parts = urlsplit(raw if "//" in raw else f"https://{raw}")
            except ValueError:
                continue
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                continue
            if parts.scheme == "http" and self.is_production:
                continue  # a plain-http origin cannot be trusted to hold the UI
            candidates.append(f"{parts.scheme}://{parts.netloc}")
        if self.site_url:
            parts = urlsplit(self.site_url)
            if parts.scheme and parts.netloc:
                candidates.append(f"{parts.scheme}://{parts.netloc}")
        # The public reading copy is a separate origin from the FastAPI app and
        # is where most students will use the reader. Its exact Pages origin is
        # allowed by default; it can still be removed by pointing
        # ENGINEVERSE_VOICE_ORIGINS at a different deployment (this list only
        # ever adds the origin, so a self-hosted copy also works unchanged).
        try:
            from engineverse.project import pages_origin

            candidates.append(pages_origin())
        except ValueError:
            pass
        # Keep order, drop duplicates.
        return list(dict.fromkeys(candidates))
    # --- n8n study assistant ---------------------------------------------
    # Two URLs, deliberately separate:
    #
    # * ``assistant_url`` is the Chat Trigger webhook the *server* calls. It
    #   never reaches the browser, so a self-hosted instance can keep it on a
    #   private network or behind an origin only this host may use.
    # * ``assistant_public_url`` is the same webhook, published on purpose for
    #   the static GitHub Pages copy, where no server exists to proxy. It is
    #   safe to publish in the sense that it is not a secret - n8n's Chat
    #   Trigger is a public endpoint by design - but it must be restricted to
    #   the production origins in the workflow itself (Allowed Origins), and
    #   the workflow must carry its own rate limits and spend guard.
    #
    # Empty means "not configured": the UI then says so instead of showing a
    # chat box that cannot answer.
    assistant_url: str = field(default_factory=lambda: os.environ.get("ENGINEVERSE_ASSISTANT_URL", "").strip())
    assistant_public_url: str = field(
        default_factory=lambda: os.environ.get("ENGINEVERSE_ASSISTANT_PUBLIC_URL", "").strip()
    )
    #: Kill switch. An operator who hits an n8n execution cap or a cost surprise
    #: turns this off and the site keeps working; only the assistant stops.
    assistant_enabled: bool = field(default_factory=lambda: _bool("ENGINEVERSE_ASSISTANT_ENABLED", True))
    #: Long enough for a slow model behind a queue, short enough that a student
    #: is not left watching a spinner. The browser adds its own margin.
    assistant_timeout_ms: int = field(default_factory=lambda: _int("ENGINEVERSE_ASSISTANT_TIMEOUT_MS", 25000))
    #: Questions allowed per browser session per hour, in addition to the
    #: per-IP limiter in main.RateLimitMiddleware. A shared campus NAT still
    #: gets a fair per-student budget.
    assistant_session_limit: int = field(default_factory=lambda: _int("ENGINEVERSE_ASSISTANT_SESSION_LIMIT", 20))

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
        try:
            normalise_assistant_url(self.assistant_url, allow_local_http=False)
        except ValueError as exc:
            problems.append(str(exc))
        try:
            normalise_assistant_url(self.assistant_public_url, allow_local_http=False)
        except ValueError as exc:
            problems.append(str(exc).replace("ENGINEVERSE_ASSISTANT_URL", "ENGINEVERSE_ASSISTANT_PUBLIC_URL"))
        if self.assistant_timeout_ms < 2000 or self.assistant_timeout_ms > 120_000:
            problems.append(
                "ENGINEVERSE_ASSISTANT_TIMEOUT_MS must be between 2000 and 120000"
            )
        if self.assistant_session_limit < 1 or self.assistant_session_limit > 500:
            problems.append("ENGINEVERSE_ASSISTANT_SESSION_LIMIT must be between 1 and 500")

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
