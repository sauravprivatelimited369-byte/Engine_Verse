"""The n8n-backed study assistant (EngineVerse × n8n).

What this module is
-------------------
A thin, server-side client for an n8n **Chat Trigger** webhook. n8n owns the
conversation: the prompt, the model, the memory and any retrieval live in the
workflow, where the operator can change them without redeploying this site. This
module owns the parts a public website must not delegate:

* **The credential boundary.** The webhook URL stays in the server's
  environment. The browser talks to ``/api/assistant/chat`` on this origin, so
  the strict Content-Security-Policy (``connect-src 'self'``) still holds and a
  self-hosted n8n can sit on a private network.
* **Abuse control.** A question is length-bounded and control characters are
  stripped here, and the endpoint is behind the per-IP ``ai`` limiter plus a
  per-session budget (see ``web/api.py``).
* **Honest failure.** Timeouts, 4xx/5xx responses and unparseable bodies become
  a small set of messages a student can act on. Upstream errors, URLs and
  stack traces never reach the browser or the audit log.
* **A stable session.** n8n's hosted chat keeps context per ``sessionId``. The
  id is derived with HMAC from (viewer or anonymous browser subject, UTC date),
  so it is stable for a day, not guessable from another browser, and stores
  nothing itself. No transcript is written by EngineVerse.

What this module deliberately does not do
-----------------------------------------
It does not claim the assistant can run code, browse, read files or know
today's news. Those capabilities exist only if the n8n workflow implements
them, and the UI says what is actually true: answers are AI-generated and may
be wrong.

Transport note: ``httpx`` is already a dependency (the optional Judge0 bridge
uses it). No SDK, no vendor lock-in, no extra package.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
from typing import Any

import httpx

from .config import get_settings
from .security.sanitize import strip_html

__all__ = [
    "AssistantUnavailable",
    "DISCLOSURE",
    "MAX_ANSWER_CHARS",
    "MAX_QUESTION_CHARS",
    "ask",
    "client_config",
    "sanitise_question",
    "session_id_for",
    "status",
    "suggestions_for",
]

#: A question long enough to be useful, short enough that the workflow and the
#: model's context are not a denial-of-wallet vector. Enforced on the server;
#: the textarea's maxlength is a convenience, not the control.
MAX_QUESTION_CHARS = 800
MIN_QUESTION_CHARS = 2
MAX_ANSWER_CHARS = 8000

DISCLOSURE = (
    "AI-generated answer. It can be wrong or out of date — check it against "
    "your notes and course material before relying on it."
)

#: What the assistant is, said plainly. The UI repeats this; the API returns it
#: so a second client cannot quietly drop the label.
IDENTITY = "EngineVerse study assistant (an AI assistant, not a person)"

#: Page-aware suggestions. A student on a coding problem does not want to be
#: asked what they are revising; a student on the planner does.
_PROMPT_SETS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("/practice/problems", "/codelab", "/compiler", "/python-compiler", "/programming"),
        (
            "Explain this error in simple words and how to fix it",
            "What is the difference between time and space complexity?",
            "Give me a hint for this problem without the full solution",
        ),
    ),
    (
        ("/practice", "/dpp", "/sheets", "/flashcards", "/revision", "/mistakes"),
        (
            "Make me a 7-day revision plan for my weakest topics",
            "Explain this answer as if I am seeing the topic for the first time",
            "Give me three practice questions on arrays with answers",
        ),
    ),
    (
        ("/topics", "/subjects", "/branches", "/explore", "/formulas", "/books", "/videos"),
        (
            "Explain this topic with a simple real-world example",
            "What should I learn before this topic?",
            "Summarise this topic as five exam points",
        ),
    ),
    (
        ("/planner", "/today", "/roadmaps", "/dashboard", "/stream", "/streams"),
        (
            "Help me plan two hours of study tonight",
            "How do I prepare for semester exams without burning out?",
            "Build me a four-week roadmap for data structures",
        ),
    ),
    (
        ("/projects", "/portfolio", "/placements", "/opportunities", "/community"),
        (
            "Suggest a final-year project I can finish in six weeks",
            "How do I present my projects on a GitHub profile?",
            "What should I prepare for a campus coding interview?",
        ),
    ),
)

DEFAULT_PROMPTS = (
    "Explain pointers in C with a simple example",
    "How do I prepare for a technical interview in 30 days?",
    "What is the difference between an array and a linked list?",
)

#: Capabilities the assistant does NOT have unless the workflow implements
#: them. Shown in the UI so a student is not told the tool can do more than it
#: can, and mirrored in docs/ASSISTANT.md.
LIMITATIONS = (
    "It cannot run your code, open files or browse the web on its own.",
    "It has no access to your account, grades or private notes.",
    "It may be wrong. Verify anything that affects marks or safety.",
    "It answers in the languages the workflow is configured for (English and Hindi by default).",
)


class AssistantUnavailable(Exception):
    """A failure a student can understand, with no upstream detail attached."""

    def __init__(self, message: str, *, status: int = 503, retryable: bool = True, reason: str = "unavailable"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable
        #: Machine-readable, safe for logs and metrics. Never the upstream body.
        self.reason = reason


# ---------------------------------------------------------------------------
# Input and output handling
# ---------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitise_question(value: Any) -> str:
    """Return a bounded, single-purpose question string.

    Rejects rather than truncates a too-long question: silently cutting a
    student's message mid-sentence produces a confidently wrong answer, and the
    client can tell them to shorten it instead. Newlines are kept (a question
    may contain a stack trace) but runs of blank lines are collapsed.
    """
    if not isinstance(value, str):
        return ""
    text = _CONTROL.sub("", value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < MIN_QUESTION_CHARS or len(text) > MAX_QUESTION_CHARS:
        return ""
    return text


def _extract_text(body: Any) -> str:
    """Pull the assistant's text out of the shapes n8n actually returns.

    The Chat Trigger replies ``{"output": "..."}``; a workflow that ends in a
    Set or Code node may return ``{"text": ...}``, a bare string, or a single
    element array of any of those (n8n wraps per-item output in an array when
    the workflow is configured to return all items). Anything else is treated
    as an unusable answer rather than rendered as JSON in the chat.
    """
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        for item in body:
            text = _extract_text(item)
            if text:
                return text
        return ""
    if isinstance(body, dict):
        for key in ("output", "text", "answer", "message", "response"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, (dict, list)):
                text = _extract_text(value)
                if text:
                    return text
        return ""
    return ""


def _clean_answer(text: str) -> str:
    """Plain text with markdown-lite left intact, HTML removed.

    The client escapes before it renders, so this is defence in depth rather
    than the only barrier: an n8n workflow that echoes a retrieved web page
    cannot smuggle markup into a page that runs under a nonce CSP.
    """
    text = strip_html(text or "")
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    if len(text) > MAX_ANSWER_CHARS:
        text = text[:MAX_ANSWER_CHARS].rsplit(" ", 1)[0].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Session identity
# ---------------------------------------------------------------------------

def session_id_for(subject: str) -> str:
    """A stable, unguessable conversation id for one subject, today.

    ``subject`` is the signed-in user id or the anonymous browser's CSRF
    subject (see ``deps.session_id``). HMAC with the instance secret means the
    value cannot be derived by someone who learns another student's id, and the
    date component bounds how long a thread can be continued. EngineVerse
    stores neither the id nor the transcript.
    """
    day = time.strftime("%Y-%m-%d", time.gmtime())
    secret = get_settings().effective_secret()
    digest = hmac.new(secret, f"assistant:{subject}:{day}".encode("utf-8"), hashlib.sha256).hexdigest()
    return "ev-" + digest[:32]


# ---------------------------------------------------------------------------
# Public description of the assistant's state
# ---------------------------------------------------------------------------

def suggestions_for(path: str) -> list[str]:
    """Three suggestions that match the page the student is reading."""
    clean = "/" + (path or "/").lstrip("/")
    for prefixes, prompts in _PROMPT_SETS:
        if any(clean.startswith(prefix) for prefix in prefixes):
            return list(prompts)
    return list(DEFAULT_PROMPTS)


def status() -> dict[str, Any]:
    """The assistant's availability, with nothing secret in it."""
    settings = get_settings()
    mode = settings.assistant_mode
    return {
        "mode": mode,
        "available": mode == "proxy",
        "identity": IDENTITY,
        "disclosure": DISCLOSURE,
        "limitations": list(LIMITATIONS),
        "maxChars": MAX_QUESTION_CHARS,
        "timeoutMs": settings.assistant_timeout_ms,
        "sessionLimitPerHour": settings.assistant_session_limit,
        # Why it is off, in the operator's language but without internals.
        "reason": (
            "The assistant is switched off on this instance."
            if not settings.assistant_enabled
            else "" if mode == "proxy"
            else "This instance has no n8n Chat Trigger configured."
        ),
    }


