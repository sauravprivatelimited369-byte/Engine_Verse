"""Public native-app download links. Never accept a caller-controlled package URL.

Native packages (.apk, .dmg, .ipa) execute outside a browser sandbox. Only an
explicitly configured, versioned release asset from *this* repository (see
:mod:`engineverse.project`), an official Apple TestFlight / App Store listing,
or a verified build placed in the server's local ``data/releases/`` directory
is advertised.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from engineverse import project

LOCAL_RELEASE_ASSETS: dict[str, str] = {
    "macos": "Meridian-macOS.dmg",
    "ios": "Meridian-iOS.ipa",
    "android": "Meridian.apk",
}

ALLOWED_DOWNLOAD_MEDIA_TYPES: dict[str, str] = {
    "Meridian-macOS.dmg": "application/x-apple-diskimage",
    "Meridian-macOS.dmg.sha256": "text/plain; charset=utf-8",
    "Meridian-iOS.ipa": "application/octet-stream",
    "Meridian-iOS.ipa.sha256": "text/plain; charset=utf-8",
    "Meridian.apk": "application/vnd.android.package-archive",
    "Meridian.apk.sha256": "text/plain; charset=utf-8",
}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")


def _release_pattern() -> re.Pattern[str]:
    # Meridian.apk is the release asset name since the MERIDIAN rebrand; the legacy Forge and EngineVerse
    # EngineVerse.apk name stays acceptable so already-published releases and
    # already-configured ENGINEVERSE_APK_URL values keep working.
    return re.compile(
        re.escape(project.release_download_prefix())
        + r"android-v[0-9][A-Za-z0-9._-]{0,63}/(?:Meridian|Forge|EngineVerse)[A-Za-z0-9._-]{0,64}\.apk\Z"
    )


def _macos_release_pattern() -> re.Pattern[str]:
    return re.compile(
        re.escape(project.release_download_prefix())
        + r"(?:(?:apple|macos)-)?v[0-9][A-Za-z0-9._-]{0,63}/(?:Meridian|Forge|EngineVerse)[A-Za-z0-9._-]{0,64}\.(?:dmg|pkg|zip)\Z"
    )


def _ios_release_pattern() -> re.Pattern[str]:
    return re.compile(
        re.escape(project.release_download_prefix())
        + r"(?:(?:apple|ios)-)?v[0-9][A-Za-z0-9._-]{0,63}/(?:Meridian|Forge|EngineVerse)[A-Za-z0-9._-]{0,64}\.ipa\Z"
    )


_IOS_TESTFLIGHT_PATTERN = re.compile(r"https://testflight\.apple\.com/join/[A-Za-z0-9]{6,24}\Z")
_IOS_APPSTORE_PATTERN = re.compile(
    r"https://apps\.apple\.com/(?:[a-z]{2}/)?app/(?:[a-z0-9-]{1,80}/)?id[0-9]{6,16}\Z"
)


def normalise_apk_url(value: str | None) -> str:
    """Return a safe, absolute Android APK download URL, or an empty string if unset."""
    url = (value or "").strip()
    if not url:
        return ""
    if not _release_pattern().fullmatch(url) or ".." in url:
        raise ValueError(
            "ENGINEVERSE_APK_URL must point to a versioned Meridian*.apk (or legacy EngineVerse*.apk) "
            "asset in this repository's Android GitHub Releases"
        )
    return url


def normalise_macos_url(value: str | None) -> str:
    """Return a safe, absolute macOS download URL, or an empty string if unset."""
    url = (value or "").strip()
    if not url:
        return ""
    if not _macos_release_pattern().fullmatch(url) or ".." in url:
        raise ValueError(
            "ENGINEVERSE_MACOS_URL must point to a versioned Meridian*.dmg/.pkg/.zip "
            "asset in this repository's GitHub Releases"
        )
    return url


def normalise_ios_url(value: str | None) -> str:
    """Return a safe, absolute iOS download/TestFlight/App Store URL, or empty if unset."""
    url = (value or "").strip()
    if not url:
        return ""
    if ".." in url:
        raise ValueError("ENGINEVERSE_IOS_URL must not contain path traversal")
    if (
        _ios_release_pattern().fullmatch(url)
        or _IOS_TESTFLIGHT_PATTERN.fullmatch(url)
        or _IOS_APPSTORE_PATTERN.fullmatch(url)
    ):
        return url
    raise ValueError(
        "ENGINEVERSE_IOS_URL must point to a versioned Meridian*.ipa asset in this repository's "
        "GitHub Releases, or an official https://testflight.apple.com / https://apps.apple.com link"
    )


def ios_url_kind(value: str | None) -> str:
    """Classify an approved or local iOS link: 'ipa', 'testflight', 'appstore', or ''."""
    url = (value or "").strip()
    if not url:
        return ""
    if url.startswith("https://testflight.apple.com/"):
        return "testflight"
    if url.startswith("https://apps.apple.com/"):
        return "appstore"
    if url.endswith(".ipa"):
        return "ipa"
    return ""


def releases_dir(explicit: Path | str | None = None) -> Path | None:
    """Return the local release directory when enabled, or None during unit tests."""
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get("ENGINEVERSE_RELEASES_DIR")
    if raw is not None:
        trimmed = raw.strip()
        if not trimmed or trimmed.lower() in {"none", "off", "0", "false"}:
            return None
        return Path(trimmed)
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("ENGINEVERSE_ENV", "").strip().lower() == "test":
        return None
    return _REPO_ROOT / "data" / "releases"


def local_release_file(filename: str, base_dir: Path | str | None = None) -> Path | None:
    """Return an allowlisted release file in ``data/releases/`` if present and non-trivial."""
    if filename not in ALLOWED_DOWNLOAD_MEDIA_TYPES:
        return None
    root = releases_dir(base_dir)
    if root is None:
        return None
    candidate = root / filename
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return None
        size = candidate.stat().st_size
    except OSError:
        return None
    if filename.endswith(".sha256"):
        return candidate if 16 <= size <= 512 else None
    return candidate if size >= 4096 else None


def local_download_path(platform: str, base_dir: Path | str | None = None) -> str:
    """Return ``/downloads/<asset>`` when a local build exists for ``platform``, else ``""``."""
    filename = LOCAL_RELEASE_ASSETS.get(platform, "")
    if not filename or local_release_file(filename, base_dir) is None:
        return ""
    return f"/downloads/{filename}"


def local_release_sha256(platform: str, base_dir: Path | str | None = None) -> str:
    """Return the lowercase SHA-256 hex digest for a local platform package, or ``""``."""
    filename = LOCAL_RELEASE_ASSETS.get(platform, "")
    pkg = local_release_file(filename, base_dir) if filename else None
    if pkg is None:
        return ""
    sha_file = local_release_file(filename + ".sha256", base_dir)
    if sha_file is not None:
        match = _SHA256_RE.search(sha_file.read_text(encoding="utf-8", errors="ignore"))
        if match:
            return match.group(1).lower()
    digest = hashlib.sha256()
    with pkg.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
