"""Tests for `scripts/redact_public_issue.py` (owner-triggered #39 redaction).

The script backs `.github/workflows/redact-public-issue.yml`. Everything here
runs offline against a fake API; no write ever reaches GitHub.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses resolve string annotations via
    # sys.modules while the module is still being executed.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scan = _load("scan_public_credentials")
redact = _load("redact_public_issue")

DIGEST = "cd" * 32
REPLACEMENT = (REPO / "docs/INCIDENT_ISSUE_39_REPLACEMENT_BODY.md").read_text(encoding="utf-8")


class FakeApi:
    def __init__(self, issue):
        self.issue = issue
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, url, token, payload=None):
        self.calls.append((method, url, payload))
        if method == "GET":
            return dict(self.issue)
        return {"state": payload.get("state"), "state_reason": payload.get("state_reason")}

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]


def dirty_issue(body=None, **extra):
    issue = {
        "number": 39,
        "state": "open",
        "title": "[learner-sync] @learner",
        "body": body if body is not None else f'{{"password_sha256": "{DIGEST}"}}',
    }
    issue.update(extra)
    return issue


class TestRefusals:
    def test_refuses_to_overwrite_a_clean_issue(self):
        api = FakeApi(dirty_issue(body='{"password_sha256": ""}'))
        result = redact.redact_issue(
            "owner/name", 39, REPLACEMENT, "t", redact._CONFIRM_PHRASE, request=api
        )
        assert result["changed"] is False
        assert result["reason"] == "no-credential-material"
        assert api.writes == []

    def test_refuses_pull_requests(self):
        api = FakeApi(dirty_issue(pull_request={"url": "https://api.github.com/pulls/39"}))
        with pytest.raises(redact.RedactionError, match="pull request"):
            redact.redact_issue(
                "owner/name", 39, REPLACEMENT, "t", redact._CONFIRM_PHRASE, request=api
            )
        assert api.writes == []

    def test_refuses_without_the_confirm_phrase(self):
        api = FakeApi(dirty_issue())
        with pytest.raises(redact.RedactionError, match="confirm"):
            redact.redact_issue("owner/name", 39, REPLACEMENT, "t", "", request=api)
        with pytest.raises(redact.RedactionError, match="confirm"):
            redact.redact_issue("owner/name", 39, REPLACEMENT, "t", "yes", request=api)
        assert api.writes == []

    def test_refuses_a_replacement_body_that_carries_a_digest(self):
        api = FakeApi(dirty_issue())
        with pytest.raises(redact.RedactionError, match="replacement body"):
            redact.redact_issue(
                "owner/name",
                39,
                f'{{"password_sha256": "{DIGEST}"}}',
                "t",
                redact._CONFIRM_PHRASE,
                request=api,
            )
        assert api.writes == []

    def test_rejects_issue_zero(self):
        with pytest.raises(redact.RedactionError):
            redact.redact_issue("owner/name", 0, REPLACEMENT, "t", "", dry_run=True)


class TestRedaction:
    def test_dry_run_reads_but_never_writes(self):
        api = FakeApi(dirty_issue())
        result = redact.redact_issue(
            "owner/name", 39, REPLACEMENT, "t", "", dry_run=True, request=api
        )
        assert result == {
            "number": 39,
            "changed": False,
            "reason": "dry-run",
            "fields": ("password_sha256",),
            "state": "open",
        }
        assert api.writes == []

    def test_confirmed_run_replaces_body_and_closes(self):
        api = FakeApi(dirty_issue())
        result = redact.redact_issue(
            "owner/name", 39, REPLACEMENT, "t", redact._CONFIRM_PHRASE, request=api
        )
        assert result["changed"] is True
        assert result["state"] == "closed"
        assert result["state_reason"] == "not_planned"
        assert len(api.writes) == 1
        method, url, payload = api.writes[0]
        assert method == "PATCH"
        assert url.endswith("/repos/owner/name/issues/39")
        assert payload["body"] == REPLACEMENT
        assert payload["state"] == "closed"
        assert payload["state_reason"] == "not_planned"

    def test_credential_in_a_comment_is_not_silently_ignored(self):
        # The script redacts bodies; a comment needs the manual procedure.
        # A clean body must not make it claim success.
        api = FakeApi(dirty_issue(body="progress only, see comment"))
        result = redact.redact_issue(
            "owner/name", 39, REPLACEMENT, "t", redact._CONFIRM_PHRASE, request=api
        )
        assert result["reason"] == "no-credential-material"
        assert api.writes == []


class TestOutput:
    def test_rendered_output_never_contains_the_value(self):
        api = FakeApi(dirty_issue())
        result = redact.redact_issue(
            "owner/name", 39, REPLACEMENT, "t", redact._CONFIRM_PHRASE, request=api
        )
        text = redact.render_result(result)
        assert DIGEST not in text
        assert "#39" in text
        assert "password_sha256" in text
        assert "rotate" in text

    def test_self_test_passes(self, capsys):
        assert redact.main(["--self-test"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_repository_replacement_body_is_clean(self):
        # The body the workflow pastes must itself be credential-free.
        assert scan.credential_fields_in_text(REPLACEMENT) == ()
        assert "redacted" in REPLACEMENT.lower()
        assert "credential" in REPLACEMENT.lower()


class TestWorkflowBoundary:
    def test_workflow_is_manual_only_and_scopes_issues_write(self):
        workflow = (
            REPO / ".github/workflows/redact-public-issue.yml"
        ).read_text(encoding="utf-8")
        assert "workflow_dispatch:" in workflow
        assert "pull_request_target" not in workflow
        assert "repository_dispatch" not in workflow
        assert "schedule:" not in workflow
        permissions = workflow[workflow.index("permissions:") : workflow.index("concurrency:")]
        assert "issues: write" in permissions
        assert "contents: read" in permissions
        # Inputs must reach the script through env, never shell interpolation.
        assert "--issue \"$ISSUE\"" in workflow
        assert "${{ inputs.issue }}" not in workflow.split("run: |")[-1]
