"""Public Android download links. Never accept a caller-controlled APK URL.

An APK is executable code installed outside an app store. Only an explicitly
configured, versioned release asset from *this* repository (see
:mod:`engineverse.project`) is advertised. Setting this URL does not build or
sign an APK; the Android workflow does that (see docs/ANDROID.md).
"""
from __future__ import annotations

import re

from engineverse import project


def _release_pattern() -> re.Pattern[str]:
    # Forge.apk is the release asset name since the FORGE rebrand; the legacy
    # EngineVerse.apk name stays acceptable so already-published releases and
    # already-configured ENGINEVERSE_APK_URL values keep working.
    return re.compile(
        re.escape(project.release_download_prefix())
        + r"android-v[0-9][A-Za-z0-9._-]{0,63}/(?:Forge|EngineVerse)[A-Za-z0-9._-]{0,64}\.apk\Z"
    )


def normalise_apk_url(value: str | None) -> str:
    """Return a safe, absolute download URL, or an empty string if unset."""
    url = (value or "").strip()
    if not url:
        return ""
    if not _release_pattern().fullmatch(url) or ".." in url:
        raise ValueError(
            "ENGINEVERSE_APK_URL must point to a versioned Forge*.apk (or legacy EngineVerse*.apk) "
            "asset in this repository's Android GitHub Releases"
        )
    return url
