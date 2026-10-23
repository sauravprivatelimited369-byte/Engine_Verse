"""Execution honesty: nothing may imply code ran when it did not.

When the judge is disabled (the production default) or a language has no
runtime on the host, Run/Submit must report "not run", award no XP, move no
counters, and disable the editor buttons. A refusal presented as a result -
or as XP - is the failure mode these tests pin down.
"""
from __future__ import annotations

import pytest

from engineverse import db, judge
from engineverse.config import reload_settings


def _csrf(html: str) -> str:
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


@pytest.fixture()
def disabled_judge(monkeypatch):
    monkeypatch.setenv("ENGINEVERSE_JUDGE", "disabled")
    reload_settings()
    judge.reset_provider()
    yield
    # Undo the env patch *before* reloading: the monkeypatch finaliser runs
    # after this fixture's teardown, so reloading first would cache the
    # still-disabled settings for every following test (the full-suite-only
    # judge failures). undo() is idempotent; the finaliser calls it again.
    monkeypatch.undo()
    judge.reset_provider()
    reload_settings()


CODE = (
    "def two_sum(nums, target):\n"
    "    seen = {}\n"
    "    for i, v in enumerate(nums):\n"
    "        if target - v in seen:\n"
    "            return [seen[target - v], i]\n"
    "        seen[v] = i\n"
    "    return []\n"
)


class TestNotExecutedVerdicts:
    @pytest.mark.parametrize(
        ("status", "ran"),
        [
            ("accepted", True),
            ("wrong_answer", True),
            ("runtime_error", True),
            ("timeout", True),
            ("compile_error", True),
            ("unsupported_language", False),
            ("sandbox_unavailable", False),
            ("internal_error", False),
        ],
    )
    def test_executed_matches_the_verdict(self, status, ran):
        assert judge.executed(status) is ran

    def test_run_when_disabled_reports_not_executed(self, signed_in, disabled_judge):
        token = _csrf(signed_in.get("/practice/problems/two-sum").text)
        response = signed_in.post(
            "/api/coding/run",
            json={"problemSlug": "two-sum", "language": "python", "code": CODE},
            headers={"x-csrf-token": token},
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["status"] == "unsupported_language"
        assert result["executed"] is False
        assert result["stdout"] == ""
        assert "disabled" in result["stderr"].lower()
        assert result["judge"]["name"] == "disabled"
        assert result["passed"] is None

    def test_submit_when_disabled_awards_no_xp_and_counts_nothing(
        self, signed_in, demo_user, disabled_judge
    ):
        from engineverse import progress

        problem = db.query_one("SELECT id, attempt_count, solve_count FROM coding_problems WHERE slug = 'two-sum'")
        xp_before = progress.total_xp(demo_user["id"])
        token = _csrf(signed_in.get("/practice/problems/two-sum").text)
        response = signed_in.post(
            "/api/coding/submit",
            json={"problemSlug": "two-sum", "language": "python", "code": CODE},
            headers={"x-csrf-token": token},
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["executed"] is False
        assert result["xp"] == 0
        assert result["firstAccepted"] is False
        after = db.query_one("SELECT attempt_count, solve_count FROM coding_problems WHERE id = ?", problem["id"])
        assert after["attempt_count"] == problem["attempt_count"], "an unjudged submission moved attempt_count"
        assert after["solve_count"] == problem["solve_count"]
        assert progress.total_xp(demo_user["id"]) == xp_before, "an unjudged submission awarded XP"
        row = db.query_one(
            "SELECT status, is_accepted FROM coding_submissions WHERE id = ?", result["id"]
        )
        assert row is not None and row["is_accepted"] == 0

    def test_an_unknown_language_is_not_executed(self, signed_in, disabled_judge):
        token = _csrf(signed_in.get("/practice/problems/two-sum").text)
        response = signed_in.post(
            "/api/coding/run",
            json={"problemSlug": "two-sum", "language": "brainfuck", "code": "++++"},
            headers={"x-csrf-token": token},
        )
        assert response.status_code == 200, response.text
        assert response.json()["result"]["executed"] is False


class TestProblemPageHonesty:
    def test_disabled_judge_disables_run_and_submit(self, signed_in, disabled_judge):
        html = signed_in.get("/practice/problems/two-sum").text
        assert "Code execution is off" in html
        assert "judge: disabled" in html
        assert "Supported here: none" in html
        run = html[html.index('id="btn-run"') : html.index('id="btn-run"') + 200]
        assert "disabled" in run, "Run stays enabled while execution is off"
        submit_at = html.index('id="btn-submit"')
        submit = html[submit_at : submit_at + 200]
        assert "disabled" in submit, "Submit stays enabled while execution is off"

    def test_page_names_what_can_run_here(self, client):
        html = client.get("/practice/problems/two-sum").text
        assert "Supported here:" in html
        # Every listed language is either runnable or explicitly marked as
        # having no runtime on this server.
        assert "(no runtime here)" in html or "Code execution is off" in html or "Runnable" in html

    def test_languages_api_reports_runnable_separately(self, client):
        body = client.get("/api/coding/languages").json()
        assert body["ok"] is True
        assert isinstance(body["runnable"], list)
        for language in body["languages"]:
            assert "runnable" in language
