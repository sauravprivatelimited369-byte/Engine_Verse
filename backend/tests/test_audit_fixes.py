"""Regression tests for the 2026-10-18 full audit fixes.

Each test pins a confirmed finding from docs/AUDIT_2026-10-18.md so the
defect cannot silently return:

* F-03 leaderboard period/field mismatch and privacy opt-out
* F-04 settings preference checkboxes ignoring stored values
* F-05 raw diagram hotspot JSON emitted with |safe in an attribute
* F-06 anonymous ValueError for non-integer numeric environment variables
* F-02 static-copy code runner honesty (contract-level, like
  test_pages_live_contract.py)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engineverse import auth, db, progress
from engineverse.security.ids import now_ms, ulid

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "AuditFixPass#2026"
DAY_MS = 86_400_000


def _learner(tag: str) -> dict:
    return auth.register(
        email=f"{tag}@example.com", username=tag, password=PASSWORD,
        full_name=f"Audit {tag}",
    )


def _csrf(html: str) -> str:
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]


@pytest.mark.usefixtures("seeded")
class TestLeaderboardAuditFixes:
    def test_week_and_month_periods_rank_by_recent_xp_not_all_time(self):
        """The page submits period=week/month; the query only knew weekly/monthly."""
        suffix = os.urandom(3).hex()
        veteran = _learner(f"auditvet{suffix}")
        newcomer = _learner(f"auditnew{suffix}")
        # Veteran: large all-time total, but every XP event is 40 days old.
        db.execute("UPDATE streaks SET total_xp = 1000 WHERE user_id = ?", veteran["id"])
        db.execute(
            "INSERT INTO xp_events (id,user_id,amount,reason,created_at) VALUES (?,?,?,?,?)",
            ulid(), veteran["id"], 1000, "question.correct", now_ms() - 40 * DAY_MS,
        )
        # Newcomer: small total, earned just now.
        progress.award_xp(newcomer["id"], 50, "question.correct", "question", "audit-q")

        all_rows = {r["username"]: r for r in progress.leaderboard(period="all", limit=200)}
        assert all_rows[veteran["username"]]["xp"] > all_rows[newcomer["username"]]["xp"]

        for spelling in ("week", "weekly"):
            rows = {r["username"]: r for r in progress.leaderboard(period=spelling, limit=200)}
            assert rows[newcomer["username"]]["xp"] == 50, spelling
            assert rows[veteran["username"]]["xp"] == 0, spelling
        for spelling in ("month", "monthly"):
            rows = {r["username"]: r for r in progress.leaderboard(period=spelling, limit=200)}
            assert rows[veteran["username"]]["xp"] == 0, spelling

    def test_rows_carry_the_fields_the_template_renders(self):
        rows = progress.leaderboard(period="all", limit=5)
        assert rows, "seeded leaderboard should not be empty"
        for row in rows:
            # leaderboard.html reads current_streak and topics; both used to
            # be absent (streak was aliased "streak"), rendering blanks.
            assert row["current_streak"] is not None
            assert row["streak"] == row["current_streak"]
            assert isinstance(row["topics"], int)

    def test_show_progress_opt_out_hides_learner_from_leaderboard(self):
        suffix = os.urandom(3).hex()
        private = _learner(f"auditpriv{suffix}")
        progress.award_xp(private["id"], 25, "question.correct", "question", "audit-q2")
        usernames = {r["username"] for r in progress.leaderboard(limit=200)}
        assert private["username"] in usernames

        db.execute(
            "UPDATE profiles SET privacy = ? WHERE user_id = ?",
            json.dumps({"showEmail": False, "showActivity": True,
                        "showProgress": False, "searchable": True}),
            private["id"],
        )
        usernames = {r["username"] for r in progress.leaderboard(limit=200)}
        assert private["username"] not in usernames, (
            "a learner who opted out of showing progress is still ranked publicly"
        )


@pytest.mark.usefixtures("seeded")
class TestSettingsPreferencesRenderStoredValues:
    def test_unchecked_privacy_stays_unchecked_and_survives_a_resave(self, signed_in, demo_user):
        db.execute(
            "UPDATE profiles SET privacy = ?, notification_prefs = ? WHERE user_id = ?",
            json.dumps({"showEmail": True, "showActivity": False,
                        "showProgress": False, "searchable": False}),
            json.dumps({"newDpp": False, "streakReminder": True,
                        "milestone": False, "communityReply": True}),
            demo_user["id"],
        )
        page = signed_in.get("/settings")
        assert page.status_code == 200

        def checkbox(name: str) -> str:
            start = page.text.index(f'name="{name}"')
            return page.text[page.text.rindex("<input", 0, start):page.text.index(">", start)]

        assert "checked" not in checkbox("show_progress")
        assert "checked" not in checkbox("show_activity")
        assert "checked" not in checkbox("searchable")
        assert "checked" in checkbox("show_email")
        assert "checked" not in checkbox("new_dpp")
        assert "checked" in checkbox("streak_reminder")

        # Saving the form as rendered (browser sends only ticked boxes) must
        # not silently re-enable the opted-out settings.
        response = signed_in.post(
            "/settings/preferences",
            data={"csrf_token": _csrf(page.text), "show_email": "on",
                  "streak_reminder": "on", "community_reply": "on"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        stored = json.loads(db.query_one(
            "SELECT privacy FROM profiles WHERE user_id = ?", demo_user["id"])["privacy"])
        assert stored["showProgress"] is False
        assert stored["searchable"] is False
        assert stored["showEmail"] is True


class TestDiagramHotspotEscaping:
    def test_topic_template_does_not_emit_raw_hotspot_json(self):
        template = (ROOT / "backend" / "templates" / "topic.html").read_text(encoding="utf-8")
        assert "diagram.hotspots | safe" not in template
        assert "hotspots_data | tojson | forceescape" in template

    def test_hotspot_attribute_round_trips_through_escaping(self):
        from jinja2 import Environment

        env = Environment(autoescape=True)
        rendered = env.from_string(
            '<figure data-hotspots="{{ d | tojson | forceescape }}">'
        ).render(d=[{"label": "Bernoulli's \"principle\" <script>", "x": 1}])
        assert "<script>" not in rendered
        assert 'data-hotspots="[{&#34;' in rendered


class TestConfigIntegerValidation:
    def test_non_integer_env_var_names_itself(self, monkeypatch):
        from engineverse.config import Settings

        monkeypatch.setenv("ENGINEVERSE_JUDGE_TIMEOUT_MS", "5s")
        with pytest.raises(RuntimeError, match="ENGINEVERSE_JUDGE_TIMEOUT_MS"):
            Settings()

    def test_integer_env_var_still_parses(self, monkeypatch):
        from engineverse.config import Settings

        monkeypatch.setenv("ENGINEVERSE_JUDGE_TIMEOUT_MS", "7000")
        assert Settings().judge_timeout_ms == 7000


class TestStaticRunnerHonestyContract:
    """The Pages runtime must never fabricate a pass (AUDIT F-02)."""

    @pytest.fixture(scope="class")
    def runtime(self) -> str:
        return (ROOT / "backend" / "static" / "js" / "pages-live.js").read_text(encoding="utf-8")

    def test_no_expected_output_is_copied_as_program_output(self, runtime):
        # The old "Structured AST verifier" returned matchedCase.expected as
        # stdout with status accepted for C/Java/Go/... submissions.
        assert "matchedCase" not in runtime
        assert "Structured AST" not in runtime

    def test_unrunnable_languages_report_not_executed(self, runtime):
        assert 'status: "unsupported_language"' in runtime
        assert "executed: false" in runtime
        assert "Your code was not executed" in runtime
        assert "cannot run here" in runtime

    def test_static_copy_offers_no_otp_or_sign_in(self, runtime):
        for claim in ("OTP Sent", "Dispatched to", "Instant verification code",
                      "Sent 6-digit", "otp_api_url\")", "sendOtp", "verifyOtp"):
            assert claim not in runtime, claim

    def test_static_copy_uploads_nothing(self, runtime):
        assert "toGithubSnapshot" not in runtime
        assert "api.github.com" not in runtime
        assert "fetch(\"https://" not in runtime

    def test_exporter_keeps_an_honest_runner_notice(self):
        from scripts import export_pages

        assert "not executed" in export_pages.STATIC_RUNNER_NOTICE
        enabled = export_pages.enable_problem_editor(
            '<select id="lang-select"><option value="cpp" disabled>C++ (starter only)</option></select>'
            '<div class="callout warning mb"><span class="label">Code execution is off</span> x</div>'
            '<button class="btn btn-ghost" id="btn-run" type="button">Run</button>'
        )
        assert "Static-copy runner" in enabled
        assert "Code execution is off" not in enabled
