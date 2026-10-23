"""The native Android app (android/) agrees with the website and stays hardened.

The Gradle build itself runs in GitHub Actions (.github/workflows/android-build.yml),
which compiles, lints and unit-tests it. These checks are the fast, always-on
part: the bundled catalogue matches the seed data, the app points at this
repository's site, no signing secret is committed, and the in-app web viewer
keeps its restrictions.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engineverse import catalog, project

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
APP = ANDROID / "app"
SRC = APP / "src" / "main"
KOTLIN = sorted((APP / "src").rglob("*.kt"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def asset() -> dict:
    return json.loads(_read(SRC / "assets" / "catalog.json"))


class TestBundledCatalogue:
    def test_format_and_site(self, asset):
        assert asset["format"] == "engineverse-android-catalog"
        assert asset["version"] == 1
        assert asset["site"] == project.pages_url()

    def test_matches_the_seeded_catalogue(self, asset, seeded):
        expected = {
            s["slug"]: sorted(t["slug"] for t in catalog.topics_for_subject(s["id"]))
            for s in catalog.list_subjects(limit=10_000)
        }
        bundled = {s["slug"]: sorted(t["slug"] for t in s["topics"]) for s in asset["subjects"]}
        assert bundled == expected, "run scripts/export_android_catalog.py"

    def test_every_topic_has_a_page_on_the_site(self, asset, client, seeded):
        topics = [t["slug"] for s in asset["subjects"] for t in s["topics"]]
        assert len(topics) > 300
        for slug in topics[:: max(1, len(topics) // 25)]:
            assert client.get(f"/topics/{slug}").status_code == 200, slug

    def test_slugs_are_safe_route_segments(self, asset):
        slug = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
        for subject in asset["subjects"]:
            assert slug.match(subject["slug"]), subject["slug"]
            for topic in subject["topics"]:
                assert slug.match(topic["slug"]), topic["slug"]


class TestBuildConfiguration:
    def test_site_and_repository_urls_are_this_repository(self):
        gradle = _read(APP / "build.gradle.kts")
        assert f'"\\"{project.pages_url()}\\""' in gradle
        assert f'"\\"{project.repo_url()}\\""' in gradle

    def test_release_signing_comes_only_from_the_environment(self):
        gradle = _read(APP / "build.gradle.kts")
        for name in ("ENGINEVERSE_KEYSTORE_FILE", "ENGINEVERSE_KEYSTORE_PASSWORD",
                     "ENGINEVERSE_KEY_ALIAS", "ENGINEVERSE_KEY_PASSWORD"):
            assert f'environmentVariable("{name}")' in gradle
        assert not re.search(r'(storePassword|keyPassword)\s*=\s*"', gradle), "a literal password in the build"

    def test_no_signing_material_is_committed(self):
        found = [p for p in ANDROID.rglob("*")
                 if p.suffix in {".jks", ".keystore", ".p12", ".pem"} or p.name == "local.properties"]
        assert found == []

    def test_toolchain_versions(self):
        wrapper = _read(ANDROID / "gradle" / "wrapper" / "gradle-wrapper.properties")
        assert "gradle-9.4.1-bin.zip" in wrapper
        assert (ANDROID / "gradle" / "wrapper" / "gradle-wrapper.jar").stat().st_size > 40_000
        versions = _read(ANDROID / "gradle" / "libs.versions.toml")
        assert 'agp = "9.1.1"' in versions
        gradle = _read(APP / "build.gradle.kts")
        assert "targetSdk = 36" in gradle and "minSdk = 24" in gradle
        # AGP 9 compiles Kotlin itself; applying kotlin-android as well breaks the build.
        assert not re.search(r'id\s*=\s*"org\.jetbrains\.kotlin\.android"|kotlin\("android"\)', versions + gradle)


class TestManifestAndWebViewer:
    def test_manifest_is_https_only_with_minimal_permissions(self):
        manifest = _read(SRC / "AndroidManifest.xml")
        assert 'android:usesCleartextTraffic="false"' in manifest
        permissions = set(re.findall(r'uses-permission android:name="([^"]+)"', manifest))
        assert permissions == {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE"}
        network = _read(SRC / "res" / "xml" / "network_security_config.xml")
        assert 'cleartextTrafficPermitted="false"' in network
        assert 'src="user"' not in network, "user-installed CAs must not be trusted"

    def test_the_web_viewer_is_restricted(self):
        viewer = _read(SRC / "java" / "io" / "github" / "sauravprivatelimited369byte" / "engineverse" / "ui" / "WebViewerScreen.kt")
        for setting in ("allowFileAccess = false", "allowContentAccess = false",
                        "MIXED_CONTENT_NEVER_ALLOW", "setSupportMultipleWindows(false)",
                        "safeBrowsingEnabled = true", "policy.decide(url)"):
            assert setting in viewer, setting
        everything = "\n".join(_read(p) for p in KOTLIN)
        assert "addJavascriptInterface" not in everything
        assert "setAllowUniversalAccessFromFileURLs" not in everything

    def test_every_drawable_the_code_uses_exists(self):
        used = set()
        for path in KOTLIN:
            used |= set(re.findall(r"R\.drawable\.([a-z0-9_]+)", _read(path)))
        drawables = {p.stem for p in (SRC / "res").glob("drawable*/*.xml")}
        assert used and used <= drawables, used - drawables

    def test_web_paths_the_app_opens_exist_on_the_site(self, client, seeded):
        paths = set()
        for path in KOTLIN:
            paths |= set(re.findall(r'openWeb\("([a-z0-9/-]+)"\)', _read(path)))
        assert {"dpp/", "codelab/", "opportunities/"} <= paths
        for path in sorted(paths):
            response = client.get("/" + path.rstrip("/"))
            assert response.status_code == 200, path


class TestResourcesAndWorkflow:
    def test_every_resource_reference_resolves(self):
        res = SRC / "res"
        files = [SRC / "AndroidManifest.xml", *res.rglob("*.xml")]
        refs = set()
        for f in files:
            refs.update(re.findall(r"@(string|color|style|drawable|mipmap|xml)/([A-Za-z0-9_.]+)", _read(f)))
        values = "\n".join(_read(p) for p in res.glob("values*/*.xml"))
        missing = []
        for kind, name in sorted(refs):
            if kind in {"string", "color", "style"}:
                if f'name="{name}"' not in values:
                    missing.append(f"@{kind}/{name}")
            elif not list(res.glob(f"{kind}*/{name}.*")):
                missing.append(f"@{kind}/{name}")
        assert not missing, missing
        assert '<string name="app_name">EngineVerse</string>' in _read(res / "values" / "strings.xml")

    def test_gradle_wrapper_is_executable_for_ci(self):
        import os
        assert os.access(ANDROID / "gradlew", os.X_OK)

    def test_ci_workflow_builds_tests_lints_and_uploads_debug_apk(self):
        wf = _read(ROOT / ".github" / "workflows" / "android-build.yml")
        for needle in (
            "working-directory: android",
            "actions/setup-java@v6",
            "gradle/actions/setup-gradle@v6",
            "testDebugUnitTest",
            "lintDebug",
            "assembleDebug",
            "actions/upload-artifact@v7",
            "if-no-files-found: error",
        ):
            assert needle in wf, needle
        # Release signing reads secrets into a temp file and never echoes them.
        assert "secrets.ANDROID_KEYSTORE_BASE64" in wf
        assert "$RUNNER_TEMP/engineverse-release.jks" in wf
        assert "echo \"$KEYSTORE" not in wf
        assert "inputs.release" in wf
        assert not (ROOT / ".github" / "workflows" / "android-apk.yml").exists()
        assert not (ROOT / "scripts" / "build_android_apk.py").exists()

    def test_site_downloads_explain_the_in_app_limit_instead_of_faking_success(self):
        viewer = _read(SRC / "java" / "io" / "github" / "sauravprivatelimited369byte" / "engineverse" / "ui" / "WebViewerScreen.kt")
        assert '" EngineVerseAndroid/"' in viewer
        assert "onShowFileChooser" in viewer
        js = ROOT / "backend" / "static" / "js"
        for name in ("codelab.js", "pages-live.js", "planner.js", "capabilities.js"):
            text = _read(js / name)
            assert "/EngineVerseAndroid\\//.test(navigator.userAgent)" in text, name
            assert "EngineVerseAndroid.shareSourceFile" not in text, name
