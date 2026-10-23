"""The n8n study assistant: transport, failure states, privacy and export.

Three layers are covered:

1. **Pure functions** - URL validation, question bounds, answer extraction and
   the session digest. These are where a mistake turns into a security bug.
2. **The real HTTP round trip** - against ``scripts/mock_n8n.py``, which speaks
   n8n's Chat Trigger contract. This is the only way to prove the transport
   works without the operator's credentials, and it is explicitly a stand-in:
   no test here claims to have reached the user's n8n cloud workspace.
3. **The web edges** - CSRF, rate limits, the unconfigured state, the rendered
   page, and the static Pages export.
"""
from __future__ import annotations

import json
import re
import threading
import time

import pytest

from engineverse import assistant
from engineverse.config import get_settings, normalise_assistant_url, reload_settings
from scripts import export_pages, mock_n8n

CHAT_URL = "https://example.app.n8n.cloud/webhook/engineverse/chat"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def configured(monkeypatch):
    """A server with a valid Chat Trigger URL, for one test."""
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", CHAT_URL)
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_ENABLED", "true")
    reload_settings()
    return get_settings()


@pytest.fixture()
def mock_server():
    """A real HTTP server speaking the n8n Chat Trigger contract."""
    server = mock_n8n.serve("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}/webhook/engineverse/chat"
    finally:
        server.shutdown()
        server.server_close()


def _csrf(html: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    assert match, "every page carries a CSRF meta tag"
    return match.group(1)


def post_question(client, question: str, *, page: str = "/assistant"):
    """POST as the browser does: page first (cookie), then the JSON call."""
    token = _csrf(client.get(page).text)
    return client.post(
        "/api/assistant/chat",
        json={"question": question},
        headers={"X-CSRF-Token": token, "Accept": "application/json"},
    )


# ---------------------------------------------------------------------------
# 1. Pure functions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        ("", ""),
        (None, ""),
        ("https://x.app.n8n.cloud/webhook/abc/chat", "https://x.app.n8n.cloud/webhook/abc/chat"),
        ("  https://x.app.n8n.cloud/webhook/abc/chat?x=1  ", "https://x.app.n8n.cloud/webhook/abc/chat?x=1"),
    ],
)
def test_valid_assistant_urls_are_accepted(value, expected):
    assert normalise_assistant_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com/webhook/x/chat",          # plain HTTP off localhost
        "ftp://example.com/webhook/x/chat",           # wrong scheme
        "https:///webhook/x/chat",                    # no host
        "https://user:pass@example.com/webhook/x",    # credentials in URL
        "https://example.com/",                       # the editor, not a webhook
        "https://example.com/webhook/x/chat#frag",    # fragment
        "https://example.com/webhook/a b",            # whitespace
    ],
)
def test_bad_assistant_urls_are_refused(value):
    with pytest.raises(ValueError):
        normalise_assistant_url(value)


def test_local_http_is_allowed_only_when_asked():
    local = "http://127.0.0.1:5678/webhook/engineverse/chat"
    with pytest.raises(ValueError):
        normalise_assistant_url(local)
    assert normalise_assistant_url(local, allow_local_http=True) == local


def test_question_bounds_and_control_characters():
    assert assistant.sanitise_question("  What is a pointer?  ") == "What is a pointer?"
    assert assistant.sanitise_question("Explain\x00\x07 this") == "Explain this"
    assert assistant.sanitise_question("a\n\n\n\nb") == "a\n\nb"
    assert assistant.sanitise_question("") == ""
    assert assistant.sanitise_question("x") == ""                      # too short
    assert assistant.sanitise_question("z" * (assistant.MAX_QUESTION_CHARS + 1)) == ""
    assert assistant.sanitise_question("z" * assistant.MAX_QUESTION_CHARS) != ""
    assert assistant.sanitise_question(["not", "a", "string"]) == ""
    assert assistant.sanitise_question(None) == ""


@pytest.mark.parametrize(
    "body, expected",
    [
        ({"output": "hello"}, "hello"),
        ({"text": "hello"}, "hello"),
        ([{"output": "first"}, {"output": "second"}], "first"),
        # A JSON *string* is already the answer text; it is never parsed twice.
        ('{"output": "quoted"}', '{"output": "quoted"}'),
        ({"data": []}, ""),
        ({"output": ""}, ""),
        ("plain text", "plain text"),
        ({"output": {"text": "nested"}}, "nested"),
    ],
)
def test_answer_extraction_handles_n8n_shapes(body, expected):
    assert assistant._extract_text(body) == expected


def test_answer_html_is_removed_and_length_is_bounded():
    cleaned = assistant._clean_answer("<script>alert(1)</script>**bold** answer")
    assert "<script>" not in cleaned and "**bold**" in cleaned
    long = assistant._clean_answer("word " * 5000)
    assert len(long) <= assistant.MAX_ANSWER_CHARS + 1


