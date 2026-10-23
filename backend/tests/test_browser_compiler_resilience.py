"""Regression tests for browser & sandbox compiler resilience across all 11 languages.

Covers the full root-cause chain behind mobile/WebAssembly worker timeouts,
memory bloat, CDN gzip double-decompression, missing standard-library/stdin
support, and language-switching editor persistence:

1. Vendor runtime fetcher (`scripts/fetch_browser_runtimes.py`):
   - `clang` text patches remove `cache:"no-store"` and `redirect:"error"`,
     eliminate the extra 160 MB `Uint8Array.from(s)` copy in `Cn`, and delete
     raw `.wasm` byte buffers from `Rn` once `WebAssembly.compile` caches the
     compiled `WebAssembly.Module` in `wn` (~300 MB RAM saved on mobile).
   - `rust` text patches check the gzip magic header (`0x1f 0x8b`) before
     decompressing so GitHub Pages / CDN `Content-Encoding: gzip` never fails.
   - `bash` (`just-bash`) is vendored into `runtimes/bash/bash.iife.js`.
2. Service Worker (`backend/static/sw.js`):
   - Caches worker scripts (`ev-runtime-worker.js`, `csharp-worker.js`) in `CORE`
     and applies cache-first caching for immutable `/runtimes/*` & `/pyodide/*`
     assets while restricting `/static/offline.html` fallback strictly to navigation.
3. Workers & Frontend Runtimes (`ev-runtime-worker.js`, `csharp-worker.js`,
   `pages-live.js`, `codelab.js`, `app.js`):
   - Split cold-boot timeouts (`EV_RUNTIME_BOOT_TIMEOUT_MS` / `EV_PYODIDE_BOOT_TIMEOUT_MS`)
     from per-run execution timeouts (`EV_RUNTIME_RUN_TIMEOUT_MS` / `EV_PYODIDE_RUN_TIMEOUT_MS`),
     self-healing boot promises on transient load failure, idle pre-warming,
     progress status streaming, and per-language editor storage (`${STORAGE}:${lang}`).
   - Clang compiles GNU17 (`-std=gnu17`) and GNU++20 (`-std=gnu++20`), Go wires
     real POSIX `os.Stdin`/`os.Stderr`, JavaScript & TypeScript support both
     Node `require("fs").readFileSync(0)` / `import * as fs from "fs"` and
     `input`/`print`/`readline` without parameter-shadowing `SyntaxError`s,
     Pyodide flushes raw UTF-8 stdout/stderr bytes, and Bash executes in-worker.
4. Server Judge & Drivers (`backend/engineverse/judge/local.py`,
   `backend/engineverse/drivers.py`, `seed_data/practice_data.py`):
   - `_detect_java_main_class`, C `gnu17`/`-lm`, C++20, Bash, TS `es2022`,
     dual standalone + function-style JavaScript execution, and runnable
     `two-sum` stubs & solutions in `python`, `javascript`, `java`, and `cpp`.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

from engineverse import drivers
from engineverse.judge.local import RUNNERS, _detect_java_main_class
from seed_data.practice_data import CODING_PROBLEMS

REPO = Path(__file__).resolve().parents[2]


def _load_fetch_runtimes_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_browser_runtimes",
        REPO / "scripts" / "fetch_browser_runtimes.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRuntimeVendorPatchesAndManifest:
    def test_all_eight_browser_runtime_bundles_are_registered(self):
        mod = _load_fetch_runtimes_module()
        assert set(mod.RUNTIMES.keys()) == {
            "clang",
            "java",
            "go",
            "rust",
            "sql",
            "typescript",
            "csharp",
            "bash",
        }
        assert mod.RUNTIMES["bash"]["package"] == "just-bash"
        assert mod.RUNTIMES["bash"]["bundle_bash"] is True
        assert mod.RUNTIMES["bash"]["languages"] == ["bash"]

    def test_clang_memory_and_cache_patches_are_configured_and_functional(self):
        mod = _load_fetch_runtimes_module()
        patches = mod.RUNTIMES["clang"]["text_patches"]["clang-wasm.global.js"]
        assert len(patches) == 4
        combined_before = "\n".join(before for before, _ in patches)
        combined_after = "\n".join(after for _, after in patches)
        assert 'cache:"no-store"' in combined_before
        assert 'cache:"no-store"' not in combined_after
        assert 'redirect:"follow"' in combined_after
        assert "Rn.delete(r)" in combined_after

    def test_rust_gzip_idempotency_patches_guard_magic_header(self):
        mod = _load_fetch_runtimes_module()
        patches = mod.RUNTIMES["rust"]["text_patches"]["worker.iife.js"]
        assert len(patches) == 2
        combined_after = "\n".join(after for _, after in patches)
        assert "a!==31||b!==139" in combined_after


class TestServiceWorkerAndFrontendContracts:
    def test_service_worker_caches_workers_runtimes_and_navigation_only_offline_fallback(self):
        sw = (REPO / "backend" / "static" / "sw.js").read_text("utf-8")
        assert "/static/js/ev-runtime-worker.js" in sw
        assert "/static/js/csharp-worker.js" in sw
        assert "/runtimes/" in sw
        assert "/pyodide/" in sw
        assert 'request.mode === "navigate"' in sw

    def test_split_boot_and_run_timeouts_and_self_healing_workers(self):
        pages_live = (REPO / "backend" / "static" / "js" / "pages-live.js").read_text("utf-8")
        worker_js = (REPO / "backend" / "static" / "js" / "ev-runtime-worker.js").read_text("utf-8")
        csharp_js = (REPO / "backend" / "static" / "js" / "csharp-worker.js").read_text("utf-8")
        codelab_js = (REPO / "backend" / "static" / "js" / "codelab.js").read_text("utf-8")
        app_js = (REPO / "backend" / "static" / "js" / "app.js").read_text("utf-8")

        # Separate boot timeout vs per-run execution timeout + prewarm & status APIs.
        assert "EV_RUNTIME_BOOT_TIMEOUT_MS" in pages_live
        assert "EV_RUNTIME_RUN_TIMEOUT_MS" in pages_live
        assert "EV_PYODIDE_BOOT_TIMEOUT_MS" in pages_live
        assert "EV_PYODIDE_RUN_TIMEOUT_MS" in pages_live
        assert "window.EV_BROWSER_PREWARM" in pages_live
        assert "window.EV_ON_RUNTIME_STATUS" in pages_live
        assert "bash:" in pages_live

        # Modern standards, real POSIX Go stdin, typed TS Node modules, Bash worker support.
        assert '"gnu17"' in worker_js
        assert '"gnu++20"' in worker_js
        assert 'declare module "fs"' in worker_js
        assert "JustBash" in worker_js
        assert 'msg.type === "init"' in worker_js

        # C# worker explicit pre-boot support.
        assert 'msg.type === "init"' in csharp_js

        # CodeLab browser fallback + per-language problem editor storage.
        assert "EV_BROWSER_TERMINAL" in codelab_js
        assert "EV_BROWSER_PREWARM" in codelab_js
        assert "storageKeyFor" in app_js
        assert "EV_BROWSER_PREWARM" in app_js


class TestServerJudgeAndDriverEnhancements:
    def test_java_main_class_detection_supports_any_public_or_package_class(self):
        assert _detect_java_main_class("public class Main { public static void main(String[] a){} }") == "Main"
        assert (
            _detect_java_main_class(
                "import java.util.*;\npublic final class Solution {\n  public static void main(String[] args) {}\n}"
            )
            == "Solution"
        )
        assert _detect_java_main_class("class FastSolver { public static void main(String[] args) {} }") == "FastSolver"

    def test_local_sandbox_uses_modern_c_cpp_and_bash_flags(self):
        assert "-std=gnu17" in RUNNERS["c"]["compile"]
        assert "-lm" in RUNNERS["c"]["compile"]
        assert "-std=gnu++20" in RUNNERS["cpp"]["compile"]
        assert RUNNERS["bash"]["run"][0] in ("bash", "sh")

    @pytest.mark.skipif(not shutil.which("node"), reason="node required to execute composed JS harness")
    def test_javascript_driver_accepts_both_function_and_standalone_stdin_programs(self):
        fn_prog = drivers.compose(
            "javascript",
            "function twoSum(nums, target) {\n"
            "  const seen = new Map();\n"
            "  for (let i = 0; i < nums.length; i++) {\n"
            "    if (seen.has(target - nums[i])) return [seen.get(target - nums[i]), i];\n"
            "    seen.set(nums[i], i);\n"
            "  }\n"
            "  return [];\n"
            "}\n",
            "list-target",
            "function twoSum(nums, target) {",
        )
        out_fn = subprocess.run(
            ["node", "-e", fn_prog],
            input="[2,7,11,15]\n9\n",
            capture_output=True,
            text=True,
            check=False,
        )
        assert out_fn.returncode == 0
        assert out_fn.stdout.strip() in ("[0, 1]", "[0,1]")

        standalone_prog = drivers.compose(
            "javascript",
            'const fs = require("fs");\n'
            'const lines = fs.readFileSync(0, "utf8").trim().split(/\\n+/);\n'
            "const nums = JSON.parse(lines[0]);\n"
            "const target = JSON.parse(lines[1]);\n"
            "const seen = new Map();\n"
            "for (let i = 0; i < nums.length; i++) {\n"
            "  if (seen.has(target - nums[i])) { console.log(JSON.stringify([seen.get(target - nums[i]), i])); break; }\n"
            "  seen.set(nums[i], i);\n"
            "}\n",
            "list-target",
            "function twoSum(nums, target) {",
        )
        out_standalone = subprocess.run(
            ["node", "-e", standalone_prog],
            input="[2,7,11,15]\n9\n",
            capture_output=True,
            text=True,
            check=False,
        )
        assert out_standalone.returncode == 0
        assert out_standalone.stdout.strip() == "[0,1]"

        missing_prog = drivers.compose("javascript", "// nothing defined\n", "list-target", "function twoSum(nums, target) {")
        out_missing = subprocess.run(
            ["node", "-e", missing_prog],
            input="[2,7,11,15]\n9\n",
            capture_output=True,
            text=True,
            check=False,
        )
        assert out_missing.returncode != 0
        assert "twoSum" in out_missing.stderr

    def test_two_sum_has_complete_runnable_stubs_and_solutions_across_all_four_languages(self):
        two_sum = next(p for p in CODING_PROBLEMS if p["slug"] == "two-sum")
        for lang in ("python", "javascript", "java", "cpp"):
            assert lang in two_sum["stub"] and two_sum["stub"][lang].strip()
            assert lang in two_sum["solution"] and two_sum["solution"][lang].strip()
        assert "public static void main" in two_sum["stub"]["java"]
        assert "int main(" in two_sum["stub"]["cpp"]
