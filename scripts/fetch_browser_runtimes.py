"""Download the pinned in-browser language runtimes into a built static site.

Why this exists: the GitHub Pages copy has no server to compile code on, so
languages other than JavaScript (Web Worker) and Python (CPython/Pyodide,
vendored by ``scripts/fetch_pyodide.py``) used to report NOT RUN there. Real
compilers and interpreters now exist as WebAssembly/JavaScript builds, and
this script vendors them - pinned, same-origin, no third-party CDN at
runtime - so the static copy genuinely compiles and runs every language
EngineVerse teaches:

    C / C++     Clang 22 compiled to WebAssembly (@live-codes/clang-wasm)
    Java        OpenJDK's javac + the TeaVM AOT compiler (@live-codes/java-wasm)
    Go          the GopherJS Go compiler (@live-codes/go2js)
    Rust        rustc's Miri interpreter on WebAssembly (@live-codes/rust-wasm
                + the @live-codes/wasm-rustc toolchain artifacts)
    C#          the real Roslyn compiler on Blazor WebAssembly
                (@live-codes/blazor-wasm - the same bundle the hosted
                judge's Node runner uses, see scripts/setup_toolchains.py)
    TypeScript  the official TypeScript compiler (typescript npm package)
    SQL         SQLite compiled to WebAssembly (sql.js)
    Shell       POSIX sh / Bash interpreter in the browser (just-bash)

Every runtime is fetched lazily by the browser only when a learner picks
that language, and each one is verified end-to-end (a program is compiled
and run, with stdin) by ``scripts/check_browser_runtimes.js`` in the Pages
workflow. If a download fails here, the workflow still deploys: the
manifest simply omits that language and the browser honestly reports
NOT RUN for it, exactly as it does for a missing Pyodide.

Usage:
    python scripts/fetch_browser_runtimes.py --out site/runtimes
    python scripts/fetch_browser_runtimes.py --out site/runtimes --only java,rust
    python scripts/fetch_browser_runtimes.py --self-check
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

#: Pinned npm packages. Scoped name -> tarball file name on the registry.
def _tarball_url(package: str, version: str) -> str:
    name = package.rsplit("/", 1)[-1]
    return f"https://registry.npmjs.org/{package}/-/{name}-{version}.tgz"


#: What to vendor for each runtime. ``members`` maps tarball paths (under
#: ``package/``) to destinations relative to the runtime's output directory;
#: a key ending in "/" copies the whole subtree, and the value is the
#: destination prefix for it. ``languages`` is what the browser may claim.
RUNTIMES: dict[str, dict] = {
    "clang": {
        "package": "@live-codes/clang-wasm",
        "version": "0.3.0",
        "languages": ["c", "cpp"],
        "members": {
            "dist/clang-wasm.global.js": "clang-wasm.global.js",
            "assets/": "assets/",
            "LICENSE": "LICENSE",
        },
        "receipts": "src/asset-receipts.js",
        # Mobile/CDN performance & memory fixes on the vendored Clang 22 bundle:
        #   1) Permit normal HTTP/SW cache hits and transparent edge redirects
        #      instead of forcing `cache:"no-store"` / `redirect:"error"`;
        #   2) Avoid element-by-element `Uint8Array.from(n)` copies over multi-MB
        #      compressed/decompressed WASM buffers;
        #   3) Drop raw `.wasm` byte buffers from `Rn` immediately after
        #      `WebAssembly.compile(o)` caches the `WebAssembly.Module` in `wn`,
        #      saving ~300 MB of peak worker RAM on mobile devices.
        "text_patches": {
            "clang-wasm.global.js": [
                (
                    '{cache:"no-store",credentials:"omit",redirect:"error",referrerPolicy:"no-referrer"}',
                    '{credentials:"omit",redirect:"follow",referrerPolicy:"no-referrer"}',
                ),
                (
                    '{credentials:"omit",redirect:"error",referrerPolicy:"no-referrer"}',
                    '{credentials:"omit",redirect:"follow",referrerPolicy:"no-referrer"}',
                ),
                (
                    "try{let r=Uint8Array.from(n),i=new ReadableStream(",
                    "try{let r=n instanceof Uint8Array?n:new Uint8Array(n),i=new ReadableStream(",
                ),
                (
                    "let s=await i;return le(_),e?.set?.(1),Uint8Array.from(s)};async function Ct(n,e,t,_=zt){le(t);let r=`${n}\\0${_}`,i=t?void 0:wn.get(r);if(i)return i;let s=(async()=>{let o=await Cn(n,e,_,t);le(t);let a=await jt(WebAssembly.compile(o),t);return le(t),a})()",
                    "let s=await i;return le(_),e?.set?.(1),s};async function Ct(n,e,t,_=zt){le(t);let r=`${n}\\0${_}`,i=t?void 0:wn.get(r);if(i)return i;let s=(async()=>{let o=await Cn(n,e,_,t);le(t);let a=await jt(WebAssembly.compile(o),t);return Rn.delete(r),le(t),a})()",
                ),
            ],
        },
    },
    "java": {
        "package": "@live-codes/java-wasm",
        "version": "0.1.0",
        "languages": ["java"],
        "members": {
            "dist/": "",
            "LICENSE": "LICENSE",
        },
        # The worker compiles every submission as "Main.java", so a learner's
        # `public class Hello` fails javac's file-name rule. The server judge
        # instead writes the source to <PublicClass>.java (see judge/local.py);
        # naming the in-memory file after the requested mainClass gives the
        # browser identical semantics with the source itself untouched.
        "text_patches": {
            "worker-java.js": [
                ('addSourceFile("Main.java",t)', 'addSourceFile(e+".java",t)'),
            ],
        },
    },
    "rust": {
        "package": "@live-codes/rust-wasm",
        "version": "0.3.0",
        "languages": ["rust"],
        "members": {
            "dist/worker.iife.js": "worker.iife.js",
            "LICENSE": "LICENSE.rust-wasm",
        },
        # The toolchain artifacts (Miri + sysroot) ship in a second package;
        # only the gzip set is served (the loader inflates it client-side).
        "extra_package": ("@live-codes/wasm-rustc", "0.1.0"),
        "extra_glob": ".gz",
        "extra_dest": "toolchain/",
        # GitHub Pages / Fastly serves `.gz` files with `Content-Encoding: gzip`,
        # so `fetch()` hands the worker an already-gunzipped stream starting with
        # `\0asm` instead of `0x1f 0x8b`. Peek the 2-byte gzip header before
        # piping through DecompressionStream("gzip") so both raw `.gz` files and
        # CDN-decompressed responses work identically without double-gunzip failure.
        "text_patches": {
            "worker.iife.js": [
                (
                    'async function xt(_,t){if(!t)return _;if(typeof DecompressionStream>"u")'
                    'throw new Error("This browser lacks DecompressionStream, needed to unpack the toolchain.");'
                    'return _.pipeThrough(new DecompressionStream("gzip"))}',
                    'async function xt(_,t){if(!t)return _;const r=_.getReader(),c=[];let n=0,d=!1;'
                    'while(n<2){const v=await r.read();if(v.done){d=!0;break}if(v.value&&v.value.byteLength){'
                    'c.push(v.value);n+=v.value.byteLength}}let i=0,a,b;for(const u of c){for(const k of u){'
                    'if(a===void 0)a=k;else if(b===void 0){b=k;break}}if(b!==void 0)break}'
                    'const s=new ReadableStream({async pull(ctrl){if(i<c.length){ctrl.enqueue(c[i++]);return}'
                    'if(d){r.releaseLock();ctrl.close();return}const v=await r.read();'
                    'if(v.done){d=!0;r.releaseLock();ctrl.close();return}if(v.value)ctrl.enqueue(v.value)},'
                    'cancel(reason){return r.cancel(reason)}});if(a!==31||b!==139)return s;'
                    'if(typeof DecompressionStream>"u")throw new Error('
                    '"This browser lacks DecompressionStream, needed to unpack the toolchain.");'
                    'return s.pipeThrough(new DecompressionStream("gzip"))}',
                ),
                (
                    'return _&&_.put(l,s.clone()).catch(()=>{}),{bytes:await xt(s.body,t.gzipped).then(It),cached:!1}',
                    'const u=await xt(s.body,t.gzipped).then(It);'
                    'return _&&_.put(l,new Response(u,{headers:{"content-type":"application/octet-stream"}})).catch(()=>{}),'
                    '{bytes:u,cached:!1}',
                ),
            ],
        },
    },
    "go": {
        "package": "@live-codes/go2js",
        "version": "0.5.3",
        "languages": ["go"],
        "members": {
            "build/go2js-compile.js": "go2js-compile.js",
            "build/pkg/": "pkg/",
            "LICENSE": "LICENSE",
            "LICENSE-GopherJS": "LICENSE-GopherJS",
        },
    },
    "sql": {
        "package": "sql.js",
        "version": "1.15.1",
        "languages": ["sql"],
        "members": {
            "dist/sql-wasm.js": "sql-wasm.js",
            "dist/sql-wasm.wasm": "sql-wasm.wasm",
            "LICENSE": "LICENSE",
        },
    },
    "typescript": {
        "package": "typescript",
        "version": "5.9.3",
        "languages": ["typescript"],
        "members": {
            "lib/typescript.js": "typescript.js",
            "LICENSE.txt": "LICENSE.txt",
        },
        # The lib .d.ts closure the in-browser type checker loads (computed
        # from /// <reference lib="..."/> chains at vendor time). ES2020
        # only: the browser TS environment declares console/input/print
        # itself rather than pulling in DOM globals (see ev-runtime-worker).
        "lib_anchors": ("lib.es2020.d.ts",),
    },
    "csharp": {
        "package": "@live-codes/blazor-wasm",
        # Same pin as scripts/setup_toolchains.py (BLAZOR_WASM_VERSION): the
        # hosted judge and the browser run the identical Roslyn bundle.
        "version": "0.1.1",
        "languages": ["csharp"],
        "members": {
            "blazor-wasm.js": "blazor-wasm.js",
            "_framework/": "_framework/",
            "refs.zip": "refs.zip",
            "razor.zip": "razor.zip",
        },
        "patch_dotnet_js": True,
    },
    "bash": {
        "package": "just-bash",
        "version": "3.6.0",
        "languages": ["bash"],
        "members": {
            "LICENSE": "LICENSE",
        },
        "bundle_bash": True,
    },
}


def _download(url: str) -> bytes:
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "EngineVerse fetch_browser_runtimes"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def _safe_members(tar: tarfile.TarFile):
    for member in tar.getmembers():
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            continue
        if member.isfile():
            yield member


def _extract_prefix(tar_bytes: bytes, members: dict[str, str], dest: Path) -> list[str]:
    """Copies the whitelisted members of an npm tarball into ``dest``."""
    written: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        available = {m.name: m for m in _safe_members(tar)}
        for source, target in members.items():
            if source.endswith("/"):
                hits = sorted(n for n in available if n.startswith(f"package/{source}"))
                if not hits:
                    raise FileNotFoundError(f"tarball has no subtree package/{source}")
                for name in hits:
                    rel = name[len("package/" + source):]
                    out = dest / target / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(tar.extractfile(available[name]).read())
                    written.append(str(out.relative_to(dest)))
            else:
                member = available.get(f"package/{source}")
                if member is None:
                    # License files are vendored when upstream ships one;
                    # their absence (e.g. @live-codes/rust-wasm) must not
                    # sink an otherwise complete runtime.
                    if Path(source).name.startswith("LICENSE"):
                        continue
                    raise FileNotFoundError(f"tarball has no package/{source}")
                out = dest / target
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(tar.extractfile(member).read())
                written.append(str(out.relative_to(dest)))
    return written


def _extract_glob(tar_bytes: bytes, suffix: str, dest: Path) -> list[str]:
    """Copies every tarball file whose name ends in ``suffix`` (paths kept)."""
    written: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in _safe_members(tar):
            if not member.name.startswith("package/") or not member.name.endswith(suffix):
                continue
            rel = member.name[len("package/"):]
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tar.extractfile(member).read())
            written.append(rel)
    return written


def _lib_closure(tar_bytes: bytes, anchors: tuple[str, ...]) -> dict[str, bytes]:
    """The transitive ``lib.*.d.ts`` closure of the anchor libraries."""
    wanted: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        available = {m.name: m for m in _safe_members(tar)}
        queue = list(anchors)
        while queue:
            name = queue.pop()
            if name in wanted:
                continue
            member = available.get(f"package/lib/{name}")
            if member is None:
                raise FileNotFoundError(f"typescript tarball has no lib/{name}")
            text = tar.extractfile(member).read()
            wanted[name] = text
            for ref in re.findall(r'/// <reference lib="([^"]+)"', text.decode("utf-8", "replace")):
                queue.append(f"lib.{ref}.d.ts")
    return wanted


def _asset_receipts(tar_bytes: bytes, source: str) -> str | None:
    """Pulls ASSET_RECEIPTS out of the clang package for the copied assets.

    The package's own ``clang-wasm-copy-assets`` writes the same file next
    to the assets so a host can verify what it serves; mirror that here.
    """
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        member = tar.getmember(f"package/{source}")
        text = tar.extractfile(member).read().decode("utf-8")
    match = re.search(r"ASSET_RECEIPTS\s*=\s*(\{.*\})\s*;?\s*$", text, re.S)
    if not match:
        return None
    return json.dumps(json.loads(match.group(1)), indent=2) + "\n"


def _patch_csharp_bundle(dest: Path) -> None:
    """Applies the same dotnet.js patch the hosted judge's bundle gets.

    ``scripts/setup_toolchains.py`` patches the server-side copy so
    WebAssembly.compileStreaming receives a real Response; the vendored
    browser copy must behave identically, so reuse that exact code rather
    than keeping a second copy of the patch in step by hand.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import setup_toolchains

    setup_toolchains._apply_dotnet_js_patches(dest)


