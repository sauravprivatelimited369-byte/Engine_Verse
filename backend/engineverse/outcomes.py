"""Learning outcomes: are learners answering more accurately and independently?

XP, streaks and page counts measure activity, not learning. Every measure
here is computed from the attempt history the app already keeps - the
``submissions``, ``mistakes``, ``coding_submissions`` and ``user_progress``
tables - so there is no new tracking and no schema change. Each measure
answers one concrete question:

* first-attempt accuracy - of the questions met for the first time, how many
  were answered right? Retries cannot inflate it.
* accuracy trend - first-half vs second-half accuracy over the learner's own
  chronological attempt history. A positive delta means later answers are
  better than earlier ones.
* retry success - of the questions ever answered wrong, how many were later
  answered right? (Recovery, not just attempts.)
* independent-correct share - of all correct answers, how many came on the
  first attempt, before the learner had seen the explanation?
* coding solve rate - problems solved, first-submission accept rate, and the
  median submissions needed to solve one.

Small samples report ``None`` rather than a noisy percentage: a trend over
six attempts is not evidence of anything. The thresholds are named below so
a reader can see exactly when a measure unlocks.
"""
from __future__ import annotations

from typing import Any

from . import db

#: Minimum attempts before a first-half/second-half trend is reported. Fewer
#: than this and the halves are too small to say anything.
MIN_ATTEMPTS_FOR_TREND = 8

#: Minimum ever-wrong questions before a retry-success rate is reported.
MIN_WRONG_FOR_RETRY_RATE = 3

#: Minimum solved problems before a median submissions-to-solve is reported.
MIN_SOLVED_FOR_MEDIAN = 3


def _pct(part: int, whole: int) -> int:
    return round(part / whole * 100) if whole else 0


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def practice_gains(user_id: str) -> dict[str, Any]:
    """Accuracy, improvement and independence from the answer history."""
    # Submission ids are ULIDs, which sort in creation order on every
    # database, so MIN(id) is the first attempt however coarse created_at is.
    firsts = db.query(
        "SELECT first_sub.is_correct AS first_correct FROM submissions first_sub "
        "JOIN (SELECT question_id, MIN(id) AS first_id FROM submissions "
        "WHERE user_id = ? GROUP BY question_id) f ON f.first_id = first_sub.id",
        user_id,
    )
    questions_attempted = len(firsts)
    first_correct = sum(1 for row in firsts if row["first_correct"])

    history = db.query(
        "SELECT is_correct FROM submissions WHERE user_id = ? ORDER BY created_at ASC, id ASC",
        user_id,
    )
    attempts = len(history)
    correct = sum(1 for row in history if row["is_correct"])

    first_half_accuracy: int | None = None
    second_half_accuracy: int | None = None
    accuracy_delta: int | None = None
    if attempts >= MIN_ATTEMPTS_FOR_TREND:
        cut = attempts // 2
        first_half = history[:cut]
        second_half = history[cut:]
        first_half_accuracy = _pct(sum(1 for row in first_half if row["is_correct"]), len(first_half))
        second_half_accuracy = _pct(sum(1 for row in second_half if row["is_correct"]), len(second_half))
        accuracy_delta = second_half_accuracy - first_half_accuracy

    ever_wrong = db.query(
        "SELECT question_id, COALESCE(sum(is_correct), 0) AS correct, count(*) AS total "
        "FROM submissions WHERE user_id = ? GROUP BY question_id HAVING COALESCE(sum(is_correct), 0) < count(*)",
        user_id,
    )
    recovered = sum(1 for row in ever_wrong if int(row["correct"]) > 0)
    retry_success_rate = (
        _pct(recovered, len(ever_wrong)) if len(ever_wrong) >= MIN_WRONG_FOR_RETRY_RATE else None
    )

    mistakes = db.query(
        "SELECT COALESCE(sum(CASE WHEN resolved_at IS NULL THEN 1 ELSE 0 END), 0) AS open, "
        "COALESCE(sum(CASE WHEN resolved_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS resolved "
        "FROM mistakes WHERE user_id = ?",
        user_id,
    )
    mistakes_open = int(mistakes[0]["open"]) if mistakes else 0
    mistakes_resolved = int(mistakes[0]["resolved"]) if mistakes else 0

    return {
        "questionsAttempted": questions_attempted,
        "attempts": attempts,
        "overallAccuracy": _pct(correct, attempts),
        "firstAttemptAccuracy": _pct(first_correct, questions_attempted) if questions_attempted else None,
        "firstHalfAccuracy": first_half_accuracy,
        "secondHalfAccuracy": second_half_accuracy,
        # Positive means later answers are better than earlier ones.
        "accuracyDelta": accuracy_delta,
        "retrySuccessRate": retry_success_rate,
        "mistakesOpen": mistakes_open,
        "mistakesResolved": mistakes_resolved,
        # Share of correct answers that needed no retry and no explanation.
        "independentCorrectShare": _pct(first_correct, correct) if correct else None,
    }


def coding_gains(user_id: str) -> dict[str, Any]:
    """Solve rate and attempts-to-solve from judged submissions.

    Only submissions the judge actually ran count: refusals
    (unsupported_language / sandbox_unavailable / internal_error) are not
    attempts at the problem.
    """
    from .judge import NOT_EXECUTED_STATUSES

    placeholders = ",".join("?" for _ in NOT_EXECUTED_STATUSES)
    rows = db.query(
        f"SELECT problem_id, id, is_accepted FROM coding_submissions "
        f"WHERE user_id = ? AND status NOT IN ({placeholders}) ORDER BY created_at ASC, id ASC",
        user_id, *sorted(NOT_EXECUTED_STATUSES),
    )
    by_problem: dict[str, list[dict]] = {}
    for row in rows:
        by_problem.setdefault(row["problem_id"], []).append(row)
    solved = {pid: attempts for pid, attempts in by_problem.items() if any(a["is_accepted"] for a in attempts)}
    firsts_accepted = sum(1 for attempts in by_problem.values() if attempts and attempts[0]["is_accepted"])
    to_solve: list[int] = []
    for attempts in solved.values():
        used = 0
        for attempt in attempts:
            used += 1
            if attempt["is_accepted"]:
                break
        to_solve.append(used)
    return {
        "problemsAttempted": len(by_problem),
        "problemsSolved": len(solved),
        "solveRate": _pct(len(solved), len(by_problem)) if by_problem else None,
        "firstSubmissionAcceptRate": _pct(firsts_accepted, len(by_problem)) if by_problem else None,
        "medianSubmissionsToSolve": _median(to_solve) if len(to_solve) >= MIN_SOLVED_FOR_MEDIAN else None,
    }


def topic_gains(user_id: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT count(*) AS started, "
        "COALESCE(sum(CASE WHEN status IN ('completed','mastered') THEN 1 ELSE 0 END), 0) AS completed, "
        "COALESCE(sum(CASE WHEN status = 'mastered' THEN 1 ELSE 0 END), 0) AS mastered, "
        "COALESCE(avg(mastery), 0) AS avg_mastery FROM user_progress WHERE user_id = ?",
        user_id,
    ) or {}
    return {
        "started": int(row.get("started") or 0),
        "completed": int(row.get("completed") or 0),
        "mastered": int(row.get("mastered") or 0),
        "avgMastery": round(float(row.get("avg_mastery") or 0)),
    }


def learning_gains(user_id: str) -> dict[str, Any]:
    """The full outcome report for one learner."""
    return {
        "practice": practice_gains(user_id),
        "coding": coding_gains(user_id),
        "topics": topic_gains(user_id),
    }
