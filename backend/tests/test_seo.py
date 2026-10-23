"""Search-engine and social metadata for the public site.

What a crawler or a link preview reads, checked on the rendered pages:

* one canonical URL per page, with filter parameters dropped and page/card kept;
* a unique <title>, and a meta description on every public page;
* robots.txt that keeps private pages out of the crawl, and a sitemap that lists
  only canonical addresses;
* a 404 that is not indexed and names no canonical;
* 301s for retired addresses, and no redirect for the API;
* Open Graph and Twitter images at the card size, in PNG, with WebP copies;
* alt text and lazy loading on every image;
* Organization and BreadcrumbList structured data;
* server-rendered content in the first HTML response, without JavaScript.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from engineverse import db, navigation, redirects

ROOT = Path(__file__).resolve().parents[2]
STATIC_IMG = ROOT / "backend" / "static" / "img"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

#: Public pages without query strings. Each is rendered anonymously.
PUBLIC_PAGES = [
    "/", "/explore", "/topics/arrays", "/subjects/data-structures-algorithms",
    "/branches/computer-science", "/practice", "/practice/questions",
    "/practice/problems", "/practice/problems/two-sum", "/programming/python",
    "/projects", "/sheets", "/formulas", "/install", "/about", "/community",
    "/streams", "/roadmaps", "/flashcards", "/resources", "/videos", "/books",
]


def _meta(html: str, pattern: str) -> str | None:
    match = re.search(pattern, html)
    return match.group(1) if match else None


def _title(html: str) -> str | None:
    return _meta(html, r"<title>(.*?)</title>")


def _canonical(html: str) -> str | None:
    return _meta(html, r'<link rel="canonical" href="([^"]+)"')


def _description(html: str) -> str | None:
    return _meta(html, r'<meta name="description" content="([^"]*)"')


def _json_ld(html: str) -> list:
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return [json.loads(block) for block in blocks]


# ---------------------------------------------------------------------------
# Canonical, titles and descriptions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_every_public_page_has_one_canonical_title_and_description(client, seeded, path):
    html = client.get(path).text
    assert html.count('rel="canonical"') == 1, path
    canonical = _canonical(html)
    assert canonical and canonical.startswith("http"), path
    assert "?" not in canonical, f"{path} canonical carries a query: {canonical}"
    assert (_title(html) or "").strip(), f"{path} has no title"
    description = _description(html) or ""
    assert 20 <= len(description) <= 200, f"{path} description is {len(description)} characters"


def test_a_description_is_the_page_s_own_not_the_tagline(client, seeded):
    """Forty pages used to share the tagline as their description."""
    tagline = "Engineering, studied properly."
    html = client.get("/explore").text
    assert _description(html) != tagline
    assert "catalogue" in (_description(html) or "").lower()


def test_titles_are_unique_across_public_pages(client, seeded):
    titles = {}
    for path in PUBLIC_PAGES:
        titles.setdefault(_title(client.get(path).text), []).append(path)
    duplicates = {title: paths for title, paths in titles.items() if len(paths) > 1}
    assert not duplicates, f"pages share a title: {duplicates}"


def test_canonical_drops_filters_but_keeps_pagination(client, seeded):
    assert _canonical(client.get("/search?q=bernoulli").text).endswith("/search")
    assert _canonical(client.get("/explore?branch=civil-engineering").text).endswith("/explore")
    assert _canonical(client.get("/topics/arrays?depths=all").text).endswith("/topics/arrays")
    assert _canonical(client.get("/explore?page=2").text).endswith("/explore?page=2")
    assert _canonical(client.get("/explore?page=1").text).endswith("/explore")


def test_no_page_is_marked_noindex_when_anonymous(client, seeded):
    for path in PUBLIC_PAGES:
        assert 'name="robots" content="noindex' not in client.get(path).text, path


# ---------------------------------------------------------------------------
# robots.txt and the sitemap
# ---------------------------------------------------------------------------

def test_robots_txt_keeps_private_pages_out_of_the_crawl(client, seeded):
    body = client.get("/robots.txt").text
    for path in navigation.NON_INDEXABLE:
        assert f"Disallow: {path}\n" in body, path
    assert "Disallow: /api/\n" in body
    assert body.rstrip().splitlines()[-1].startswith("Sitemap: ")


def test_sitemap_is_well_formed_and_lists_only_canonical_addresses(client, seeded):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    locations = [node.text for node in ElementTree.fromstring(response.content).iter(f"{NS}loc")]
    assert locations, "the sitemap is empty"
    assert len(locations) == len(set(locations)), "the sitemap lists an address twice"
    for loc in locations:
        query = loc.split("?", 1)[1] if "?" in loc else ""
        keys = {part.split("=", 1)[0] for part in query.split("&") if part}
        assert keys <= {"page", "card"}, f"non-canonical address in the sitemap: {loc}"


def test_sitemap_omits_private_pages(client, seeded):
    body = client.get("/sitemap.xml").text
    for path in navigation.NON_INDEXABLE:
        assert f"{path}</loc>" not in body, path


# ---------------------------------------------------------------------------
# Errors and redirects
# ---------------------------------------------------------------------------

def test_the_404_page_is_noindex_and_names_no_canonical(client, seeded):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert 'name="robots" content="noindex' in response.text
    assert 'rel="canonical"' not in response.text
    assert "That page does not exist." in response.text


@pytest.mark.parametrize("old, new", [
    ("/topics/arrays/", "/topics/arrays"),
    ("/topic/arrays", "/topics/arrays"),
    ("/subjects", "/explore"),
    ("/practise/questions/", "/practice/questions"),
    ("/problems/two-sum", "/practice/problems/two-sum"),
    ("/explore/first-year", "/explore?year=1"),
    ("/explore/first-year/", "/explore?year=1"),
])
def test_retired_addresses_answer_301_to_their_replacement(client, seeded, old, new):
    response = client.get(old, follow_redirects=False)
    assert response.status_code == 301, old
    assert response.headers["location"] == new


def test_the_dashboard_alias_is_a_permanent_redirect(client, seeded):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 301 and response.headers["location"] == "/"


def test_a_redirect_keeps_the_query_string(client, seeded):
    response = client.get("/topics/arrays/?depths=all", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/topics/arrays?depths=all"


def test_every_redirect_target_is_a_real_page(client, seeded):
    for old, new in redirects.EXACT.items():
        if old.endswith(".html"):
            continue
        response = client.get(new.split("?", 1)[0], follow_redirects=False)
        assert response.status_code == 200, f"{old} -> {new} answers {response.status_code}"


def test_the_api_is_never_redirected(client, seeded):
    response = client.get("/api/nope/", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["ok"] is False


@pytest.mark.parametrize("target", ["//evil.example/x/", "/topic/../x", "/topic/a/b", "//x/"])
def test_redirect_rules_never_build_an_offsite_or_nested_location(target):
    result = redirects.target_for(target)
    assert result is None or (result.startswith("/") and not result.startswith("//"))


# ---------------------------------------------------------------------------
# Social previews and images
# ---------------------------------------------------------------------------

def test_the_social_card_is_an_absolute_1200x630_png(client, seeded):
    html = client.get("/").text
    image = _meta(html, r'<meta property="og:image" content="([^"]+)"')
    assert image and image.startswith("http") and image.endswith("/static/img/og-image.png")
    assert _meta(html, r'<meta property="og:image:width" content="([^"]+)"') == "1200"
    assert _meta(html, r'<meta property="og:image:height" content="([^"]+)"') == "630"
    assert _meta(html, r'<meta name="twitter:card" content="([^"]+)"') == "summary_large_image"
    response = client.get("/static/img/og-image.png")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"


def test_the_social_card_is_the_same_on_every_page(client, seeded):
    for path in ("/topics/arrays", "/install"):
        html = client.get(path).text
        assert _meta(html, r'<meta property="og:image" content="([^"]+)"').endswith("/static/img/og-image.png")


@pytest.mark.parametrize("name", ["og-image.webp", "app-icon-192.webp", "app-icon-512.webp"])
def test_the_webp_copies_exist_and_decode(name):
    from PIL import Image

    path = STATIC_IMG / name
    assert path.exists(), name
    with Image.open(path) as image:
        assert image.format == "WEBP"
    if name == "og-image.webp":
        with Image.open(path) as image:
            assert image.size == (1200, 630)


def test_the_install_page_shows_the_app_icon_as_webp_with_a_png_fallback(client, seeded):
    html = client.get("/install").text
    assert '<source type="image/webp" srcset="/static/img/app-icon-192.webp">' in html
    assert 'src="/static/icons/icon-192.png"' in html
    # The site name is configurable and other tests share the database, so the
    # check is on the descriptive part of the alt text, not on the name.
    assert re.search(r'alt="[^"]+ app icon: the M mark inside a meridian ring"', html)


def _img_tags(html: str) -> list[str]:
    return re.findall(r"<img\b[^>]*>", html)


@pytest.mark.parametrize("path", PUBLIC_PAGES + ["/topics/bernoullis-equation"])
def test_every_image_has_alt_text_and_a_loading_strategy(client, seeded, path):
    for tag in _img_tags(client.get(path).text):
        alt = re.search(r'alt="([^"]*)"', tag)
        assert alt and alt.group(1).strip(), f"{path}: image without alt text: {tag[:120]}"
        loading = re.search(r'loading="(lazy|eager)"', tag)
        assert loading, f"{path}: image without a loading attribute: {tag[:120]}"


def test_below_the_fold_images_load_lazily(client, seeded):
    tag = next(t for t in _img_tags(client.get("/install").text) if "app-icon" in t or "icon-192" in t)
    assert 'loading="eager"' in tag, "the first-screen icon must not wait for lazy loading"


# ---------------------------------------------------------------------------
# Structured data
# ---------------------------------------------------------------------------

def test_the_home_page_declares_the_organisation(client, seeded):
    blocks = _json_ld(client.get("/").text)
    organisations = [b for b in blocks if b.get("@type") == "Organization"]
    assert len(organisations) == 1
    org = organisations[0]
    assert org["@context"] == "https://schema.org"
    assert org["name"] and org["url"].startswith("http") and org["logo"].startswith("http")
    assert org["sameAs"] and org["sameAs"][0].startswith("https://github.com/")
    assert "email" not in org and "address" not in org, "no contact or address is invented"


def test_organisation_data_is_only_on_the_home_page(client, seeded):
    assert not [b for b in _json_ld(client.get("/explore").text) if b.get("@type") == "Organization"]


def test_breadcrumb_data_mirrors_the_visible_trail(client, seeded):
    html = client.get("/topics/arrays").text
    crumbs = [b for b in _json_ld(html) if b.get("@type") == "BreadcrumbList"]
    assert len(crumbs) == 1
    items = crumbs[0]["itemListElement"]
    visible = re.findall(r'<nav class="crumbs"[^>]*>(.*?)</nav>', html, re.S)[0]
    # The trail runs Home > Learn > subject > topic, so the structured data has the
    # same four levels as the visible breadcrumb, in the same order.
    assert len(items) == len(re.findall(r"<li>", visible)) == 4
    assert [item["name"] for item in items][0::3] == ["Home", "Arrays"]
    assert items[1]["name"] == "Learn"
    assert [item["position"] for item in items] == [1, 2, 3, 4]
    assert items[0]["item"].endswith("/") and items[0]["item"].startswith("http")
    assert items[-1]["item"] == _canonical(html)


def test_no_breadcrumb_data_on_a_page_without_a_trail(client, seeded):
    assert not [b for b in _json_ld(client.get("/").text) if b.get("@type") == "BreadcrumbList"]


def test_structured_data_is_valid_json_on_every_public_page(client, seeded):
    for path in PUBLIC_PAGES:
        for block in _json_ld(client.get(path).text):
            assert "@context" in block and "@type" in block, path


# ---------------------------------------------------------------------------
# Server rendering
# ---------------------------------------------------------------------------

def test_content_is_in_the_first_html_response(client, seeded):
    """Crawlers read the HTML as sent; the page must not depend on JavaScript."""
    topic = db.query_one("SELECT title FROM topics WHERE slug = 'arrays'")
    html = client.get("/topics/arrays").text
    assert topic["title"] in html
    problem = db.query_one("SELECT title FROM coding_problems WHERE slug = 'two-sum'")
    assert problem["title"] in client.get("/practice/problems/two-sum").text


# ---------------------------------------------------------------------------
# The static copy
# ---------------------------------------------------------------------------

def test_the_export_rewrites_srcset_under_the_pages_base():
    from scripts import export_pages

    html = export_pages.rewrite_html('<source srcset="/static/img/app-icon-192.webp">', "/EngineVerse/")
    assert 'srcset="/EngineVerse/static/img/app-icon-192.webp"' in html


def test_the_export_writes_refresh_pages_for_exact_redirects(tmp_path):
    from scripts import export_pages

    site = tmp_path / "site"
    site.mkdir()
    (site / "explore" / "first-year").mkdir(parents=True)
    (site / "explore" / "first-year" / "index.html").write_text("real page", encoding="utf-8")
    export_pages.write_redirect_stubs(site, "/EngineVerse/")

    stub = (site / "subjects" / "index.html").read_text(encoding="utf-8")
    assert 'http-equiv="refresh" content="0; url=/EngineVerse/explore/"' in stub
    assert 'name="robots" content="noindex, follow"' in stub
    assert (site / "explore" / "first-year" / "index.html").read_text(encoding="utf-8") == "real page"
