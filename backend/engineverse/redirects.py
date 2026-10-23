"""Permanent (301) redirects for URLs that are not, or are no longer, pages.

Search engines and bookmarks hold on to old addresses. Each entry here answers
a request for a retired or mistyped URL with a 301 to the page that replaced it,
so the old address stops producing a 404 and its ranking moves to the new one.

Two kinds of rule:

* ``EXACT`` maps one path to one destination.
* ``PREFIXES`` maps a singular or misspelt section (``/topic/x``) onto its plural
  (``/topics/x``), keeping the slug. A slug is only carried across when it matches
  ``SLUG`` - a fixed character set - so a crafted path can never produce a
  redirect to another host or a protocol-relative ``//`` location.

Trailing slashes are handled separately by ``target_for``: ``/topics/arrays/`` is
permanently redirected to ``/topics/arrays``, so one page has one address.

The static GitHub Pages copy cannot send a 301. ``scripts/export_pages.py`` writes
a page for each ``EXACT`` entry that refreshes to its target instead.
"""
from __future__ import annotations

import re

#: One path, one destination. Targets must be real pages; the test suite checks
#: that every target answers 200.
EXACT: dict[str, str] = {
    "/index.html": "/",
    "/home": "/",
    "/learn": "/explore",
    "/subjects": "/explore",
    "/branches": "/explore",
    "/topics": "/explore",
    "/code": "/programming",
    "/practise": "/practice",
    "/problems": "/practice/problems",
    "/sheet": "/sheets",
    "/explore/first-year": "/explore?year=1",
}

#: Old section name -> new section name. The slug after it is kept.
PREFIXES: dict[str, str] = {
    "/topic/": "/topics/",
    "/subject/": "/subjects/",
    "/branch/": "/branches/",
    "/project/": "/projects/",
    "/roadmap/": "/roadmaps/",
    "/sheet/": "/sheets/",
    "/problem/": "/practice/problems/",
    "/problems/": "/practice/problems/",
    "/practise/": "/practice/",
}

#: A slug we are willing to echo into a Location header.
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}")

#: A raw request path that may be treated as a plain path: no double slashes,
#: no characters that need a second look.
_PLAIN_PATH = re.compile(r"/[A-Za-z0-9._~%/-]*")


def target_for(path: str) -> str | None:
    """The permanent redirect target for ``path``, or None to leave it alone.

    The query string is not part of ``path`` and is re-attached by the caller.
    Each rule is applied to the path without its trailing slash, so a redirect
    always lands on the final address in one hop.
    """
    if not path or not path.startswith("/") or path.startswith("//"):
        return None
    bare = path.rstrip("/") or "/"
    if bare in EXACT:
        return EXACT[bare]
    for old, new in PREFIXES.items():
        if bare.startswith(old):
            slug = bare[len(old):]
            if SLUG.fullmatch(slug):
                return new + slug
            return None
    if bare != path and _PLAIN_PATH.fullmatch(path) and not bare.startswith("//"):
        return bare
    return None
