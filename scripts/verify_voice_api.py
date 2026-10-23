#!/usr/bin/env python3
"""Check the public voice backend and the exported voice configuration.

Two independent jobs, both read-only:

``--url https://backend.example``
    Called *before* the site is exported, when ``ENGINEVERSE_VOICE_API_URL``
    is configured. It proves the origin is a bare public HTTPS origin, that
    ``GET /api/voice/status`` answers with a status payload, that the response
    does not carry a credential or a signed URL, and that it allows the
    published GitHub Pages origin (a real preflight ``OPTIONS`` request, not
    just a GET from a server). A configured-but-unreachable backend fails the
    build here instead of being published as a dead Listen button.

``--site site``
    Called *after* the export. It reads the generated
    ``#ev-voice-config`` block and asserts that it matches the configured
    origin (or is honestly empty in voice-disabled mode), and that no API key
    or signed conversation URL reached the static output.

Neither check proves that ElevenLabs itself answers for this account: that
needs the real key and voice ID, and is a separate live test. The status
payload is deliberately inspected for *shape*, not for a fabricated success.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.export_pages import normalise_app_url  # noqa: E402

PAGES_ORIGIN = "https://sauravprivatelimited369-byte.github.io"
TIMEOUT = 15
CONFIG_RE = re.compile(
    r'<script[^>]+id="ev-voice-config"[^>]*>\s*(\{.*?\})\s*</script>', re.S
)
#: Anything that must never be published: a key, a bearer token, a signed
#: conversation URL, or the agent id (which is not a key, but is server-side
#: configuration and is never needed by the reader).
# Key-shaped, not merely prefixed: "sk_sources" in a lesson is not a key.
FORBIDDEN = (
    (re.compile(r"sk_[A-Za-z0-9_\-]{20,}"), "an ElevenLabs API key"),
    (re.compile(r"xi-api-key", re.I), "an API key header"),
    (re.compile(r"ELEVENLABS_API_KEY"), "a key variable name"),
    (re.compile(r"convai/conversation\?[^\"'\s]+"), "a signed conversation URL"),
    (re.compile(r"agent_[A-Za-z0-9]{16,}"), "an agent id"),
)


def _fail(message: str) -> None:
    print(f"FAIL  {message}")
    raise SystemExit(1)


def check_url(url: str) -> str:
    """Validate the origin and return it normalised, or exit non-zero."""
    try:
        origin = normalise_app_url(url)
    except SystemExit:
        _fail("ENGINEVERSE_VOICE_API_URL is not a bare public HTTPS origin")
    if not origin.startswith("https://"):
        _fail("ENGINEVERSE_VOICE_API_URL must use HTTPS in a deployment")
    print(f"ok    voice API origin is a bare HTTPS origin: {origin}")
    return origin


def _request(url: str, *, method: str = "GET", headers: dict | None = None):
    request = Request(url, method=method, headers=headers or {})
    return urlopen(request, timeout=TIMEOUT)


def check_status(origin: str) -> dict:
    """GET /api/voice/status from the published origin and validate it."""
    url = f"{origin}/api/voice/status"
    try:
        with _request(url, headers={"Origin": PAGES_ORIGIN, "Accept": "application/json"}) as response:
            body = response.read()
            allow = response.headers.get("access-control-allow-origin", "")
            code = response.status
    except HTTPError as error:
        _fail(f"{url} answered HTTP {error.code}; the backend is not serving /api/voice")
    except (URLError, TimeoutError, OSError) as error:
        _fail(f"{url} is unreachable ({error.__class__.__name__}); nothing was published")
    if code != 200:
        _fail(f"{url} answered HTTP {code}")
    print(f"ok    GET /api/voice/status answered 200")
    try:
        payload = json.loads(body)
    except ValueError:
        _fail("/api/voice/status did not return JSON")
    if not isinstance(payload, dict) or "tts" not in payload:
        _fail("/api/voice/status has no tts block; the deployed build predates the voice API")
    tts = payload.get("tts") or {}
    conversation = payload.get("conversation") or {}
    # Report the truth, including "not configured": a reachable backend with
    # no key is a real deployment state, not a build failure.
    print(
        "ok    deployed status: tts "
        f"{'available' if tts.get('available') else 'NOT configured'}, "
        f"tutor {'available' if conversation.get('available') else 'NOT configured'}"
    )
    if allow == "*":
        _fail(
            "the backend answers Access-Control-Allow-Origin: * ; set "
            "ENGINEVERSE_VOICE_ORIGINS to the Pages origin instead"
        )
    if allow and allow != PAGES_ORIGIN:
        _fail(f"the backend allows origin {allow!r}, not {PAGES_ORIGIN!r}")
    if allow:
        print(f"ok    CORS allows the published origin {PAGES_ORIGIN}")
    else:
        print("warn  no Access-Control-Allow-Origin on this request (check ENGINEVERSE_VOICE_ORIGINS)")
    check_preflight(origin)
    text = body.decode("utf-8", "replace")
    for pattern, what in FORBIDDEN:
        if pattern.search(text):
            _fail(f"/api/voice/status exposes {what}")
    print("ok    the status payload carries no key, agent id or signed URL")
    return payload


def check_preflight(origin: str) -> None:
    """A browser sends OPTIONS before a JSON POST; it must be answered."""
    url = f"{origin}/api/voice/speech"
    try:
        with _request(
            url,
            method="OPTIONS",
            headers={
                "Origin": PAGES_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        ) as response:
            allow = response.headers.get("access-control-allow-origin", "")
            methods = (response.headers.get("access-control-allow-methods", "") or "").upper()
            code = response.status
    except HTTPError as error:
        _fail(f"preflight to {url} answered HTTP {error.code}")
    except (URLError, TimeoutError, OSError):
        _fail(f"preflight to {url} is unreachable")
    if code not in (200, 204):
        _fail(f"preflight to {url} answered HTTP {code}")
    if allow != PAGES_ORIGIN:
        _fail(f"preflight did not allow {PAGES_ORIGIN} (got {allow!r})")
    if "POST" not in methods:
        _fail("preflight does not allow POST")
    print("ok    CORS preflight for POST /api/voice/speech allows the Pages origin")


def check_site(site: Path, expected: str) -> None:
    index = site / "index.html"
    if not index.is_file():
        _fail(f"{index} is missing")
    html = index.read_text(encoding="utf-8")
    match = CONFIG_RE.search(html)
    if not match:
        _fail("the export has no #ev-voice-config block")
    try:
        config = json.loads(match.group(1))
    except ValueError:
        _fail("the exported #ev-voice-config is not valid JSON")
    api_base = str(config.get("apiBase", ""))
    if config.get("staticCopy") is not True:
        _fail("the export did not mark itself as the static copy")
    if expected:
        if api_base != expected:
            _fail(f"the exported apiBase is {api_base!r}, expected {expected!r}")
        print(f"ok    the exported site calls the configured backend {api_base}")
    else:
        if api_base:
            _fail(f"the exported apiBase is {api_base!r} with no configured origin")
        print("ok    voice-disabled export: apiBase is empty and the page says voice is not connected")
    # Every HTML file, not just the home page: a key must reach none of them.
    for page in site.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="replace")
        for pattern, what in FORBIDDEN:
            if pattern.search(text):
                _fail(f"{page.relative_to(site)} contains {what}")
    print("ok    no key, agent id or signed URL in any exported page")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="", help="configured public voice API origin")
    parser.add_argument("--site", default="", help="exported site directory to inspect")
    parser.add_argument("--self-check", action="store_true", help="check this script's own rules")
    args = parser.parse_args()
    if args.self_check:
        assert normalise_app_url("https://voice.example.com") == "https://voice.example.com"
        assert PAGES_ORIGIN.endswith(".github.io") and "/" not in PAGES_ORIGIN.split("//", 1)[1]
        sample = '{"apiBase": "https://voice.example.com", "staticCopy": true}'
        assert CONFIG_RE.search(f'<script type="application/json" id="ev-voice-config">{sample}</script>')
        print("verify_voice_api: self-check ok")
        return 0
    if not args.url and not args.site:
        parser.error("give --url, --site, or --self-check")
    expected = check_url(args.url) if args.url else ""
    if args.url and not args.site:
        check_status(expected)
    if args.site:
        check_site(Path(args.site), expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
