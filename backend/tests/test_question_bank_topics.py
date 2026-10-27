"""Choosing a topic in the question bank shows that topic's MCQs.

The bank handler honoured ``?topic=<slug>`` long before the page offered any
way to ask for it: the filter form had Subject, Difficulty and Kind selects
and no Topic select at all, so "the MCQs for this part" could only be reached
by hand-editing the URL or by the one recovery-plan link on /mistakes. On the
GitHub Pages copy it was worse - the exported page is static, a static host
ignores the query string, and nothing in the browser runtime filtered the
list, so every control in the form submitted, reloaded and showed the same
first screen. Selecting a topic was a demo.

These tests pin the fix from the server side: the form offers every topic
that has questions (grouped under its subject, with its MCQ count), choosing
one narrows the bank to exactly that topic's questions, a topic paired with
the wrong subject still wins instead of AND-ing into an empty page, and the
exported quiz-bank.json carries the subject/topic fields the browser-side
filter in pages-live.js matches on. The browser behaviour itself is exercised
against a real export by scripts/check_question_bank.js.
"""
from __future__ import annotations

import html
import json
import re

from engineverse import db, practice
from scripts import export_pages


def _a_topic_with_questions() -> dict:
    row = db.query_one(
        "SELECT t.slug, t.title, t.subject_id, count(q.id) AS n "
        "FROM topics t JOIN questions q ON q.topic_id = t.id AND q.is_active = 1 "
        "WHERE t.status = 'published' GROUP BY t.id ORDER BY n DESC, t.title LIMIT 1"
    )
    assert row, "the seed must put at least one question on a published topic"
    return row


def test_the_filter_form_offers_a_topic_selector(signed_in):
    page = signed_in.get("/practice/questions").text
    form = re.search(r'<form[^>]*id="qb-filter"[^>]*>(.*?)</form>', page, re.S)
    assert form, "the question bank filter form must carry id=qb-filter"
    fields = re.findall(r'name="([^"]+)"', form.group(1))
    assert "topic" in fields, f"the form offers no topic to choose: {fields}"
    topic = _a_topic_with_questions()
    option = re.search(
        rf'<option value="{re.escape(topic["slug"])}" data-subject="{re.escape(topic["subject_id"])}"[^>]*>([^<]*)</option>',
        form.group(1),
    )
    assert option, "a topic with questions must be one of the selectable options"
    assert f'({topic["n"]})' in html.unescape(option.group(1)), (
        "the option must say how many MCQs choosing it will show"
    )


def test_question_topics_lists_only_topics_with_questions(seeded):
    rows = practice.question_topics()
    assert rows, "the seeded catalogue has topic questions"
    by_slug = {row["slug"]: row for row in rows}
    expected = {
        row["slug"]: row["n"]
        for row in db.query(
            "SELECT t.slug, count(q.id) AS n FROM topics t "
            "JOIN questions q ON q.topic_id = t.id AND q.is_active = 1 "
            "WHERE t.status = 'published' GROUP BY t.id"
        )
    }
    assert set(by_slug) == set(expected), (
        "the selector must offer exactly the topics that have questions - "
        "no topic whose honest answer is an empty page, none missing"
    )
    for slug, n in expected.items():
        assert by_slug[slug]["count"] == n, f"{slug} is listed with the wrong MCQ count"
        assert by_slug[slug]["subject_id"], f"{slug} must name its subject for the optgroup"
    # Ordered by subject then title, so the template's grouping never splits
    # one subject's topics across two optgroups.
    keys = [(row["subject_name"], row["title"]) for row in rows]
    assert keys == sorted(keys)


