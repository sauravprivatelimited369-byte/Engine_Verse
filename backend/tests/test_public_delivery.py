"""Pages handoff, signed Android link and private encrypted off-site backup."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from engineverse import project
from engineverse.config import reload_settings
from engineverse.distribution import normalise_apk_url
from scripts import export_pages, verify_apk_release, verify_hosted_app, verify_pages, verify_twa

ROOT = Path(__file__).resolve().parents[2]
APK = project.release_download_prefix() + "android-v1.2.3/EngineVerse.apk"
ORIGIN = "https://learn.example.org"
FINGERPRINT = ":".join(["A1"] * 32)


def test_apk_url_is_versioned_and_owned_by_this_repo():
    assert normalise_apk_url("") == ""
    assert normalise_apk_url(APK) == APK
    for invalid in (
        "https://evil.example/EngineVerse.apk", "javascript:alert(1)",
        "https://github.com/other/EngineVerse/releases/download/android-v1.2.3/EngineVerse.apk",
        APK + "?redirect=evil", APK.replace("android-v1.2.3", "../android-v1.2.3"),
        APK.replace("EngineVerse.apk", "debug.apk"),
    ):
        with pytest.raises(ValueError):
            normalise_apk_url(invalid)


def test_install_is_public_even_when_catalogue_requires_signin(seeded, monkeypatch):
    monkeypatch.setenv("ENGINEVERSE_SIGNIN", "required")
    monkeypatch.delenv("ENGINEVERSE_APK_URL", raising=False)
    reload_settings()
    from main import create_app
    try:
        with TestClient(create_app(), follow_redirects=False) as web:
            page = web.get("/install")
            assert page.status_code == 200
            assert "No signed APK has been published" in page.text
            assert "Download EngineVerse.apk" not in page.text
            assert web.get("/explore").status_code == 303
            assert web.get("/.well-known/assetlinks.json").status_code == 404
    finally:
        monkeypatch.undo()
        reload_settings()


def test_only_the_approved_apk_is_advertised(seeded, monkeypatch):
    from main import create_app
    monkeypatch.setenv("ENGINEVERSE_APK_URL", APK)
    reload_settings()
    try:
        with TestClient(create_app()) as web:
            assert f'href="{APK}"' in web.get("/install").text
        monkeypatch.setenv("ENGINEVERSE_APK_URL", "https://evil.example/download.apk")
        settings = reload_settings()
        assert not settings.approved_apk_url
        monkeypatch.setenv("ENGINEVERSE_ENV", "production")
        assert any("ENGINEVERSE_APK_URL" in error for error in reload_settings().production_problems())
    finally:
        monkeypatch.undo()
        reload_settings()


def test_gateway_keeps_paths_and_never_claims_a_release_without_one(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    site = tmp_path / "site"
    export_pages.export_gateway(site, "/EngineVerse/", ORIGIN)
    manifest = json.loads((site / "deployment.json").read_text())
    assert manifest == {"revision": "a" * 40, "mode": "gateway",
                        "base": "/EngineVerse/", "app_url": ORIGIN}
    home = (site / "index.html").read_text()
    moved = (site / "404.html").read_text()
    assert f'href="{ORIGIN}/"' in home
    assert f'href="{ORIGIN}/install"' in home
    assert "Download signed" not in home
    assert "location.replace(app+path+location.search+location.hash)" in moved
    assert "/EngineVerse/static/css/app.css" in home
    assert "Not hosted yet" in export_pages.gateway_page("/EngineVerse/", "", "EngineVerse")
    assert "there is no APK download here" in export_pages.reading_copy_install_main(ORIGIN)
    assert "Download signed" not in export_pages.reading_copy_install_main(ORIGIN)
    export_pages.export_gateway(site, "/EngineVerse/", ORIGIN, apk_url=APK)
    assert f'href="{APK}"' in (site / "index.html").read_text()
    assert f'href="{APK}"' in (site / "404.html").read_text()


@pytest.mark.skipif(not shutil.which("node"), reason="Node is required to test the browser redirect")
def test_old_pages_bookmark_opens_same_page_on_host_and_not_on_another_origin():
    page = export_pages.gateway_page("/EngineVerse/", ORIGIN, "EngineVerse", not_found=True)
    script = re.search(r"<script>(.*?)</script>", page, flags=re.S).group(1)
    program = """
