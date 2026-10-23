"""Regression tests for the 2026-10-19 follow-up audit.

Covers: public issue #39 credential exposure (defence in depth), the SRS
ease-factor cap (F-19), and the public-registry privacy boundary.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGES_JS = (REPO / "backend/static/js/pages-live.js").read_text(encoding="utf-8")


class TestRemoteSnapshotCannotSetCredentials:
    """A registry snapshot is untrusted: merging it must never adopt hashes."""

    def test_merge_preserves_only_local_credential_hashes(self):
        merge = PAGES_JS[PAGES_JS.index("function mergeSnapshotIntoStore"):]
        merge = merge[: merge.index("\n  }", merge.index("store.accounts[uname] = merged"))]
        assert 'password_sha256: existing.password_sha256 || ""' in merge
        assert 'email_sha256: existing.email_sha256 || ""' in merge
        assert 'phone_sha256: existing.phone_sha256 || ""' in merge
        assert "snapshot.password_sha256" not in merge
        assert "snapshot.email_sha256" not in merge
        assert "snapshot.phone_sha256" not in merge

    def test_outgoing_snapshot_still_sends_empty_credential_fields(self):
        snap = PAGES_JS[PAGES_JS.index("function toGithubSnapshot"):]
        snap = snap[: snap.index("\n  }", snap.index("updated_at:"))]
        assert 'password_sha256: ""' in snap
        assert 'email_sha256: ""' in snap


class TestPublicRegistryBoundary:
    def test_committed_registry_holds_no_credential_material(self):
        data = json.loads((REPO / "data/learners/registry.json").read_text(encoding="utf-8"))
        for username, rec in (data.get("learners") or {}).items():
            for key in ("password_digest", "password_sha256", "email_sha256", "phone_sha256"):
                assert rec.get(key, "") == "", f"{username}.{key} must be empty in the public registry"
            assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", json.dumps(rec))

    def test_sync_workflow_never_triggers_on_public_issues(self):
        wf = (REPO / ".github/workflows/learner-data-sync.yml").read_text(encoding="utf-8")
        assert "issues:" not in wf
        assert "workflow_dispatch" in wf


class TestSrsEaseCap:
    def test_repeated_easy_ratings_cannot_inflate_ease_without_bound(self, signed_in, seeded):
        from engineverse import db

        card = db.query_one("SELECT id FROM flashcards LIMIT 1")
        user = db.query_one("SELECT id FROM users WHERE username = 'asha'")

        def _csrf(html: str) -> str:
            marker = 'name="csrf_token" value="'
            start = html.index(marker) + len(marker)
            return html[start : html.index('"', start)]

        token = _csrf(signed_in.get("/practice").text)
        for _ in range(12):
            resp = signed_in.post(
                "/api/revision/review",
                json={"cardId": card["id"], "rating": "easy"},
                headers={"x-csrf-token": token},
            )
            assert resp.status_code == 200, resp.text
        row = db.query_one(
            "SELECT ease_factor FROM user_flashcards WHERE user_id = ? AND flashcard_id = ?",
            user["id"], card["id"],
        )
        assert float(row["ease_factor"]) <= 2.8
