#!/usr/bin/env python3
"""Write the Android app's offline catalogue from the website's seed data.

    python scripts/export_android_catalog.py            # rewrite the asset
    python scripts/export_android_catalog.py --check    # fail if it is stale

The app (android/) bundles ``app/src/main/assets/catalog.json`` so subjects and
topics can be browsed, searched and tracked with no connection. The file is
derived, never hand-edited: it is built from a fresh database seeded exactly
like the website (scripts/seed.py), and the output is deterministic (sorted
keys, no timestamps) so ``--check`` and the test suite can compare it byte for
byte. Only published subjects and topics are included, with the same fields the
website shows on its catalogue cards.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "android" / "app" / "src" / "main" / "assets" / "catalog.json"
FORMAT = "engineverse-android-catalog"
VERSION = 1


def build_catalog() -> dict:
    """Reads the catalogue from the database the environment points at."""
    sys.path.insert(0, str(ROOT / "backend"))
    from engineverse import catalog, project  # noqa: PLC0415 - needs the env first

    subjects = []
    for subject in catalog.list_subjects(limit=10_000):
        if subject.get("status") not in (None, "published"):
            continue
        topics = []
        for topic in catalog.topics_for_subject(subject["id"]):
            if topic.get("status") not in (None, "published"):
                continue
            try:
                tags = json.loads(topic.get("tags") or "[]")
            except ValueError:
                tags = []
            topics.append({
                "slug": topic["slug"],
                "title": topic["title"],
                "summary": topic.get("summary") or "",
                "difficulty": topic.get("difficulty") or "",
                "minutes": int(topic.get("est_minutes") or 0),
                "tags": [str(t) for t in tags][:8],
                "reviewed": topic.get("accuracy_state") == "reviewed",
            })
        if subject.get("is_first_year"):
            group = "First year"
        else:
            group = subject.get("branch_name") or ""
        subjects.append({
            "slug": subject["slug"],
            "name": subject["name"],
            "code": subject.get("code") or "",
            "group": group,
            "description": subject.get("description") or "",
            "topics": topics,
        })
    return {
        "format": FORMAT,
        "version": VERSION,
        "site": project.pages_url(),
        "subjects": subjects,
    }


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _generate_in_fresh_database() -> str:
    """Seeds a throwaway database (like the Pages export) and renders from it."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "catalog.sqlite3"
        env = os.environ.copy()
        env.update({
            "ENGINEVERSE_ENV": "development",
            "ENGINEVERSE_DB_PATH": str(db_path),
            "ENGINEVERSE_DB_URL": "",
            "ENGINEVERSE_SECRET": "android-catalog-export-local-only-0001",
        })
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "seed.py"), "--fresh", "--no-demo"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
        )
        code = (
            "import sys; sys.path.insert(0, %r);"
            "import export_android_catalog as e;"
            "sys.stdout.write(e.render(e.build_catalog()))" % str(ROOT / "scripts")
        )
        return subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=env, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed asset is out of date")
    args = parser.parse_args()

    text = _generate_in_fresh_database()
    data = json.loads(text)
    topics = sum(len(s["topics"]) for s in data["subjects"])
    if args.check:
        current = ASSET.read_text(encoding="utf-8") if ASSET.exists() else ""
        if current != text:
            print(f"{ASSET.relative_to(ROOT)} is out of date; run scripts/export_android_catalog.py", file=sys.stderr)
            return 1
        print(f"catalog.json is current ({len(data['subjects'])} subjects, {topics} topics)")
        return 0
    ASSET.parent.mkdir(parents=True, exist_ok=True)
    ASSET.write_text(text, encoding="utf-8")
    print(f"wrote {ASSET.relative_to(ROOT)}: {len(data['subjects'])} subjects, {topics} topics, {len(text)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
