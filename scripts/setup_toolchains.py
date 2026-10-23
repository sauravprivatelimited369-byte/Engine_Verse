#!/usr/bin/env python3
"""Install the real language toolchains the EngineVerse local judge compiles and
runs submissions with.

Every catalogue language needs its genuine toolchain on the host: the judge
never fakes a language by routing it to another runtime. This script provisions
all of them so ``runnable_languages()`` reports the whole catalogue.

Why the odd install locations
-----------------------------
The sandbox hides the application checkout and the account's home directory
from submitted code (empty tmpfs mounts inside the child's mount namespace).
Toolchains therefore live *outside* both trees - ``/opt/engineverse/toolchains``
by default - with symlinks in ``/usr/local/bin``. A toolchain installed under
``$HOME`` or inside the repository would vanish inside the sandbox and every
submission would fail with "command not found".

Where the binaries come from
----------------------------
The toolchains are vendored inside ordinary registry packages, so a host that
can reach PyPI and the npm registry can provision a judge with no access to
vendor download hosts:

    Java       jdk4py wheel (PyPI)            - Temurin 25 JRE (java) ...
    ... + ECJ   @vscjava/java-language-server   - Eclipse Compiler for Java,
               (npm, org.eclipse.jdt.core.compiler.batch) behind a javac shim.
               jdk4py ships a runtime only - the compiler jar is the standalone
               ECJ that runs on it, which is a genuine javac-grade compiler.
    Go         go-bin wheel (PyPI)            - prebuilt Go toolchain
    Rust       arena-rust-toolchain (PyPI)    - rustc/cargo, split wheels
    .NET SDK   (system install only, 8+)      - never vendored here: the only SDK
               packaged for npm was .NET Core 3.1, end-of-life since Dec 2022.
               C# runs on the WASM bundle below; a supported system SDK is
               reported and used as-is. See install_dotnet().
    C# WASM    @live-codes/blazor-wasm (npm)   - real Roslyn on WebAssembly: modern
               C# (top-level statements, LINQ, interpolation) with stdin support
    TypeScript typescript + @types/node (npm) - tsc for the TypeScript runner
    Ruby       @ruby/3.3-wasm-wasi (npm)      - CRuby on WASM for the Ruby runner

Usage
-----
    python3 scripts/setup_toolchains.py            # install everything
    python3 scripts/setup_toolchains.py --check    # report, install nothing
    python3 scripts/setup_toolchains.py go java    # install selected languages

Environment
-----------
    ENGINEVERSE_TOOLCHAIN_DIR   install prefix (default /opt/engineverse/toolchains)
    ENGINEVERSE_TOOLCHAIN_BIN   symlink dir      (default /usr/local/bin)

Needs write access to both directories (run via sudo on a stock server).
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

PREFIX = Path(os.environ.get("ENGINEVERSE_TOOLCHAIN_DIR", "/opt/engineverse/toolchains"))
BIN_DIR = Path(os.environ.get("ENGINEVERSE_TOOLCHAIN_BIN", "/usr/local/bin"))

# Versions pinned so a re-run provisions the same toolchains.
GO_BIN_VERSION = "1.27.3"
JDK4PY_VERSION = "25.0.2.1"
RUST_VERSION = "1.97.0"
BLAZOR_WASM_VERSION = "0.1.1"

# Oldest .NET SDK major this script (and judge/local.py) will let near a
# submission. Below this the runtime is end-of-life and unpatchable.
DOTNET_MIN_MAJOR = 8

log_lines: list[str] = []


def say(message: str) -> None:
    print(message, flush=True)
    log_lines.append(message)


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    say(f"    $ {' '.join(str(a) for a in argv)}")
    return subprocess.run([str(a) for a in argv], check=True, **kwargs)


def arch() -> str:
    machine = platform.machine()
    return {"x86_64": "x86_64", "AMD64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}.get(machine, machine)


def which_ok(binary: str) -> str | None:
    found = shutil.which(binary)
    return found if found else None


def link_bin(target: Path, names: list[str]) -> None:
    """Symlink *names* in BIN_DIR pointing at *target*'s binaries.

    An existing real installation is never replaced; the system toolchain wins
    and the bundled copy simply goes unused.
    """
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = target / "bin" / name
        if not source.exists():
            # .NET keeps its muxer at the root rather than under bin/.
            source = target / name
        if not source.exists():
            say(f"    ! {name} not found under {target}")
            continue
        link = BIN_DIR / name
        if link.is_symlink() or link.exists():
            say(f"    = {link} already present; leaving it alone")
            continue
        link.symlink_to(source)
        say(f"    + {link} -> {source}")


# --------------------------------------------------------------------------
# PyPI helpers
# --------------------------------------------------------------------------

def pip_download(dest: Path, requirements: list[str]) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    run([
        sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary", ":all:",
        "-d", dest, *requirements,
    ])
    return sorted(dest.glob("*.whl"))


def extract_wheel(wheel: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(dest)


def find_under(root: Path, relative: str) -> Path | None:
    matches = sorted(root.rglob(relative))
    return matches[0] if matches else None


# --------------------------------------------------------------------------
# Toolchains
# --------------------------------------------------------------------------

def install_jdk() -> None:
    """Java toolchain: Temurin JRE (jdk4py) + the Eclipse Compiler for Java.

    jdk4py's wheel is a jlink'd ``java.se`` runtime - it has no ``javac``. The
    compiler comes from the standalone ECJ batch compiler jar
    (``org.eclipse.jdt.core.compiler.batch``), vendored inside the
    ``@vscjava/java-language-server`` npm package. A small ``javac`` shim drives
    ECJ with javac-style arguments so the judge runner (and learners' muscle
    memory) see a normal ``javac``.
    """
    if which_ok("javac") and which_ok("java"):
        say(f"  java: already on PATH ({shutil.which('javac')})")
        return
    say(f"  java: downloading jdk4py {JDK4PY_VERSION} (JRE) from PyPI")
    with tempfile.TemporaryDirectory(prefix="ev-tc-jdk-") as tmp:
        tmpp = Path(tmp)
        wheels = pip_download(tmpp / "dl", [f"jdk4py=={JDK4PY_VERSION}"])
        wheel = next(w for w in wheels if "x86_64" in w.name or "aarch64" in w.name or "any" in w.name)
        extract_wheel(wheel, tmpp / "x")
        java_binary = find_under(tmpp / "x", "bin/java")
        if java_binary is None:
            raise SystemExit("jdk4py wheel does not contain bin/java")
        home = java_binary.parent.parent
        target = PREFIX / "java"
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(home), target)
        for binary in (target / "bin").iterdir():
            binary.chmod(0o755)

        say("  java: downloading the Eclipse Compiler for Java (ECJ) from npm")
        run(["npm", "pack", "@vscjava/java-language-server@0.1.2", "--pack-destination", str(tmpp)])
        tarball = next(tmpp.glob("*.tgz"))
        with tarfile.open(tarball) as tar:
            tar.extractall(tmpp / "npm")
        ecj = next(iter((tmpp / "npm").rglob("org.eclipse.jdt.core.compiler.batch_*.jar")), None)
        if ecj is None:
            raise SystemExit("java-language-server package does not contain the ECJ batch compiler jar")
        ecj_target = target / "lib" / "ecj.jar"
        ecj_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ecj, ecj_target)

    java_bin = target / "bin" / "java"
    shim = target / "bin" / "javac"
    shim.write_text(
        "#!/bin/sh\n"
        "# javac-compatible front end for the Eclipse Compiler for Java (ECJ).\n"
        "# EngineVerse provisions this only when no real JDK is installed: the\n"
        "# jdk4py wheel ships a java.se runtime without javac, and ECJ is a\n"
        "# genuine javac-grade compiler that runs on it. javac-only flags are\n"
        "# translated, everything else is passed through unchanged.\n"
        f'JAVA_BIN="{java_bin}"\n'
        f'ECJ_JAR="{ecj_target}"\n'
        'if [ "$#" -eq 1 ] && [ "$1" = "-version" ]; then\n'
        '  echo "javac 25.0.2 (Eclipse Compiler for Java, EngineVerse shim)"\n'
        '  exit 0\n'
        'fi\n'
        'JVM=""\n'
        'n=$#\n'
        'while [ "$n" -gt 0 ]; do\n'
        '  arg=$1\n'
        '  shift; n=$((n - 1))\n'
        '  case "$arg" in\n'
        '    -Xlint*) ;;                          # javac lint switch; ECJ uses -warn\n'
        '    -J*) JVM="$JVM ${arg#-J}" ;;         # JVM flags go to the runner JVM\n'
        '    *) set -- "$@" "$arg" ;;\n'
        '  esac\n'
        'done\n'
        'exec "$JAVA_BIN" $JVM -Xmx256m -XX:CompressedClassSpaceSize=64m '
        '-XX:ReservedCodeCacheSize=64m -XX:MaxMetaspaceSize=128m -Xss4m '
        '-cp "$ECJ_JAR" org.eclipse.jdt.internal.compiler.batch.Main "$@"\n'
    )
    shim.chmod(0o755)
    link_bin(target, ["java", "javac", "jcmd", "jfr", "jinfo", "jmap", "jps", "jrunscript", "jstack", "jstat", "jwebserver", "keytool", "rmiregistry"])
    say(f"  java: JRE + ECJ javac shim installed to {target}")


def install_go() -> None:
    """Prebuilt Go toolchain via the go-bin wheel."""
    if which_ok("go"):
        say(f"  go: already on PATH ({shutil.which('go')})")
        return
    say(f"  go: downloading go-bin {GO_BIN_VERSION} from PyPI")
    with tempfile.TemporaryDirectory(prefix="ev-tc-go-") as tmp:
        wheels = pip_download(Path(tmp) / "dl", [f"go-bin=={GO_BIN_VERSION}"])
        wheel = wheels[0]
        extract_wheel(wheel, Path(tmp) / "x")
        go_binary = find_under(Path(tmp) / "x", "go/bin/go")
        if go_binary is None:
            go_binary = find_under(Path(tmp) / "x", "bin/go")
        if go_binary is None:
            raise SystemExit("go-bin wheel does not contain a go binary")
        goroot = go_binary.parent.parent
        target = PREFIX / "go"
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(goroot), target)
        # Zip extraction drops the executable bits the toolchain was packed
        # with; without them `go` cannot even start its own compile toolchain.
        for rel in ("bin", "pkg/tool"):
            root = target / rel
            if root.is_dir():
                for binary in root.rglob("*"):
                    if binary.is_file():
                        binary.chmod(0o755)
    link_bin(target, ["go", "gofmt"])
    say(f"  go: installed to {target}")


def install_rust() -> None:
    """Rust toolchain via arena-rust-toolchain's split data wheels.

    That package's own ``install()`` shells out to a ``zstd`` binary that many
    minimal hosts lack (and its data-package list references an unpublished
    fourth part), so the parts are assembled and decompressed here in Python.
    """
    if which_ok("rustc") and which_ok("cargo"):
        say(f"  rust: already on PATH ({shutil.which('rustc')})")
        return
    say(f"  rust: downloading arena-rust-toolchain {RUST_VERSION} from PyPI")
    with tempfile.TemporaryDirectory(prefix="ev-tc-rust-") as tmp:
        tmpp = Path(tmp)
        run([
            sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(tmpp / "pysite"),
            "zstandard",
        ])
        wheels = pip_download(tmpp / "dl", [
            f"arena-rust-toolchain=={RUST_VERSION}",
            f"arena-rust-toolchain-data1=={RUST_VERSION}",
            f"arena-rust-toolchain-data2=={RUST_VERSION}",
            f"arena-rust-toolchain-data3=={RUST_VERSION}",
        ])
        for wheel in wheels:
            extract_wheel(wheel, tmpp / "x")
        # Part files live in the data package directories, one concatenated
        # zstd stream across packages in data1 -> data2 -> data3 order.
        parts: list[Path] = []
        for pkg in ("arena_rust_toolchain_data1", "arena_rust_toolchain_data2", "arena_rust_toolchain_data3"):
            pkg_dir = tmpp / "x" / pkg
            parts.extend(sorted(p for p in pkg_dir.iterdir() if p.is_file() and not p.name.startswith("_")))
        if not parts:
            raise SystemExit("arena-rust-toolchain data wheels contained no archive parts")
        combined = tmpp / "toolchain.tar.zst"
        with combined.open("wb") as out:
            for part in parts:
                with part.open("rb") as handle:
                    shutil.copyfileobj(handle, out)
        say(f"  rust: decompressing {combined.stat().st_size // (1024 * 1024)} MB toolchain archive")
        sys.path.insert(0, str(tmpp / "pysite"))
        import zstandard  # noqa: WPS433 - deliberately imported after path setup

        target = PREFIX / "rust"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with combined.open("rb") as compressed:
            with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    tar.extractall(target)
        rustc = find_under(target, "bin/rustc")
        if rustc is None:
            raise SystemExit("extracted Rust archive does not contain bin/rustc")
        root = rustc.parent.parent
        if root != target:
            # Normalise to PREFIX/rust so the layout is always rust/bin/rustc.
            staged = PREFIX / "rust.staged"
            if staged.exists():
                shutil.rmtree(staged)
            shutil.move(str(root), str(staged))
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(staged), str(target))
    link_bin(target, ["rustc", "cargo", "rustfmt", "cargo-clippy", "clippy-driver"])
    say(f"  rust: installed to {target}")


def _dotnet_major(binary: str) -> int:
    """Major version of the first SDK a dotnet muxer reports (0 = unknown)."""
    try:
        probe = subprocess.run(
            [binary, "--list-sdks"], capture_output=True, text=True, timeout=15
        )
        first = (probe.stdout or "").strip().splitlines()[:1]
        return int(first[0].split(".", 1)[0]) if first else 0
    except Exception:  # noqa: BLE001 - an unprobeable SDK is reported, not trusted
        return 0


def install_dotnet() -> None:
    """Report a system .NET SDK. This script never installs one any more.

    It used to download ``dotnet-sdk-3.1-linux-x64`` from npm and vendor
    OpenSSL 1.1 shared libraries so the 3.1 runtime could load on OpenSSL 3
    hosts. .NET Core 3.1 went end-of-life in December 2022 (OpenSSL 1.1 in
    September 2023): provisioning an unpatchable runtime to execute learner
    code is exactly the standing hole PHP2Shell made impossible to ignore.
    C# runs on the Roslyn-on-WASM bundle (install_csharp_wasm). A system
    SDK >= 8 on PATH is used as-is by the judge's classic runner; anything
    older is refused there too (see judge/local.py).
    """
    found = which_ok("dotnet")
    if not found:
        say("  csharp: no system .NET SDK; the Roslyn-on-WASM runner covers C#")
        return
    major = _dotnet_major(found)
    if major and major < DOTNET_MIN_MAJOR:
        say(
            f"  csharp: WARNING system SDK at {found} is .NET {major} (end-of-life); "
            "the judge refuses it. Remove it or install .NET 8+."
        )
        return
    say(f"  csharp: system .NET SDK on PATH ({found}); using it as-is")


def _judge_assets() -> Path:
    """The repo's judge module directory (hosts the runner scripts we install)."""
    return Path(__file__).resolve().parent.parent / "backend" / "engineverse" / "judge"


