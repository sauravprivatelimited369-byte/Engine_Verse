"""The student copilot: a server-side bridge to the operator's n8n workflow.

Why a bridge rather than the n8n chat widget
--------------------------------------------
EngineVerse's browser never contacts a third-party origin. The application's
Content-Security-Policy is ``default-src 'self'``, ``connect-src 'self'`` and
``script-src 'self' 'nonce-...'``, there is no CDN, and tests fail if a
third-party host appears in a template. Dropping ``@n8n/chat`` into a page would
mean relaxing all three, publishing the webhook URL in client source, and
opening the workflow to cross-origin calls from every site on the internet.

So the browser posts to ``/api/assistant/chat`` on this origin, and this module
forwards a bounded request to the URL in ``ENGINEVERSE_ASSISTANT_URL`` with the
credential in ``ENGINEVERSE_ASSISTANT_TOKEN``. The URL and token exist only in
this process's environment; neither is rendered, logged, or returned.

That choice is also a constraint: this module cannot verify that the operator's
workflow is reachable or correctly configured. It reports honestly what
happened on the last request instead of assuming the service is up.

What is sent
------------
The question, a per-tab session id (so the workflow can keep context), and the
page path that the student asked from. Nothing else: no account id, no email,
no IP, no learning history, no cookies. Neither the question nor the reply is
stored by this module; only a count of characters, the outcome and the latency
are recorded in the operator's audit log.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from .config import get_settings
from .security.audit import record

#: A student question is not an essay. Short enough to keep prompt cost bounded
#: and long enough for a pasted stack trace's key lines.
MAX_MESSAGE_CHARS = 1200
MIN_MESSAGE_CHARS = 2

#: Refuse to hand back an unbounded reply. n8n is not a trusted renderer: a
#: misconfigured node could return a whole document, and the browser would try
#: to paint it.
MAX_REPLY_CHARS = 12_000

#: Session ids are opaque. This shape is what the browser generates; anything
#: else is replaced rather than trusted, so a caller cannot inject a workflow
#: memory key of its choosing.
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_PAGE_RE = re.compile(r"^/[A-Za-z0-9/_.\-]{0,180}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: Reply fields, in the order n8n's Chat Trigger and common webhook workflows
#: use. ``output`` is the Chat Trigger's own field.
_REPLY_KEYS = ("output", "text", "reply", "answer", "message")

#: Aggregated feedback categories. Free text is deliberately not accepted: it
#: would be storing student writing without a reason to.
FEEDBACK_CODES = frozenset({"wrong", "unclear", "unsafe", "off_topic", "other"})

DISCLOSURE = (
    "This assistant is a software service, not a person. It is powered by an "
    "n8n AI workflow operated alongside EngineVerse, and it can be wrong. "
    "Check anything important against your notes or a textbook."
)

PRIVACY = (
    "Your question is sent through this server to the operator's AI workflow so "
    "it can answer. EngineVerse does not store the conversation, your account or "
    "your IP is not attached to it, and no analytics tool receives it. Do not "
    "paste passwords, tokens or anyone else's personal details."
)


class AssistantError(Exception):
    """A refusal or failure with a message safe to show a student.

    ``code`` is a stable machine-readable string so the browser can choose the
    right recovery control; ``message`` is written for a reader, never copied
    from an upstream body.
    """

    status = 502
    code = "assistant_unavailable"

    def __init__(self, message: str, *, retry_after: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after

    def as_dict(self) -> dict:
        body = {"ok": False, "error": self.message, "code": self.code}
        if self.retry_after:
            body["retryAfter"] = self.retry_after
        return body


class AssistantNotConfigured(AssistantError):
    status = 503
    code = "assistant_not_configured"


class AssistantRejected(AssistantError):
    status = 422
    code = "assistant_invalid_request"


class AssistantBusy(AssistantError):
    """The workflow's own rate limit answered, not this server's."""

    status = 429
    code = "assistant_upstream_busy"


class AssistantTimeout(AssistantError):
    status = 504
    code = "assistant_timeout"


class AssistantUnavailable(AssistantError):
    status = 502
    code = "assistant_unavailable"


@dataclass(frozen=True)
class Endpoint:
    """A validated view of the operator's configuration."""

    url: str
    token: str
    auth_header: str
    timeout_s: int
    display_name: str


def _parse_url(raw: str) -> tuple[str, str]:
    """Returns ``(url, problem)``. ``problem`` is an operator-facing reason."""
    if not raw:
        return "", "missing"
    parsed = urlparse(raw)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return "", "The configured assistant URL is not an http(s) URL."
    if parsed.username or parsed.password:
        return "", "The assistant URL contains credentials; use the token variable instead."
    if get_settings().is_production and parsed.scheme != "https":
        return "", "The assistant URL must use https in production."
    if len(raw) > 2048:
        return "", "The assistant URL is too long."
    return raw, ""


