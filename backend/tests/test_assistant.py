"""The student copilot: the n8n bridge, its failure states and its UI contract.

Two layers are tested here, and they answer different questions:

* ``engineverse.assistant`` is exercised with ``httpx.MockTransport`` for the
  response shapes and failure modes an n8n workflow can produce. This is what
  keeps a wrong deployment from looking like an answer.
* One test starts a real HTTP server on loopback and points the app at it, so
  the whole path - CSRF, handler, threadpool, HTTP client, JSON parse, audit -
  runs against a real socket. That stand-in is *not* the operator's n8n
  instance: ``scripts/check_assistant.py`` is what verifies the real one, and
  the documentation says so.
"""
from __future__ import annotations

import html
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from engineverse import assistant
from engineverse.config import reload_settings
from engineverse.security import ratelimit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token(client, page: str = "/assistant") -> str:
    response = client.get(page)
    assert response.status_code == 200, response.status_code
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
    assert match, "the page carries no CSRF meta tag"
    return html.unescape(match.group(1))


def _chat(client, body, *, token=None):
    return client.post(
        "/api/assistant/chat",
        json=body,
        headers={"X-CSRF-Token": token or _token(client), "Accept": "application/json"},
    )


def _configure(monkeypatch, url: str = "https://n8n.example.test/webhook/abc/chat", **extra):
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", url)
    for key, value in extra.items():
        monkeypatch.setenv(key, value)
    reload_settings()
    return assistant.endpoint()


def _mock(handler):
    """A client_factory that answers from `handler` instead of the network."""
    def factory(target):
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(5.0),
            follow_redirects=False,
        )

    return factory


@pytest.fixture()
def unconfigured(monkeypatch):
    monkeypatch.delenv("ENGINEVERSE_ASSISTANT_URL", raising=False)
    monkeypatch.delenv("ENGINEVERSE_ASSISTANT_TOKEN", raising=False)
    reload_settings()
    yield
    reload_settings()


# ---------------------------------------------------------------------------
# Configuration and status
# ---------------------------------------------------------------------------

def test_without_a_url_nothing_is_claimed(client, unconfigured):
    body = client.get("/api/assistant/status").json()
    assert body["ok"] is True and body["configured"] is False
    assert body["reason"]
    # The status payload must never grow a URL or a token field.
    assert "url" not in body and "token" not in body and "workflow" not in body
    assert body["maxMessageChars"] == assistant.MAX_MESSAGE_CHARS


def test_ask_refuses_honestly_when_no_workflow_is_connected(client, unconfigured):
    response = _chat(client, {"message": "Explain recursion", "sessionId": "a" * 32})
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False and body["code"] == "assistant_not_configured"
    assert "not connected" in body["error"].lower()


def test_invalid_urls_disable_the_copilot(monkeypatch):
    for bad in ("not-a-url", "ftp://n8n.example.test/hook", "https://user:pw@n8n.example.test/hook"):
        monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", bad)
        reload_settings()
        assert assistant.endpoint() is None, bad
    monkeypatch.delenv("ENGINEVERSE_ASSISTANT_URL")
    reload_settings()


def test_production_refuses_plaintext_and_credentials_in_the_url(monkeypatch):
    from engineverse.config import Settings

    base = dict(
        env="production", secret="x" * 40, db_url="postgresql://u:p@localhost/db",
        site_url="https://engineverse.test", judge="disabled",
    )
    plaintext = Settings(assistant_url="http://n8n.internal/webhook/x/chat", **base)
    assert any("https" in problem for problem in plaintext.production_problems())

    credentialed = Settings(assistant_url="https://u:p@n8n.test/webhook/x/chat", **base)
    assert any("credentials" in problem for problem in credentialed.production_problems())

    fine = Settings(assistant_url="https://n8n.test/webhook/x/chat", **base)
    assert fine.production_problems() == []


def test_the_token_header_is_configurable_and_validated(monkeypatch):
    target = _configure(
        monkeypatch,
        ENGINEVERSE_ASSISTANT_TOKEN="secret-value",
        ENGINEVERSE_ASSISTANT_AUTH_HEADER="Authorization",
    )
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"output": "ok"})

    assistant.ask("Explain stacks", session_id="b" * 32, client_factory=_mock(handler))
    assert seen["authorization"] == "secret-value"
    assert target.auth_header == "Authorization"


