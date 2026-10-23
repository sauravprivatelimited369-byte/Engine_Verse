#!/usr/bin/env python3
"""Gate a Pages switch on an actual public HTTPS EngineVerse deployment.

Read-only: it never creates accounts, submits code, or sends learner data.
It checks, over the real public origin:

* HTTPS with a verifiable certificate (urllib verifies TLS by default),
  a production /health payload, and the PWA manifest;
* authentication entry points: sign-in, registration and install pages;
* the password-recovery page renders its form without revealing a reset
  token or a development-mode block;
* data isolation for anonymous callers: account and submission APIs
  answer 401 instead of leaking rows;
* judge honesty: the languages endpoint reports its runnable set in a
  shape the editor can consume, or stays behind sign-in;
* secret hygiene: no .env, SQLite file or git metadata is web-served.

It is still not a substitute for a human testing registration end to end,
signing in, restoring a backup onto a disposable database, delivering a
real reset email/SMS, or probing the Judge0 host's isolation. Those need
credentials and a disposable environment, so they cannot be a public,
unauthenticated gate. See docs/DEPLOYMENT.md ("Production validation
checklist") for the manual steps this script does not cover.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.export_pages import normalise_app_url  # noqa: E402

#: Language slugs the catalogue may legitimately report as runnable. Anything
#: else in the runnable list is a shape the editor cannot consume. This must
#: stay equal to ``engineverse.judge.KNOWN_LANGUAGES`` (asserted by the test
#: suite): in particular a deployment reporting "php" as runnable fails this
#: gate - PHP execution was removed entirely after PHP2Shell
#: (CVE-2026-109618 / CVE-2026-109619), and Kotlin was never an offered
#: runnable language, only an unexposed Judge0 mapping.
KNOWN_LANGUAGE_SLUGS = frozenset({
    "python", "java", "javascript", "typescript", "cpp", "c", "go", "rust",
    "bash", "ruby", "csharp", "sql",
})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _request(origin: str, path: str) -> Request:
    return Request(origin + path, headers={"User-Agent": "EngineVerse-Deployment-Check/1.0"})


def fetch(origin: str, path: str, *, limit: int = 65536) -> tuple[str, str]:
    """No cross-origin redirect to a login page or an unrelated server."""
    with build_opener(NoRedirect).open(_request(origin, path), timeout=12) as response:
        if response.status != 200:
            raise ValueError(f"{path} returned HTTP {response.status}, expected 200")
        content_type = response.headers.get("Content-Type", "")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"{path} exceeded the check size limit")
        return content_type, data.decode("utf-8")


def fetch_raw(origin: str, path: str, *, limit: int = 65536) -> tuple[int, dict, str]:
    """Returns (status, lower-cased headers, body) without following redirects.

    Unlike fetch, non-2xx statuses are data, not failures: several checks
    assert that an endpoint refuses (401) or is absent (404).
    """
    try:
        with build_opener(NoRedirect).open(_request(origin, path), timeout=12) as response:
            status = response.status
            headers = {key.lower(): value for key, value in response.headers.items()}
            data = response.read(limit + 1)
    except HTTPError as exc:
        status = exc.code
        headers = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        try:
            data = exc.read(limit + 1)
        except Exception:
            data = b""
    if len(data) > limit:
        raise ValueError(f"{path} exceeded the check size limit")
    return status, headers, data.decode("utf-8", "replace")


def _is_login_redirect(status: int, headers: dict) -> bool:
    location = (headers.get("location") or "").strip()
    return status in (301, 302, 303, 307, 308) and location.startswith("/login")


def verify(origin: str, *, get=fetch, get_raw=fetch_raw) -> None:
    origin = normalise_app_url(origin)
    if not origin.startswith("https://"):
        raise ValueError("The public full app must use a real HTTPS domain")
    warnings: list[str] = []

    status, headers, body = get_raw(origin, "/health")
    if status != 200:
        raise ValueError(f"/health returned HTTP {status}, expected 200")
    if "application/json" not in headers.get("content-type", ""):
        raise ValueError("/health did not return JSON")
    health = json.loads(body)
    if (health.get("ok") is not True or not isinstance(health.get("brand"), str)
            or not health["brand"].strip()):
        raise ValueError("/health did not identify a running EngineVerse app")
    if "users" in health or "tables" in health:
        raise ValueError("/health exposes development-only fields: use a production deployment")
    for header, meaning in (
        ("strict-transport-security", "HSTS"),
        ("content-security-policy", "Content-Security-Policy"),
        ("x-content-type-options", "X-Content-Type-Options"),
    ):
        if header not in headers:
            warnings.append(f"missing {meaning} header on /health response")

    kind, body = get(origin, "/manifest.webmanifest")
    if "application/manifest+json" not in kind and "application/json" not in kind:
        raise ValueError("Android web manifest is missing")
    manifest = json.loads(body)
    if manifest.get("start_url") != "/" or manifest.get("scope") != "/" or not manifest.get("icons"):
        raise ValueError("The full app must serve a root-scoped PWA manifest")
    for path, marker in (("/login", 'action="/login"'),
                         ("/register", 'action="/register"'),
                         ("/install", "Android")):
        kind, body = get(origin, path)
        if "text/html" not in kind or marker not in body:
            raise ValueError(f"{path} is not an accessible full-app page")

    # --- recovery flow: the form must exist and must not leak a token -------
    status, headers, body = get_raw(origin, "/forgot-password")
    if status != 200 or "action=\"/forgot-password\"" not in body:
        raise ValueError("/forgot-password does not serve the recovery form")
    if "Development build" in body or "reset-password?token=" in body:
        raise ValueError("/forgot-password reveals reset tokens: development mode is on")

    # --- data isolation: anonymous callers get refusals, not rows ------------
    for path in ("/api/me", "/api/coding/submissions"):
        status, _headers, body = get_raw(origin, path)
        if status != 401:
            raise ValueError(f"{path} answered HTTP {status} anonymously, expected 401")
        lowered = body.lower()
        if "sign in" not in lowered and '"ok": false' not in lowered and '"ok":false' not in lowered:
            raise ValueError(f"{path} refusal does not explain itself")

    # --- judge honesty: a consumable runnable set, or none visible -----------
    status, _headers, body = get_raw(origin, "/api/coding/languages")
    if status == 401:
        print("Note: catalogue APIs sit behind sign-in; judge shape not observable anonymously.")
    elif status != 200:
        raise ValueError(f"/api/coding/languages returned HTTP {status}, expected 200 or 401")
    else:
        payload = json.loads(body)
        languages = payload.get("languages")
        runnable = payload.get("runnable")
        if not isinstance(languages, list) or not languages:
            raise ValueError("/api/coding/languages returned no language catalogue")
        if not isinstance(runnable, list):
            raise ValueError("/api/coding/languages does not report a runnable set")
        unknown = [entry for entry in runnable if entry not in KNOWN_LANGUAGE_SLUGS]
        if unknown:
            raise ValueError(f"/api/coding/languages reports unknown runnable entries: {sorted(set(unknown))}")
        for language in languages:
            if not isinstance(language, dict) or "slug" not in language or "runnable" not in language:
                raise ValueError("/api/coding/languages entries lack slug/runnable fields")
        if runnable:
            print(f"Judge reports {len(runnable)} runnable language(s): {', '.join(sorted(runnable))}. "
                  "Isolation of that judge was NOT verified by this check.")
        else:
            print("Judge reports no runnable languages: execution is disabled on this host.")

    # --- secret hygiene: dumps, env files and git metadata stay unserved -----
    for path in ("/.env", "/data/engineverse.sqlite", "/.git/config"):
        status, headers, _body = get_raw(origin, path)
        if status == 404 or _is_login_redirect(status, headers):
            continue
        raise ValueError(f"{path} is web-served (HTTP {status}): secrets or dumps may be exposed")

    print("Verified live HTTPS EngineVerse app: health, PWA, login, registration, install, "
          "recovery form, anonymous-API isolation, judge shape and secret hygiene.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    print("Not covered here: account registration, backup restores, mail/SMS delivery and "
          "Judge0 isolation. Run the manual production validation checklist in docs/DEPLOYMENT.md.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="HTTPS origin for the full app")
    args = parser.parse_args()
    try:
        verify(args.url)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Full app is not ready; leaving the Pages reading copy live: {exc}") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
