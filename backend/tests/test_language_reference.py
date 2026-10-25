"""The deep language reference: data contract, storage and rendered pages.

The reference is a separate resource from the course paths, so it gets its own
contract: ten languages, every section populated to its minimum, official
sources only, and every seeded page reachable from the hub, the nav, the sitemap
and search.
"""
from __future__ import annotations

import json

import pytest

from engineverse import db, navigation, search
from seed_data import language_reference

LANGUAGES = language_reference.LANGUAGE_ORDER
SECTIONS = ("facts", "syntax", "types", "stdlib", "errors", "idioms", "versions", "sources")


def test_the_authored_data_reports_its_own_coverage():
    totals = language_reference.totals()
    assert totals["languages"] == len(LANGUAGES) == 10
    assert totals["rosetta_tasks"] == 10
    assert totals["rows"] >= 550, f"reference shrank to {totals['rows']} rows"


@pytest.mark.parametrize("language", LANGUAGES)
def test_each_language_has_every_section_to_its_minimum(language):
    entry = language_reference.REFERENCE[language]
    assert len(entry["model"]) >= 2
    for section in SECTIONS:
        assert len(entry[section]) >= language_reference.MIN_ROWS[section], (language, section)
    for source in entry["sources"]:
        assert source["url"].startswith("https://"), source
    assert entry["version"].strip() and entry["tagline"].strip()


def test_the_cross_language_tasks_cover_every_language():
    tasks = language_reference.ROSETTA
    assert len(tasks) == 10
    assert len({task["task"] for task in tasks}) == len(tasks)
    for task in tasks:
        assert set(task["snippets"]) == set(LANGUAGES), task["task"]
        assert task["note"].strip()


def test_every_reference_is_stored_once_per_language(seeded):
    rows = db.query(
        "SELECT l.slug, r.version, r.tagline, r.body FROM language_references r "
        "JOIN programming_languages l ON l.id = r.language_id ORDER BY l.order_index"
    )
    assert [row["slug"] for row in rows] == list(LANGUAGES)
    for row in rows:
        payload = json.loads(row["body"])
        assert set(payload) == set(SECTIONS) | {"model"}, row["slug"]
        assert len(payload["errors"]) >= language_reference.MIN_ROWS["errors"]
    assert int(db.scalar("SELECT count(*) FROM language_reference_tasks")) == 10


def test_the_hub_links_every_language(client, seeded):
    html = client.get("/programming/reference").text
    for language in LANGUAGES:
        assert f'href="/programming/{language}/reference"' in html, language
    assert "One task, 10 languages" in html
    assert html.count("Open the reference") == 10


@pytest.mark.parametrize("language", ["python", "java", "javascript", "typescript", "c",
                                      "cpp", "csharp", "go", "rust", "sql"])
def test_each_language_page_renders_its_sections(client, seeded, language):
    response = client.get(f"/programming/{language}/reference")
    assert response.status_code == 200
    html = response.text
    for heading in ("The execution model", "Syntax that carries meaning", "The type system in practice",
                    "The standard library by job", "Errors, causes and fixes", "Idioms for real tasks",
                    "Version history that matters", "Upstream sources"):
        assert heading in html, (language, heading)
    assert 'rel="canonical"' in html
    assert html.count('rel="canonical"') == 1
    assert 20 <= len(_description(html) or "") <= 200


def _description(html: str) -> str | None:
    import re

    match = re.search(r'<meta name="description" content="([^"]*)"', html)
    return match.group(1) if match else None


def test_an_unknown_language_reference_is_a_404(client, seeded):
    assert client.get("/programming/cobol/reference").status_code == 404


def test_the_reference_is_a_navigation_destination(client, seeded):
    destination = navigation.find("/programming/reference")
    assert destination is not None
    assert destination.indexable is True
    assert "/programming/reference" in navigation.indexable_paths()
    assert destination.label in client.get("/programming/reference").text


def test_the_sitemap_lists_the_hub_and_every_language(client, seeded):
    body = client.get("/sitemap.xml").text
    assert "/programming/reference</loc>" in body
    for language in LANGUAGES:
        assert f"/programming/{language}/reference</loc>" in body, language


def test_references_are_searchable_as_their_own_entity(client, seeded):
    assert search.ENTITY_URLS["reference"] == "/programming/{id}/reference"
    rows = db.query("SELECT entity_id, title FROM search_index WHERE entity_type = 'reference'")
    assert {row["entity_id"] for row in rows} == set(LANGUAGES)
    assert all("reference" in row["title"].lower() for row in rows)


def test_the_language_page_points_at_its_reference(client, seeded):
    html = client.get("/programming/python").text
    assert 'href="/programming/python/reference"' in html