# ---------------------------------------------------------------------------
# A real round trip against a local stand-in for the workflow
# ---------------------------------------------------------------------------

class _Webhook(BaseHTTPRequestHandler):
    received: list[dict] = []
    reply = {"output": "A stack is last-in, first-out."}

    def do_POST(self):  # noqa: N802 - http.server's API
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        headers = {key.lower(): value for key, value in self.headers.items()}
        type(self).received.append({"body": body, "headers": headers, "path": self.path})
        if self.path.endswith("/broken"):
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Traceback: database password is hunter2")
            return
        payload = json.dumps(type(self).reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture()
def webhook(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Webhook)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Webhook.received = []
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_URL", f"http://127.0.0.1:{server.server_port}/webhook/abc/chat")
    monkeypatch.setenv("ENGINEVERSE_ASSISTANT_TOKEN", "test-token-not-real")
    reload_settings()
    yield server
    server.shutdown()
    server.server_close()
    reload_settings()


def test_a_question_reaches_the_workflow_and_the_answer_comes_back(client, webhook):
    token = _token(client)
    response = _chat(
        client,
        {"message": "What is a stack?", "sessionId": "c" * 32, "page": "/topics/arrays"},
        token=token,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["reply"] == "A stack is last-in, first-out."
    assert body["sessionId"] == "c" * 32
    assert body["provider"] == "n8n workflow"
    assert "disclosure" in body

    assert len(_Webhook.received) == 1
    sent = _Webhook.received[0]
    assert sent["path"] == "/webhook/abc/chat"
    assert sent["body"]["action"] == "sendMessage"
    assert sent["body"]["chatInput"] == "What is a stack?"
    assert sent["body"]["sessionId"] == "c" * 32
    assert sent["body"]["metadata"] == {"source": "engineverse", "page": "/topics/arrays"}
    assert sent["headers"]["x-engineverse-key"] == "test-token-not-real"
    # The credential and the webhook URL are server-side only.
    assert "test-token-not-real" not in response.text
    assert "127.0.0.1" not in response.text


def test_upstream_errors_are_not_echoed_to_the_student(client, webhook):
    webhook.RequestHandlerClass.reply = {"output": "fine"}
    # Point the same app at the failing path on the same server.
    import os

    os.environ["ENGINEVERSE_ASSISTANT_URL"] = (
        f"http://127.0.0.1:{webhook.server_port}/webhook/abc/chat/broken"
    )
    reload_settings()
    response = _chat(client, {"message": "What is a stack?", "sessionId": "d" * 32})
    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "assistant_unavailable"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert "127.0.0.1" not in response.text


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    ({"output": "chat-trigger shape"}, "chat-trigger shape"),
    ({"text": "text shape"}, "text shape"),
    ({"reply": "reply shape"}, "reply shape"),
    ({"answer": "answer shape"}, "answer shape"),
    ({"data": {"output": "wrapped shape"}}, "wrapped shape"),
    ([{"text": "first block"}, {"text": "second block"}], "first block\n\nsecond block"),
    ("a bare string", "a bare string"),
])
def test_the_common_workflow_reply_shapes_are_understood(monkeypatch, payload, expected):
    _configure(monkeypatch)
    def handler(request):
        return httpx.Response(200, json=payload)
    result = assistant.ask("Explain queues", session_id="e" * 32, client_factory=_mock(handler))
    assert result["reply"] == expected


def test_an_unreadable_body_is_an_error_not_an_empty_answer(monkeypatch):
    _configure(monkeypatch)

    def not_json(request):
        return httpx.Response(200, text="<html>Welcome to n8n</html>", headers={"content-type": "text/html"})

    with pytest.raises(assistant.AssistantUnavailable) as excinfo:
        assistant.ask("Explain queues", client_factory=_mock(not_json))
    assert "could not read" in excinfo.value.message

    def empty(request):
        return httpx.Response(200, json={"output": ""})

    with pytest.raises(assistant.AssistantUnavailable):
        assistant.ask("Explain queues", client_factory=_mock(empty))


