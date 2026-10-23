#!/usr/bin/env python3
"""Read-only scan for credential material posted in a repository's public issues.

This implements step 4 of `docs/INCIDENT_RESPONSE.md`: look for
`password_sha256`, `password_digest`, `email_sha256` and `phone_sha256` in
issues, pull requests, and their comments. It exists because issue #39 carried
a `password_sha256` value from the pre-fix static-copy sync flow for three days
and nothing in the repository could see it: a repository scan cannot read
public issue bodies.

Properties that matter:

* **It never prints a matched value.** A report names the issue/PR number, the
  location, and the field — never the digest. That keeps the scan output safe
  to paste into a ticket or a CI log.
* **It is read-only.** It calls two GET endpoints and nothing else. The
  accompanying workflow grants `contents: read`, `issues: read`,
  `pull-requests: read` and no write scope.
* **Empty fields are not findings.** Current snapshots are progress-only and
  still serialise `"password_sha256": ""` for schema compatibility. Flagging
  that would make every reviewed sync issue a false positive, so only a
  digest-shaped, non-empty value counts.

Exit codes: ``0`` clean, ``1`` findings, ``2`` usage/API failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# The four field names named in docs/INCIDENT_RESPONSE.md. They are searched
# case-insensitively because legacy clients were not consistent about it.
CREDENTIAL_FIELDS = ("password_sha256", "password_digest", "email_sha256", "phone_sha256")

_API_ROOT = "https://api.github.com"
_REPO_SHAPE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# `"password_sha256": "<value>"`, `password_digest: <value>`, or the same with
# single quotes. The third group covers an unquoted token.
_FIELD_PATTERNS = {
    field: re.compile(
        rf"""["']?{field}["']?\s*[:=]\s*(?:"([^"]*)"|'([^']*)'|([^\s,}}\]]+))""",
        re.IGNORECASE,
    )
    for field in CREDENTIAL_FIELDS
}

# SHA-256, SHA-512, scrypt/argon2 hex digests: 32+ hex characters. The device
# local Pages digest is exactly 64 hex characters; a truncated or salted hex
# digest still matches. Deliberately hex-only: a field whose value is prose
# ("redacted", "empty") is not credential material and must not fail CI.
_DIGEST_SHAPE = re.compile(r"^[0-9a-fA-F]{32,}$")

_PLACEHOLDERS = {"", "empty", "none", "null", "redacted", "<redacted>", "[redacted]"}


class ScanError(RuntimeError):
    """The scan could not be completed; the message never contains a token."""


@dataclass(frozen=True)
class Finding:
    """One post that carries a digest-shaped credential value.

    The value itself is intentionally not stored: a dataclass that can be
    printed or logged must not carry the secret it found.
    """

    number: int
    kind: str  # "issue" or "pull request"
    location: str  # "body" or "comment"
    fields: tuple[str, ...]
    comment_id: int | None = None


def _value(match: re.Match[str]) -> str:
    for group in match.groups():
        if group is not None:
            return group
    return ""


def _looks_like_digest(value: str) -> bool:
    cleaned = value.strip()
    if cleaned.lower() in _PLACEHOLDERS:
        return False
    return bool(_DIGEST_SHAPE.match(cleaned))


def credential_fields_in_text(text: str) -> tuple[str, ...]:
    """Return the credential field names carrying a non-empty digest value."""

    if not text:
        return ()
    hits: list[str] = []
    for field, pattern in _FIELD_PATTERNS.items():
        for match in pattern.finditer(text):
            if _looks_like_digest(_value(match)):
                hits.append(field)
                break
    return tuple(sorted(hits))


def _request_json(url: str, token: str, timeout: float = 30.0):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "engineverse-public-credential-scan",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message", "")
        except Exception:  # noqa: BLE001 - the body is not trusted to be JSON
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise ScanError(
            f"GitHub API returned HTTP {exc.code} for {url.split('?')[0]}{suffix}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ScanError(f"Could not reach api.github.com: {exc.reason}") from exc


def scan_repository(
    repo: str,
    token: str,
    fetch=None,
    per_page: int = 100,
    max_items: int = 1000,
) -> tuple[list[Finding], int]:
    """Scan every issue/PR body and comment reachable through the REST API.

    Returns ``(findings, items_scanned)``. Pull requests come back from the
    issues endpoint with a ``pull_request`` key; their comments use the same
    endpoint, so one crawl covers both.
    """

    if not _REPO_SHAPE.match(repo):
        raise ScanError(f"--repo must look like owner/name, got {repo!r}")
    if per_page < 1 or per_page > 100:
        raise ScanError("--per-page must be between 1 and 100")
    # Resolve at call time, not definition time, so tests (and callers) can
    # substitute a fetcher without re-importing the module.
    request = fetch or _request_json

    findings: list[Finding] = []
    scanned = 0
    page = 1
    while scanned < max_items:
        batch = request(
            f"{_API_ROOT}/repos/{repo}/issues?state=all&per_page={per_page}&page={page}",
            token,
        )
        if not isinstance(batch, list):
            raise ScanError("Unexpected response from the issues endpoint.")
        if not batch:
            break
        for item in batch:
            if scanned >= max_items:
                break
            scanned += 1
            number = int(item.get("number") or 0)
            kind = "pull request" if item.get("pull_request") else "issue"
            body_fields = credential_fields_in_text(
                f"{item.get('title') or ''}\n{item.get('body') or ''}"
            )
            if body_fields:
                findings.append(Finding(number, kind, "body", body_fields))

            comment_page = 1
            while True:
                comments = request(
                    f"{_API_ROOT}/repos/{repo}/issues/{number}/comments"
                    f"?per_page={per_page}&page={comment_page}",
                    token,
                )
                if not isinstance(comments, list):
                    raise ScanError("Unexpected response from the comments endpoint.")
                if not comments:
                    break
                for comment in comments:
                    comment_fields = credential_fields_in_text(comment.get("body") or "")
                    if comment_fields:
                        findings.append(
                            Finding(
                                number,
                                kind,
                                "comment",
                                comment_fields,
                                comment_id=comment.get("id"),
                            )
                        )
                if len(comments) < per_page:
                    break
                comment_page += 1
        if len(batch) < per_page:
            break
        page += 1

    findings.sort(key=lambda finding: (finding.number, finding.location, finding.comment_id or 0))
    return findings, scanned


def render_report(repo: str, findings: list[Finding], scanned: int) -> str:
    lines = [
        f"Public credential scan for {repo}: {scanned} issue(s)/PR(s) checked "
        "(titles, bodies, comments).",
    ]
    if not findings:
        lines.append("No digest-shaped credential value found. This is not proof that none exists:")
        lines.append("the scan only sees what the API returns and only recognises hex digests.")
        return "\n".join(lines)

    lines.append(f"{len(findings)} finding(s). Matched values are deliberately not printed:")
    for finding in findings:
        where = f"comment {finding.comment_id}" if finding.comment_id else "body"
        lines.append(
            f"  - #{finding.number} ({finding.kind}) {where}: {', '.join(finding.fields)}"
        )
    lines.append("")
    lines.append("Treat each value as permanently public, even after editing the post: GitHub may")
    lines.append("retain edit history. Follow docs/INCIDENT_RESPONSE.md and")
    lines.append("docs/INCIDENT_ISSUE_39_REDACTION.md. Do not quote the value in a ticket,")
    lines.append("comment, or commit.")
    return "\n".join(lines)


def self_check() -> None:
    """Offline checks, so the detector can be verified without a network or a repo."""

    assert credential_fields_in_text('{"password_sha256": ""}') == ()
    assert credential_fields_in_text('{"password_sha256": null}') == ()
    assert credential_fields_in_text('"password_sha256": "<redacted>"') == ()
    digest = "ab" * 32
    assert credential_fields_in_text(f'{{"password_sha256": "{digest}"}}') == ("password_sha256",)
    assert credential_fields_in_text(f"password_digest: {digest}") == ("password_digest",)
    assert credential_fields_in_text(f"EMAIL_SHA256='{digest}'") == ("email_sha256",)
    assert credential_fields_in_text(f"phone_sha256: {digest[:16]}") == ()
    assert credential_fields_in_text("password_sha256 is documented but empty") == ()

    finding = Finding(39, "issue", "body", ("password_sha256",))
    report = render_report("owner/name", [finding], 1)
    assert digest not in report
    assert "#39" in report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/name (default: $GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "",
        help="read-capable token (default: $GITHUB_TOKEN or $GH_TOKEN)",
    )
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--max-items", type=int, default=1000)
    parser.add_argument("--self-test", action="store_true", help="run offline checks and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        self_check()
        print("scan_public_credentials self-check: OK")
        return 0

    if not args.repo:
        print("error: --repo (or GITHUB_REPOSITORY) is required", file=sys.stderr)
        return 2
    if not args.token:
        print(
            "error: a read-capable token is required (--token, $GITHUB_TOKEN, or $GH_TOKEN). "
            "Unauthenticated requests are limited to 60 per hour, which a real scan exceeds.",
            file=sys.stderr,
        )
        return 2

    try:
        findings, scanned = scan_repository(
            args.repo, args.token, per_page=args.per_page, max_items=args.max_items
        )
    except ScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_report(args.repo, findings, scanned))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
