"""Learning outcomes measure accuracy and independence, not activity.

XP and streaks go up whenever a learner clicks. The measures in
engineverse.outcomes come from the attempt history instead: first-attempt
accuracy (retries cannot inflate it), the trend of later answers versus
earlier ones, recovery from mistakes, and real solve rates. Small samples
report None rather than a noisy percentage.
"""
from __future__ import annotations

import itertools

import pytest

from engineverse import auth, db, outcomes
from engineverse.security.ids import now_ms, ulid

PASSWORD = "Str0ngPassphrase#42!"

pytestmark = pytest.mark.usefixtures("seeded")

_tag_counter = itertools.count()


def _register() -> dict:
    tag = f"outcome{next(_tag_counter)}"
    return auth.register(
        email=f"{tag}@example.test", username=tag, password=PASSWORD,
        full_name="Outcome Learner", ip="203.0.113.9", user_agent="pytest",
    )


def _mcq_ids(count: int) -> list[str]:
    rows = db.query(
        "SELECT q.id FROM questions q WHERE q.kind = 'mcq' AND q.is_active = 1 "
        "AND (SELECT count(*) FROM question_options o WHERE o.question_id = q.id AND o.is_correct = 1) = 1 "
        "ORDER BY q.id LIMIT ?", count,
    )
    assert len(rows) == count, "seed must hold enough single-answer MCQs"
    return [row["id"] for row in rows]


def _answer(user_id: str, question_id: str, correct: bool, ts: int) -> None:
    db.execute(
        "INSERT INTO submissions (id,user_id,question_id,answer_index,is_correct,created_at) "
        "VALUES (?,?,?,?,?,?)",
        ulid(), user_id, question_id, 0 if correct else 1, 1 if correct else 0, ts,
    )


def _code_attempt(user_id: str, problem_id: str, status: str, ts: int, accepted: bool) -> None:
    db.execute(
        "INSERT INTO coding_submissions (id,user_id,problem_id,language,code,status,passed,total,"
        "is_accepted,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ulid(), user_id, problem_id, "python", "pass", status, 0, 1,
        1 if accepted else 0, ts,
    )


class TestPracticeGains:
    def test_empty_history_reports_nones_not_zeroes(self):
        user = _register()
        gains = outcomes.practice_gains(user["id"])
        assert gains["questionsAttempted"] == 0
        assert gains["attempts"] == 0
        assert gains["firstAttemptAccuracy"] is None
        assert gains["accuracyDelta"] is None
        assert gains["retrySuccessRate"] is None
        assert gains["independentCorrectShare"] is None

    def test_first_attempt_accuracy_ignores_retries(self):
        user = _register()
        first, second = _mcq_ids(2)
        base = now_ms()
        _answer(user["id"], first, False, base + 1)
        _answer(user["id"], first, True, base + 2)
        _answer(user["id"], second, True, base + 3)
        gains = outcomes.practice_gains(user["id"])
        assert gains["questionsAttempted"] == 2
        assert gains["attempts"] == 3
        assert gains["firstAttemptAccuracy"] == 50
        assert gains["overallAccuracy"] == 67
        # One of the two correct answers came on a first attempt.
        assert gains["independentCorrectShare"] == 50

    def test_trend_stays_blank_below_the_sample_threshold(self):
        user = _register()
        ids = _mcq_ids(3)
        base = now_ms()
        for index in range(6):
            _answer(user["id"], ids[index % 3], index >= 3, base + index)
        gains = outcomes.practice_gains(user["id"])
        assert gains["attempts"] == 6
        assert gains["accuracyDelta"] is None
        assert gains["firstHalfAccuracy"] is None

    def test_trend_compares_later_answers_with_earlier_ones(self):
        user = _register()
        ids = _mcq_ids(4)
        base = now_ms()
        for index, question_id in enumerate(ids):
            _answer(user["id"], question_id, False, base + index)
        for position, question_id in enumerate(ids):
            _answer(user["id"], question_id, True, base + 10 + position)
        gains = outcomes.practice_gains(user["id"])
        assert gains["firstHalfAccuracy"] == 0
        assert gains["secondHalfAccuracy"] == 100
        assert gains["accuracyDelta"] == 100

    def test_retry_success_counts_recovery_from_wrong_answers(self):
        user = _register()
        first, second, third = _mcq_ids(3)
        base = now_ms()
        _answer(user["id"], first, False, base + 1)
        _answer(user["id"], first, True, base + 2)
        _answer(user["id"], second, False, base + 3)
        _answer(user["id"], second, True, base + 4)
        _answer(user["id"], third, False, base + 5)
        gains = outcomes.practice_gains(user["id"])
        assert gains["retrySuccessRate"] == 67

    def test_retry_success_stays_blank_for_tiny_samples(self):
        user = _register()
        (only,) = _mcq_ids(1)
        base = now_ms()
        _answer(user["id"], only, False, base + 1)
        _answer(user["id"], only, True, base + 2)
        assert outcomes.practice_gains(user["id"])["retrySuccessRate"] is None

    def test_mistakes_open_and_resolved_come_from_the_notebook(self):
        user = _register()
        first, second, third = _mcq_ids(3)
        base = now_ms()
        db.execute(
            "INSERT INTO mistakes (id,user_id,question_id,given,correct,created_at) VALUES (?,?,?,?,?,?)",
            ulid(), user["id"], first, "B", "A", base,
        )
        db.execute(
            "INSERT INTO mistakes (id,user_id,question_id,given,correct,created_at) VALUES (?,?,?,?,?,?)",
            ulid(), user["id"], second, "B", "A", base,
        )
        db.execute(
            "INSERT INTO mistakes (id,user_id,question_id,given,correct,resolved_at,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ulid(), user["id"], third, "B", "A", base + 1, base,
        )
        gains = outcomes.practice_gains(user["id"])
        assert gains["mistakesOpen"] == 2
        assert gains["mistakesResolved"] == 1