def test_a_very_long_reply_is_truncated_and_labelled(monkeypatch):
    _configure(monkeypatch)

    def huge(request):
        return httpx.Response(200, json={"output": "word " * 5000})

    result = assistant.ask("Explain everything", client_factory=_mock(huge))
    assert len(result["reply"]) <= assistant.MAX_REPLY_CHARS + 60
    assert result["reply"].endswith("[Reply truncated by EngineVerse.]")


def test_timeouts_and_network_failures_have_their_own_states(monkeypatch):
    _configure(monkeypatch)

    def slow(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(assistant.AssistantTimeout) as excinfo:
        assistant.ask("Explain queues", client_factory=_mock(slow))
    assert excinfo.value.status == 504
    assert "did not answer in time" in excinfo.value.message

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(assistant.AssistantUnavailable) as excinfo:
        assistant.ask("Explain queues", client_factory=_mock(down))
    assert "could not be reached" in excinfo.value.message


def test_the_workflows_own_rate_limit_keeps_its_retry_after(monkeypatch):
    """n8n limiting us is not the same failure as this server limiting a student."""
    _configure(monkeypatch)

    def limited(request):
        return httpx.Response(429, headers={"retry-after": "90"}, json={"message": "slow down"})

    with pytest.raises(assistant.AssistantBusy) as excinfo:
        assistant.ask("Explain queues", client_factory=_mock(limited))
    assert excinfo.value.status == 429
    assert excinfo.value.code == "assistant_upstream_busy"
    assert excinfo.value.retry_after == 90


def test_there_is_no_redirect_following(monkeypatch):
    """A redirect must not carry the credential header to another host."""
    _configure(monkeypatch, ENGINEVERSE_ASSISTANT_TOKEN="do-not-leak")

    def redirect(request):
        return httpx.Response(302, headers={"location": "https://attacker.example/collect"})

    with pytest.raises(assistant.AssistantUnavailable):
        assistant.ask("Explain queues", client_factory=_mock(redirect))


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"message": "a"},
    {"message": ""},
    {"message": "x" * (assistant.MAX_MESSAGE_CHARS + 1)},
    {"message": 42},
    {"message": None},
])
def test_short_and_oversized_questions_are_refused(client, webhook, body):
    response = _chat(client, dict(body, sessionId="f" * 32))
    assert response.status_code == 422
    body_json = response.json()
    assert body_json["ok"] is False and body_json["code"] == "assistant_invalid_request"
    assert not _Webhook.received, "an invalid question must not reach the workflow"


def test_a_control_character_is_stripped_and_never_forwarded(client, webhook):
    response = _chat(client, {"message": "What\x00 is\x07 a queue?", "sessionId": "g" * 32})
    assert response.status_code == 200
    assert _Webhook.received[0]["body"]["chatInput"] == "What is a queue?"


