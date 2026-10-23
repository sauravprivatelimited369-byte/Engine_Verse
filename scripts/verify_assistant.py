#!/usr/bin/env python3
"""Verify an n8n Chat Trigger end to end, with one real message.

Use this after wiring the workflow into EngineVerse. It proves the thing that
matters and that no unit test can prove for you: that the webhook you configured
answers, and that EngineVerse's client can read the answer.

    # After setting ENGINEVERSE_ASSISTANT_URL (or passing --url):
    python scripts/verify_assistant.py

    # Before importing credentials, just confirm the URL is well formed:
    python scripts/verify_assistant.py --dry-run

What it does
------------
Sends exactly one message ("Say hello in one sentence...") using the same
request body, headers and parser as the running site (``engineverse.assistant``),
then prints the HTTP outcome, latency and the first part of the reply. It costs
one n8n execution and one model call. It does not send anything else, store
anything, or retry.

Exit codes
----------
0  the assistant answered
1  the assistant was reached but failed (timeout, 5xx, empty answer)
2  the configuration is invalid or missing (nothing was sent)

Never prints a credential. The URL is printed with any query string removed,
because a webhook URL can be a bearer secret in itself.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engineverse import assistant  # noqa: E402
from engineverse.config import normalise_assistant_url  # noqa: E402

PROBE = "Say hello in one short sentence and name yourself as the EngineVerse assistant."


def safe_display(url: str) -> str:
    """The URL with the query string removed, safe to print."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one test message to the configured n8n Chat Trigger.")
    parser.add_argument("--url", default=os.environ.get("ENGINEVERSE_ASSISTANT_URL", ""),
                        help="Chat Trigger webhook URL (default: $ENGINEVERSE_ASSISTANT_URL)")
    parser.add_argument("--allow-local", action="store_true",
                        help="allow http:// for localhost only (development)")
    parser.add_argument("--dry-run", action="store_true", help="validate the URL and exit")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="request timeout")
    args = parser.parse_args()

    try:
        url = normalise_assistant_url(args.url, allow_local_http=args.allow_local)
    except ValueError as exc:
        print(f"configuration error: {exc}")
        return 2
    if not url:
        print("configuration error: no assistant URL set.")
        print("Set ENGINEVERSE_ASSISTANT_URL to the Chat Trigger 'Chat URL' from n8n,")
        print("or pass --url. See docs/N8N_AUTOMATION.md.")
        return 2

    print(f"endpoint: {safe_display(url)}")
    if args.dry_run:
        print("dry run: the URL is well formed. Nothing was sent.")
        return 0

    print("sending exactly one message…")
    try:
        result = asyncio.run(
            assistant.ask(PROBE, session_id="ev-verify-" + os.urandom(8).hex(), page="/assistant",
                          timeout_ms=args.timeout_ms, url=url)
        )
    except assistant.AssistantUnavailable as exc:
        print(f"FAILED ({exc.status}, {exc.reason}): {exc.message}")
        if exc.reason in {"refused", "unconfigured"}:
            print("Check that the workflow is Active and the Chat Trigger is public in Embedded Chat mode.")
        if exc.reason == "upstream_404":
            print("A 404 usually means the webhook path is wrong or the workflow is not active.")
        if exc.reason == "upstream_401":
            print("A 401/403 means the Chat Trigger requires authentication that EngineVerse did not send.")
        return 1
    except Exception as exc:  # noqa: BLE001 - report, do not traceback into a shared log
        print(f"FAILED (unexpected {type(exc).__name__}): {exc}")
        return 1

    answer = result["answer"]
    print(f"OK  {result['latency_ms']:.0f} ms")
    print("answer (first 400 characters):")
    print("  " + answer[:400].replace("\n", "\n  "))
    if len(answer) > 400:
        print(f"  … ({len(answer)} characters in total)")
    print()
    print("The assistant is reachable. Now check it in the browser:")
    print("  - self-hosted: the launcher on any page, and /assistant")
    print("  - static Pages: set the repository variable ENGINEVERSE_ASSISTANT_PUBLIC_URL")
    print("    to the same Chat URL and allow this origin in the workflow's Allowed Origins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
