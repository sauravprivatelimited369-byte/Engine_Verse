"""Tests for `scripts/scan_public_credentials.py` (issue #39 detection).

The detector implements step 4 of `docs/INCIDENT_RESPONSE.md`: find credential
material posted in public issues/PRs/comments. These tests run offline; no
GitHub API call is made.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/scan_public_credentials.py"

_SPEC = importlib.util.spec_from_file_location("scan_public_credentials", SCRIPT)
assert _SPEC and _SPEC.loader
scan = importlib.util.module_from_spec(_SPEC)
# `from __future__ import annotations` + dataclasses look the module up in
# sys.modules while resolving string annotations, so register it first.
sys.modules[_SPEC.name] = scan
_SPEC.loader.exec_module(scan)

# Synthetic, obviously fake digest. The real leaked value must never appear in
# the test suite either.
FAKE_DIGEST = "ab" * 32


class FakeApi:
    """Minimal paged stand-in for the two GET endpoints the scan uses."""

    def __init__(self, issues, comments=None):
        self.issues = issues
        self.comments = comments or {}
        self.calls: list[str] = []

    def __call__(self, url, token):
        assert token  # the scan must always send one
        self.calls.append(url)
        if "/comments" in url:
            number = int(url.split("/issues/")[1].split("/")[0])
            page = int(url.rsplit("page=", 1)[1])
            per_page = int(url.split("per_page=")[1].split("&")[0])
            items = self.comments.get(number, [])
            return items[(page - 1) * per_page : page * per_page]
        page = int(url.rsplit("page=", 1)[1])
        per_page = int(url.split("per_page=")[1].split("&")[0])
        return self.issues[(page - 1) * per_page : page * per_page]


class TestTextDetection:
    def test_empty_credential_fields_are_not_findings(self):
        # Current progress-only snapshots still serialise empty fields for
        # schema compatibility; flagging them would make every sync issue a
        # false positive.
        text = (
            '{"username": "learner", "password_sha256": "", '
            '"email_sha256": "", "phone_sha256": ""}'
        )
        assert scan.credential_fields_in_text(text) == ()

    def test_digest_in_json_body_is_found(self):
        text = '{"username": "learner", "password_sha256": "%s"}' % FAKE_DIGEST
        assert scan.credential_fields_in_text(text) == ("password_sha256",)

    def test_unquoted_and_case_insensitive_forms_are_found(self):
        assert scan.credential_fields_in_text(f"password_digest: {FAKE_DIGEST}") == (
            "password_digest",
        )
        assert scan.credential_fields_in_text(f'EMAIL_SHA256="{FAKE_DIGEST}"') == (
            "email_sha256",
        )
        assert scan.credential_fields_in_text(f"phone_sha256: {FAKE_DIGEST}") == (
            "phone_sha256",
        )

    def test_short_or_prose_values_are_not_findings(self):
        assert scan.credential_fields_in_text("password_sha256: deadbeef") == ()
        assert scan.credential_fields_in_text('"password_sha256": "not set"') == ()
        assert scan.credential_fields_in_text('"password_sha256": "[redacted]"') == ()
        assert scan.credential_fields_in_text("password_sha256 is empty") == ()


class TestRepositoryScan:
    def test_body_and_comment_findings_are_reported_by_location(self):
        api = FakeApi(
            issues=[
                {"number": 1, "title": "clean", "body": '{"password_sha256": ""}'},
                {
                    "number": 2,
                    "title": "sync",
                    "body": f'{{"password_sha256": "{FAKE_DIGEST}"}}',
                },
                {
                    "number": 3,
                    "title": "pr",
                    "body": "no credentials here",
                    "pull_request": {"url": "https://api.github.com/pulls/3"},
                },
            ],
            comments={
                1: [{"id": 11, "body": "looks fine"}],
                2: [{"id": 22, "body": f"leaked: password_sha256={FAKE_DIGEST}"}],
                3: [{"id": 33, "body": "nothing"}],
            },
        )
        findings, scanned = scan.scan_repository("owner/name", "test-token", fetch=api)

        assert scanned == 3
        assert findings == [
            scan.Finding(2, "issue", "body", ("password_sha256",)),
            scan.Finding(2, "issue", "comment", ("password_sha256",), comment_id=22),
        ]

    def test_pagination_walks_every_page(self):
        issues = [
            {"number": n, "title": f"issue {n}", "body": "progress only"}
            for n in range(1, 4)
        ]
        api = FakeApi(issues=issues)
        findings, scanned = scan.scan_repository(
            "owner/name", "test-token", fetch=api, per_page=2
        )
        assert findings == []
        assert scanned == 3
        # page 1 (2 items), page 2 (1 item) -> stop, no empty page request.
        issue_calls = [url for url in api.calls if "/comments" not in url]
        assert len(issue_calls) == 2

    def test_report_never_contains_the_value(self):
        api = FakeApi(
            issues=[
                {"number": 39, "title": "sync", "body": f'{{"password_sha256": "{FAKE_DIGEST}"}}'}
            ]
        )
        findings, scanned = scan.scan_repository("owner/name", "test-token", fetch=api)
        report = scan.render_report("owner/name", findings, scanned)
        assert FAKE_DIGEST not in report
        assert "#39" in report
        assert "password_sha256" in report

    def test_bad_repo_shape_is_rejected(self):
        try:
            scan.scan_repository("not-a-repo", "test-token", fetch=FakeApi([]))
        except scan.ScanError as exc:
            assert "owner/name" in str(exc)
        else:  # pragma: no cover - the assertion below is the point
            raise AssertionError("a repo without owner/name must be rejected")


class TestCommandLine:
    def test_self_test_exits_zero(self, capsys):
        assert scan.main(["--self-test"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_missing_repo_exits_two(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert scan.main(["--token", "x"]) == 2

    def test_findings_exit_one(self, monkeypatch, capsys):
        api = FakeApi(
            issues=[
                {"number": 39, "title": "sync", "body": f'{{"password_sha256": "{FAKE_DIGEST}"}}'}
            ]
        )
        monkeypatch.setattr(scan, "_request_json", api)
        assert scan.main(["--repo", "owner/name", "--token", "test-token"]) == 1
        out = capsys.readouterr().out
        assert "#39" in out
        assert FAKE_DIGEST not in out


class TestWorkflowBoundary:
    def test_scheduled_scan_is_read_only(self):
        workflow = (
            REPO / ".github/workflows/public-credential-scan.yml"
        ).read_text(encoding="utf-8")
        permissions = workflow[workflow.index("permissions:") : workflow.index("jobs:")]
        assert "contents: read" in permissions
        assert "issues: read" in permissions
        assert "pull-requests: read" in permissions
        assert "write" not in permissions
        assert "schedule:" in workflow
        assert "workflow_dispatch:" in workflow