def test_session_id_is_stable_private_and_scoped():
    first = assistant.session_id_for("browser-a")
    second = assistant.session_id_for("browser-a")
    other = assistant.session_id_for("browser-b")
    assert first == second
    assert first != other
    assert first.startswith("ev-") and len(first) == 35
    # It is a digest, not a reversible encoding of the subject.
    assert "browser" not in first


def test_client_config_never_carries_the_webhook(monkeypatch, configured):
    config = assistant.client_config("/practice/problems/two-sum")
    assert config["mode"] == "proxy"
    assert config["endpoint"] == "/api/assistant/chat"
    assert "n8n.cloud" not in json.dumps(config)
    # Suggestions follow the page the student is on.
    assert any("error" in prompt.lower() for prompt in config["prompts"])


def test_client_config_is_off_without_configuration():
    config = assistant.client_config("/")
    assert config["mode"] == "off"
    assert config["endpoint"] == ""


def test_suggestions_are_page_aware():
    coding = assistant.suggestions_for("/codelab")
    planner = assistant.suggestions_for("/planner")
    assert coding != planner
    assert len(coding) == len(planner) == 3
    assert assistant.suggestions_for("/unknown-page") == list(assistant.DEFAULT_PROMPTS)


# ---------------------------------------------------------------------------
# 2. The real transport, against a server speaking n8n's contract
# ---------------------------------------------------------------------------

def test_real_round_trip_to_a_chat_trigger(mock_server, monkeypatch):
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", mock_server)
    reload_settings()
    result = __import__("asyncio").run(
        assistant.ask("What is a pointer in C?", session_id=assistant.session_id_for("test"), page="/assistant")
    )
    assert "Mock n8n reply" in result["answer"]
    assert result["latency_ms"] >= 0
    assert "AI-generated" in result["disclosure"]


@pytest.mark.parametrize(
    "suffix, status, reason",
    [
        ("-error", 503, "upstream_500"),
        ("-limited", 429, "upstream_rate_limited"),
        ("-empty", 502, "empty_answer"),
    ],
)
def test_upstream_failures_become_typed_errors(mock_server, monkeypatch, suffix, status, reason):
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", mock_server + suffix)
    reload_settings()
    import asyncio

    with pytest.raises(assistant.AssistantUnavailable) as caught:
        asyncio.run(assistant.ask("hello there", session_id="ev-test"))
    assert caught.value.status == status
    assert caught.value.reason == reason
    # The upstream body is never the message a student sees.
    assert "workflow failed" not in caught.value.message


def test_timeout_is_reported_as_a_timeout(mock_server, monkeypatch):
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", mock_server + "-slow")
    reload_settings()
    import asyncio

    started = time.perf_counter()
    with pytest.raises(assistant.AssistantUnavailable) as caught:
        asyncio.run(assistant.ask("hello there", session_id="ev-test", timeout_ms=800))
    assert caught.value.reason == "timeout"
    assert time.perf_counter() - started < 10


# ---------------------------------------------------------------------------
# 3. HTTP API edges
# ---------------------------------------------------------------------------

def test_unconfigured_instance_says_so(client):
    response = post_question(client, "Explain arrays")
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["unavailable"] is True
    assert body["retryable"] is False
    assert "n8n" in body["error"] or "not available" in body["error"].lower()


def test_status_endpoint_describes_the_assistant_without_secrets(client):
    body = client.get("/api/assistant/status").json()
    assert body["ok"] is True
    assert body["mode"] in {"off", "proxy"}
    assert "n8n" not in json.dumps(body).lower() or body["mode"] == "off"
    assert body["limitations"] and body["disclosure"]


def test_missing_csrf_token_is_rejected_before_any_upstream_call(client, monkeypatch, configured):
    called = False

    async def fake(question, **kwargs):  # pragma: no cover - must not run
        nonlocal called
        called = True
        return {"answer": "no", "latency_ms": 1, "identity": "", "disclosure": ""}

    monkeypatch.setattr(assistant, "ask", fake)
    response = client.post("/api/assistant/chat", json={"question": "hello"}, headers={"Accept": "application/json"})
    assert response.status_code == 403
    assert called is False


