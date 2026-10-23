"""Static export contract: URL rewriting, install page, editor and boot data.

Formerly test_github_sync_and_apk.py. The learner registry sync it also
covered was removed (public issues held learner data); those tests went with it.
"""
from __future__ import annotations

import json

from engineverse import project
from scripts import export_pages

APK = project.release_download_prefix() + "android-v1.0.0/EngineVerse.apk"


def test_release_download_prefix_names_this_repository():
    assert APK.startswith(project.repo_url() + "/releases/download/")
    assert "authorsauravkushwaha" not in APK


def test_static_pages_rewrite_links_install_page_and_problem_editor():
    rewritten = export_pages.rewrite_html(
        '<a href="/settings">Settings</a><a href="/dashboard">Dashboard</a>',
        "/EngineVerse/",
    )
    assert 'href="/EngineVerse/settings/"' in rewritten
    assert 'href="/EngineVerse/dashboard/"' in rewritten

    install_with_apk = export_pages.reading_copy_install_main("", APK)
    assert f'href="{APK}"' in install_with_apk
    install_without = export_pages.reading_copy_install_main("", "")
    assert "releases/download" not in install_without
    assert "actions/workflows/android-build.yml" in install_without

    problem_html = (
        '<select id="lang-select">'
        '<option value="python">Python</option>'
        '<option value="cpp" disabled>C++ (starter only)</option>'
        '</select>'
        '<button class="btn btn-ghost" id="btn-run" type="button">Run</button>'
    )
    enabled = export_pages.enable_problem_editor(problem_html)
    assert "disabled" not in enabled
    assert "(starter only)" not in enabled
    assert 'id="btn-submit"' in enabled


def test_live_boot_carries_data_urls_and_no_account_plumbing():
    boot = export_pages.live_boot("/EngineVerse/", ["2026-10-15"], apk_url=APK)
    payload = json.loads(boot.split(">", 1)[1].rsplit("<", 1)[0])
    assert payload["quizBank"] == "/EngineVerse/quiz-bank.json"
    assert payload["codingProblems"] == "/EngineVerse/coding-problems.json"
    assert payload["studioSnapshot"] == "/EngineVerse/studio-snapshot.json"
    assert payload["workflowsCatalog"] == "/EngineVerse/workflows-catalog.json"
    assert payload["swarmCorpus"] == "/EngineVerse/swarm-corpus.json"
    assert payload["apkUrl"] == APK
    for removed in ("vault", "githubRepo", "githubVaultPath", "otpApiUrl", "identity"):
        assert removed not in payload, f"boot data still carries {removed!r}"


def test_forms_redirected_to_hosting_never_post():
    html = export_pages.rewrite_html('<form method="post" action="/practice/check"></form>', "/EngineVerse/")
    assert 'method="get"' in html and 'action="/EngineVerse/hosting/"' in html


def _hero(html: str) -> str:
    """The first screen only: what a reader is told before scrolling."""
    return html.split("</section>", 1)[0]


def test_static_home_page_makes_no_account_claims(client, monkeypatch):
    """The Pages copy has no accounts, so the hero must not promise them.

    Asserted on meaning rather than on one sentence: the exported hero has to
    say where progress lives (this browser), and must not tell a reader that an
    account keeps it, or send them to a server this copy does not have. The
    hosted copy is the mirror image. Copy may be rewritten; the claim may not.
    """
    monkeypatch.setenv("ENGINEVERSE_STATIC_EXPORT", "1")
    static_hero = _hero(client.get("/").text)
    assert "this browser" in static_hero
    assert "account keeps progress" not in static_hero
    assert "self-hosted" not in static_hero

    monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT")
    hosted_hero = _hero(client.get("/").text)
    assert "One account keeps progress across devices" in hosted_hero
    assert "this browser" not in hosted_hero
