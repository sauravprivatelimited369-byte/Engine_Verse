"""Regression tests for the 2026-10-28 audit findings.

Each test names the finding it guards. They read the seed data directly, so
they need no database, and they fail if a fixed defect is reintroduced:

* first-year classification (MA201 was flagged first-year in Semester 3);
* algorithm complexity labels (Binary Search was shown as O(n) time and space,
  and 58 problems had silently inherited that default);
* the Two Sum statement promised any order while the judge compares exact text;
* cross-language checkpoints must record which language they test;
* the stream filter must treat shared subjects as always-relevant.
"""
from __future__ import annotations

import re
from pathlib import Path

from seed_data import catalog, coding_book, coding_core, coding_streams, complexity, language_curriculum, practice_data

REPO = Path(__file__).resolve().parents[2]


def _bank() -> list[dict]:
    return (
        list(practice_data.CODING_PROBLEMS)
        + list(coding_core.PROBLEMS)
        + list(coding_streams.PROBLEMS)
        + list(coding_book.PROBLEMS)
    )


# --- first-year classification ----------------------------------------------

def test_first_year_subjects_are_in_a_first_year_semester():
    """A subject flagged first-year must sit in Semester 1 or 2 (or the shared Foundation slot)."""
    offenders = [
        (slug, semester)
        for (slug, _name, _branch, semester, first_year, *_rest) in catalog.SUBJECTS
        if first_year and semester not in (0, 1, 2)
    ]
    assert offenders == [], f"first-year subjects outside years 1 and 2: {offenders}"


def test_engineering_mathematics_iii_is_a_second_year_subject():
    row = next(s for s in catalog.SUBJECTS if s[0] == "engineering-mathematics-3")
    assert row[3] == 3 and row[4] is False, "MA201 is Semester 3 (Year 2 in SEMESTERS)"


def test_first_year_core_has_thirteen_shared_subjects():
    first_year = [s for s in catalog.SUBJECTS if s[4]]
    assert len(first_year) == 13
    assert all(s[2] is None for s in first_year), "the first-year core is shared, not branch-specific"


# --- complexity labels --------------------------------------------------------

def test_every_judged_problem_has_a_reviewed_complexity():
    slugs = [p["slug"] for p in _bank()]
    assert len(slugs) == len(set(slugs)), "duplicate problem slugs"
    missing = [s for s in slugs if complexity.bounds(s) is None]
    assert missing == [], f"problems without reviewed complexity: {missing}"


def test_no_stale_problem_entries_in_complexity_table():
    slugs = {p["slug"] for p in _bank()}
    stale = sorted(set(complexity.REVIEWED) - slugs)
    assert stale == [], f"complexity entries for problems that do not exist: {stale}"


def test_binary_search_is_logarithmic_in_time_and_constant_in_space():
    assert complexity.bounds("binary-search") == ("O(log n)", "O(1)")
    assert complexity.bounds("search-rotated") == ("O(log n)", "O(1)")


def test_linear_scan_labels_are_not_claimed_for_halving_algorithms():
    """Any problem whose reference solution halves a range must not be labelled O(n)."""
    halving = {"binary-search", "sqrt-integer", "koko-eating-bananas", "search-rotated"}
    for slug in halving:
        time, _space = complexity.bounds(slug)
        assert "log" in time, f"{slug} halves its search range but is labelled {time}"


def test_reverse_linked_list_uses_constant_extra_space():
    assert complexity.bounds("reverse-linked-list")[1] == "O(1)"


def test_seeder_refuses_problem_without_reviewed_complexity():
    import importlib.util

    spec = importlib.util.spec_from_file_location("seed_script", REPO / "scripts" / "seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module._reviewed_bounds("not-a-real-problem")
    except module.SeedRefused as error:
        assert "reviewed complexity" in str(error)
    else:  # pragma: no cover - the guard is the point of this test
        raise AssertionError("an unreviewed problem was accepted")


# --- Two Sum statement and judge contract -----------------------------------

def test_two_sum_does_not_promise_any_order_the_judge_cannot_accept():
    two_sum = next(p for p in practice_data.CODING_PROBLEMS if p["slug"] == "two-sum")
    assert "any order" not in two_sum["statement"]
    assert "smaller one first" in two_sum["statement"]
    # The reference answer returns the smaller index first on every test.
    for test in two_sum["tests"]:
        left, right = (int(x) for x in test["expected"].strip("[]").split(","))
        assert left < right


# --- cross-language checkpoints ----------------------------------------------

def test_every_language_checkpoint_states_its_language():
    entries = language_curriculum.checkpoint_questions()
    assert entries, "no checkpoints generated"
    for entry in entries:
        assert entry["language"] in language_curriculum.LANGUAGE_ORDER, entry["slug"]
        assert entry["subject"] == language_curriculum.CHECKPOINT_SUBJECT


# --- stream filter -------------------------------------------------------------

def test_shared_subject_cards_are_marked_so_the_stream_filter_keeps_them():
    card = (REPO / "backend" / "templates" / "_subject_card.html").read_text(encoding="utf-8")
    assert "data-ev-stream-shared" in card
    js = (REPO / "backend" / "static" / "js" / "stream.js").read_text(encoding="utf-8")
    assert re.search(r"\[data-ev-stream-shared\]", js), "stream.js must count shared items as visible"


def test_homepage_study_plan_total_is_derived_not_hardcoded():
    home = (REPO / "backend" / "templates" / "home.html").read_text(encoding="utf-8")
    assert "~65 min total" not in home
    assert "timed_total" in home
