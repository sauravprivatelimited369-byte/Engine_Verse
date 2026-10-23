"""The exported personal pages and the browser runtime are one contract.

``scripts/export_pages.py`` writes the GitHub Pages copies of ``/dashboard``,
``/settings``, ``/mistakes`` and the other personal pages as HTML strings, and
``backend/static/js/pages-live.js`` drives them by element id. Nothing links
the two files, so they can drift apart silently: an id renamed on one side
leaves a page that renders but never fills in. These tests fail loudly when
the two sides disagree.

The static copy has no accounts (owner decision, 2026-10-23): progress lives
in this browser's localStorage and moves between devices as a JSON export.
The old browser-side passwords, OTP codes, GitHub token and "learner vault"
were removed, and the tests below keep them from coming back.
``scripts/check_static_site.js`` runs the same pages under jsdom.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scripts import export_pages

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = ROOT / "backend" / "static" / "js" / "pages-live.js"

# Ids the runtime creates itself, or that only exist on the live server build.
# Anything else it looks up must be in the exported markup.
CREATED_BY_THE_RUNTIME = {
    "ev-community-post-form",
    "ev-live-community-composer",
    "ev-rev-back",
    "ev-rev-card",
    "ev-rev-counter",
    "ev-rev-flip",
    "ev-rev-front",
    "ev-rev-rate",
    "ev-rev-subject",
}


@pytest.fixture(scope="module")
def runtime_source() -> str:
    return JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def templates() -> dict[str, str]:
    """The server-rendered templates the exporter rebuilds for Pages."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "backend" / "templates").rglob("*.html"))
    }


@pytest.fixture(scope="module")
def exported(tmp_path_factory) -> dict[str, str]:
    """Writes the exported account pages and returns ``path -> html``."""
    site = tmp_path_factory.mktemp("pages-export")
    # fill_shell() swaps whatever is inside `<main id="main" class="wrap">`, so
    # the stub has to use that exact opening tag.
    shell = (
        "<!doctype html><html><head><title>EngineVerse</title></head><body>"
        '<header class="topbar"><div class="topbar-right"></div></header>'
        '<main id="main" class="wrap"></main>'
        '<script type="application/json" id="ev-live">{}</script>'
        "</body></html>"
    )
    export_pages.write_account_pages(site, "/EngineVerse/", shell)
    pages = {}
    for path in sorted(site.rglob("*.html")):
        pages[str(path.relative_to(site))] = path.read_text(encoding="utf-8")
    assert len(pages) >= 8, f"the exporter wrote only {len(pages)} account pages"
    return pages


def _ids_referenced(source: str) -> set[str]:
    found = set(re.findall(r'getElementById\(\s*["`]([^"`$]+)["`]', source))
    found |= set(re.findall(r'querySelector(?:All)?\(\s*["`]#([A-Za-z0-9_-]+)["`]', source))
    return found


def _flexible_lookups(source: str) -> list[tuple[str, ...]]:
    """Every ``firstEl("a", "b")`` group of accepted ids for one control."""
    groups: list[tuple[str, ...]] = []
    for match in re.finditer(r"firstEl\(([^)]*)\)", source):
        ids = tuple(re.findall(r'"([A-Za-z0-9_-]+)"', match.group(1)))
        if len(ids) > 1:
            groups.append(ids)
    return groups


def _ids_in(html: str) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', html))


class TestExportedMarkupAndRuntimeAgree:
    def test_every_id_the_runtime_looks_up_exists_in_the_exported_pages(self, runtime_source, exported, templates):
        # The runtime also drives pages the exporter copies from the templates
        # (the code editor on a problem page, the mobile menu button in the
        # shell), so both sources count as "the markup".
        markup = set()
        for html in list(exported.values()) + list(templates.values()):
            markup |= _ids_in(html)
        referenced = _ids_referenced(runtime_source)
        missing = sorted(
            ident
            for ident in referenced
            if ident not in markup and ident not in CREATED_BY_THE_RUNTIME
        )
        assert not missing, (
            "pages-live.js looks these ids up but no exported page defines them: "
            f"{missing}"
        )

    def test_every_flexible_lookup_has_at_least_one_of_its_ids_present(self, runtime_source, exported):
        markup = set()
        for html in exported.values():
            markup |= _ids_in(html)
        broken = [
            " / ".join(group)
            for group in _flexible_lookups(runtime_source)
            if not any(ident in markup for ident in group)
        ]
        assert not broken, f"firstEl() accepts only ids no page has: {broken}"

    def test_the_personal_pages_carry_the_ids_the_runtime_fills(self, exported):
        expected = {
            "dashboard/index.html": ["ev-dash-greeting", "ev-stat-xp", "ev-stat-streak", "ev-stat-topics",
                                     "ev-dash-activity", "ev-dash-bookmarks"],
            "profile/index.html": ["ev-profile-name", "ev-profile-topics", "ev-profile-problems"],
            "settings/index.html": ["ev-profile-form", "ev-export-json", "ev-import-json", "ev-clear-data",
                                    "ev-settings-status"],
            "mistakes/index.html": ["ev-mistakes-list"],
            "portfolio/index.html": ["ev-portfolio-title", "ev-portfolio-print"],
        }
        for page, ids in expected.items():
            missing = [i for i in ids if f'id="{i}"' not in exported[page]]
            assert not missing, f"{page} is missing {missing}"

    def test_the_settings_form_field_names_match_the_runtime(self, exported, runtime_source):
        html = exported["settings/index.html"]
        for name in ("display_name", "branch", "year_of_study", "bio"):
            assert f'name="{name}"' in html, f"settings form has no {name} field"
            assert f"elements.{name}" in runtime_source, f"pages-live.js does not read {name}"

    def test_no_exported_page_collects_credentials_or_contact_details(self, exported):
        for page, html in exported.items():
            assert not re.search(r'type="(password|email|tel)"', html), f"{page} asks for credentials or contact details"
            assert not re.search(r"\bOTP\b|one-time code|6-digit", html), f"{page} still mentions OTP codes"

    def test_the_old_accounts_are_not_described_as_existing(self, exported):
        for page, html in exported.items():
            text = re.sub(r"\s+", " ", html)
            for phrase in ("learner vault", "GitHub Vault", "registry.json", "personal access token",
                           "Sign in to sync", "authorsauravkushwaha"):
                assert phrase.lower() not in text.lower(), f"{page} mentions {phrase!r}"

    def test_the_old_sign_in_urls_explain_the_local_model(self, exported):
        for page in ("login/index.html", "register/index.html", "forgot-password/index.html"):
            text = re.sub(r"\s+", " ", exported[page])
            assert "no accounts" in text.lower(), f"{page} does not say this copy has no accounts"
            assert "/EngineVerse/settings/" in text, f"{page} does not point to export/import"

    def test_the_runtime_has_no_remote_sync_or_secret_storage(self, runtime_source):
        for needle in ("api.github.com", "githubToken", "password_sha256", "BroadcastChannel",
                       "webhook", "otpApi", "ghp_"):
            assert needle not in runtime_source, f"pages-live.js still contains {needle!r}"

    def test_no_exported_account_page_posts_to_a_server(self, exported):
        """The Pages copy has no backend: no personal page submits anywhere."""
        for page, html in exported.items():
            assert not re.search(r'<form[^>]*method="post"', html, re.I), f"{page} has a POST form"
            for action in re.findall(r'<form[^>]*action="([^"]*)"', html):
                assert not action.startswith("/"), f"{page} posts to {action} with no server to answer"
