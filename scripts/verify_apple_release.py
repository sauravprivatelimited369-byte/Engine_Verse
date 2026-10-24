#!/usr/bin/env python3
"""Verify configured or locally built macOS (.dmg) and iOS (.ipa) packages.

Like ``scripts/verify_apk_release.py``, an empty URL is valid and means the
site must not advertise an unbuilt release asset. When set (or when
``--local-dir`` is passed after ``build_apple.sh``), the archive structure,
Mach-O executable header, bundled offline catalogue and SHA-256 sidecar are
checked before anything is published.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from engineverse.distribution import (  # noqa: E402
    ios_url_kind,
    normalise_ios_url,
    normalise_macos_url,
)

MAX_PACKAGE_BYTES = 250 * 1024 * 1024
MACHO_64_LE = b"\xcf\xfa\xed\xfe"
MACHO_FAT_BE = b"\xca\xfe\xba\xbe"
MACHO_FAT_64_BE = b"\xca\xfe\xba\xbf"
_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")


def _fetch_bytes(url: str, *, max_bytes: int = MAX_PACKAGE_BYTES) -> bytes:
    request = Request(url, headers={"User-Agent": "Meridian-Release-Verifier/1.0"})
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise ValueError(f"Release asset answered HTTP {response.status}")
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "text/html" in ctype:
            raise ValueError("Release URL returned an HTML page instead of a binary package")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Release package exceeds sanity size limit")
    return data


def verify_dmg_bytes(data: bytes, *, expected_sha256: str = "") -> str:
    if len(data) < 4096:
        raise ValueError("macOS package is unexpectedly small")
    head = data[:64].lstrip().lower()
    if head.startswith((b"<!doctype", b"<html")):
        raise ValueError("macOS package payload is HTML, not a disk image")
    # Apple UDIF (.dmg) stores a 512-byte 'koly' trailer at EOF.
    if data[-512:-508] != b"koly":
        raise ValueError("macOS .dmg is missing the Apple UDIF 'koly' trailer")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest != expected_sha256.lower():
        raise ValueError(f"macOS .dmg SHA-256 mismatch: expected {expected_sha256}, got {digest}")
    return digest


def verify_ipa_bytes(data: bytes, *, expected_sha256: str = "") -> str:
    if len(data) < 4096:
        raise ValueError("iOS .ipa is unexpectedly small")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ValueError(f"Corrupt ZIP entry in iOS .ipa: {bad}")
            names = set(archive.namelist())
            required = {
                "Payload/Meridian.app/Info.plist",
                "Payload/Meridian.app/Meridian",
                "Payload/Meridian.app/catalog.json",
            }
            missing = sorted(required - names)
            if missing:
                raise ValueError(f"iOS .ipa missing required bundle files: {', '.join(missing)}")
            exe_head = archive.open("Payload/Meridian.app/Meridian").read(4)
            if exe_head not in {MACHO_64_LE, MACHO_FAT_BE, MACHO_FAT_64_BE}:
                raise ValueError("Payload/Meridian.app/Meridian is not a 64-bit Mach-O binary")
    except zipfile.BadZipFile as exc:
        raise ValueError("iOS .ipa is not a valid ZIP archive") from exc
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest != expected_sha256.lower():
        raise ValueError(f"iOS .ipa SHA-256 mismatch: expected {expected_sha256}, got {digest}")
    return digest


def _parse_sha256_text(text: str) -> str:
    match = _SHA256_RE.search(text)
    if not match:
        raise ValueError("Invalid .sha256 digest file")
    return match.group(1).lower()


def verify_local_dir(directory: Path) -> dict[str, str]:
    dmg_path = directory / "Meridian-macOS.dmg"
    dmg_sha_path = directory / "Meridian-macOS.dmg.sha256"
    ipa_path = directory / "Meridian-iOS.ipa"
    ipa_sha_path = directory / "Meridian-iOS.ipa.sha256"

    for p in (dmg_path, dmg_sha_path, ipa_path, ipa_sha_path):
        if not p.is_file():
            raise ValueError(f"Expected build artifact missing: {p}")

    dmg_expected = _parse_sha256_text(dmg_sha_path.read_text(encoding="utf-8"))
    ipa_expected = _parse_sha256_text(ipa_sha_path.read_text(encoding="utf-8"))
    dmg_digest = verify_dmg_bytes(dmg_path.read_bytes(), expected_sha256=dmg_expected)
    ipa_digest = verify_ipa_bytes(ipa_path.read_bytes(), expected_sha256=ipa_expected)
    return {"macos_sha256": dmg_digest, "ios_sha256": ipa_digest}


def verify_urls(
    macos_url: str,
    ios_url: str,
    *,
    fetch=_fetch_bytes,
) -> dict[str, str]:
    clean_macos = normalise_macos_url(macos_url)
    clean_ios = normalise_ios_url(ios_url)
    out: dict[str, str] = {}

    if clean_macos:
        data = fetch(clean_macos)
        if clean_macos.endswith(".dmg"):
            out["macos_sha256"] = verify_dmg_bytes(data)
        else:
            if len(data) < 4096:
                raise ValueError("macOS release package is unexpectedly small")
            out["macos_sha256"] = hashlib.sha256(data).hexdigest()

    if clean_ios:
        kind = ios_url_kind(clean_ios)
        if kind == "ipa":
            data = fetch(clean_ios)
            out["ios_sha256"] = verify_ipa_bytes(data)
        else:
            # Official Apple TestFlight / App Store listing: check HTTP 200 reachability.
            req = Request(clean_ios, headers={"User-Agent": "Meridian-Release-Verifier/1.0"})
            with urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    raise ValueError(f"iOS store URL answered HTTP {resp.status}")
            out["ios_kind"] = kind

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macos-url", default=os.environ.get("ENGINEVERSE_MACOS_URL", ""))
    parser.add_argument("--ios-url", default=os.environ.get("ENGINEVERSE_IOS_URL", ""))
    parser.add_argument("--local-dir", default="", help="Verify built artifacts in a local directory")
    args = parser.parse_args()

    if args.local_dir:
        digests = verify_local_dir(Path(args.local_dir))
        print(
            f"Verified local Apple packages: macOS sha256={digests['macos_sha256'][:16]}… "
            f"iOS sha256={digests['ios_sha256'][:16]}…"
        )
        return 0

    if not args.macos_url.strip() and not args.ios_url.strip():
        print("No ENGINEVERSE_MACOS_URL or ENGINEVERSE_IOS_URL configured; external Apple release URLs omitted.")
        return 0

    digests = verify_urls(args.macos_url, args.ios_url)
    print(f"Verified Apple release URLs: {digests}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