def _apply_dotnet_js_patches(bundle: Path) -> None:
    """Teach the bundle's Node-mode fetch shim to serve real HTTP responses.

    ``_framework/dotnet.js`` routes file:// reads through fs and returns a
    minimal response object with no ``status`` and a content-length of 0, which
    the .NET HttpClient rejects (status 0) or ZipArchive cannot parse
    ("CDCorrupt"). These replacements give it a full response: 200 status,
    real content-length, a true ArrayBuffer, text(), and a ReadableStream body
    (the streaming reader is what HttpContent actually consumes).
    """
    dotnet_js = next((bundle / "_framework").glob("dotnet.js"))
    src = dotnet_js.read_text(encoding="utf-8")
    patches = [
        (
            'return{ok:!0,headers:{length:0,get:()=>null},url:e,arrayBuffer:()=>r,'
            'json:()=>JSON.parse(r),text:()=>{throw new Error("NotImplementedException")}}}',
            # A real Response: WebAssembly.compileStreaming requires one
            # (a duck-typed object throws ERR_INVALID_ARG_TYPE), and it
            # already provides arrayBuffer/text/body/headers natively.
            'return new Response(new Uint8Array(r),{status:200,statusText:"OK",headers:'
            '{"content-type":e.endsWith(".wasm")?"application/wasm":"application/octet-stream",'
            '"content-length":String(r.length)}})}',
        ),
    ]
    for old, new in patches:
        count = src.count(old)
        if count == 0 and new.split("}}")[0][:40] in src:
            continue  # already patched on an earlier run
        if count != 1:
            raise SystemExit(f"dotnet.js patch anchor found {count} times (expected 1); bundle layout changed")
        src = src.replace(old, new)
    dotnet_js.write_text(src, encoding="utf-8")


