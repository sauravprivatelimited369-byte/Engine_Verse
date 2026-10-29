"""Regression tests for the 2026-10-29 audit round.

Each test pins a finding from the 100-point product audit of the published
site, so the defect cannot quietly come back:

* The platform answered "what can I run here?" three different ways, and none
  of them was true of the deployment the reader was on.
* A server deployment claimed JavaScript "runs in your browser" although the
  worker that would have run it only exists on the static copy - and the
  cached answer survived a change of deployment, so one page's answer leaked
  onto another.
* Engineering Mathematics III sat in the first-year catalogue.
* The navigation could not tell the study tutor from the study assistant, nor
  the code compiler from the Python compiler from the coding problems.
* A draft note and a reviewed note looked the same.
* A subject page did not say which regulation its syllabus came from.
* Nothing measured where students gave up, and the obvious fix - a tracker -
  is exactly what this platform refuses to ship.
* A filter that matched nothing left the reader at a dead end.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engineverse import catalog, execution, feedback, navigation

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "backend" / "templates"
STATIC = ROOT / "backend" / "static"


def _csrf(client, path: str = "/") -> str:
    """The anonymous CSRF token the page itself hands out."""
    html = client.get(path).text
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, "the page must carry a CSRF token"
    return match.group(1)


def _sign_in(client) -> str:
    """Signs in as the demo student and returns a fresh CSRF token.

    The token has to be fetched *after* the sign-in: it is bound to the
    session, and signing in replaces the anonymous one.
    """
    token = _csrf(client, "/login")
    client.post(
        "/login",
        data={"csrf_token": token, "identifier": "asha@example.com",
              "password": "LearnBuild#2026!", "next": "/dashboard"},
        follow_redirects=False,
    )
    return _csrf(client, "/dashboard")


# ---------------------------------------------------------------------------
# 1. One answer to "what runs here?"
# ---------------------------------------------------------------------------


class TestExecutionCapabilities:
    def test_a_server_deployment_runs_nothing_in_the_browser(self, monkeypatch):
        """The browser worker is only built on the static copy.

        A server deployment has no /runtimes/ directory and no worker script,
        so "runs in your browser" there was a promise the page could not keep.
        """
        monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT", raising=False)
        caps = execution.capabilities()
        assert caps["browser"]["available"] is False
        assert caps["browser"]["languages"] == []

    def test_the_static_copy_carries_the_browser_engines(self, monkeypatch):
        monkeypatch.setenv("ENGINEVERSE_STATIC_EXPORT", "1")
        caps = execution.capabilities()
        assert caps["static_copy"] is True
        assert caps["browser"]["available"] is True
        assert "python" in caps["browser"]["languages"]
        assert "javascript" in caps["browser"]["languages"]

    def test_the_answer_does_not_depend_on_which_page_was_rendered_first(self, monkeypatch):
        """A cached capability answer leaked from the static copy onto the server.

        The static export and the hosted app are rendered by the same process
        in the test suite, and the browser-language set was cached on first
        use. Whichever page rendered first decided the answer for the rest of
        the process.
        """
        monkeypatch.setenv("ENGINEVERSE_STATIC_EXPORT", "1")
        assert execution.capabilities()["browser"]["available"] is True
        monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT")
        assert execution.capabilities()["browser"]["available"] is False
        monkeypatch.setenv("ENGINEVERSE_STATIC_EXPORT", "1")
        assert execution.capabilities()["browser"]["available"] is True

    def test_every_language_gets_exactly_one_verdict(self, monkeypatch):
        monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT", raising=False)
        caps = execution.capabilities()
        assert caps["languages"], "the catalogue teaches languages; the table must not be empty"
        for row in caps["languages"]:
            assert row["mode"] in {"server", "browser", "unavailable"}
            assert row["label"], f"{row['slug']} has no label"
            if row["mode"] == "unavailable":
                assert row["can_judge"] is False

    def test_a_browser_runtime_never_claims_to_judge(self, monkeypatch):
        """The browser runs a program; the hidden test cases live on the server."""
        monkeypatch.setenv("ENGINEVERSE_STATIC_EXPORT", "1")
        caps = execution.capabilities()
        for row in caps["languages"]:
            if row["mode"] == "browser":
                assert row["can_judge"] is False, row["slug"]

    def test_the_compiler_page_prints_the_capability_table(self, client):
        html = client.get("/compiler").text
        assert "What runs here" in html
        assert "cpl-capabilities" in html

    def test_the_compiler_page_says_when_nothing_executes(self, client, monkeypatch):
        """With no judge and no browser runtime the page must say so plainly."""
        from engineverse import judge
        from engineverse.config import reload_settings

        monkeypatch.setenv("ENGINEVERSE_JUDGE", "disabled")
        monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT", raising=False)
        reload_settings()
        judge.reset_provider()
        try:
            html = client.get("/compiler").text
            assert "Nothing executes on this deployment" in html
        finally:
            monkeypatch.undo()
            judge.reset_provider()
            reload_settings()

    def test_the_problem_page_says_when_nothing_executes(self, client, monkeypatch):
        from engineverse import judge
        from engineverse.config import reload_settings

        monkeypatch.setenv("ENGINEVERSE_JUDGE", "disabled")
        monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT", raising=False)
        reload_settings()
        judge.reset_provider()
        try:
            html = client.get("/practice/problems/two-sum").text
            assert "Code execution is off" in html
        finally:
            monkeypatch.undo()
            judge.reset_provider()
            reload_settings()

    def test_the_sheet_page_agrees_with_the_capability_table(self, client):
        """A sheet must not claim a judge the deployment does not have."""
        html = client.get("/sheets").text
        assert "Code execution is off" not in html


# ---------------------------------------------------------------------------
# 2. The catalogue says what it is
# ---------------------------------------------------------------------------


class TestCatalogueHonesty:
    def test_engineering_mathematics_iii_is_not_a_first_year_subject(self, seeded):
        """It is a third-year course; the first-year shelf was wrong."""
        from engineverse import db

        row = db.query_one(
            "SELECT is_first_year FROM subjects WHERE slug = 'engineering-mathematics-3'"
        )
        assert row is not None, "the subject must exist"
        assert not row["is_first_year"], "Engineering Mathematics III is not a year-one course"

    def test_the_first_year_shelf_holds_only_year_one_courses(self, seeded):
        from engineverse import db

        rows = db.query(
            "SELECT s.slug AS slug, sm.year AS year FROM subjects s "
            "LEFT JOIN semesters sm ON sm.id = s.semester_id "
            "WHERE s.is_first_year = 1 AND s.status = 'published'"
        )
        assert rows, "the first-year shelf must not be empty"
        for row in rows:
            assert row["year"] == 1, f"{row['slug']} is not a year-one course"

    def test_a_subject_carries_its_syllabus_alignment(self, seeded):
        subject = catalog.get_subject("engineering-mathematics-3")
        assert subject is not None
        alignment = catalog.subject_alignment(subject["id"])
        assert alignment["semester_label"], "the semester must be named"
        assert alignment["credits"], "the credits must be stated"
        assert alignment["curricula"], "the subject must name the syllabus it belongs to"
        first = alignment["curricula"][0]
        assert first["university"]
        assert first["effective_year"]

    def test_every_topic_says_whether_it_was_edited(self, seeded):
        from engineverse import db

        topics = db.query("SELECT id FROM topics LIMIT 5")
        assert topics
        for topic in topics:
            review = catalog.topic_review(topic["id"])
            assert review["state"] in {"reviewed", "draft", "needs_review"}
            assert review["label"], "every topic needs a review label"


# ---------------------------------------------------------------------------
# 3. The navigation tells the difference between things
# ---------------------------------------------------------------------------


def _blurbs() -> dict[str, str]:
    out: dict[str, str] = {}
    for section in navigation.SECTIONS:
        for dest in section.destinations:
            out[dest.label] = dest.blurb
    return out


class TestNavigationDistinctions:
    def test_the_tutor_and_the_assistant_are_described_differently(self):
        blurbs = _blurbs()
        tutor = blurbs["Study tutor"]
        assistant = blurbs["Study assistant"]
        assert tutor != assistant
        assert "notes" in tutor.lower()
        assert "assistant" in assistant.lower()

    def test_the_three_code_destinations_are_described_differently(self):
        blurbs = _blurbs()
        problems = blurbs["Coding problems"]
        compiler = blurbs["Code compiler"]
        python = blurbs["Python compiler"]
        assert len({problems, compiler, python}) == 3

    def test_no_two_destinations_in_a_group_say_the_same_thing(self):
        for section in navigation.SECTIONS:
            blurbs = [d.blurb for d in section.destinations if d.blurb]
            assert len(blurbs) == len(set(blurbs)), f"{section.key} repeats a blurb"


# ---------------------------------------------------------------------------
# 4. One product name in the things a reader sees
# ---------------------------------------------------------------------------


class TestBrandConsistency:
    def test_the_readers_own_name_is_published_to_the_browser(self, client):
        html = client.get("/").text
        assert "window.EngineVerse" in html
        assert "siteName" in html

    def test_no_page_calls_the_site_the_wrong_name(self, client):
        """EngineVerse was the repository name; the product is Meridian."""
        for path in ("/", "/explore", "/assistant", "/tutor"):
            html = client.get(path).text
            # Strip the script blocks: the browser namespace is an internal
            # API name, not something a reader sees.
            visible = re.sub(r"<script.*?</script>", "", html, flags=re.S)
            assert "EngineVerse" not in visible, path

    def test_the_voice_reader_uses_the_configured_name(self):
        source = (STATIC / "js" / "voice.js").read_text(encoding="utf-8")
        assert "SITE_NAME" in source
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        # ``window.EngineVerse`` is the browser namespace - an internal API
        # name, not a name a reader sees - and the Android user-agent token is
        # an identifier. What must not exist is the old name inside a string.
        for literal in re.findall(r'"[^"\n]*"|\'[^\'\n]*\'', code):
            if "EngineVerseAndroid" in literal:
                continue
            assert "EngineVerse" not in literal, literal


# ---------------------------------------------------------------------------
# 5. Measurement without a tracker
# ---------------------------------------------------------------------------


class TestPrivacyPreservingFeedback:
    def test_the_tables_hold_no_identifier_column(self):
        schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
        for table in ("content_feedback", "page_stats"):
            block = schema.split(f"CREATE TABLE IF NOT EXISTS {table}", 1)[1]
            block = block.split(");", 1)[0]
            for forbidden in ("user_id", "ip", "email", "session", "user_agent", "device"):
                assert forbidden not in block, f"{table} stores {forbidden}"

    def test_the_path_is_normalised_before_it_is_stored(self):
        assert feedback.normalise_path("/topic/x?ref=email") == "/topic/x"
        assert feedback.normalise_path("/topic/x#part") == "/topic/x"
        assert feedback.normalise_path("https://elsewhere.test/x") == "/"
        assert feedback.normalise_path(None) == "/"

    def test_an_unknown_verdict_is_refused_rather_than_coerced(self):
        result = feedback.vote("/topic/x", "excellent")
        assert result["stored"] is False
        assert result["reason"] == "unknown_verdict"

    def test_a_vote_is_stored_without_anything_that_identifies_a_person(self, seeded):
        result = feedback.vote("/topic/bernoullis-equation", "not_useful", detail="the formula")
        assert result["stored"] is True
        from engineverse import db

        row = db.query_one(
            "SELECT path, kind, verdict, detail FROM content_feedback ORDER BY created_at DESC LIMIT 1"
        )
        assert row["path"] == "/topic/bernoullis-equation"
        assert row["verdict"] == "not_useful"
        assert row["detail"] == "the formula"

    def test_the_summary_needs_the_right_role(self, client):
        response = client.get("/api/content/feedback/summary")
        assert response.status_code in (401, 403)

    def test_the_public_endpoint_refuses_an_unknown_verdict(self, client):
        token = _csrf(client)
        response = client.post(
            "/api/content/feedback",
            json={"path": "/x", "verdict": "excellent"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 400

    def test_the_public_endpoint_stores_a_real_vote(self, client):
        token = _csrf(client)
        response = client.post(
            "/api/content/feedback",
            json={"path": "/topic/bernoullis-equation", "verdict": "useful"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200
        assert response.json().get("stored") is True

    def test_the_widget_is_offered_on_the_pages_it_is_about(self, client):
        for path in ("/topics/bernoullis-equation", "/subjects/engineering-mathematics-3"):
            html = client.get(path).text
            assert "data-ev-useful" in html, path

    def test_the_widget_tells_the_reader_it_is_anonymous(self, client):
        html = client.get("/topics/bernoullis-equation").text
        assert "Anonymous" in html

    def test_a_run_of_votes_from_one_browser_is_capped(self, client):
        """A script must not be able to fill the table with noise.

        The cap is per browser and lives in memory only, so the test uses a
        fresh client (a fresh cookie, therefore a fresh bucket).
        """
        token = _csrf(client)
        stored = 0
        for index in range(25):
            response = client.post(
                "/api/content/feedback",
                json={"path": "/topic/bernoullis-equation", "verdict": "useful",
                      "detail": f"note {index}"},
                headers={"X-CSRF-Token": token},
            )
            assert response.status_code == 200
            if response.json().get("stored"):
                stored += 1
        assert 0 < stored <= 20, f"{stored} votes were stored; the cap is 20 an hour"


# ---------------------------------------------------------------------------
# 6. A filter that matches nothing must not be a dead end
# ---------------------------------------------------------------------------


class TestEmptyStates:
    @pytest.mark.parametrize(
        "path,needle",
        [
            ("/books?q=zzzznotabook", "All books"),
            ("/formulas?q=zzzznotaformula", "All formulas"),
            ("/flashcards?q=zzzznotacard", "All decks"),
        ],
    )
    def test_a_search_with_no_hits_offers_a_way_out(self, client, path, needle):
        html = client.get(path).text
        assert "empty" in html
        assert needle in html

    def test_the_search_page_offers_next_steps(self, client):
        html = client.get("/search?q=zzzznotathing").text
        assert "Browse the catalogue" in html


# ---------------------------------------------------------------------------
# 7. The homepage is a first visit, not a feature list
# ---------------------------------------------------------------------------


class TestHomepageFirstVisit:
    def test_the_hero_states_the_real_study_time(self, client):
        html = client.get("/").text
        # The plan total is computed from the plan, not typed into the copy.
        assert re.search(r"~\s*\d+\s*min total", html), "the hero must state the plan's real total"

    def test_the_hero_offers_a_way_in_by_intent(self, client):
        html = client.get("/").text
        assert "mx-goal" in html

    def test_the_hero_links_to_the_whole_catalogue(self, client):
        html = client.get("/").text
        assert 'href="/explore"' in html


# ---------------------------------------------------------------------------
# 8. A number without a meaning is not information
# ---------------------------------------------------------------------------


class TestMasteryMeansSomething:
    def test_a_mastery_percentage_carries_a_label(self):
        from engineverse import progress

        assert progress.mastery_level(0)["label"] == "Not started"
        assert progress.mastery_level(45)["label"] == "Getting there"
        assert progress.mastery_level(90)["label"] == "Mastered"

    def test_every_band_explains_what_moves_it_up(self):
        from engineverse import progress

        for percent in (0, 10, 45, 75, 95):
            level = progress.mastery_level(percent)
            assert level["label"]
            assert level["note"]

    def test_the_bands_agree_with_the_stored_status(self):
        """A topic is "mastered" at 85, so the label must say so at 85."""
        from engineverse import progress

        assert progress.mastery_level(85)["label"] == "Mastered"
        assert progress.mastery_level(84)["label"] != "Mastered"
        assert progress.mastery_level(50)["label"] != "Not started"

    def test_the_dashboard_prints_the_label_not_just_the_number(self, client, seeded):
        from starlette.testclient import TestClient

        from engineverse import db, progress

        app = client.app
        with TestClient(app, raise_server_exceptions=False) as signed_in:
            _sign_in(signed_in)
            viewer = db.query_one("SELECT id FROM users WHERE email = 'asha@example.com'")["id"]
            topic = db.query_one("SELECT id FROM topics LIMIT 1")["id"]
            db.execute(
                "INSERT INTO user_progress (user_id, topic_id, status, mastery, time_spent_s, last_viewed_at) "
                "VALUES (?,?,'in_progress',45,0,?) ON CONFLICT(user_id, topic_id) DO UPDATE SET mastery = 45",
                viewer, topic, 1_700_000_000_000,
            )
            html = signed_in.get("/dashboard").text
            assert "Getting there" in html


class TestPlanMinutes:
    def test_the_plan_total_is_computed_not_typed(self, client):
        """Every page that mentions the plan's length must agree."""
        from backend.web import pages as pages_mod

        html = client.get("/").text
        match = re.search(r"~(\d+)\s*min total", html)
        assert match, "the homepage must state the plan's length"
        assert int(match.group(1)) == pages_mod.plan_minutes()

    def test_no_page_says_about_an_hour_any_more(self):
        for name in ("home.html", "dashboard.html"):
            source = (TEMPLATES / name).read_text(encoding="utf-8")
            assert "about an hour" not in source, name
            assert "Roughly an hour" not in source, name