def endpoint() -> Endpoint | None:
    """The configured endpoint, or ``None`` when the copilot is not connected."""
    settings = get_settings()
    url, problem = _parse_url(settings.assistant_url)
    if problem or not url:
        return None
    return Endpoint(
        url=url,
        token=settings.assistant_token,
        auth_header=settings.assistant_auth_header or "X-EngineVerse-Key",
        timeout_s=max(5, min(120, int(settings.assistant_timeout_s))),
        display_name=(settings.assistant_display_name or "EngineVerse copilot")[:60],
    )


def configured() -> bool:
    return endpoint() is not None


def status() -> dict:
    """Public, secret-free state for the page and the widget.

    ``configured`` says only that this process holds a usable URL. It is not a
    claim that the workflow answers: that is what ``lastCheck`` is for, and it
    is written by an actual request.
    """
    settings = get_settings()
    configured_now = configured()
    return {
        "configured": configured_now,
        "name": settings.assistant_display_name or "EngineVerse copilot",
        "provider": "n8n workflow (operator-run)",
        "maxMessageChars": MAX_MESSAGE_CHARS,
        "minMessageChars": MIN_MESSAGE_CHARS,
        "disclosure": DISCLOSURE,
        "privacy": PRIVACY,
        "reason": "" if configured_now else (
            "No assistant workflow is connected to this instance."
            if not settings.assistant_url else "The assistant URL is misconfigured."
        ),
    }


def suggestions_for(path: str) -> list[str]:
    """Four prompts that make sense on the page the student is reading.

    Kept deterministic and short: a suggestion that does not fit the page is
    worse than no suggestion, because the answer will not either.
    """
    base = [
        "Explain a concept from my syllabus in simple language",
        "Help me debug a Python error I keep getting",
        "Make me a 7-day revision plan for one subject",
        "Which EngineVerse tool should I use for interview prep?",
    ]
    if path.startswith("/codelab") or path.startswith("/compiler"):
        return [
            "Why does my program print the wrong total? Show me how to debug it",
            "Explain the difference between a syntax error and a runtime error",
            "How do I read a Python traceback from the bottom up?",
        ]
    if path.startswith("/practice/problems") or path.startswith("/programming"):
        return [
            "Explain the approach to this problem without giving me the code",
            "What is the time complexity of a hash-map lookup, and why?",
            "How should I practise DSA if I only have 30 minutes a day?",
        ]
    if path.startswith("/flashcards") or path.startswith("/revision"):
        return [
            "Turn this topic into active-recall questions",
            "How does spaced repetition actually work?",
            "Make a one-page revision sheet structure for an engineering exam",
        ]
    if path.startswith("/planner"):
        return [
            "Help me plan a week around two exams and one assignment",
            "How do I use the 25-minute focus timer without burning out?",
            "Make a realistic study timetable for a college student",
        ]
    if path.startswith("/workflows") or path.startswith("/studio"):
        return base
    if path.startswith("/assistant"):
        return [
            "Explain pointers in C++ like I am new to programming",
            "Debug this Python error: IndexError: list index out of range",
            "Build me a 4-week plan for learning web development",
            "मुझे डेडलॉक आसान भाषा में समझाइए",
        ]
    if path.startswith("/tutor"):
        return [
            "What is the difference between this tutor and the AI assistant?",
            "Explain Bernoulli's equation and when it applies",
            "Which topics should I revise first for my exam?",
        ]
    return base


def _clean_message(message: str) -> str:
    if not isinstance(message, str):
        raise AssistantRejected("Ask a question as text.")
    text = _CONTROL_RE.sub("", message).strip()
    if len(text) < MIN_MESSAGE_CHARS:
        raise AssistantRejected("Ask a question first.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise AssistantRejected(
            f"Keep the question under {MAX_MESSAGE_CHARS} characters."
        )
    return text


def _clean_session(session_id: str) -> str:
    candidate = (session_id or "").strip()
    if _SESSION_RE.fullmatch(candidate):
        return candidate
    # Not an error: a stale or hand-edited tab gets a fresh workflow memory key
    # rather than sharing one with every other malformed caller.
    return uuid4().hex


def _clean_page(page: str) -> str:
    return page if isinstance(page, str) and _PAGE_RE.fullmatch(page) else ""


def _extract_reply(payload: object) -> str:
    """Pulls the assistant's text out of the shapes n8n workflows return.

    The Chat Trigger answers ``{"output": "..."}``. Hand-built webhooks
    commonly answer ``{"text": ...}``, ``{"reply": ...}`` or
    ``{"answer": ...}``, sometimes wrapped in ``data``. A list of content
    blocks (``[{"text": "..."}]``) is joined. Anything else is a configuration
    problem, and saying so is better than showing an empty bubble.
    """
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        parts = [_extract_reply(item) for item in payload]
        return "\n\n".join(part for part in parts if part).strip()
    if isinstance(payload, dict):
        for key in _REPLY_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("data", "json", "result"):
            if key in payload:
                found = _extract_reply(payload[key])
                if found:
                    return found
    return ""