def _write_wasm_node_shims(bundle: Path) -> None:
    """node-fetch / node-abort-controller stand-ins the runtime `require`s.

    In Node mode the runtime refuses to start HTTP support without these two
    packages. The real node-fetch cannot read file:// URLs anyway; this shim
    serves the bundle's own files (refs.zip, razor.zip) from disk and nothing
    else, so the compiler's reference fetches work with no network.
    """
    fetch_dir = bundle / "node_modules" / "node-fetch"
    abort_dir = bundle / "node_modules" / "node-abort-controller"
    fetch_dir.mkdir(parents=True, exist_ok=True)
    abort_dir.mkdir(parents=True, exist_ok=True)
    (fetch_dir / "package.json").write_text(
        '{ "name": "node-fetch", "version": "2.7.0", "main": "index.cjs" }\n', encoding="utf-8"
    )
    (fetch_dir / "index.cjs").write_text(
        '''"use strict";
const fs = require("fs");
const path = require("path");
const BASE = path.dirname(path.dirname(__dirname)) + path.sep;
function urlToFile(url) {
  const u = String(url).split("?")[0];
  if (u.startsWith("file://")) return require("url").fileURLToPath(u);
  if (u.startsWith(BASE)) return u.slice(BASE.length);
  return null;
}
function makeHeaders(map) {
  const m = new Map(Object.entries(map || {}).map(([k, v]) => [String(k).toLowerCase(), v]));
  return {
    get: (k) => (m.has(String(k).toLowerCase()) ? m.get(String(k).toLowerCase()) : null),
    has: (k) => m.has(String(k).toLowerCase()),
    entries: () => m.entries(),
  };
}
function makeResponse(buf, status, headers) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    headers: makeHeaders(headers),
    url: "",
    arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength),
    text: async () => buf.toString("utf8"),
    json: async () => JSON.parse(buf.toString("utf8")),
  };
}
function fetch(input, init) {
  const url = String(typeof input === "string" ? input : (input && (input.url || input.href)) || input);
  const file = urlToFile(url);
  if (file) {
    try {
      const data = fs.readFileSync(file);
      return Promise.resolve(makeResponse(data, 200, { "content-type": "application/octet-stream" }));
    } catch (e) {
      return Promise.resolve(makeResponse(Buffer.from("not found"), 404, {}));
    }
  }
  return Promise.reject(new TypeError("EngineVerse node-fetch shim: blocked URL " + url.slice(0, 120)));
}
fetch.default = fetch;
module.exports = fetch;
module.exports.default = fetch;
''',
        encoding="utf-8",
    )
    (abort_dir / "package.json").write_text(
        '{ "name": "node-abort-controller", "version": "3.1.1", "main": "index.cjs" }\n', encoding="utf-8"
    )
    (abort_dir / "index.cjs").write_text(
        '"use strict";\nmodule.exports = { AbortController: globalThis.AbortController, AbortSignal: globalThis.AbortSignal };\nmodule.exports.default = module.exports;\n',
        encoding="utf-8",
    )