def test_choosing_a_topic_shows_only_that_topics_mcqs(signed_in):
    topic = _a_topic_with_questions()
    page = signed_in.get(f"/practice/questions?topic={topic['slug']}").text
    shown = re.findall(r'data-quiz="([^"]+)"', page)
    expected_ids = {
        row["id"]
        for row in db.query(
            "SELECT q.id FROM questions q JOIN topics t ON t.id = q.topic_id "
            "WHERE t.slug = ? AND q.is_active = 1",
            topic["slug"],
        )
    }
    assert set(shown) == expected_ids and len(shown) == len(expected_ids), (
        "choosing a topic must change the bank to that topic's questions, all of them"
    )
    # The form describes what is on screen: the topic is selected, and the
    # subject select has followed it to the topic's own subject.
    assert re.search(
        rf'<option value="{re.escape(topic["slug"])}"[^>]*\bselected\b', page
    ), "the chosen topic must stay selected after filtering"
    assert re.search(
        rf'<option value="{re.escape(topic["subject_id"])}"[^>]*\bselected\b', page
    ), "the subject select must show the topic's subject after filtering"
    # And every card says which topic it belongs to.
    assert f'href="/topics/{topic["slug"]}"' in page


def test_a_topic_wins_over_a_mismatched_subject(signed_in):
    """Applying both would AND a topic with another subject's id and show an
    empty page that reads as "this topic has no MCQs". The topic is the more
    specific request, so it wins - the same rule pages-live.js applies."""
    topic = _a_topic_with_questions()
    other = db.query_one(
        "SELECT id FROM subjects WHERE id != ? LIMIT 1", topic["subject_id"]
    )
    assert other
    page = signed_in.get(
        f"/practice/questions?topic={topic['slug']}&subject={other['id']}"
    ).text
    assert page.count("data-quiz=") == topic["n"]


def test_an_unknown_topic_is_named_in_the_banner(signed_in):
    page = signed_in.get("/practice/questions?topic=not-a-real-topic").text
    assert page.count("data-quiz=") == 0
    assert "not in the catalogue" in page, (
        "an unresolvable topic must be named as such, not leave a hole in the banner"
    )
    assert "No questions match" in page


def test_the_stem_search_in_the_form_filters(signed_in):
    row = db.query_one(
        "SELECT stem FROM questions WHERE is_active = 1 AND stem LIKE '%Bernoulli%' LIMIT 1"
    )
    if row is None:
        return  # seed without that word: nothing meaningful to search for
    whole = signed_in.get("/practice/questions").text.count("data-quiz=")
    page = signed_in.get("/practice/questions?q=Bernoulli").text
    assert 0 < page.count("data-quiz=") < whole
    assert "Bernoulli" in html.unescape(page)


def test_the_exported_quiz_bank_carries_what_the_browser_filter_matches(seeded, tmp_path):
    """pages-live.js filters quiz-bank.json on subjectId/topicSlug/difficulty/
    kind/slug/stem. If any of those stops being exported, choosing a topic on
    the Pages copy silently matches nothing again."""
    export_pages.write_quiz_bank(tmp_path, "/EngineVerse/")
    bank = json.loads((tmp_path / "quiz-bank.json").read_text(encoding="utf-8"))
    total = int(db.scalar("SELECT count(*) FROM questions WHERE is_active = 1") or 0)
    assert len(bank) == total

    topic = _a_topic_with_questions()
    on_topic = [item for item in bank.values() if item["topicSlug"] == topic["slug"]]
    assert len(on_topic) == topic["n"], "every MCQ of a topic must be findable by its slug"
    for item in on_topic:
        assert item["subjectId"] == topic["subject_id"], (
            "a topic question's subjectId must be its topic's subject, or the "
            "browser's topic-wins rule would filter the topic's own MCQs out"
        )
        assert item["topicUrl"] == f"/EngineVerse/topics/{topic['slug']}/" or item["topicUrl"].endswith(
            f"/topics/{topic['slug']}/"
        )
    for item in bank.values():
        for field in ("id", "slug", "kind", "difficulty", "stem", "subjectId", "topicSlug", "options"):
            assert field in item, f"quiz-bank entry {item.get('id')} lost {field}"
    # Exported in the server's order, so the static first screen is the same
    # first screen: the first entries' ids equal the hosted page one's.
    first_page, _total = practice.list_questions(limit=24)
    assert list(bank)[:24] == [q["id"] for q in first_page]