class TestCodingGains:
    def test_unexecuted_submissions_are_not_attempts(self):
        user = _register()
        problems = [row["id"] for row in db.query("SELECT id FROM coding_problems ORDER BY id LIMIT 5")]
        base = now_ms()
        solved, quick, stuck, refused, instant = problems
        _code_attempt(user["id"], solved, "wrong_answer", base + 1, False)
        _code_attempt(user["id"], solved, "accepted", base + 2, True)
        _code_attempt(user["id"], quick, "accepted", base + 3, True)
        _code_attempt(user["id"], stuck, "wrong_answer", base + 4, False)
        _code_attempt(user["id"], stuck, "timeout", base + 5, False)
        _code_attempt(user["id"], refused, "sandbox_unavailable", base + 6, False)
        _code_attempt(user["id"], instant, "unsupported_language", base + 7, False)
        gains = outcomes.coding_gains(user["id"])
        assert gains["problemsAttempted"] == 3
        assert gains["problemsSolved"] == 2
        assert gains["solveRate"] == 67
        # Only `quick` was accepted on its first executed submission.
        assert gains["firstSubmissionAcceptRate"] == 33
        # Two solved problems is below the median threshold.
        assert gains["medianSubmissionsToSolve"] is None

    def test_median_submissions_to_solve(self):
        user = _register()
        problems = [row["id"] for row in db.query("SELECT id FROM coding_problems ORDER BY id LIMIT 3")]
        base = now_ms()
        for position, problem_id in enumerate(problems):
            for attempt in range(position + 1):
                last = attempt == position
                _code_attempt(user["id"], problem_id, "accepted" if last else "wrong_answer",
                              base + position * 10 + attempt, last)
        gains = outcomes.coding_gains(user["id"])
        assert gains["problemsSolved"] == 3
        # 1, 2 and 3 submissions to solve.
        assert gains["medianSubmissionsToSolve"] == 2.0

    def test_empty_coding_history_reports_nones(self):
        user = _register()
        gains = outcomes.coding_gains(user["id"])
        assert gains["problemsAttempted"] == 0
        assert gains["solveRate"] is None
        assert gains["medianSubmissionsToSolve"] is None


class TestTopicGains:
    def test_mastery_bands_come_from_progress_rows(self):
        user = _register()
        topics = [row["id"] for row in db.query("SELECT id FROM topics WHERE status='published' LIMIT 3")]
        db.execute(
            "INSERT INTO user_progress (user_id,topic_id,status,mastery,last_viewed_at) VALUES (?,?,?,?,?)",
            user["id"], topics[0], "mastered", 90, base_now(),
        )
        db.execute(
            "INSERT INTO user_progress (user_id,topic_id,status,mastery,last_viewed_at) VALUES (?,?,?,?,?)",
            user["id"], topics[1], "completed", 60, base_now(),
        )
        db.execute(
            "INSERT INTO user_progress (user_id,topic_id,status,mastery,last_viewed_at) VALUES (?,?,?,?,?)",
            user["id"], topics[2], "in_progress", 30, base_now(),
        )
        gains = outcomes.topic_gains(user["id"])
        assert gains == {"started": 3, "completed": 2, "mastered": 1, "avgMastery": 60}


def base_now() -> int:
    return now_ms()


class TestOutcomesApi:
    def test_anonymous_callers_are_refused(self, client):
        assert client.get("/api/outcomes").status_code == 401

    def test_signed_in_learners_get_all_three_axes(self, signed_in):
        body = signed_in.get("/api/outcomes").json()
        assert body["ok"] is True
        assert set(body["gains"]) == {"practice", "coding", "topics"}
        assert "firstAttemptAccuracy" in body["gains"]["practice"]
        assert "solveRate" in body["gains"]["coding"]

    def test_profile_page_shows_learning_gains(self, signed_in):
        html = signed_in.get("/profile").text
        assert "Learning gains" in html
        assert "First-try accuracy" in html