def install_csharp_wasm() -> None:
    """Modern C# via the real Roslyn compiler running on WebAssembly.

    The @live-codes/blazor-wasm bundle embeds the full .NET runtime plus the
    actual Microsoft.CodeAnalysis compiler (BlazorRunner), so submissions get
    current-language C# - top-level statements, string interpolation, records,
    generics, LINQ - and stdin support, entirely offline. This is the C#
    runner this script installs; a supported system .NET SDK (8+) is the
    judge's only other C# path and is never downloaded here.
    """
    target = PREFIX / "csharp-wasm"
    if (target / "runner.mjs").is_file() and (target / "_framework").is_dir():
        say("  csharp-wasm: already installed")
        return
    say(f"  csharp-wasm: downloading @live-codes/blazor-wasm {BLAZOR_WASM_VERSION} from npm")
    with tempfile.TemporaryDirectory(prefix="ev-tc-blazor-") as tmp:
        tmpp = Path(tmp)
        run(["npm", "pack", f"@live-codes/blazor-wasm@{BLAZOR_WASM_VERSION}", "--pack-destination", str(tmpp)])
        tarball = next(tmpp.glob("*.tgz"))
        with tarfile.open(tarball) as tar:
            tar.extractall(tmpp / "x")
        marker = find_under(tmpp / "x", "blazor-wasm.js")
        if marker is None:
            raise SystemExit("npm @live-codes/blazor-wasm package does not contain blazor-wasm.js")
        pkg = marker.parent
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(pkg, target)
    _apply_dotnet_js_patches(target)
    _write_wasm_node_shims(target)
    runner = _judge_assets() / "csharp_wasm_runner.mjs"
    if not runner.is_file():
        raise SystemExit(f"missing runner script {runner}")
    shutil.copy(runner, target / "runner.mjs")
    # NOTE: do not add "type": "module" here - blazor-wasm.js is a UMD bundle
    # whose top-level `this` is undefined under ESM and it dies silently.
    say(f"  csharp-wasm: Roslyn-on-WASM installed to {target} (modern C# + stdin)")


