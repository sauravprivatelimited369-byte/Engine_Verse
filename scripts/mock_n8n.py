#!/usr/bin/env python3
"""A local stand-in for an n8n Chat Trigger webhook.

Why this exists
---------------
EngineVerse's assistant integration must be testable without the operator's
n8n credentials, without spending model credit, and without the internet. This
script speaks the same HTTP contract as n8n's hosted chat (see
docs/N8N_AUTOMATION.md) and returns *canned* text. It is not a model and it does
not call one: every answer says so.

It is used by:
  * ``backend/tests/test_assistant.py`` - the real httpx round trip;
  * a developer who wants to see the widget work before their workflow is live:

        python scripts/mock_n8n.py --port 5678 &
        ENGINEVERSE_ASSISTANT_URL=http://127.0.0.1:5678/webhook/engineverse/chat \\
            uvicorn main:app --app-dir backend --port 8000

Endpoints
---------
POST /webhook/engineverse/chat            a normal answer
POST /webhook/engineverse/chat-slow       sleeps 30s (timeout behaviour)
POST /webhook/engineverse/chat-error      HTTP 500 (unavailable state)
POST /webhook/engineverse/chat-empty      HTTP 200 with no output
POST /webhook/engineverse/chat-limited    HTTP 429 (rate-limited state)
GET  /health                              {"ok": true}

No request body is logged: the point of the real integration is that questions
are not retained, and a test server should not demonstrate the opposite.
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

MAX_BODY = 16 * 1024

#: Origins allowed by the CORS pre-flight. On a real n8n instance these are set
#: on the Chat Trigger node ("Allowed Origins"). Kept here so the direct
#: (static Pages) transport can be exercised locally too.
ALLOWED_ORIGINS = (
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
)


def _reply_text(prompt: str, session: str) -> str:
    """A deterministic, clearly-labelled answer with the shapes n8n returns."""
    sample = (prompt or "").strip().replace("\n", " ")[:160]
    return (
        "**Mock n8n reply — not a model.**\n\n"
        f"You asked: {sample or '(nothing)'}\n\n"
        f"This response came from `scripts/mock_n8n.py` for session `{session[:8] or 'none'}`. "
        "It exists to prove the transport works: EngineVerse → server → Chat Trigger → "
        "this reply → the chat panel.\n\n"
        "- Swap the URL for your real workflow to get real answers.\n"
        "- Answers are AI-generated; check anything important."
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "EngineVerseMockN8n/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 - stdlib signature
        # Quiet by default: the usual access log would print the path only, but
        # tests are noisy enough without it.
        return

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")

    def _send(self, status: int, payload: dict | None = None, *, raw: str = "") -> None:
        body = raw.encode("utf-8") if raw else json.dumps(payload or {}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib naming
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if urlsplit(self.path).path == "/health":
            self._send(200, {"ok": True, "service": "mock-n8n"})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        path = urlsplit(self.path).path.rstrip("/")
        if not path.startswith("/webhook/engineverse/chat"):
            self._send(404, {"ok": False, "error": "unknown webhook"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"ok": False, "error": "bad body"})
            return
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"ok": False, "error": "bad json"})
            return
        if not isinstance(data, dict):
            self._send(400, {"ok": False, "error": "bad json"})
            return

        variant = path.rsplit("/", 1)[-1].replace("chat", "").strip("-")
        session = str(data.get("sessionId") or "")

        if variant == "slow":
            time.sleep(30)
            self._send(200, {"output": "Late."})
            return
        if variant == "error":
            self._send(500, {"ok": False, "error": "workflow failed"})
            return
        if variant == "empty":
            self._send(200, {"output": ""})
            return
        if variant == "limited":
            self._send(429, {"ok": False, "error": "too many"})
            return

        if data.get("action") == "loadPreviousSession":
            self._send(200, {"data": []})
            return

        prompt = data.get("chatInput")
        if not isinstance(prompt, str) or not prompt.strip():
            self._send(400, {"ok": False, "error": "chatInput is required"})
            return
        # n8n's hosted chat reads "output"; the array form is what a workflow
        # that returns all items produces, and EngineVerse accepts both.
        self._send(200, {"output": _reply_text(prompt, session)})


def serve(host: str = "127.0.0.1", port: int = 5678) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Local n8n Chat Trigger stand-in.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5678)
    args = parser.parse_args()
    server = serve(args.host, args.port)
    print(f"Mock n8n chat listening on http://{args.host}:{args.port}/webhook/engineverse/chat")
    print("This is a test double. It returns canned text and calls no model.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