const vm = require('node:vm');
const script = %s;
function target(path, search='') {
  let result = null;
  const location = { pathname: path, search, hash: '#section', replace: (value) => result = value };
  vm.runInNewContext(script, { location });
  return result;
}
if (target('/EngineVerse/topics/ohms-law/', '?depths=all') !==
    'https://learn.example.org/topics/ohms-law/?depths=all#section') process.exit(1);
if (target('/EngineVerseEvil/topics/ohms-law/') !== null) process.exit(2);
if (target('/EngineVerse/../outside/') !== 'https://learn.example.org/#section') process.exit(3);
""" % json.dumps(script)
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_pages_verifier_checks_gateway_mode_sha_and_links(monkeypatch):
    page = export_pages.gateway_page("/EngineVerse/", ORIGIN, "EngineVerse")
    moved = export_pages.gateway_page("/EngineVerse/", ORIGIN, "EngineVerse", not_found=True)
    sha = "b" * 40

    def fake_fetch(url, _sha, _attempt, _content_type):
        if url.endswith("deployment.json"):
            return json.dumps({"revision": sha, "mode": "gateway", "app_url": ORIGIN})
        if url.endswith("404.html"):
            return moved
        if url.endswith("app.css"):
            return "body { color: #fff; }"
        return page

    monkeypatch.setattr(verify_pages, "_fetch", fake_fetch)
    verify_pages.verify("https://user.github.io/EngineVerse/", sha, mode="gateway",
                        app_url=ORIGIN, attempts=1, delay=0)
    with pytest.raises(SystemExit, match="expected Pages mode"):
        verify_pages.verify("https://user.github.io/EngineVerse/", sha,
                            mode="reading-copy", attempts=1, delay=0)
    with pytest.raises(SystemExit, match="not pointing"):
        verify_pages.verify("https://user.github.io/EngineVerse/", sha, mode="gateway",
                            app_url="https://other.example.org", attempts=1, delay=0)


def _host_response(_origin, path):
    if path == "/health":
        return "application/json", json.dumps({"ok": True, "brand": "EngineVerse"})
    if path == "/manifest.webmanifest":
        return "application/manifest+json", json.dumps({
            "start_url": "/", "scope": "/", "icons": [{"src": "/static/icons/icon-512.png"}]
        })
    if path == "/login":
        return "text/html", '<form action="/login"></form>'
    if path == "/register":
        return "text/html", '<form action="/register"></form>'
    if path == "/install":
        return "text/html", "<h1>Android</h1>"
    raise ValueError(path)


def _host_raw_response(_origin, path):
    """A healthy production host, as (status, headers, body) triples."""
    if path == "/health":
        return 200, {"content-type": "application/json",
                     "strict-transport-security": "max-age=63072000",
                     "content-security-policy": "default-src 'self'",
                     "x-content-type-options": "nosniff"}, json.dumps({"ok": True, "brand": "EngineVerse"})
    if path == "/forgot-password":
        return 200, {"content-type": "text/html"}, '<form action="/forgot-password"></form>'
    if path in ("/api/me", "/api/coding/submissions"):
        return 401, {"content-type": "application/json"}, '{"ok": false, "error": "Sign in to continue."}'
    if path == "/api/coding/languages":
        return 200, {"content-type": "application/json"}, json.dumps({
            "ok": True, "runnable": [],
            "languages": [{"slug": "python", "runnable": False}],
        })
    if path in ("/.env", "/data/engineverse.sqlite", "/.git/config"):
        return 404, {"content-type": "text/html"}, "Not found"
    raise ValueError(path)


def test_gateway_requires_a_real_production_app_with_open_registration():
    verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=_host_raw_response)
    def development(origin, path):
        if path == "/health":
            return "application/json", json.dumps({"ok": True, "brand": "EngineVerse", "users": 1})
        return _host_response(origin, path)
    def development_raw(origin, path):
        if path == "/health":
            return 200, {"content-type": "application/json"}, json.dumps(
                {"ok": True, "brand": "EngineVerse", "users": 1})
        return _host_raw_response(origin, path)
    with pytest.raises(ValueError, match="development-only"):
        verify_hosted_app.verify(ORIGIN, get=development, get_raw=development_raw)
    def closed(origin, path):
        if path == "/register":
            return "text/html", "Registration closed"
        return _host_response(origin, path)
    with pytest.raises(ValueError, match="register"):
        verify_hosted_app.verify(ORIGIN, get=closed, get_raw=_host_raw_response)
    with pytest.raises(ValueError, match="HTTPS"):
        verify_hosted_app.verify("http://localhost:8000", get=_host_response,
                                 get_raw=_host_raw_response)


def _raw_with(overrides):
    def get_raw(origin, path):
        if path in overrides:
            return overrides[path]
        return _host_raw_response(origin, path)
    return get_raw


def test_gateway_requires_a_recovery_form_without_leaked_tokens():
    missing = _raw_with({"/forgot-password": (404, {}, "Not found")})
    with pytest.raises(ValueError, match="forgot-password"):
        verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=missing)
    leaked = _raw_with({"/forgot-password": (
        200, {"content-type": "text/html"},
        '<form action="/forgot-password"></form><div>Development build</div>'
        '<a href="/reset-password?token=abc123">Continue</a>')})
    with pytest.raises(ValueError, match="reset tokens"):
        verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=leaked)


def test_gateway_requires_anonymous_api_isolation():
    leaking = _raw_with({"/api/me": (
        200, {"content-type": "application/json"}, '{"ok": true, "user": {"id": "u1"}}')})
    with pytest.raises(ValueError, match="/api/me"):
        verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=leaking)
    leaking_submissions = _raw_with({"/api/coding/submissions": (
        200, {"content-type": "application/json"}, '{"ok": true, "submissions": []}')})
    with pytest.raises(ValueError, match="/api/coding/submissions"):
        verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=leaking_submissions)


def test_gateway_checks_the_judge_shape_and_secret_hygiene():
    bogus = _raw_with({"/api/coding/languages": (
        200, {"content-type": "application/json"},
        json.dumps({"ok": True, "runnable": ["klingon"], "languages": []}))})
    with pytest.raises(ValueError, match="runnable|language catalogue"):
        verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=bogus)
    behind_signin = _raw_with({"/api/coding/languages": (
        401, {"content-type": "application/json"}, '{"ok": false}')})
    verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=behind_signin)
    served_env = _raw_with({"/.env": (200, {"content-type": "text/plain"}, "ENGINEVERSE_SECRET=x")})
    with pytest.raises(ValueError, match="/.env"):
        verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=served_env)
    login_redirect = _raw_with({"/.env": (303, {"location": "/login?next=/.env"}, "")})
    verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=login_redirect)


def test_gateway_warns_on_missing_security_headers(capsys):
    bare = _raw_with({"/health": (
        200, {"content-type": "application/json"}, json.dumps({"ok": True, "brand": "EngineVerse"}))})
    verify_hosted_app.verify(ORIGIN, get=_host_response, get_raw=bare)
    captured = capsys.readouterr().out
    assert "WARNING" in captured and "HSTS" in captured


def test_gate_expectations_match_the_real_app(client):
    """Every new gate assertion, checked against the real routes.

    The stubbed tests above prove the gate refuses bad hosts; this proves a
    healthy EngineVerse app actually satisfies those assertions, so the gate
    cannot fail a good deployment (apart from the production-only /health
    shape, which the test environment deliberately does not mimic).
    """
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert 'action="/forgot-password"' in response.text
    assert "Development build" not in response.text
    assert "reset-password?token=" not in response.text

    for path in ("/api/me", "/api/coding/submissions"):
        response = client.get(path)
        assert response.status_code == 401, path
        lowered = response.text.lower()
        assert "sign in" in lowered or "signed in" in lowered or '"ok":false' in lowered, path

    response = client.get("/api/coding/languages")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["languages"], list) and payload["languages"]
    assert isinstance(payload["runnable"], list)
    assert not (set(payload["runnable"]) - verify_hosted_app.KNOWN_LANGUAGE_SLUGS)
    for language in payload["languages"]:
        assert "slug" in language and "runnable" in language

    for path in ("/.env", "/data/engineverse.sqlite", "/.git/config"):
        assert client.get(path).status_code == 404, path

    health = client.get("/health")
    assert health.status_code == 200
    assert "content-security-policy" in {key.lower() for key in health.headers}


def test_digital_asset_links_must_match_the_actual_signing_key():
    def get(_origin, _path):
        return "application/json", json.dumps([{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {"namespace": "android_app", "package_name": "org.engineverse.app",
                       "sha256_cert_fingerprints": [FINGERPRINT]},
        }])
    verify_twa.verify(ORIGIN, "org.engineverse.app", FINGERPRINT, get=get)
    with pytest.raises(ValueError, match="do not match"):
        verify_twa.verify(ORIGIN, "org.engineverse.app", ":".join(["AB"] * 32), get=get)
    with pytest.raises(ValueError, match="required"):
        verify_twa.verify(ORIGIN, "bad package", FINGERPRINT, get=get)


def test_pages_never_advertises_a_missing_or_draft_apk_release():
    commands = []
    def run(args, **_kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "assets": [{"name": "EngineVerse.apk", "size": 100}], "isDraft": False,
        }))
    verify_apk_release.verify(APK, run=run)
    assert commands[0][3] == "android-v1.2.3"
    with pytest.raises(ValueError):
        verify_apk_release.verify("https://evil.example/app.apk", run=run)
    def draft(_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "assets": [{"name": "EngineVerse.apk", "size": 100}], "isDraft": True,
        }))
    with pytest.raises(ValueError, match="nonempty"):
        verify_apk_release.verify(APK, run=draft)


def test_encrypted_backup_requires_private_repo_and_uploads_only_ciphertext(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "release-args"
    (bin_dir / "gh").write_text(
        '#!/bin/sh\nif [ "$1" = repo ]; then echo "${TEST_PRIVATE:-true}"; exit 0; fi\n'
        'for arg in "$@"; do case "$arg" in *.age)\n'
        '  [ -s "$arg" ] && ! grep -q "private-learner" "$arg" || exit 8;; esac; done\n'
        'printf "%s\\n" "$@" > "$TEST_RELEASE_ARGS"\n', encoding="utf-8",
    )
    (bin_dir / "pg_dump").write_text('#!/bin/sh\nprintf "private-learner@example.org"\n', encoding="utf-8")
    (bin_dir / "age").write_text(
        '#!/bin/sh\n[ "$1" = -r ] && [ "$3" = -o ] || exit 8\ncat >/dev/null\n'
        'head -c 80 /dev/zero | tr "\\000" X > "$4"\n', encoding="utf-8",
    )
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    temp = tmp_path / "private-temp"
    temp.mkdir()
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
           "TEST_RELEASE_ARGS": str(log), "TMPDIR": str(temp),
           "ENGINEVERSE_BACKUP_REPO": "operator/engineverse-private-backups",
           "ENGINEVERSE_BACKUP_AGE_RECIPIENT": "age1recipient-for-test",
           "GH_TOKEN": "private-gh-token-never-print", "PGHOST": "db", "PGUSER": "backup",
           "PGDATABASE": "engineverse", "PGPASSWORD": "private-db-password-never-print"}
    result = subprocess.run(["bash", "scripts/backup_github.sh"], cwd=ROOT,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "release\ncreate\nengineverse-backup-" in log.read_text()
    assert "private-learner" not in log.read_text() + result.stdout + result.stderr
    assert "private-db-password" not in result.stdout + result.stderr
    assert "private-gh-token" not in result.stdout + result.stderr
    assert list(temp.iterdir()) == [], "temporary ciphertext must be removed after upload"
    log.unlink()
    env["TEST_PRIVATE"] = "false"
    refused = subprocess.run(["bash", "scripts/backup_github.sh"], cwd=ROOT,
                             env=env, capture_output=True, text=True)
    assert refused.returncode != 0
    assert "not private" in refused.stderr
    assert not log.exists(), "a public repository must never receive a release"
    # If pg_dump emitted bytes and THEN failed, pipefail must still refuse an
    # apparently encrypted but incomplete archive; nothing is uploaded.
    env["TEST_PRIVATE"] = "true"
    (bin_dir / "pg_dump").write_text(
        '#!/bin/sh\nprintf "partial-private-learner@example.org"\nexit 3\n', encoding="utf-8"
    )
    incomplete = subprocess.run(["bash", "scripts/backup_github.sh"], cwd=ROOT,
                                env=env, capture_output=True, text=True)
    assert incomplete.returncode != 0 and not log.exists()
    assert list(temp.iterdir()) == []


@pytest.mark.skipif(not shutil.which("node"), reason="Node is required for the TWA build self-check")
def test_twa_generator_refuses_to_point_at_the_pages_or_an_untrusted_host():
    result = subprocess.run(["node", "android/build-twa.cjs", "--self-check"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "self-check ok" in result.stdout


def test_public_compose_keeps_postgres_private_and_does_not_commit_credentials():
    edge = (ROOT / "deploy" / "public.yml").read_text()
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()
    github = (ROOT / "deploy" / "github-backups.yml").read_text()
    base = (ROOT / "deploy" / "docker-compose.yml").read_text()
    assert "80:80" in edge and "443:443" in edge
    assert "header_up X-Forwarded-For {remote_host}" in caddy
    assert "ENGINEVERSE_APK_URL" in base and "ENGINEVERSE_TWA_SHA256" in base
    assert "PGUSER: engineverse_app" in github and "ENGINEVERSE_BACKUP_GH_TOKEN:?" in github
    assert "networks: [internal, backup-egress]" in github
    assert '127.0.0.1:8000:8000' in base and '"5432:5432"' not in base


def test_macos_and_ios_urls_are_strictly_validated():
    from engineverse.distribution import ios_url_kind, normalise_ios_url, normalise_macos_url

    macos_dmg = project.release_download_prefix() + "apple-v1.0.0/Meridian-macOS.dmg"
    macos_tag_v = project.release_download_prefix() + "v1.0.0/Meridian-macOS.dmg"
    ios_ipa = project.release_download_prefix() + "apple-v1.0.0/Meridian-iOS.ipa"
    tf_url = "https://testflight.apple.com/join/AbCdEf12"
    store_url = "https://apps.apple.com/us/app/meridian-study/id1234567890"

    assert normalise_macos_url("") == ""
    assert normalise_macos_url(macos_dmg) == macos_dmg
    assert normalise_macos_url(macos_tag_v) == macos_tag_v

    assert normalise_ios_url("") == ""
    assert normalise_ios_url(ios_ipa) == ios_ipa
    assert normalise_ios_url(tf_url) == tf_url
    assert normalise_ios_url(store_url) == store_url
    assert ios_url_kind(ios_ipa) == "ipa"
    assert ios_url_kind(tf_url) == "testflight"
    assert ios_url_kind(store_url) == "appstore"
    assert ios_url_kind("/downloads/Meridian-iOS.ipa") == "ipa"

    for invalid_mac in (
        "https://evil.example/Meridian-macOS.dmg",
        "javascript:alert(1)",
        macos_dmg + "?redirect=evil",
        macos_dmg.replace("apple-v1.0.0", "../apple-v1.0.0"),
        project.release_download_prefix() + "apple-v1.0.0/untrusted.dmg",
    ):
        with pytest.raises(ValueError):
            normalise_macos_url(invalid_mac)

    for invalid_ios in (
        "https://evil.example/Meridian-iOS.ipa",
        "http://apps.apple.com/app/id1234567890",
        ios_ipa + "?token=1",
        "https://testflight.apple.com/join/../../etc",
        project.release_download_prefix() + "apple-v1.0.0/Meridian.mobileconfig",
    ):
        with pytest.raises(ValueError):
            normalise_ios_url(invalid_ios)


def test_apple_package_verifier_and_local_downloads_work_end_to_end(seeded, tmp_path, monkeypatch):
    import hashlib
    import io
    import zipfile
    from main import create_app
    from scripts import verify_apple_release

    # Construct minimal valid DMG (with Apple UDIF 'koly' trailer) and IPA (with Mach-O binary + plist + catalog).
    dmg_bytes = b"\x00" * 5000 + b"koly" + b"\x00" * 508
    dmg_sha = hashlib.sha256(dmg_bytes).hexdigest()

    ipa_buf = io.BytesIO()
    with zipfile.ZipFile(ipa_buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("Payload/Meridian.app/Info.plist", b"<?xml version='1.0'?><plist/>")
        zf.writestr("Payload/Meridian.app/Meridian", b"\xcf\xfa\xed\xfe" + b"\x00" * 5000)
        zf.writestr("Payload/Meridian.app/catalog.json", b'{"format":"engineverse-apple-catalog","version":1,"subjects":[]}')
    ipa_bytes = ipa_buf.getvalue()
    ipa_sha = hashlib.sha256(ipa_bytes).hexdigest()

    (tmp_path / "Meridian-macOS.dmg").write_bytes(dmg_bytes)
    (tmp_path / "Meridian-macOS.dmg.sha256").write_text(f"{dmg_sha}  Meridian-macOS.dmg\n")
    (tmp_path / "Meridian-iOS.ipa").write_bytes(ipa_bytes)
    (tmp_path / "Meridian-iOS.ipa.sha256").write_text(f"{ipa_sha}  Meridian-iOS.ipa\n")

    verified = verify_apple_release.verify_local_dir(tmp_path)
    assert verified == {"macos_sha256": dmg_sha, "ios_sha256": ipa_sha}

    monkeypatch.setenv("ENGINEVERSE_SIGNIN", "required")
    monkeypatch.setenv("ENGINEVERSE_RELEASES_DIR", str(tmp_path))
    reload_settings()
    try:
        with TestClient(create_app(), follow_redirects=False) as web:
            install = web.get("/install")
            assert install.status_code == 200
            assert 'href="/downloads/Meridian-macOS.dmg"' in install.text
            assert 'href="/downloads/Meridian-iOS.ipa"' in install.text
            assert 'id="macos"' in install.text and 'id="ios"' in install.text and 'id="android"' in install.text

            dmg_resp = web.get("/downloads/Meridian-macOS.dmg")
            assert dmg_resp.status_code == 200
            assert dmg_resp.content == dmg_bytes
            assert "attachment" in dmg_resp.headers.get("content-disposition", "")

            ipa_resp = web.get("/downloads/Meridian-iOS.ipa")
            assert ipa_resp.status_code == 200
            assert ipa_resp.content == ipa_bytes

            # Disallowed filenames never resolve even when present in tmp_path.
            (tmp_path / "secret.txt").write_text("nope")
            assert web.get("/downloads/secret.txt").status_code == 404
    finally:
        monkeypatch.undo()
        reload_settings()

