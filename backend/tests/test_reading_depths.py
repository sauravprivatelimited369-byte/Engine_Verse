"""The four reading depths must be four different documents.

The homepage offers "Beginner, Standard, Advanced, Industry" as four editions
of the same topic. That promise was empty: ``standard`` was built from all
thirteen sections, so ``beginner`` was a strict *subset* of it. A learner who
picked "Beginner" read exactly the sentences a learner who picked "Standard"
read, only fewer of them, and both openings were the same paragraph.

These tests hold the promise down:

* no section body may appear in two depths;
* no depth may be a subset of another;
* every depth must open with different text;
* every topic must actually publish four depths.
"""
from __future__ import annotations

import pytest

from scripts import seed
from seed_data import foundations as topics_foundations
from seed_data import subject_paths, topics_core, topics_cse

ALL_TOPICS = (
    list(topics_cse.TOPICS)
    + list(topics_core.TOPICS)
    + list(topics_foundations.TOPICS)
    + list(subject_paths.TOPICS)
)

DEPTHS = ("beginner", "standard", "advanced", "industry")


def _slug(entry: dict) -> str:
    from engineverse.security.sanitize import slugify

    return slugify(entry["title"])


def _bodies(entry: dict, depth: str) -> list[str]:
    slug = _slug(entry)
    return [
        seed.section_body(kind, entry, slug, depth)
        for kind in seed.DEPTHS[depth]
        if seed.section_body(kind, entry, slug, depth)
    ]


class TestTheDepthTable:
    def test_there_are_four_depths(self):
        assert set(seed.DEPTHS) == set(DEPTHS)

    def test_every_section_kind_is_known(self):
        known = {kind for kind, _, _ in seed.SECTIONS}
        for depth, kinds in seed.DEPTHS.items():
            for kind in kinds:
                assert kind in known, f"{depth} names an unknown section kind {kind!r}"

    def test_no_depth_is_a_strict_subset_of_another(self):
        for left in DEPTHS:
            for right in DEPTHS:
                if left == right:
                    continue
                left_kinds = set(seed.DEPTHS[left])
                right_kinds = set(seed.DEPTHS[right])
                assert not left_kinds < right_kinds, (
                    f"{left} is a strict subset of {right}: choosing it buys the "
                    "reader nothing"
                )


class TestTheDocumentsDiffer:
    @pytest.mark.parametrize("entry", ALL_TOPICS, ids=_slug)
    def test_no_section_body_is_shared_between_two_depths(self, entry):
        seen: dict[str, str] = {}
        for depth in DEPTHS:
            for body in _bodies(entry, depth):
                normalised = body.strip()
                if not normalised:
                    continue
                owner = seen.get(normalised)
                assert owner is None, (
                    f"{entry['title']}: the {owner} and {depth} readings share a "
                    "section verbatim"
                )
                seen[normalised] = depth

    @pytest.mark.parametrize("entry", ALL_TOPICS, ids=_slug)
    def test_every_depth_opens_with_different_text(self, entry):
        openings = {}
        for depth in DEPTHS:
            bodies = _bodies(entry, depth)
            assert bodies, f"{entry['title']}: the {depth} reading is empty"
            openings[depth] = bodies[0].strip()
        assert len(set(openings.values())) == len(DEPTHS), (
            f"{entry['title']}: two readings open with the same paragraph"
        )

    def test_the_beginner_reading_is_not_the_standard_reading(self):
        """The specific complaint: the same introductory explanation twice."""
        entry = next(e for e in topics_core.TOPICS if e["title"] == "Bernoulli's Equation")
        slug = _slug(entry)
        beginner = seed.section_body("simple", entry, slug, "beginner")
        standard = seed.section_body("simple", entry, slug, "standard")
        assert beginner == standard, (
            "the beginner and standard readings must not open with the same "
            "explanation"
        )


class TestThePublishedNotes:
    def test_every_topic_publishes_four_depths(self, seeded):
        from engineverse import db

        rows = db.query(
            "SELECT t.slug AS slug, n.quality_level AS level FROM topics t "
            "JOIN notes n ON n.topic_id = t.id WHERE n.status='published'"
        )
        by_topic: dict[str, set[str]] = {}
        for row in rows:
            by_topic.setdefault(row["slug"], set()).add(row["level"])
        incomplete = {
            slug: sorted(set(DEPTHS) - levels)
            for slug, levels in by_topic.items()
            if set(DEPTHS) - levels
        }
        assert not incomplete, f"topics missing a reading depth: {incomplete}"

    def test_the_database_agrees_with_the_builder(self, seeded):
        from engineverse import db

        rows = db.query(
            "SELECT n.quality_level AS level, sec.kind AS kind, sec.body AS body "
            "FROM note_sections sec JOIN notes n ON n.id = sec.note_id "
            "WHERE n.status='published'"
        )
        by_depth: dict[str, set[str]] = {}
        for row in rows:
            by_depth.setdefault(row["level"], set()).add(row["body"].strip())
        assert set(by_depth) == set(DEPTHS)
        for left in DEPTHS:
            for right in DEPTHS:
                if left >= right:
                    continue
                shared = by_depth[left] & by_depth[right]
                assert not shared, (
                    f"the {left} and {right} readings share {len(shared)} section(s) "
                    "verbatim"
                )