def _bundle_bash(dest: Path, version: str) -> str:
    """Bundles ``just-bash`` into a single zero-CDN browser worker IIFE.

    ``just-bash``'s published browser entry imports ``node:zlib`` for ``gzip``
    and ``gunzip`` commands; mapping ``node:zlib`` to pinned ``fflate`` yields a
    pure client-side bundle with full POSIX ``sh``/``bash``, ``awk``, ``sed``,
    ``grep``, ``sort``, ``uniq``, ``wc``, ``cut``, ``tr``, ``jq``, and ``stdin``.
    """
    with tempfile.TemporaryDirectory(prefix="ev-bash-bundle-") as tmp:
        work = Path(tmp)
        subprocess.run(
            [
                "npm", "install", "--prefix", str(work), "--no-audit", "--no-fund",
                f"just-bash@{version}", "fflate@0.8.2", "esbuild@0.25.0",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        zlib_shim = work / "zlib-shim.mjs"
        zlib_shim.write_text(
            'import { gzipSync as fGzip, gunzipSync as fGunzip, zlibSync, unzlibSync, '
            'inflateSync as fInflate, deflateSync as fDeflate } from "fflate";\n'
            'const toU8 = (b) => b instanceof Uint8Array ? b : new TextEncoder().encode(String(b));\n'
            'export const constants = { Z_BEST_COMPRESSION: 9, Z_DEFAULT_COMPRESSION: 6, Z_NO_COMPRESSION: 0 };\n'
            'export const gzipSync = (b) => fGzip(toU8(b));\n'
            'export const gunzipSync = (b) => fGunzip(toU8(b));\n'
            'export const deflateSync = (b) => zlibSync(toU8(b));\n'
            'export const inflateSync = (b) => unzlibSync(toU8(b));\n'
            'export const deflateRawSync = (b) => fDeflate(toU8(b));\n'
            'export const inflateRawSync = (b) => fInflate(toU8(b));\n'
            'export default { constants, gzipSync, gunzipSync, deflateSync, inflateSync, inflateRawSync, deflateRawSync };\n',
            encoding="utf-8",
        )
        entry = work / "entry.mjs"
        entry.write_text(
            'import { Bash } from "just-bash";\n'
            'globalThis.JustBash = { Bash };\n',
            encoding="utf-8",
        )
        out = dest / "bash.iife.js"
        subprocess.run(
            [
                str(work / "node_modules" / ".bin" / "esbuild"),
                str(entry),
                "--bundle",
                "--platform=browser",
                "--format=iife",
                "--minify",
                f"--alias:node:zlib={zlib_shim}",
                f"--alias:zlib={zlib_shim}",
                f"--outfile={out}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    return "bash.iife.js"


def fetch_runtime(key: str, spec: dict, out_dir: Path) -> dict:
    dest = out_dir / key
    dest.mkdir(parents=True, exist_ok=True)
    tarball = _download(_tarball_url(spec["package"], spec["version"]))
    print(f"  {spec['package']}@{spec['version']}: {len(tarball) / 1_048_576:.1f} MiB tarball")
    written = _extract_prefix(tarball, spec["members"], dest)

    if spec.get("receipts"):
        receipts = _asset_receipts(tarball, spec["receipts"])
        if receipts:
            (dest / "asset-receipts.json").write_text(receipts, encoding="utf-8")
            written.append("asset-receipts.json")
    if spec.get("extra_package"):
        package, version = spec["extra_package"]
        extra = _download(_tarball_url(package, version))
        written += [f"{spec['extra_dest']}{rel}" for rel in
                    _extract_glob(extra, spec["extra_glob"], dest / spec["extra_dest"].rstrip("/"))]
    libs: list[str] = []
    if spec.get("lib_anchors"):
        closure = _lib_closure(tarball, tuple(spec["lib_anchors"]))
        for name, data in sorted(closure.items()):
            (dest / name).write_bytes(data)
            libs.append(name)
    if spec.get("patch_dotnet_js"):
        _patch_csharp_bundle(dest)
    if spec.get("bundle_bash"):
        written.append(_bundle_bash(dest, spec["version"]))
    for relpath, pairs in (spec.get("text_patches") or {}).items():
        target = dest / relpath
        text = target.read_text(encoding="utf-8")
        for needle, replacement in pairs:
            if text.count(needle) != 1:
                raise ValueError(
                    f"{relpath}: patch anchor not found exactly once: {needle!r}"
                )
            text = text.replace(needle, replacement)
        target.write_text(text, encoding="utf-8")
        print(f"  patched {relpath} ({len(pairs)} replacement(s))")

    total = sum((dest / rel).stat().st_size for rel in written)
    print(f"  -> {dest} ({len(written)} files, {total / 1_048_576:.1f} MiB)")
    entry = {
        "package": spec["package"],
        "version": spec["version"],
        "languages": spec["languages"],
        "bytes": total,
        "files": len(written),
    }
    if libs:
        entry["libs"] = libs
    return entry


def _vendored_entry(key: str, spec: dict, out_dir: Path) -> dict | None:
    """Manifest entry for a runtime already vendored into ``out_dir`` by an
    earlier run (``--only`` must not drop languages that exist on disk)."""
    folder = out_dir / key
    files = [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
    if not files:
        return None
    entry = {
        "package": spec["package"],
        "version": spec["version"],
        "languages": spec["languages"],
        "bytes": sum(p.stat().st_size for p in files),
        "files": len(files),
    }
    # The TypeScript entry carries its lib closure; keep it across --only
    # runs by reading the vendored lib files back off disk.
    libs = sorted(p.name for p in folder.glob("lib.*.d.ts"))
    if libs:
        entry["libs"] = libs
    return entry


def fetch(out_dir: Path, only: set[str] | None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"format": 1, "runtimes": {}}
    failures = 0
    for key, spec in RUNTIMES.items():
        if only and key not in only:
            if (entry := _vendored_entry(key, spec, out_dir)) is not None:
                manifest["runtimes"][key] = entry
            continue
        print(f"[{key}] {spec['package']}@{spec['version']} -> {', '.join(spec['languages'])}")
        try:
            manifest["runtimes"][key] = fetch_runtime(key, spec, out_dir)
        except Exception as exc:  # noqa: BLE001 - one bad runtime must not sink the rest
            failures += 1
            print(f"  ! {key} failed and was omitted from the manifest: {exc}", file=sys.stderr)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    present = sorted({lang for rt in manifest["runtimes"].values() for lang in rt["languages"]})
    print(f"manifest: {len(manifest['runtimes'])} runtimes, languages: {', '.join(present) or 'none'}")
    # Partial success is still a successful step (the browser degrades
    # honestly per missing language); fail only when nothing was vendored
    # that was asked for.
    return 0 if present or not only else 1


def _self_check() -> int:
    for key, spec in RUNTIMES.items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", spec["version"]), f"{key} version must be an exact pin"
        url = _tarball_url(spec["package"], spec["version"])
        assert url.startswith("https://registry.npmjs.org/"), url
        assert spec["languages"], key
    repo = Path(__file__).resolve().parents[1]
    live = (repo / "backend" / "static" / "js" / "pages-live.js").read_text(encoding="utf-8")
    for marker in ("manifest.json", "ev-runtime-worker.js", "worker-java.js", "worker.iife.js", "csharp-worker.js"):
        assert marker in live, f"pages-live.js no longer loads {marker}"
    for worker in ("ev-runtime-worker.js", "csharp-worker.js"):
        assert (repo / "backend" / "static" / "js" / worker).is_file(), f"missing backend/static/js/{worker}"
    exporter = (repo / "scripts" / "export_pages.py").read_text(encoding="utf-8")
    assert '"runtimes"' in exporter, "exporter no longer advertises the runtimes/ URL"
    print(f"fetch_browser_runtimes self-check OK ({len(RUNTIMES)} pinned runtimes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="directory to write the runtimes into (e.g. site/runtimes)")
    parser.add_argument("--only", default="", help="comma-separated runtime keys to fetch (default: all)")
    parser.add_argument("--self-check", action="store_true", help="validate wiring without downloading")
    args = parser.parse_args(argv)
    if args.self_check:
        return _self_check()
    if args.out is None:
        parser.error("--out is required unless --self-check is given")
    only = {part.strip() for part in args.only.split(",") if part.strip()} or None
    return fetch(args.out, only)


if __name__ == "__main__":
    raise SystemExit(main())
