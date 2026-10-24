#!/usr/bin/env python3
"""Write the iOS & macOS app's offline catalogue from the website's seed data.

    python scripts/export_apple_catalog.py            # rewrite the asset
    python scripts/export_apple_catalog.py --check    # fail if it is stale

The multiplatform SwiftUI app (apple/) bundles ``Resources/catalog.json`` so
subjects and topics can be browsed, searched and tracked offline on iPhone,
iPad and Mac. Derived deterministically from a freshly seeded database, using
the same schema as ``scripts/export_android_catalog.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import export_android_catalog as android_export  # noqa: E402

ASSET = ROOT / "apple" / "Resources" / "catalog.json"
FORMAT = "engineverse-apple-catalog"
VERSION = 1


def generate_apple_catalog() -> str:
    raw = android_export._generate_in_fresh_database()
    data = json.loads(raw)
    data["format"] = FORMAT
    data["version"] = VERSION
    return android_export.render(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed asset is out of date")
    args = parser.parse_args()

    text = generate_apple_catalog()
    data = json.loads(text)
    topics = sum(len(s["topics"]) for s in data["subjects"])
    if args.check:
        current = ASSET.read_text(encoding="utf-8") if ASSET.exists() else ""
        if current != text:
            print(f"{ASSET.relative_to(ROOT)} is out of date; run scripts/export_apple_catalog.py", file=sys.stderr)
            return 1
        print(f"apple/Resources/catalog.json is current ({len(data['subjects'])} subjects, {topics} topics)")
        return 0
    ASSET.parent.mkdir(parents=True, exist_ok=True)
    ASSET.write_text(text, encoding="utf-8")
    print(f"wrote {ASSET.relative_to(ROOT)}: {len(data['subjects'])} subjects, {topics} topics, {len(text)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