def install_typescript() -> None:
    """Real tsc plus Node typings so TypeScript is compiled, not just stripped."""
    if which_ok("tsc") and Path("/usr/local/lib/node_modules/@types/node").is_dir():
        say("  typescript: tsc and @types/node already present")
        return
    say("  typescript: npm install -g typescript @types/node")
    run(["npm", "install", "-g", "typescript", "@types/node"])
    say("  typescript: installed")


def install_ruby_wasm() -> None:
    """CRuby compiled to WASM (runs under Node) for the Ruby runner."""
    node_modules = Path("/usr/local/lib/node_modules")
    have_api = (node_modules / "@ruby" / "wasm-wasi").is_dir()
    have_vm = any((node_modules / "@ruby").glob("*.wasm-wasi")) if (node_modules / "@ruby").is_dir() else False
    if not (have_api and have_vm):
        say("  ruby: npm install -g @ruby/wasm-wasi @ruby/3.3-wasm-wasi")
        run(["npm", "install", "-g", "@ruby/wasm-wasi", "@ruby/3.3-wasm-wasi"])
    else:
        say("  ruby: @ruby/wasm-wasi and the ruby.wasm VM already present")
    target = PREFIX / "ruby-wasm"
    target.mkdir(parents=True, exist_ok=True)
    runner = _judge_assets() / "ruby_wasm_runner.mjs"
    if not runner.is_file():
        raise SystemExit(f"missing runner script {runner}")
    shutil.copy(runner, target / "runner.mjs")
    say(f"  ruby: runner installed to {target / 'runner.mjs'} (CRuby 3.3 on WASM)")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

