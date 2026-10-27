"""The global stream switcher: the picker, the branch catalogue and the filter.

A learner picks their stream once and the site shows only that stream. That
promise is carried by three things, and each has a test here:

* ``web.deps.stream_list`` / ``stream_base`` put the branch catalogue and the
  deployment's path prefix into every page, so ``base.html`` can render the
  switcher without a route having to remember to pass it;
* ``backend/templates/base.html`` renders the switcher and the ``#ev-streams``
  data block on every page, and ``backend/static/js/stream.js`` applies the
  filter (``scripts/check_stream_filter.js`` exercises the browser half);
* ``/explore?show_all=1`` renders the whole catalogue on one page, because the
  static copy is a single document and a stream filter that could only see the
  first page's subjects would look empty for any branch that starts later.
"""
from __future__ import annotations

import json
import re

from engineverse import catalog, library


def _json_block(html: str, block_id: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="%s"[^>]*>(.*?)</script>' % block_id, html, re.S
    )
    assert match, f"page has no #{block_id} block"
    return json.loads(match.group(1))


def test_every_page_carries_the_branch_catalogue(client):
    """The switcher is shared by every page, so the catalogue must be too.

    A route that forgot to pass the list would lose the control entirely; putting
    it in the base context is what keeps that impossible.
    """
    for path in ("/", "/explore", "/streams", "/stream/computer-science", "/about"):
        page = client.get(path)
        assert page.status_code == 200, path
        payload = _json_block(page.text, "ev-streams")
        slugs = {row["slug"] for row in payload["streams"]}
        assert slugs == {row["slug"] for row in catalog.list_branches()}, path
        assert payload["base"] == ""


def test_the_switcher_markup_is_on_every_page(client):
    """The menu is real markup with real links, so it works without JavaScript."""
    for path in ("/", "/explore", "/streams"):
        html = client.get(path).text
        assert 'id="ev-stream-btn"' in html, path
        assert 'id="ev-stream-pop"' in html, path
        assert "ev-stream-menu" in html, path
        # One link per branch, all pointing at that branch's hub.
        links = re.findall(r'href="/stream/([a-z0-9-]+)"', html)
        assert len(links) >= len(catalog.list_branches()), path


def test_subject_cards_name_their_branch(client):
    """The filter needs to know which branch each card belongs to."""
    html = client.get("/explore").text
    tagged = re.findall(r'class="card subject-card"[^>]*data-ev-stream="([a-z0-9-]+)"', html)
    assert tagged, "no subject card carries data-ev-stream"
    known = {row["slug"] for row in catalog.list_branches()}
    for slug in tagged:
        assert slug in known, f"card names an unknown branch {slug!r}"


def test_explore_paginates_by_default_and_renders_everything_with_show_all(client):
    """The live app pages; the static copy cannot, so it asks for the lot."""
    total = catalog.count_subjects()
    default = client.get("/explore").text
    assert default.count('class="card subject-card"') == min(24, total)
    assert "Page 1 of" in default or "of %d subjects" % total in default

    whole = client.get("/explore", params={"show_all": "1"}).text
    assert whole.count('class="card subject-card"') == total
    assert "Page 1 of" not in whole


def test_streams_index_tags_its_cards(client):
    html = client.get("/streams").text
    tagged = re.findall(r'<div class="card" data-ev-stream="([a-z0-9-]+)"', html)
    known = {row["slug"] for row in catalog.list_branches()}
    assert len(tagged) == len(known)
    assert set(tagged) == known


def test_home_branch_shelf_tags_its_rows(client):
    html = client.get("/").text
    tagged = re.findall(r'<li data-ev-stream="([a-z0-9-]+)">', html)
    assert tagged, "the home shelf does not tag its branch rows"
    known = {row["slug"] for row in catalog.list_branches()}
    assert set(tagged) <= known


def test_stream_list_shortens_long_branch_names():
    from web.deps import stream_list

    rows = {row["slug"]: row for row in stream_list()}
    assert rows["computer-science"]["short"] == "Computer Science"
    assert rows["computer-science"]["name"] == "Computer Science Engineering"
    # A name that already fits is left alone rather than truncated.
    assert rows["electronics-communication"]["short"] == "Electronics & Communication"


# ---------------------------------------------------------------------------
# The stream's own resources
# ---------------------------------------------------------------------------

def test_resources_are_filed_under_their_stream(seeded):
    """Every resource belongs to a stream, so a stream shelf has something to show.

    Before the seeder set ``branch_id`` every row in the table was NULL and the
    per-stream reading shelves were empty for every branch.
    """
    branches = catalog.list_branches()
    assert branches
    for branch in branches:
        assert library.count_resources(branch_id=branch["id"]) > 0, branch["slug"]
    total = library.count_resources()
    assert total > 0
    # The branch's own rows are a real subset of the table, not the whole table
    # counted once per branch.
    assert library.count_resources(branch_id=branches[0]["id"]) < total


def test_the_hub_shows_a_reading_shelf_for_its_stream(client):
    html = client.get("/stream/computer-science").text
    assert "Optional reading for this stream" in html
    # Deep links into the internal shelf, anchored at the resource.
    assert "/resources/offsite?branch=computer-science#" in html


def test_the_reading_shelf_links_inward_not_outward(client):
    """The hub's promise holds for the new shelf: it links to the shelf, not away."""
    html = client.get("/stream/computer-science").text
    shelf = html.split("Optional reading for this stream", 1)[1].split("</section>", 1)[0]
    external = re.findall(r'href="(https?://[^"]+)"', shelf)
    assert external == [], external


def test_the_offsite_shelf_filters_by_stream(client):
    page = client.get("/resources/offsite", params={"branch": "computer-science"})
    assert page.status_code == 200
    assert "Optional external reading for Computer Science Engineering" in page.text
    # The branch survives the type filter, so the two controls work together.
    filtered = client.get(
        "/resources/offsite", params={"branch": "computer-science", "kind": "documentation"}
    )
    assert "branch=computer-science" in filtered.text


def test_an_unknown_stream_filter_is_ignored(client):
    page = client.get("/resources/offsite", params={"branch": "not-a-branch"})
    assert page.status_code == 200
    assert "Optional external reading for" not in page.text


def test_the_streams_index_counts_each_streams_links(client):
    html = client.get("/streams").text
    assert re.search(r"\d+ links", html)
