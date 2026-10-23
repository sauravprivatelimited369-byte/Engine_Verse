"""Owner-decision follow-ups (2026-10-19): knowledge XP + every-language compilers.

Covers the three decisions taken on the audit backlog:

* F-13 reversed: XP is competitive/knowledge-based - it pays for first-time
  correct answers and first accepted solutions only, never for attempts,
  repeats or re-views.
* F-14/F-15: a compiler + terminal for every taught language in the website
  (hosted judge runners for all catalogue languages, Worker-isolated
  JavaScript and real CPython/Pyodide on the static copy), plus the separate
  Python compiler page.
* F-18: no prices were added - nothing to test here beyond leaving plans
  alone (covered by existing capability tests).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engineverse import coding, db, practice, progress
from engineverse.drivers import WRAPPERS, compose, entrypoint, javascript_driver
from engineverse.judge import KNOWN_LANGUAGES, provider_info, run_custom
from engineverse.judge.judge0 import LANGUAGE_IDS as JUDGE0_IDS
from engineverse.judge.local import RUNNERS, LocalSandboxProvider

REPO = Path(__file__).resolve().parents[2]

_CAN_ISOLATE = bool(provider_info().get("available"))
requires_isolation = pytest.mark.skipif(
    not _CAN_ISOLATE,
    reason="host cannot create the required namespaces; the sandbox refuses to run code",
)


def _csrf(html: str) -> str:
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


# ---------------------------------------------------------------------------
# Knowledge XP
# ---------------------------------------------------------------------------

class TestKnowledgeXp:
    def _mcq(self):
        question = db.query_one(
            "SELECT q.id, q.difficulty FROM questions q WHERE q.kind = 'mcq' AND q.is_active = 1 "
            "AND (SELECT count(*) FROM question_options o WHERE o.question_id = q.id AND o.is_correct = 0) >= 1 "
            "LIMIT 1"
        )
        assert question is not None
        rows = db.query(
            "SELECT is_correct FROM question_options WHERE question_id = ? ORDER BY order_index",
            question["id"],
        )
        right = next(i for i, row in enumerate(rows) if row["is_correct"])
        wrong = next(i for i, row in enumerate(rows) if not row["is_correct"])
        return question, right, wrong

    def test_wrong_answers_earn_nothing_and_first_correct_pays_once(self, seeded, demo_user):
        question, right, wrong = self._mcq()
        expected_value = {"easy": 5, "beginner": 5, "medium": 10, "hard": 15, "expert": 25}.get(
            question["difficulty"], 10
        )
        # The seeded demo history may already include this question; clear it
        # so the first-correct rule is what is being measured.
        db.execute("DELETE FROM submissions WHERE user_id = ? AND question_id = ?",
                   demo_user["id"], question["id"])
        before = progress.total_xp(demo_user["id"])

        wrong_result = practice.record_answer(demo_user["id"], question["id"], option_index=wrong)
        assert wrong_result["correct"] is False and wrong_result["xp"] == 0

        first = practice.record_answer(demo_user["id"], question["id"], option_index=right)
        assert first["correct"] is True and first["xp"] == expected_value

        repeat = practice.record_answer(demo_user["id"], question["id"], option_index=right)
        assert repeat["correct"] is True and repeat["alreadySolved"] is True and repeat["xp"] == 0

        assert progress.total_xp(demo_user["id"]) == before + expected_value
        attempt_events = db.scalar(
            "SELECT count(*) AS c FROM xp_events WHERE user_id = ? AND reason = 'question.attempt'",
            demo_user["id"],
        )
        assert int(attempt_events or 0) == 0, "no attempt-XP events may be written anymore"

    def test_topic_view_pays_only_the_first_view(self, seeded, demo_user):
        topic = db.query_one(
            "SELECT t.id FROM topics t WHERE NOT EXISTS "
            "(SELECT 1 FROM user_progress up WHERE up.user_id = ? AND up.topic_id = t.id) LIMIT 1",
            demo_user["id"],
        )
        assert topic is not None
        before = progress.total_xp(demo_user["id"])
        progress.mark_topic_viewed(demo_user["id"], topic["id"], minutes=1)
        progress.mark_topic_viewed(demo_user["id"], topic["id"], minutes=1)
        progress.mark_topic_viewed(demo_user["id"], topic["id"], minutes=1)
        assert progress.total_xp(demo_user["id"]) == before + 2, \
            "refreshing a topic page must not farm XP"

    @requires_isolation
    def test_repeat_accepted_solution_earns_no_xp(self, seeded, demo_user):
        problem = coding.get_problem("two-sum")
        assert problem is not None
        db.execute("DELETE FROM coding_submissions WHERE user_id = ? AND problem_id = ?",
                   demo_user["id"], problem["id"])
        solution = (
            "def two_sum(nums, target):\n    seen = {}\n"
            "    for i, v in enumerate(nums):\n"
            "        if target - v in seen:\n            return [seen[target - v], i]\n"
            "        seen[v] = i\n    return []\n"
        )
        first = coding.submit(demo_user["id"], problem["id"], "python", solution)
        assert first["status"] == "accepted" and first["xp"] == 30 and first["firstAccepted"] is True
        again = coding.submit(demo_user["id"], problem["id"], "python", solution)
        assert again["status"] == "accepted" and again["xp"] == 0 and again["firstAccepted"] is False


# ---------------------------------------------------------------------------
# Every-language runners
# ---------------------------------------------------------------------------

class TestEveryLanguageHasACompiler:
    def test_catalogue_languages_have_runners_known_slugs_and_judge0_ids(self, seeded):
        rows = db.query("SELECT slug, judge_slug FROM programming_languages")
        assert rows, "no languages seeded"
        for row in rows:
            judge_slug = row["judge_slug"]
            assert judge_slug, f"{row['slug']} has no judge slug - it cannot be compiled anywhere"
            assert judge_slug in RUNNERS, f"{row['slug']} has no local runner"
            assert judge_slug in KNOWN_LANGUAGES, f"{row['slug']} missing from KNOWN_LANGUAGES"
            assert judge_slug in JUDGE0_IDS, f"{row['slug']} missing from the Judge0 map"

    def test_terminal_templates_cover_the_whole_catalogue(self, seeded):
        rows = coding.terminal_languages()
        slugs = {row["slug"] for row in rows}
        catalogue = {row["slug"] for row in db.query("SELECT slug FROM programming_languages")}
        assert slugs == catalogue
        for row in rows:
            assert row["slug"] in coding.TERMINAL_TEMPLATES, f"{row['slug']} has no terminal starter"
            assert row["code"].strip(), f"{row['slug']} starter is empty"

    def test_missing_toolchains_are_not_advertised(self):
        provider = LocalSandboxProvider()
        # C# is the one language whose compiler may legitimately be present
        # without its namesake binary: the vendored Roslyn-on-WASM runner
        # (scripts/setup_toolchains.py) compiles C# with Node and needs no
        # `dotnet` at all. Every other language needs its own toolchain.
        csharp_wasm_runner = Path(
            os.environ.get("ENGINEVERSE_CSHARP_WASM", "/opt/engineverse/toolchains/csharp-wasm/runner.mjs")
        ).is_file()
        for language, binary in (("go", "go"), ("rust", "rustc"), ("csharp", "dotnet"), ("java", "javac")):
            if shutil.which(binary) is not None:
                continue
            if language == "csharp" and csharp_wasm_runner:
                assert provider.supports(language) is True, \
                    "the vendored Roslyn WASM runner is installed but C# is not advertised"
                continue
            assert provider.supports(language) is False, \
                f"{language} advertised without {binary} installed"

    @requires_isolation
    def test_typescript_really_executes(self):
        if not (shutil.which("node") or shutil.which("tsc")):
            pytest.skip("no Node/TypeScript toolchain on this host")
        result = run_custom(
            "typescript",
            "function add(a: number, b: number): number { return a + b; }\nconsole.log(add(20, 22));\n",
        )
        assert result.status == "accepted", result.stderr
        assert result.stdout.strip() == "42"

    @requires_isolation
    def test_sql_really_executes_with_stdin_as_setup(self):
        result = run_custom(
            "sql",
            "SELECT name, score FROM students WHERE score >= 80 ORDER BY score DESC;",
            "CREATE TABLE students(name TEXT, score INT);\n"
            "INSERT INTO students VALUES ('Asha', 88), ('Ravi', 74), ('Meena', 91);",
        )
        assert result.status == "accepted", result.stderr
        assert result.stdout.splitlines() == ["Meena | 91", "Asha | 88"]

    @requires_isolation
    def test_sql_error_is_a_runtime_error_not_a_fake_success(self):
        result = run_custom("sql", "SELECT * FROM table_that_does_not_exist;")
        assert result.status == "runtime_error"
        assert "no such table" in result.stderr


# ---------------------------------------------------------------------------
# JavaScript judged problems (drivers)
# ---------------------------------------------------------------------------

class TestJavaScriptDrivers:
    def test_every_wrapper_has_a_javascript_driver_except_raw(self):
        for wrapper in WRAPPERS:
            driver = javascript_driver(wrapper, "solve_it")
            if wrapper == "raw":
                assert driver == ""
            else:
                assert "EngineVerse harness" in driver and "__EV_" not in driver, wrapper

    def test_javascript_signature_entrypoints_parse(self):
        assert entrypoint("function twoSum(nums, target) {") == "twoSum"
        assert entrypoint("class LRUCache {") == "LRUCache"
        assert entrypoint("def two_sum(nums, target):") == "two_sum"

    def test_compose_appends_the_javascript_harness(self):
        program = compose("javascript", "function twoSum(a, b) { return []; }",
                          "list-target", "function twoSum(nums, target) {")
        assert "twoSum" in program and "EngineVerse harness" in program
        # Languages without a driver set still run verbatim - never pretend.
        assert compose("java", "public class Main {}", "int-list-int", None) == "public class Main {}"

    @requires_isolation
    def test_javascript_two_sum_is_really_judged(self, seeded):
        if not shutil.which("node"):
            pytest.skip("node is not installed on this host")
        problem = coding.get_problem("two-sum")
        assert problem is not None
        stubs = {row["slug"]: row for row in coding.stubs_for(problem["id"])}
        assert "javascript" in stubs, "two-sum lost its JavaScript stub"
        code = (
            "function twoSum(nums, target) {\n  const seen = new Map();\n"
            "  for (let i = 0; i < nums.length; i++) {\n"
            "    if (seen.has(target - nums[i])) return [seen.get(target - nums[i]), i];\n"
            "    seen.set(nums[i], i);\n  }\n  return [];\n}\n"
        )
        result = coding.run(problem["id"], "javascript", code, "[2, 7, 11, 15]\n9")
        assert result["executed"] is True, result
        assert result["status"] == "accepted", result
        assert (result["stdout"] or "").strip() == "[0, 1]", result


# ---------------------------------------------------------------------------
# Compiler pages
# ---------------------------------------------------------------------------

class TestCompilerPages:
    def test_compiler_pages_render_with_every_language(self, client, seeded):
        catalogue = [row["slug"] for row in db.query("SELECT slug FROM programming_languages")]
        for path, title in (("/compiler", "Code compiler"), ("/python-compiler", "Python compiler")):
            page = client.get(path)
            assert page.status_code == 200, path
            assert title in page.text, path
            for slug in catalogue:
                assert f'value="{slug}"' in page.text, f"{slug} missing from {path}"
            assert 'id="cpl-data"' in page.text and 'id="cpl-run"' in page.text

    @requires_isolation
    def test_terminal_api_runs_a_complete_python_program(self, signed_in):
        token = _csrf(signed_in.get("/compiler").text)
        response = signed_in.post(
            "/api/coding/run",
            json={"csrf_token": token, "language": "python", "problemSlug": None,
                  "code": 'name = input().strip()\nprint(f"Hello, {name}!")', "input": "Asha"},
            headers={"x-csrf-token": token},
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["executed"] is True and result["status"] == "accepted", result
        assert "Hello, Asha!" in result["stdout"], result

    def test_sitemap_lists_the_compiler_pages(self, client, seeded):
        sitemap = client.get("/sitemap.xml")
        assert sitemap.status_code == 200
        assert "/compiler" in sitemap.text and "/python-compiler" in sitemap.text


# ---------------------------------------------------------------------------
# Static copy: workers, Pyodide, exported drivers
# ---------------------------------------------------------------------------

class TestStaticCopyExecution:
    @pytest.fixture(scope="class")
    def pages_live(self) -> str:
        return (REPO / "backend" / "static" / "js" / "pages-live.js").read_text(encoding="utf-8")

    def test_python_transpiler_is_gone_and_pyodide_is_the_python_path(self, pages_live):
        assert "transpilePythonToJS" not in pages_live
        assert "transpileToJS" not in pages_live
        assert "loadPyodide" in pages_live
        assert "driverPython" in pages_live, "browser judging must use the exported server driver"

    def test_javascript_runs_in_a_worker_not_in_the_page(self, pages_live):
        assert "new Worker" in pages_live
        assert "EV_BROWSER_TERMINAL" in pages_live
        # `new Function` may exist only inside the worker source strings.
        for line in pages_live.splitlines():
            if "new Function" in line and "const run = " not in line and "const factory = " not in line:
                assert line.strip().startswith("//"), f"page-origin eval crept back in: {line.strip()}"

    def test_exported_problems_carry_the_python_driver(self, seeded, tmp_path):
        sys.path.insert(0, str(REPO / "scripts"))
        import export_pages

        export_pages.write_coding_problems(tmp_path)
        import json

        problems = json.loads((tmp_path / "coding-problems.json").read_text(encoding="utf-8"))
        two_sum = problems["two-sum"]
        assert "EngineVerse harness" in two_sum["driverPython"]
        assert "two_sum" in two_sum["driverPython"]

    def test_fetch_pyodide_self_check(self):
        done = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "fetch_pyodide.py"), "--self-check"],
            capture_output=True, text=True, timeout=60,
        )
        assert done.returncode == 0, done.stderr
        assert "self-check OK" in done.stdout

    def test_fetch_browser_runtimes_self_check(self):
        done = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "fetch_browser_runtimes.py"), "--self-check"],
            capture_output=True, text=True, timeout=60,
        )
        assert done.returncode == 0, done.stderr
        assert "self-check OK" in done.stdout


class TestStaticCopyAllLanguages:
    """The static copy drives every language's real WebAssembly toolchain
    (section 5c of pages-live.js) instead of reporting NOT RUN for all but
    JavaScript/Python - while keeping the honest NOT RUN fallback for a
    deployment whose runtime files are missing."""

    @pytest.fixture(scope="class")
    def pages_live(self) -> str:
        return (REPO / "backend" / "static" / "js" / "pages-live.js").read_text(encoding="utf-8")

    def test_every_language_has_a_real_engine_wired(self, pages_live):
        # One worker per engine family, all loaded from same-origin files.
        for marker in (
            "ev-runtime-worker.js",   # Clang / TypeScript / SQLite / Go adapter
            "worker-java.js",         # OpenJDK javac + TeaVM
            "worker.iife.js",         # rustc/Miri toolchain worker
            "csharp-worker.js",       # Roslyn on Blazor WebAssembly
            "manifest.json",          # the deployment's runtime inventory
        ):
            assert marker in pages_live, marker
        # The terminal and the problem judge both route through the runtimes.
        assert "evRuntimeRun" in pages_live
        assert "EV_RUNTIME_LANGUAGES" in pages_live

    def test_honest_fallback_survives(self, pages_live):
        # No manifest entry -> the language is still reported not-executed.
        assert 'status: "unsupported_language"' in pages_live
        assert "executed: false" in pages_live
        assert "Your code was not executed" in pages_live
        assert "cannot run here" in pages_live
        # And nothing fabricates output for compiled languages.
        assert "matchedCase" not in pages_live

    def test_workers_are_independent_files_with_real_protocols(self):
        adapter = (REPO / "backend" / "static" / "js" / "ev-runtime-worker.js").read_text(encoding="utf-8")
        for marker in ("createCompiler", "createProgram", "initSqlJs", "go2jsCompile"):
            assert marker in adapter, marker
        csharp = (REPO / "backend" / "static" / "js" / "csharp-worker.js").read_text(encoding="utf-8")
        assert "BlazorRunner" in csharp

    def test_codelab_delegates_to_the_browser_terminal(self):
        codelab = (REPO / "backend" / "static" / "js" / "codelab.js").read_text(encoding="utf-8")
        assert "EV_BROWSER_TERMINAL" in codelab
        assert "manifest.json" in codelab

    def test_exporter_advertises_the_runtimes_url(self):
        sys.path.insert(0, str(REPO / "scripts"))
        import export_pages

        boot = export_pages.live_boot("/", [])
        assert '"runtimes"' in boot
