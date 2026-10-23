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


def _code_only(js: str) -> str:
    """Strip comments so explanations of removed features do not count."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", js)


class TestNoCredentialsInTheStaticCopy:
    """Issue #39 follow-up. The original defence (blank the hashes before a
    registry snapshot) was superseded: the static copy no longer has accounts,
    so there are no credentials to blank and no snapshot to send."""

    def test_runtime_has_no_snapshot_or_credential_code(self):
        code = _code_only(PAGES_JS)
        for gone in ("mergeSnapshotIntoStore", "toGithubSnapshot", "password_sha256",
                     "email_sha256", "phone_sha256", "api.github.com", "Authorization"):
            assert gone not in code, gone

    def test_imported_profiles_are_whitelisted(self):
        body = PAGES_JS[PAGES_JS.index("function sanitizeProfile"):]
        body = body[: body.index("\n  }\n")]
        assert "const p = defaultProfile();" in body
        # Fields are copied one by one; the raw object is never spread or assigned.
        assert "...raw" not in body
        assert "Object.assign(p, raw" not in body
        assert "password" not in _code_only(body)


class TestPublicRegistryBoundary:
    def test_public_learner_registry_and_sync_are_gone(self):
        assert not (REPO / "data/learners/registry.json").exists()
        assert not (REPO / ".github/workflows/learner-data-sync.yml").exists()
        for wf in (REPO / ".github/workflows").glob("*.yml"):
            text = wf.read_text(encoding="utf-8")
            assert "sync_learner_data" not in text, wf.name
            assert "data/learners" not in text, wf.name


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