# ---------------------------------------------------------------------------
# 9. A wrong answer needs a way forward
# ---------------------------------------------------------------------------


class TestRecoveryPath:
    def test_a_wrong_answer_offers_a_way_forward(self, client, seeded):
        """The result page must point at the topic and at more practice."""
        from starlette.testclient import TestClient

        from engineverse import db, practice

        app = client.app
        with TestClient(app, raise_server_exceptions=False) as signed_in:
            token = _sign_in(signed_in)
            question = db.query_one(
                "SELECT id FROM questions WHERE is_active = 1 AND topic_id IS NOT NULL LIMIT 1"
            )
            options = practice.options_for(question["id"], reveal=True)
            wrong = next((o for o in options if not o.get("correct")), None)
            if wrong is None:
                pytest.skip("no distractor available for this question")
            index = options.index(wrong)
            response = signed_in.post(
                "/practice/check",
                data={"csrf_token": token, "question_id": question["id"], "option": index,
                      "next": "/practice/questions"},
                follow_redirects=False,
            )
            assert response.status_code == 200
            html = response.text
            assert "What to do next" in html
            assert "/practice/questions?topic=" in html
            assert "/topics/" in html


# ---------------------------------------------------------------------------
# 10. The coverage report names the gap instead of hiding it
# ---------------------------------------------------------------------------


def test_the_coverage_report_names_the_question_imbalance():
    from scripts import coverage_report

    source = (ROOT / "scripts" / "coverage_report.py").read_text(encoding="utf-8")
    assert "Question coverage is uneven" in source
    assert callable(coverage_report.render)
