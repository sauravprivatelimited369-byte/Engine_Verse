"""Download the pinned Pyodide runtime into a built static site.

Why this exists: the GitHub Pages copy runs Python on real CPython compiled
to WebAssembly (Pyodide) instead of the old regex "transpiler". The runtime
is ~10 MB of binaries, so it does NOT live in git; the Pages workflow runs
this script after ``export_pages.py`` to place it at ``site/pyodide/``, where
``pages-live.js`` loads it from (same-origin - no third-party CDN at runtime).

Source: the official ``pyodide`` npm package tarball (registry.npmjs.org),
pinned to an exact version below. Only the files CPython-in-the-browser
needs are extracted. If the download fails, the workflow still deploys:
browser Python then honestly reports NOT RUN (pages-live.js), so a network
problem degrades one feature instead of breaking the whole site publish.

Usage:
    python scripts/fetch_pyodide.py --out site/pyodide
    python scripts/fetch_pyodide.py --self-check
"""
from __future__ import annotations

import argparse
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

PYODIDE_VERSION = "0.26.4"
TARBALL_URL = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VERSION}.tgz"

#: Files loadPyodide needs at its indexURL. LICENSE ships alongside because
#: Pyodide is MPL-2.0 and the notice should travel with the binaries.
REQUIRED_FILES = (
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)
OPTIONAL_FILES = ("LICENSE",)


def _self_check() -> int:
    assert PYODIDE_VERSION.count(".") == 2 and all(p.isdigit() for p in PYODIDE_VERSION.split(".")), \
        "PYODIDE_VERSION must be an exact pinned release"
    assert TARBALL_URL.startswith("https://registry.npmjs.org/pyodide/-/"), TARBALL_URL
    assert "pyodide.asm.wasm" in REQUIRED_FILES and "python_stdlib.zip" in REQUIRED_FILES
    # The browser worker hard-codes this entry point name; keep them in step.
    repo = Path(__file__).resolve().parents[1]
    live = (repo / "backend" / "static" / "js" / "pages-live.js").read_text(encoding="utf-8")
    assert "pyodide.js" in live and "loadPyodide" in live, "pages-live.js no longer loads Pyodide"
    exporter = (repo / "scripts" / "export_pages.py").read_text(encoding="utf-8")
    assert '"pyodide"' in exporter, "exporter no longer advertises the pyodide/ URL"
    print(f"fetch_pyodide self-check OK (pyodide {PYODIDE_VERSION})")
    return 0


def fetch(out_dir: Path) -> int:
    print(f"downloading {TARBALL_URL}")
    request = urllib.request.Request(TARBALL_URL, headers={"User-Agent": "EngineVerse fetch_pyodide"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    print(f"tarball: {len(payload) / 1_048_576:.1f} MiB")

    wanted = {f"package/{name}": name for name in (*REQUIRED_FILES, *OPTIONAL_FILES)}
    found: dict[str, int] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = wanted.get(member.name)
            if name is None or not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is None:  # pragma: no cover - corrupt archive guard
                continue
            data = extracted.read()
            (out_dir / name).write_bytes(data)
            found[name] = len(data)

    missing = [name for name in REQUIRED_FILES if not found.get(name)]
    if missing:
        print(f"error: tarball did not contain: {', '.join(missing)}", file=sys.stderr)
        return 1
    if found["pyodide.asm.wasm"] < 1_000_000:
        print("error: pyodide.asm.wasm is implausibly small; refusing a truncated runtime", file=sys.stderr)
        return 1
    total = sum(found.values())
    for name in sorted(found):
        print(f"  {name}: {found[name] / 1_048_576:.2f} MiB")
    print(f"pyodide {PYODIDE_VERSION} -> {out_dir} ({total / 1_048_576:.1f} MiB total)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="directory to write the runtime into (e.g. site/pyodide)")
    parser.add_argument("--self-check", action="store_true", help="validate wiring without downloading")
    args = parser.parse_args(argv)
    if args.self_check:
        return _self_check()
    if args.out is None:
        parser.error("--out is required unless --self-check is given")
    return fetch(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
