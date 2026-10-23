"""Where this copy of EngineVerse is published.

Every URL that names the GitHub repository, its Pages site or its Android
release assets is derived here, so a fork or a renamed repository never ships
links to somebody else's project. The value comes from, in order:

1. ``ENGINEVERSE_REPOSITORY`` (explicit operator override, ``owner/name``);
2. ``GITHUB_REPOSITORY`` (set automatically inside GitHub Actions);
3. :data:`DEFAULT_REPOSITORY`, the canonical upstream repository.

GitHub Pages serves a *project* repository at
``https://<owner-lowercased>.github.io/<name>/`` and a ``<owner>.github.io``
repository at the domain root; both are handled. The path segment keeps the
repository's case because Pages paths are case-sensitive.
"""
from __future__ import annotations

import os
import re

DEFAULT_REPOSITORY = "sauravprivatelimited369-byte/Engine_Verse"

# GitHub owner: 1-39 alphanumerics or single hyphens. Repository: letters,
# digits, ".", "-", "_" (max 100). Anything else is refused rather than
# interpolated into URLs.
_REPO_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/(?P<name>[A-Za-z0-9._-]{1,100})\Z"
)


def repository(value: str | None = None) -> str:
    """Return the validated ``owner/name`` of the repository this build serves."""
    raw = (
        value
        if value is not None
        else (
            os.environ.get("ENGINEVERSE_REPOSITORY", "").strip()
            or os.environ.get("GITHUB_REPOSITORY", "").strip()
            or DEFAULT_REPOSITORY
        )
    )
    raw = raw.strip()
    match = _REPO_RE.fullmatch(raw)
    if not match or match.group("name") in {".", ".."}:
        raise ValueError(f"Invalid GitHub repository identifier: {raw!r} (expected owner/name)")
    return raw


def owner(value: str | None = None) -> str:
    return repository(value).split("/", 1)[0]


def name(value: str | None = None) -> str:
    return repository(value).split("/", 1)[1]


def repo_url(value: str | None = None) -> str:
    """``https://github.com/owner/name`` (no trailing slash)."""
    return f"https://github.com/{repository(value)}"


def pages_origin(value: str | None = None) -> str:
    """Scheme + host of the GitHub Pages site, e.g. ``https://owner.github.io``."""
    return f"https://{owner(value).lower()}.github.io"


def pages_base(value: str | None = None) -> str:
    """URL path prefix of the Pages site: ``/Name/`` or ``/`` for a user site."""
    repo_name = name(value)
    if repo_name.lower() == f"{owner(value).lower()}.github.io":
        return "/"
    return f"/{repo_name}/"


def pages_url(value: str | None = None) -> str:
    """Full public URL of the Pages site, always ending in ``/``."""
    return pages_origin(value) + pages_base(value)


def release_download_prefix(value: str | None = None) -> str:
    """Prefix of every GitHub Releases asset download URL for this repository."""
    return f"{repo_url(value)}/releases/download/"


def issues_url(value: str | None = None) -> str:
    return f"{repo_url(value)}/issues"


def security_advisory_url(value: str | None = None) -> str:
    return f"{repo_url(value)}/security/advisories/new"