def _truncate(reply: str) -> str:
    if len(reply) <= MAX_REPLY_CHARS:
        return reply
    return reply[:MAX_REPLY_CHARS].rsplit(" ", 1)[0] + "\n\n[Reply truncated by EngineVerse.]"


def _default_client(target: Endpoint) -> httpx.Client:
    """A short-lived client with explicit limits.

    ``follow_redirects=False`` matters: a redirect from a hijacked or
    misconfigured workflow must not be followed to another host with the
    credential header attached. ``trust_env=False`` stops an operator's
    HTTP_PROXY environment from silently rerouting learner questions.
    """
    return httpx.Client(
        timeout=httpx.Timeout(
            connect=min(10.0, float(target.timeout_s)),
            read=float(target.timeout_s),
            write=10.0,
            pool=5.0,
        ),
        follow_redirects=False,
        trust_env=False,
    )


def ask(
    message: str,
    *,
    session_id: str = "",
    page: str = "",
    client_factory=None,
) -> dict:
    """Sends one question to the configured workflow and returns its answer.

    Blocking on purpose: the caller runs this in a threadpool. Raises
    :class:`AssistantError` subclasses, whose messages are safe to show.

    ``client_factory`` exists for the test suite, which supplies an
    ``httpx.MockTransport``; production always uses :func:`_default_client`.
    """
    target = endpoint()
    if target is None:
        raise AssistantNotConfigured(
            "The AI assistant is not connected on this instance. "
            "Your notes, practice and the on-site study tutor still work."
        )
    text = _clean_message(message)
    session = _clean_session(session_id)
    context_page = _clean_page(page)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "EngineVerse-assistant/1.0",
    }
    if target.token:
        headers[target.auth_header] = target.token

    body = {
        "action": "sendMessage",
        "sessionId": session,
        "chatInput": text,
        "metadata": {"source": "engineverse", "page": context_page},
    }

    started = time.perf_counter()
    factory = client_factory or _default_client
    try:
        with factory(target) as client:
            response = client.post(target.url, json=body, headers=headers)
    except httpx.TimeoutException:
        _log("timeout", text, started)
        raise AssistantTimeout(
            "The assistant did not answer in time. Try again, or ask fewer things at once."
        ) from None
    except httpx.HTTPError:
        _log("network_error", text, started)
        raise AssistantUnavailable(
            "The assistant service could not be reached. It may be paused; "
            "your other EngineVerse tools are unaffected."
        ) from None

    latency = round((time.perf_counter() - started) * 1000)

    if response.status_code == 429:
        retry_after = _retry_after(response)
        _log("upstream_limited", text, started)
        raise AssistantBusy(
            "The assistant is receiving too many questions right now. Wait a moment and try again.",
            retry_after=retry_after,
        )
    if response.status_code in (401, 403):
        _log("upstream_auth", text, started)
        raise AssistantUnavailable(
            "The assistant refused this server's request. The operator needs to check "
            "the workflow's authentication settings."
        )
    if response.status_code == 404:
        _log("upstream_missing", text, started)
        raise AssistantUnavailable(
            "The assistant endpoint was not found. The operator needs to check the "
            "workflow's production webhook URL."
        )
    if response.status_code >= 400:
        _log(f"upstream_{response.status_code}", text, started)
        raise AssistantUnavailable(
            "The assistant returned an error. Nothing you typed was lost; try again."
        )

    try:
        payload = response.json()
    except ValueError:
        _log("upstream_not_json", text, started)
        raise AssistantUnavailable(
            "The assistant returned a response this page could not read. "
            "The operator needs to check the workflow's response format."
        ) from None

    reply = _truncate(_extract_reply(payload))
    if not reply:
        _log("upstream_empty", text, started)
        raise AssistantUnavailable(
            "The assistant returned an empty answer. Try rephrasing the question."
        )

    _log("ok", text, started, latency=latency)
    return {
        "reply": reply,
        "sessionId": session,
        "latencyMs": latency,
        "provider": "n8n workflow",
        "disclosure": DISCLOSURE,
    }


def _retry_after(response: httpx.Response) -> int:
    raw = response.headers.get("retry-after", "")
    try:
        return max(1, min(600, int(raw)))
    except (TypeError, ValueError):
        return 30


def _log(outcome: str, message: str, started: float, *, latency: int | None = None) -> None:
    """Records minimal operational metadata, never the question or the reply.

    A failed request is worth counting: the operator's monitoring needs to see
    that the workflow is down without a student's words ending up in a log
    they did not agree to.
    """
    record(
        "assistant.asked",
        meta={
            "outcome": outcome,
            "question_chars": len(message),
            "latency_ms": latency if latency is not None else round((time.perf_counter() - started) * 1000),
        },
    )


def feedback(*, helpful: bool, code: str = "") -> dict:
    """Records one aggregate helpful/not-helpful vote.

    No free text, no question, no account id. ``code`` is a fixed category so
    the operator gets a trend without storing student writing.
    """
    category = code if code in FEEDBACK_CODES else ("other" if not helpful else "")
    record("assistant.feedback", meta={"helpful": bool(helpful), "code": category})
    return {"recorded": True}
