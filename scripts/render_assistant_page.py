#!/usr/bin/env python3
"""Render the /assistant page to an HTML file for the jsdom behaviour check.

The assistant page only shows a composer when a workflow is configured, so the
browser test needs an instance with `ENGINEVERSE_ASSISTANT_URL` set. Rendering
from the real template (rather than a hand-written fixture) is what keeps the
markup and the script's expectations from drifting apart.

Usage (after `scripts/export_pages.py`, which seeds `data/pages-export.sqlite`):

    ENGINEVERSE_ASSISTANT_URL=https://n8n.example.test/webhook/x/chat \\
    ENGINEVERSE_DB_PATH=data/pages-export.sqlite \\
    python scripts/render_assistant_page.py --out /tmp/assistant-page.html

Nothing here contacts the URL; it only decides which branch of the template
renders.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for entry in (str(BACKEND), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

os.environ.setdefault("ENGINEVERSE_ENV", "test")
os.environ.setdefault("ENGINEVERSE_SIGNIN", "optional")
os.environ.setdefault("ENGINEVERSE_SECRET", "render-fixture-only-not-a-real-secret")
os.environ.pop("ENGINEVERSE_STATIC_EXPORT", None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="/tmp/assistant-page.html")
    parser.add_argument("--path", default="/assistant")
    args = parser.parse_args()

    from starlette.testclient import TestClient
    import main as app_module

    with TestClient(app_module.app) as client:
        response = client.get(args.path)
        if response.status_code != 200:
            print(f"GET {args.path} returned {response.status_code}", file=sys.stderr)
            return 1
        Path(args.out).write_text(response.text, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
