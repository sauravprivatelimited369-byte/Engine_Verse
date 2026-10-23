"""Study planner, opportunities, help page and personal data export."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

STATIC = Path(__file__).resolve().parents[1] / "static"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchors.append(dict(attrs))


def _anchors(html: str) -> list[dict]:
    parser = _Links()
    parser.feed(html)
    return parser.anchors


# ------------------------------------------------------------------ routes

@pytest.mark.parametrize("path", ["/planner", "/opportunities", "/support"])
def test_new_pages_render_and_are_in_navigation(client, path):
    response = client.get(path)
    assert response.status_code == 200
    # Linked from the shared navigation (top bar, mobile panel or footer).
    assert f'href="{path}"' in response.text
    # No placeholder links on the new pages.
    assert not [a for a in _anchors(response.text) if a.get("href") in ("#", "", "javascript:void(0)")]


@pytest.mark.parametrize("path", ["/planner", "/opportunities", "/support"])
def test_new_pages_are_in_sitemap(client, path):
    body = client.get("/sitemap.xml").text
    assert re.search(rf"<loc>[^<]*{re.escape(path)}</loc>", body)


# ------------------------------------------------------------- opportunities

def test_opportunity_data_follows_editorial_rules():
    from engineverse import opportunities

    opportunities.validate()
    items = opportunities.all_opportunities()
    assert len(items) >= 15
    assert {i["category"] for i in items} == set(opportunities.CATEGORIES)
    for item in items:
        assert urlparse(item["url"]).scheme == "https"
        # Dates, deadlines and prize money go stale; the page must not state them.
        text = " ".join([item["summary"], item["cadence"]])
        assert not re.search(r"\b20\d\d\b", text), item["slug"]
        assert not re.search(r"(₹|\$|€|£)\s?\d", text), item["slug"]
        assert "deadline:" not in text.lower()


def test_discontinued_programmes_are_not_listed():
    from engineverse import opportunities

    blob = json.dumps(opportunities.all_opportunities()).lower()
    for gone in ("code jam", "kvpy", "kick start"):
        assert gone not in blob


def test_opportunities_page_links_only_to_official_sites(client):
    from engineverse import opportunities

    html = client.get("/opportunities").text
    official = {o["url"] for o in opportunities.all_opportunities()}
    external = [a for a in _anchors(html) if a.get("href", "").startswith("http")]
    page_external = {a["href"] for a in external if a["href"] in official}
    assert page_external == official
    for a in external:
        if a["href"] in official:
            assert "noopener" in a.get("rel", ""), a["href"]
    flat = " ".join(html.split())
    assert "not affiliated with or endorsed by" in flat
    assert "Check dates and eligibility on the official site" in flat


# ------------------------------------------------------------------ support

def test_support_page_points_at_this_repository(client):
    from engineverse import project

    html = client.get("/support").text
    hrefs = {a.get("href") for a in _anchors(html)}
    assert project.issues_url() in hrefs
    assert project.security_advisory_url() in hrefs
    assert "authorsauravkushwaha" not in html
    # No made-up mailbox.
    assert "mailto:" not in html
    # The server build keeps its own feedback form as the no-GitHub route.
    assert 'href="#site-feedback"' in html
    assert 'id="site-feedback"' in html


# ------------------------------------------------------------------ planner

def test_planner_is_local_only_and_labelled(client):
    html = " ".join(client.get("/planner").text.split())
    assert "Saved on this device only" in html
    assert "/static/js/planner.js" in html
    assert "<noscript>" in html


def test_planner_script_never_talks_to_the_network_or_uses_innerhtml():
    source = (STATIC / "js" / "planner.js").read_text(encoding="utf-8")
    for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", ".innerHTML", "insertAdjacentHTML", "eval("):
        assert forbidden not in source, forbidden
    assert '"ev:planner:v1"' in source
    # Imports are validated against the export format before replacing data.
    assert "raw.format !== FORMAT" in source


# ------------------------------------------------------------- data export

def test_progress_export_requires_sign_in(client):
    response = client.get("/api/me/export")
    assert response.status_code == 401


def test_progress_export_returns_only_the_callers_data(signed_in, demo_user):
    response = signed_in.get("/api/me/export")
    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "")
    assert "no-store" in response.headers.get("cache-control", "")
    payload = response.json()
    assert payload["format"] == "engineverse-progress-export"
    assert payload["version"] == 1
    assert payload["username"] == demo_user["username"]
    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k.lower()
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    all_keys = set(keys(payload))
    for secret in ("password", "password_hash", "totp_secret", "otp", "token", "session", "email", "phone"):
        assert not any(secret in k for k in all_keys), secret
    assert "$scrypt" not in json.dumps(payload)


def test_old_public_sync_endpoints_are_gone(client):
    for path in ("/api/sync/snapshot?username=asha", "/api/sync/status"):
        assert client.get(path).status_code in (404, 405)


def test_settings_page_offers_the_export(signed_in):
    html = signed_in.get("/settings").text
    assert 'href="/api/me/export"' in html
