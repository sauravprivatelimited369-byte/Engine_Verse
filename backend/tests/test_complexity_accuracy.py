"""Algorithm complexity labels must be true.

A problem page prints "Expected time O(log n) - space O(1)" before the learner
writes a line of code, and an instructor checks that line against the answer
key. When the label is wrong, the platform teaches the wrong thing while
looking authoritative - so these tests pin the labels down.

The bug this file exists for: thirteen hand-written problems declared no
complexity at all, the seeder filled the gap with a blanket ``O(n)`` time and
``O(n)`` space, and binary search shipped to learners as a linear-time,
linear-space algorithm. Its own statement says "Your algorithm must run in
O(log n)". Four more problems understated their space.

``seed_data/complexity.py`` is now the single place a bound is written down.
"""
from __future__ import annotations

import pytest

from seed_data import complexity
from seed_data import coding_book, coding_core, coding_streams, practice_data


def _all_problems() -> list[dict]:
    problems = list(practice_data.CODING_PROBLEMS)
    problems += list(coding_core.PROBLEMS)
    problems += list(coding_streams.PROBLEMS)
    problems += list(coding_book.PROBLEMS)
    return problems


PROBLEMS = _all_problems()
SLUGS = {problem["slug"] for problem in PROBLEMS}

#: The bounds that were wrong or absent before the audit, kept as a
#: regression guard so a future edit cannot quietly reintroduce them.
CORRECTED = {
    "binary-search": ("O(log n)", "O(1)"),
    "two-sum": ("O(n)", "O(n)"),
    "reverse-linked-list": ("O(n)", "O(1)"),
    "valid-parentheses": ("O(n)", "O(n)"),
    "merge-sorted-arrays": ("O(m + n)", "O(m + n)"),
    "fizzbuzz": ("O(n)", "O(n)"),
    "maximum-subarray": ("O(n)", "O(1)"),
    "lru-cache": ("O(1) per call", "O(c)"),
    "detect-cycle": ("O(n)", "O(1)"),
    "longest-substring": ("O(n)", "O(k)"),
    "coin-change": ("O(n × amount)", "O(amount)"),
    "level-order-traversal": ("O(n)", "O(w)"),
    "dijkstra-shortest-path": ("O((V + E) log V)", "O(V + E)"),
    # A breadth-first search needs room for its frontier; so does Kahn's
    # algorithm and so does the level-order queue.
    "bfs-grid-distance": ("O(rows × cols)", "O(rows × cols)"),
    "rotting-oranges": ("O(rows × cols)", "O(rows × cols)"),
    "course-schedule": ("O(V + E)", "O(V)"),
    # The subset-sum table is O(target) wide.
    "partition-equal-subset": ("O(n × target)", "O(target)"),
    # The editorial already said O(n) space; the label disagreed with it.
    "evaluate-rpn": ("O(n)", "O(n)"),
    # Median needs a sort; one-hot materialises a whole matrix; run-length
    # encoding and the moving average return a list as long as the input.
    "mean-median-mode": ("O(n log n)", "O(n)"),
    "one-hot-encode": ("O(n × k)", "O(n × k)"),
    "run-length-encoding": ("O(n)", "O(n)"),
    "moving-average": ("O(n)", "O(n) for the output"),
    "histogram-bins": ("O(n + bins)", "O(bins)"),
}


class TestTheTableIsComplete:
    def test_every_problem_has_a_stated_bound(self):
        assert complexity.missing(SLUGS) == []

    def test_the_table_names_no_problem_that_does_not_exist(self):
        assert complexity.stale(SLUGS) == []

    def test_every_problem_carries_its_bounds(self):
        for problem in PROBLEMS:
            assert problem.get("expected_time"), problem["slug"]
            assert problem.get("expected_space"), problem["slug"]

    def test_bounds_are_big_o_expressions(self):
        for problem in PROBLEMS:
            for label in ("expected_time", "expected_space"):
                value = problem[label]
                assert "O(" in value, f"{problem['slug']} {label}: {value!r}"

    def test_the_auditor_finds_nothing(self):
        from scripts.audit_complexity import audit

        assert audit(PROBLEMS) == []


class TestTheCorrectedBounds:
    @pytest.mark.parametrize(("slug", "expected"), sorted(CORRECTED.items()))
    def test_corrected_bound_is_published(self, slug, expected):
        problem = next(p for p in PROBLEMS if p["slug"] == slug)
        assert (problem["expected_time"], problem["expected_space"]) == expected

    def test_binary_search_is_not_published_as_linear(self):
        """The headline case: the statement itself demands O(log n)."""
        problem = next(p for p in PROBLEMS if p["slug"] == "binary-search")
        assert "O(log n)" in problem["statement"]
        assert problem["expected_time"] == "O(log n)"
        assert problem["expected_space"] == "O(1)"
        assert "O(n)" not in problem["expected_time"]

    def test_the_seeder_refuses_a_problem_with_no_bounds(self):
        """The old fallback filled the gap silently. Now the seed refuses."""
        from scripts.seed import SeedRefused, validate_problem_bank

        broken = dict(PROBLEMS[0])
        broken["slug"] = "no-bounds-problem"
        broken["expected_time"] = ""
        broken["expected_space"] = ""
        with pytest.raises(SeedRefused) as caught:
            validate_problem_bank([broken])
        assert "complexity" in str(caught.value)

    def test_every_problem_declares_its_bounds_in_the_table(self):
        """The table is the source; the problem must not carry a private copy."""
        for problem in PROBLEMS:
            assert (
                problem["expected_time"],
                problem["expected_space"],
            ) == complexity.bounds(problem["slug"])


class TestTheDatabaseAgrees:
    def test_published_rows_match_the_table(self, seeded):
        from engineverse import db

        rows = db.query(
            "SELECT slug, expected_time, expected_space FROM coding_problems"
        )
        assert rows, "the seeded catalogue must publish coding problems"
        for row in rows:
            assert (row["expected_time"], row["expected_space"]) == complexity.bounds(
                row["slug"]
            ), row["slug"]

    def test_the_problem_page_shows_the_correct_bound(self, client):
        html = client.get("/practice/problems/binary-search").text
        assert "O(log n)" in html
        assert "O(1)" in html