LANGUAGES = {
    "python": ("python3",),
    "java": ("javac", "java"),
    "javascript": ("node",),
    "typescript": ("node",),
    "c": ("gcc",),
    "cpp": ("g++",),
    "go": ("go",),
    "rust": ("rustc",),
    "csharp": ("dotnet",),
    "sql": ("python3",),
    "bash": ("sh",),
    "ruby": ("node",),
}


def check() -> int:
    print(f"Toolchain prefix: {PREFIX}")
    missing = []
    wasm_csharp = (PREFIX / "csharp-wasm" / "runner.mjs").is_file()
    ruby_runner = (PREFIX / "ruby-wasm" / "runner.mjs").is_file()
    for language, binaries in LANGUAGES.items():
        if language == "csharp" and wasm_csharp:
            print(f"  {language:<11} csharp-wasm=ok ({PREFIX / 'csharp-wasm'}) dotnet={shutil.which('dotnet') or 'MISSING (fallback only)'}")
            continue
        if language == "ruby" and ruby_runner:
            print(f"  {language:<11} ruby-wasm=ok ({PREFIX / 'ruby-wasm'}) node={shutil.which('node') or 'MISSING'}")
            if shutil.which('node') is None:
                missing.append(language)
            continue
        state = []
        for binary in binaries:
            found = which_ok(binary)
            state.append(f"{binary}={'ok' if found else 'MISSING'}")
        ok = all(which_ok(b) for b in binaries)
        if ok and language == "csharp":
            # A dotnet binary is not enough: an end-of-life SDK is refused by
            # the judge, so reporting it as present would be a lie.
            major = _dotnet_major(shutil.which("dotnet"))
            if major and major < DOTNET_MIN_MAJOR:
                state = [f"dotnet=EOL(.NET {major}, judge refuses it)"]
                ok = False
        if not ok:
            missing.append(language)
        print(f"  {language:<11} {' '.join(state)}")
    if which_ok("tsc"):
        print(f"  typescript  tsc=ok ({shutil.which('tsc')})")
    else:
        print("  typescript  tsc=MISSING (falls back to Node type-stripping)")
        if "typescript" not in missing:
            pass
    if missing:
        print(f"\nMissing toolchains: {', '.join(missing)}")
        return 1
    print("\nEvery catalogue language has its real toolchain on PATH.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("languages", nargs="*", help="subset to install (default: all)")
    parser.add_argument("--check", action="store_true", help="report toolchain status and exit")
    args = parser.parse_args()

    if args.check:
        return check()

    wanted = [lang.lower() for lang in args.languages] or list(LANGUAGES)
    unknown = [lang for lang in wanted if lang not in LANGUAGES and lang not in ("typescript",)]
    if unknown:
        parser.error(f"unknown language(s): {', '.join(unknown)}")

    if arch() not in ("x86_64", "aarch64"):
        say(f"unsupported architecture {arch()}; vendored toolchains cover x86_64/aarch64 Linux only")
        return 2

    PREFIX.mkdir(parents=True, exist_ok=True)

    def install_csharp() -> None:
        # The Roslyn-on-WASM bundle is the primary C# runner (modern C# +
        # stdin); the vendored SDK is the classic-program fallback. Both.
        install_dotnet()
        install_csharp_wasm()

    steps = {
        "java": install_jdk,
        "go": install_go,
        "rust": install_rust,
        "csharp": install_csharp,
        "typescript": install_typescript,
        "ruby": install_ruby_wasm,
    }
    say(f"Installing toolchains into {PREFIX} (symlinks in {BIN_DIR})")
    failed: list[str] = []
    for language, step in steps.items():
        if language not in wanted:
            continue
        try:
            step()
        except (SystemExit, subprocess.CalledProcessError, OSError) as exc:
            failed.append(language)
            say(f"  {language}: FAILED ({exc})")

    print()
    result = check()
    if failed:
        print(f"\nFailed steps: {', '.join(failed)}")
        return 1
    return result


if __name__ == "__main__":
    sys.exit(main())