def test_question_too_long_is_refused_without_calling_upstream(client, monkeypatch, configured):
    async def fake(question, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("upstream must not be called for an invalid question")

    monkeypatch.setattr(assistant, "ask", fake)
    response = post_question(client, "z" * (assistant.MAX_QUESTION_CHARS + 5))
    assert response.status_code == 422
    assert str(assistant.MAX_QUESTION_CHARS) in response.json()["error"]


def test_successful_answer_is_returned_and_audited_without_the_question(client, monkeypatch, configured):
    async def fake(question, **kwargs):
        assert question == "How do I reverse a linked list?"
        assert kwargs["session_id"].startswith("ev-")
        return {"answer": "Use three pointers.", "latency_ms": 12.3,
                "identity": assistant.IDENTITY, "disclosure": assistant.DISCLOSURE}

    monkeypatch.setattr(assistant, "ask", fake)
    response = post_question(client, "How do I reverse a linked list?")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["answer"] == "Use three pointers."
    assert body["disclosure"] == assistant.DISCLOSURE

    from engineverse import db

    rows = db.query("SELECT meta FROM audit_logs WHERE action = 'assistant.asked'")
    assert rows
    meta = " ".join(str(row["meta"]) for row in rows)
    assert "linked list" not in meta.lower()
    assert "question_chars" in meta


def test_upstream_failure_is_reported_with_a_retry_hint(client, monkeypatch, configured):
    async def fake(question, **kwargs):
        raise assistant.AssistantUnavailable("The assistant could not be reached. Please try again in a moment.",
                                             status=503, retryable=True, reason="unreachable")

    monkeypatch.setattr(assistant, "ask", fake)
    response = post_question(client, "Explain recursion")
    assert response.status_code == 503
    body = response.json()
    assert body["retryable"] is True and body["unavailable"] is True
    assert "Traceback" not in body["error"] and "httpx" not in body["error"]


def test_per_session_question_budget(client, monkeypatch, configured):
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_SESSION_LIMIT", "1")
    reload_settings()

    async def fake(question, **kwargs):
        return {"answer": "ok", "latency_ms": 1, "identity": assistant.IDENTITY,
                "disclosure": assistant.DISCLOSURE}

    monkeypatch.setattr(assistant, "ask", fake)
    first = post_question(client, "First question")
    second = post_question(client, "Second question")
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers.get("Retry-After")


# ---------------------------------------------------------------------------
# 4. Rendered page and navigation
# ---------------------------------------------------------------------------

def test_assistant_page_discloses_what_it_is(client):
    html = client.get("/assistant").text
    assert "Study assistant" in html
    assert "AI-generated" in html
    assert "cannot run your code" in html
    assert 'href="/privacy"' in html
    assert 'href="/tutor"' in html
    # The honesty rules: no claim of a human, no invented live status.
    assert "online now" not in html.lower()
    assert "agents are typing" not in html.lower()


def test_configured_page_does_not_publish_the_webhook(client, configured):
    html = client.get("/assistant").text
    assert configured.assistant_webhook == CHAT_URL
    assert CHAT_URL not in html
    assert "n8n.cloud" not in html
    assert '"mode": "proxy"' in html


def test_assistant_is_in_the_navigation_and_sitemap(client):
    from engineverse import navigation

    assert navigation.find("/assistant") is not None
    home = client.get("/").text
    assert 'href="/assistant"' in home
    sitemap = client.get("/sitemap.xml").text
    assert "/assistant" in sitemap


def test_every_page_carries_the_assistant_config_for_the_client(client):
    page = client.get("/codelab").text
    assert 'id="ev-assistant-config"' in page
    assert 'id="ev-assistant-root"' in page
    assert "/static/js/assistant.js" in page


# ---------------------------------------------------------------------------
# 5. Static GitHub Pages export
# ---------------------------------------------------------------------------

def test_static_config_uses_direct_mode_only_when_a_url_is_configured():
    off = export_pages.assistant_config("")
    assert off["mode"] == "off" and off["endpoint"] == ""

    direct = export_pages.assistant_config(CHAT_URL)
    assert direct["mode"] == "direct"
    assert direct["endpoint"] == CHAT_URL
    # No server-side status endpoint exists on Pages; do not point at one.
    assert direct["statusEndpoint"] == ""


def test_static_export_rewrites_the_config_block():
    html = (
        '<script type="application/json" id="ev-assistant-config">{"mode": "off"}</script>'
        '<script type="application/json" id="ev-live">{"base": "/"}</script>'
    )
    patched = export_pages.patch_assistant_config(html, "/EngineVerse/", CHAT_URL)
    assert CHAT_URL in patched
    assert '"mode": "direct"' in patched
    # The boot block for the rest of the static runtime is untouched.
    assert 'id="ev-live"' in patched
    # And off means off, not a stale endpoint.
    unconfigured = export_pages.patch_assistant_config(html, "/EngineVerse/", "")
    assert '"mode": "off"' in unconfigured and CHAT_URL not in unconfigured


def test_page_hint_cannot_smuggle_a_header(mock_server, monkeypatch):
    """A caller-supplied page label is reduced to printable ASCII."""
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", mock_server)
    reload_settings()
    import asyncio

    seen = {}

    real_post = None

    async def fake_post(self, url, **kwargs):  # noqa: ANN001 - httpx signature
        seen.update(kwargs.get("headers") or {})
        raise assistant.AssistantUnavailable("stop", status=503, reason="test")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    with pytest.raises(assistant.AssistantUnavailable):
        asyncio.run(assistant.ask("hello there", session_id="ev-test",
                                  page="/x\r\nInjected: yes"))
    assert "\r" not in seen["X-EngineVerse-Page"] and "\n" not in seen["X-EngineVerse-Page"]
    assert "Injected" in seen["X-EngineVerse-Page"]  # text kept, framing removed
    assert real_post is None
