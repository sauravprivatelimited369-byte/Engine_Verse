"""Static checks for the native iOS & macOS project in ``apple/``.

The Swift compiler and Xcode SDKs run in GitHub Actions
(``.github/workflows/apple-build.yml`` on ``macos-15``), not on Linux backend
runners. These tests verify the Swift project structure, ``Info.plist`` and
``PrivacyInfo.xcprivacy`` configuration, ``WKWebView`` hardening, canonical
project URLs, and that ``apple/Resources/catalog.json`` matches the seed.
"""
from __future__ import annotations

import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from engineverse import project

ROOT = Path(__file__).resolve().parents[2]
APPLE = ROOT / "apple"
CORE = APPLE / "Sources" / "MeridianCore"
APP = APPLE / "Sources" / "MeridianApp"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSwiftPackageAndManifests:
    def test_swift_package_targets_ios17_and_macos14_without_third_party_dependencies(self):
        pkg = _read(APPLE / "Package.swift")
        assert ".iOS(.v17)" in pkg
        assert ".macOS(.v14)" in pkg
        assert 'name: "MeridianCore"' in pkg
        assert 'name: "Meridian"' in pkg
        assert 'name: "MeridianCoreTests"' in pkg
        assert "github.com/" not in pkg, "Apple project must not pull third-party remote SPM packages"

    def test_macos_and_ios_info_plists_enforce_ats_and_canonical_bundle_id(self):
        mac_plist = plistlib.loads((APPLE / "Resources" / "macOS" / "Info.plist").read_bytes())
        ios_plist = plistlib.loads((APPLE / "Resources" / "iOS" / "Info.plist").read_bytes())
        for label, plist in (("macOS", mac_plist), ("iOS", ios_plist)):
            assert plist["CFBundleIdentifier"] == "io.github.sauravprivatelimited369byte.engineverse", label
            assert plist["CFBundleDisplayName"] == "Meridian", label
            assert plist["CFBundleExecutable"] == "Meridian", label
            assert plist["NSAppTransportSecurity"]["NSAllowsArbitraryLoads"] is False, label
        assert mac_plist["LSMinimumSystemVersion"] == "14.0"
        assert ios_plist["MinimumOSVersion"] == "17.0"
        assert ios_plist["UIDeviceFamily"] == [1, 2]

    def test_privacy_manifest_declares_no_tracking_or_collected_data(self):
        privacy = plistlib.loads((APPLE / "Resources" / "PrivacyInfo.xcprivacy").read_bytes())
        assert privacy["NSPrivacyTracking"] is False
        assert privacy["NSPrivacyTrackingDomains"] == []
        assert privacy["NSPrivacyCollectedDataTypes"] == []


class TestWebViewerHardening:
    def test_webview_enforces_url_policy_and_exposes_no_js_bridge(self):
        viewer = _read(APP / "WebViewerView.swift")
        assert "policy.decide(" in viewer
        assert "javaScriptCanOpenWindowsAutomatically = false" in viewer
        assert "removeAllScriptMessageHandlers()" in viewer
        assert "addScriptMessageHandler" not in viewer
        assert "evaluateJavaScript" not in viewer
        assert "EngineVerseApple/" in viewer

    def test_url_policy_locks_to_canonical_pages_origin(self):
        config = _read(CORE / "AppConfig.swift")
        assert f'"{project.pages_url()}"' in config
        assert f'"{project.repo_url()}"' in config
        assert f'"{project.issues_url()}"' in config
        policy = _read(CORE / "UrlPolicy.swift")
        assert 'case "https":' in policy
        assert 'contains("..")' in policy
        assert "comps.user != nil" in policy
        assert "port != 443" in policy

    def test_site_downloads_explain_in_app_limit_on_apple_webview_too(self):
        js_dir = ROOT / "backend" / "static" / "js"
        for name in ("codelab.js", "pages-live.js", "planner.js", "capabilities.js"):
            text = _read(js_dir / name)
            assert "/EngineVerseApple\\//.test(navigator.userAgent)" in text, name


class TestOfflineCatalogParity:
    def test_bundled_apple_catalog_matches_seed_exporter(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "export_apple_catalog.py"), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr or result.stdout

        catalog = json.loads(_read(APPLE / "Resources" / "catalog.json"))
        assert catalog["format"] == "engineverse-apple-catalog"
        assert catalog["version"] == 1
        assert len(catalog["subjects"]) >= 80
        slug_re = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
        topics = 0
        for subject in catalog["subjects"]:
            assert slug_re.match(subject["slug"])
            for topic in subject["topics"]:
                assert slug_re.match(topic["slug"])
                topics += 1
        assert topics >= 300


class TestAppleBuildWorkflowAndPackaging:
    def test_build_script_and_workflow_build_universal_dmg_and_arm64_ipa(self):
        script = _read(APPLE / "scripts" / "build_apple.sh")
        assert "--arch arm64 --arch x86_64" in script
        assert "Meridian-macOS.dmg" in script
        assert "Meridian-iOS.ipa" in script
        assert "arm64-apple-ios17.0-simulator" in script
        assert "arm64-apple-ios17.0" in script

        wf = _read(ROOT / ".github" / "workflows" / "apple-build.yml")
        assert "macos-15" in wf
        assert "export_apple_catalog.py --check" in wf
        assert "build_apple.sh --all" in wf
        assert "verify_apple_release.py --local-dir apple/build/out" in wf
        assert "meridian-macos-dmg" in wf
        assert "meridian-ios-ipa" in wf
