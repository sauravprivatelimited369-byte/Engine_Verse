#!/usr/bin/env python3
"""Redact and close a public issue that carries credential material.

This is the automated version of `docs/INCIDENT_ISSUE_39_REDACTION.md`. It
exists because the agent environment has no `issues: write` credential, while
the repository's own Actions token does when a maintainer dispatches the
`Redact Public Issue` workflow.

Safety properties:

* **It refuses to edit anything unless the issue actually contains a
  digest-shaped credential value.** Re-running it after redaction is a no-op,
  so it cannot overwrite an issue that has already been cleaned up.
* **It refuses pull requests** and requires `--confirm redact-and-close`
  (or `--dry-run`) before writing.
* **It refuses to paste a replacement body that itself contains a digest.**
* **It never prints the credential value** — only the issue number, the field
  names, and the resulting state.

Exit codes: ``0`` redacted or nothing to do, ``2`` refused or API failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# The detector is shared with the read-only scanner so both agree on what
# counts as credential material.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_public_credentials import credential_fields_in_text  # noqa: E402

_API_ROOT = "https://api.github.com"
_CONFIRM_PHRASE = "redact-and-close"


class RedactionError(RuntimeError):
    """The redaction was refused or could not be completed."""


def _request(
    method: str,
    url: str,
    token: str,
    payload: dict | None = None,
    timeout: float = 30.0,
):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "engineverse-redact-public-issue",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message", "")
        except Exception:  # noqa: BLE001 - the body is not trusted to be JSON
            detail = ""
        suffix = f": {detail}" if detail else ""
        hint = ""
        if exc.code == 403:
            hint = (
                " (the token lacks issues: write; dispatch the workflow from "
                "the repository instead of running this locally with an App token)"
            )
        raise RedactionError(
            f"GitHub API returned HTTP {exc.code} for {method} {url.split('?')[0]}"
            f"{suffix}{hint}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RedactionError(f"Could not reach api.github.com: {exc.reason}") from exc


def redact_issue(
    repo: str,
    number: int,
    replacement: str,
    token: str,
    confirm: str,
    dry_run: bool = False,
    request=_request,
) -> dict:
    """Replace an issue body and close it, but only if it carries a digest."""

    if not repo or "/" not in repo:
        raise RedactionError("--repo must look like owner/name")
    if number < 1:
        raise RedactionError("--issue must be a positive number")
    if not replacement.strip():
        raise RedactionError("the replacement body is empty")
    if credential_fields_in_text(replacement):
        raise RedactionError("refusing to write a replacement body that contains a digest")

    issue = request("GET", f"{_API_ROOT}/repos/{repo}/issues/{number}", token)
    if not isinstance(issue, dict) or "number" not in issue:
        raise RedactionError("unexpected response while reading the issue")
    if issue.get("pull_request"):
        raise RedactionError(
            f"#{number} is a pull request; this script only redacts issues"
        )

    fields = credential_fields_in_text(
        f"{issue.get('title') or ''}\n{issue.get('body') or ''}"
    )
    if not fields:
        return {
            "number": number,
            "changed": False,
            "reason": "no-credential-material",
            "state": issue.get("state"),
        }

    if dry_run:
        return {
            "number": number,
            "changed": False,
            "reason": "dry-run",
            "fields": fields,
            "state": issue.get("state"),
        }

    if confirm != _CONFIRM_PHRASE:
        raise RedactionError(
            f"refusing to edit #{number} without --confirm {_CONFIRM_PHRASE} "
            "(or --dry-run to inspect)"
        )

    updated = request(
        "PATCH",
        f"{_API_ROOT}/repos/{repo}/issues/{number}",
        token,
        {
            "body": replacement,
            "state": "closed",
            "state_reason": "not_planned",
        },
    )
    return {
        "number": number,
        "changed": True,
        "reason": "redacted-and-closed",
        "fields": fields,
        "state": updated.get("state"),
        "state_reason": updated.get("state_reason"),
    }


def render_result(result: dict) -> str:
    number = result.get("number")
    if result.get("changed"):
        return (
            f"#{number}: body replaced and issue closed "
            f"(state={result.get('state')}, reason={result.get('state_reason')}). "
            f"Fields removed: {', '.join(result.get('fields') or [])}. "
            "The value is not printed; treat it as permanently public and rotate it."
        )
    if result.get("reason") == "no-credential-material":
        return (
            f"#{number}: no digest-shaped credential value found "
            f"(state={result.get('state')}). Nothing to do."
        )
    if result.get("reason") == "dry-run":
        return (
            f"#{number}: would redact and close; fields present: "
            f"{', '.join(result.get('fields') or [])}. No write performed."
        )
    return f"#{number}: no action ({result.get('reason')})"


def _fake_request_factory(issue: dict):
    calls: list[tuple[str, str, dict | None]] = []

    def request(method, url, token, payload=None):
        calls.append((method, url, payload))
        if method == "GET":
            return issue
        return {
            "state": payload.get("state"),
            "state_reason": payload.get("state_reason"),
        }

    return request, calls


def self_check() -> None:
    digest = "ab" * 32
    replacement = "redacted body"
    dirty = {"number": 39, "state": "open", "body": f'{{"password_sha256": "{digest}"}}'}
    clean = {"number": 39, "state": "open", "body": '{"password_sha256": ""}'}

    result = redact_issue("owner/name", 39, replacement, "t", "", dry_run=True,
                          request=_fake_request_factory(dirty)[0])
    assert result["reason"] == "dry-run" and result["fields"] == ("password_sha256",)
    assert digest not in render_result(result)

    result = redact_issue("owner/name", 39, replacement, "t", "",
                          request=_fake_request_factory(clean)[0])
    assert result["reason"] == "no-credential-material"

    try:
        redact_issue("owner/name", 39, replacement, "t", "",
                     request=_fake_request_factory(dirty)[0])
    except RedactionError as exc:
        assert "confirm" in str(exc)
    else:  # pragma: no cover - the assertion below is the point
        raise AssertionError("a write without confirmation must be refused")

    request, calls = _fake_request_factory(dirty)
    result = redact_issue("owner/name", 39, replacement, "t", _CONFIRM_PHRASE,
                          request=request)
    assert result["changed"] is True
    assert calls[-1][0] == "PATCH"
    assert calls[-1][2]["state"] == "closed"
    assert calls[-1][2]["body"] == replacement

    try:
        redact_issue("owner/name", 39, f'{{"password_sha256": "{digest}"}}', "t",
                     _CONFIRM_PHRASE, request=_fake_request_factory(dirty)[0])
    except RedactionError as exc:
        assert "replacement body" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a replacement body carrying a digest must be refused")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/name (default: $GITHUB_REPOSITORY)",
    )
    parser.add_argument("--issue", type=int, required=False, help="issue number")
    parser.add_argument(
        "--body-file",
        default=str(Path(__file__).resolve().parents[1]
                    / "docs/INCIDENT_ISSUE_39_REPLACEMENT_BODY.md"),
        help="file holding the redacted replacement body",
    )
    parser.add_argument("--confirm", default="", help=f'must be "{_CONFIRM_PHRASE}"')
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "",
        help="token with issues: write (default: $GITHUB_TOKEN or $GH_TOKEN)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        self_check()
        print("redact_public_issue self-check: OK")
        return 0

    if not args.issue:
        print("error: --issue is required", file=sys.stderr)
        return 2
    if not args.token:
        print("error: a token with issues: write is required", file=sys.stderr)
        return 2

    try:
        replacement = Path(args.body_file).read_text(encoding="utf-8")
        result = redact_issue(
            args.repo,
            args.issue,
            replacement,
            args.token,
            args.confirm,
            dry_run=args.dry_run,
        )
    except (OSError, RedactionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