def test_a_malformed_session_id_is_replaced_not_trusted(client, webhook):
    response = _chat(client, {"message": "What is a queue?", "sessionId": "../../etc/passwd"})
    assert response.status_code == 200
    returned = response.json()["sessionId"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{8,64}", returned)
    assert returned != "../../etc/passwd"
    assert _Webhook.received[0]["body"]["sessionId"] == returned


def test_an_unexpected_page_value_is_not_forwarded(client, webhook):
    response = _chat(
        client,
        {"message": "What is a queue?", "sessionId": "h" * 32, "page": "javascript:alert(1)"},
    )
    assert response.status_code == 200
    assert _Webhook.received[0]["body"]["metadata"]["page"] == ""


def test_the_endpoint_requires_csrf(client, webhook):
    response = client.post("/api/assistant/chat", json={"message": "Explain queues"})
    assert response.status_code == 403
    assert not _Webhook.received


def test_the_endpoint_is_rate_limited(client, webhook, monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "assistant", (2, 3600))
    token = _token(client)
    statuses = [
        _chat(client, {"message": f"What is a queue? {index}", "sessionId": "i" * 32}, token=token).status_code
        for index in range(3)
    ]
    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429
    limited = _chat(client, {"message": "One more?", "sessionId": "i" * 32}, token=token)
    assert limited.json()["code"] == "assistant_rate_limited"
    # The GET status check is not part of the question budget.
    assert client.get("/api/assistant/status").status_code == 200


# ---------------------------------------------------------------------------
# Feedback (aggregate only)
# ---------------------------------------------------------------------------

def test_feedback_records_a_category_and_no_free_text(client, seeded):
    from engineverse import db

    token = _token(client)
    response = client.post(
        "/api/assistant/feedback",
        json={"helpful": False, "code": "wrong", "sessionId": "j" * 32,
              "answer": "this must not be stored"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200 and response.json()["recorded"] is True
    row = db.query_one(
        "SELECT meta FROM audit_logs WHERE action = 'assistant.feedback' ORDER BY created_at DESC LIMIT 1"
    )
    assert row and json.loads(row["meta"])["code"] == "wrong"
    assert "this must not be stored" not in row["meta"]

    bad = client.post(
        "/api/assistant/feedback",
        json={"helpful": "yes"},
        headers={"X-CSRF-Token": token},
    )
    assert bad.status_code == 422
    bad_code = client.post(
        "/api/assistant/feedback",
        json={"helpful": False, "code": "script"},
        headers={"X-CSRF-Token": token},
    )
    assert bad_code.status_code == 422


# ---------------------------------------------------------------------------
# Page, navigation, privacy and client-side safety
# ---------------------------------------------------------------------------

def test_the_page_explains_an_unconfigured_instance(client, unconfigured):
    response = client.get("/assistant")
    assert response.status_code == 200
    text = html.unescape(response.text)
    assert "No AI workflow is connected" in text
    assert ">Send<" not in text, "a composer that can only fail must not be rendered"
    assert "study tutor" in text
    # The floating launcher is absent too, rather than opening an apology.
    assert "data-ev-assistant-launcher" not in text


def test_a_configured_instance_gets_the_page_and_the_launcher(client, monkeypatch):
    _configure(monkeypatch)
    page = client.get("/assistant")
    text = html.unescape(page.text)
    assert 'data-ev-assistant-variant="page"' in text
    assert "data-ev-assistant-input" in text
    assert "New conversation" in text
    assert "not a person" in text or "not a human" in text

    other = client.get("/explore")
    assert "data-ev-assistant-launcher" in other.text
    assert "data-ev-assistant-dialog" in other.text
    # One launcher per page, not one per include.
    assert other.text.count("data-ev-assistant-launcher") == 1


def test_the_assistant_is_reachable_from_navigation_and_the_sitemap(client):
    from engineverse import navigation

    assert navigation.find("/assistant") is not None
    labels = {dest.path: dest.label for dest in navigation.all_destinations()}
    assert labels["/assistant"] == "AI assistant"
    assert "/assistant" in navigation.indexable_paths()
    assert "/assistant<" in client.get("/sitemap.xml").text


def test_the_privacy_page_discloses_the_assistant(client):
    text = html.unescape(client.get("/privacy").text)
    assert "The AI assistant" in text
    assert "n8n" in text
    assert "session storage" in text
    assert "not a person" in text


def test_the_client_renders_answers_as_text_never_as_markup():
    """n8n output is untrusted. The widget must not assign HTML from it."""
    from pathlib import Path

    source = Path("backend/static/js/assistant.js").read_text()
    assert ".innerHTML" not in source
    assert "document.write" not in source
    assert "insertAdjacentHTML" not in source
    assert "textContent" in source


def test_the_webhook_url_and_token_never_reach_a_template():
    """The bridge's whole point is that these stay in the process environment."""
    from pathlib import Path

    templates = Path("backend/templates").glob("*.html")
    for template in templates:
        text = template.read_text()
        # The variable *name* may be explained to an operator; its value and
        # the Jinja objects that hold it may not be interpolated.
        assert "assistant.url" not in text, template
        assert "assistant.token" not in text, template
        assert "assistant_url" not in text, template
        assert "assistant_token" not in text, template
        assert "auth_header" not in text, template


def test_suggestions_follow_the_page_the_student_is_on():
    code = assistant.suggestions_for("/codelab")
    practice = assistant.suggestions_for("/practice/problems/two-sum")
    generic = assistant.suggestions_for("/")
    assert code != generic and practice != generic
    assert any("traceback" in prompt.lower() for prompt in code)
    assert any("complexity" in prompt.lower() for prompt in practice)
    assert assistant.suggestions_for("/assistant") and len(assistant.suggestions_for("/assistant")) <= 4