def client_config(path: str = "/") -> dict[str, Any]:
    """Everything the browser needs, and nothing it does not.

    Rendered into a JSON script tag by ``base.html``. In proxy mode the n8n URL
    is absent by construction, so a view-source reader learns only that a
    same-origin endpoint exists.
    """
    settings = get_settings()
    mode = settings.assistant_mode
    return {
        "mode": mode,
        "endpoint": "/api/assistant/chat" if mode == "proxy" else "",
        "statusEndpoint": "/api/assistant/status" if mode == "proxy" else "",
        "timeoutMs": settings.assistant_timeout_ms,
        "maxChars": MAX_QUESTION_CHARS,
        "prompts": suggestions_for(path),
        "welcome": (
            "I am the EngineVerse study assistant. Ask about a topic, an error "
            "message, a revision plan or a project idea. I am an AI, so check "
            "anything important."
        ),
        "disclosure": DISCLOSURE,
        "identity": IDENTITY,
    }


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------

def _http_timeout(timeout_ms: int) -> httpx.Timeout:
    # Connect is deliberately shorter than the read window: a host that never
    # answers the TCP handshake should fail fast, while a queued n8n execution
    # (or a slow model) gets the full budget.
    return httpx.Timeout(timeout_ms / 1000.0, connect=min(8.0, timeout_ms / 1000.0))


