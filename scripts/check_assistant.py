#!/usr/bin/env python3
"""Verify that the configured AI assistant actually answers.

There are two ways to run this, and they check different things:

1. ``python scripts/check_assistant.py``
   Uses this checkout's ``ENGINEVERSE_ASSISTANT_*`` variables and calls the
   workflow directly through the same bridge the web app uses. This is the
   check an operator should run after pasting a webhook URL into ``.env``.

2. ``python scripts/check_assistant.py --app https://engineverse.example.org``
   Drives the deployed site: fetches ``/assistant`` for a CSRF token, posts a
   real question to ``/api/assistant/chat`` and prints what came back. This is
   the only check that proves the whole path works in production, including
   cookies, the reverse proxy and the workflow credential on the server.

Exit codes: 0 answered, 1 configured but failed, 2 not configured.

The workflow URL and token are never printed. The probe question and the reply
are printed because a human needs to read them to judge whether the answer is
sane; do not put anything private in ``--message``.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for entry in (str(BACKEND), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

DEFAULT_MESSAGE = "In two sentences, what is the difference between a stack and a queue?"


def _mask(url: str) -> str:
    """Host only. The path identifies the workflow and is not printed."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname}/…"


def direct(question: str) -> int:
    from engineverse import assistant
    from engineverse.config import get_settings

    settings = get_settings()
    if not assistant.configured():
        print("The assistant is NOT configured in this environment.")
        print("Set ENGINEVERSE_ASSISTANT_URL (and, if the workflow requires it,")
        print("ENGINEVERSE_ASSISTANT_TOKEN / ENGINEVERSE_ASSISTANT_AUTH_HEADER), then retry.")
        print("Nothing was contacted, so no claim can be made about the workflow.")
        return 2

    target = assistant.endpoint()
    print(f"Workflow host: {_mask(target.url)}")
    print(f"Auth header:   {target.auth_header}{' (token set)' if target.token else ' (no token set)'}")
    print(f"Timeout:       {target.timeout_s}s")
    print(f"Question:      {question}")
    try:
        result = assistant.ask(question, session_id="checkassistantprobe0000000000", page="/assistant")
    except assistant.AssistantError as exc:
        print(f"FAILED ({exc.status} {exc.code}): {exc.message}")
        return 1
    print(f"Answered in {result['latencyMs']} ms:")
    print("-" * 70)
    print(result["reply"][:2000])
    print("-" * 70)
    print("Verdict: the workflow responded. Read the answer above before trusting it.")
    return 0


def via_app(base_url: str, question: str) -> int:
    import httpx

    base = base_url.rstrip("/")
    print(f"Target site: {base}")
    try:
        with httpx.Client(timeout=60.0, follow_redirects=False, trust_env=False) as client:
            page = client.get(f"{base}/assistant")
            if page.status_code != 200:
                print(f"FAILED: GET /assistant returned {page.status_code}.")
                if page.status_code in (301, 302, 303, 307, 308):
                    print("The site redirects this path. Check ENGINEVERSE_SIGNIN; the assistant")
                    print("page is public, so a redirect means the deployment is not serving it.")
                return 1
            match = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text)
            if not match:
                print("FAILED: the page carries no CSRF token, so it is not the EngineVerse app.")
                return 1
            token = html.unescape(match.group(1))
            answer = client.post(
                f"{base}/api/assistant/chat",
                json={"message": question, "sessionId": "checkassistantprobe0000000000", "page": "/assistant"},
                headers={"X-CSRF-Token": token, "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        print(f"FAILED: could not reach the site ({type(exc).__name__}).")
        return 1

    try:
        body = answer.json()
    except ValueError:
        print(f"FAILED: the endpoint returned {answer.status_code} with a non-JSON body.")
        return 1
    if answer.status_code != 200 or not body.get("ok"):
        print(f"FAILED ({answer.status_code} {body.get('code', '')}): {body.get('error', 'no message')}")
        return 1
    print(f"Answered in {body.get('latencyMs', '?')} ms:")
    print("-" * 70)
    print(str(body.get("reply", ""))[:2000])
    print("-" * 70)
    print("Verdict: the deployed site answered through the configured workflow.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", metavar="URL", help="check a deployed site instead of this checkout's settings")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="probe question (default: a neutral two-sentence prompt)")
    args = parser.parse_args()
    if args.app:
        return via_app(args.app, args.message)
    return direct(args.message)


if __name__ == "__main__":
    raise SystemExit(main())