async def ask(
    question: str,
    *,
    session_id: str,
    page: str = "/",
    timeout_ms: int | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Send one message to the configured n8n Chat Trigger and return its text.

    ``url`` overrides the configured webhook for a trusted caller (the
    verification script, which has already validated it). The HTTP API never
    passes it: a browser cannot choose where a question is sent.

    Raises :class:`AssistantUnavailable` for every failure path, so the API can
    map it to one JSON shape. Never raises ``httpx`` exceptions.
    """
    settings = get_settings()
    target = url or settings.assistant_webhook
    if not target:
        raise AssistantUnavailable(
            "The study assistant is not configured on this server.",
            status=503, retryable=False, reason="unconfigured",
        )

    timeout = (timeout_ms or settings.assistant_timeout_ms) / 1000.0
    payload = {
        # The n8n chat contract: this is what the hosted chat widget sends.
        "action": "sendMessage",
        "sessionId": session_id,
        "chatInput": question,
    }
    # The page hint is caller-supplied, so it is reduced to printable ASCII
    # before it becomes a header value: a CR or LF in a header is at best an
    # error and at worst a smuggling attempt, and neither belongs upstream.
    safe_page = re.sub(r"[^\x20-\x7e]", "", ("/" + (page or "/").lstrip("/")))[:120]
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Sent so a workflow can vary its answer by page without trusting the
        # browser: only EngineVerse fills this in, and only with a path.
        "X-EngineVerse-Page": safe_page,
        "User-Agent": "EngineVerse-Assistant/1.0 (+https://github.com/sauravprivatelimited369-byte/Engine_Verse)",
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_http_timeout(int(timeout * 1000)), follow_redirects=False) as client:
            response = await asyncio.wait_for(
                client.post(target, json=payload, headers=headers),
                timeout=timeout + 2.0,
            )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise AssistantUnavailable(
            "The assistant took too long to answer. Please try again.",
            status=504, retryable=True, reason="timeout",
        ) from None
    except httpx.HTTPError:
        # Connection refused, DNS failure, TLS problem: none of which a student
        # can act on, and none of which we echo.
        raise AssistantUnavailable(
            "The assistant could not be reached. Please try again in a moment.",
            status=503, retryable=True, reason="unreachable",
        ) from None

    if response.status_code in (401, 403):
        # The workflow is inactive or the webhook path is wrong. Not retryable
        # from the browser; the operator sees it in the audit log.
        raise AssistantUnavailable(
            "The assistant is not accepting requests right now.",
            status=503, retryable=False, reason="refused",
        )
    if response.status_code == 429:
        raise AssistantUnavailable(
            "The assistant is handling a lot of questions. Try again in a minute.",
            status=429, retryable=True, reason="upstream_rate_limited",
        )
    if response.status_code >= 500:
        raise AssistantUnavailable(
            "The assistant is temporarily unavailable. Please try again.",
            status=503, retryable=True, reason=f"upstream_{response.status_code}",
        )
    if response.status_code != 200:
        raise AssistantUnavailable(
            "The assistant did not answer that request.",
            status=502, retryable=False, reason=f"upstream_{response.status_code}",
        )

    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        # A workflow that returns plain text is still a usable answer.
        answer = _clean_answer(response.text)
        body = None
    else:
        answer = _clean_answer(_extract_text(body))

    if not answer:
        raise AssistantUnavailable(
            "The assistant returned an empty answer. Please rephrase your question.",
            status=502, retryable=True, reason="empty_answer",
        )

    return {
        "answer": answer,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "identity": IDENTITY,
        "disclosure": DISCLOSURE,
    }
