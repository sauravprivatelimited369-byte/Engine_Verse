"""End-to-end acceptance tests for CodeLab — Online Compiler (/codelab & /api/execute)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from engineverse import codelab, judge, navigation
from engineverse.config import reload_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
_CAN_ISOLATE = bool(judge.provider_info().get("available"))
requires_sandbox = pytest.mark.skipif(
    not _CAN_ISOLATE,
    reason="host kernel blocks unprivileged user/network/PID/mount namespaces",
)


def _csrf_token(html_text: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text)
    assert match, "expected csrf-token meta tag on /codelab"
    return match.group(1)


def _post_execute(client, payload: dict, *, timeout_ms: int | None = None):
    page = client.get("/codelab")
    assert page.status_code == 200
    body = dict(payload)
    if timeout_ms is not None:
        body["timeoutMs"] = timeout_ms
    return client.post(
        "/api/execute",
        json=body,
        headers={"X-CSRF-Token": _csrf_token(page.text)},
    )


class TestCodeLabNavigationAndUI:
    def test_codelab_is_reachable_from_the_code_group_mobile_footer_and_manifest(self, client):
        """CodeLab is one menu deep, not a bar slot of its own.

        The top bar has a fixed budget (test_the_rendered_top_bar_is_grouped_not_flat
        caps it at seven entries) and the Adaptive Lab took the spare slot, so
        CodeLab moved into the Code group. What this test actually protects is
        that CodeLab stays findable without knowing its URL: it is the first
        entry in the Code menu, the mobile bar still claims /codelab for Code,
        it is still a PWA shortcut and it is still precached by the service
        worker. A bar slot was never the guarantee.
        """
        nav_items = navigation.primary_nav(signed_in=True)
        labels = [item.label for item in nav_items]
        assert "Code" in labels
        code = next(item for item in nav_items if item.label == "Code")
        listed = {child.path: child.label for child in code.children}
        assert listed.get("/codelab") == "CodeLab — Online Compiler"
        # /codelab now belongs to the Code group, so the breadcrumb reads
        # Home / Code / CodeLab and the mobile bar highlights Code.
        assert navigation.section_for("/codelab").key == "code"
        assert navigation.active_mobile("/codelab") == "Code"
        crumbs = [crumb.label for crumb in navigation.breadcrumb_trail("/codelab")]
        assert crumbs[-1] == "CodeLab — Online Compiler"

        page = client.get("/codelab")
        assert page.status_code == 200
        body = page.text
        assert "CodeLab — Online Compiler" in body
        assert 'id="cl-code-input"' in body
        assert 'id="cl-stdin-input"' in body
        assert 'id="cl-tab-output"' in body
        assert 'id="cl-tab-errors"' in body
        assert 'id="cl-tab-compilation"' in body
        assert 'id="cl-symbol-bar"' in body
        assert 'data-cl-mobile-tab="code"' in body
        assert 'data-cl-mobile-tab="stdin"' in body
        assert 'data-cl-mobile-tab="output"' in body

        manifest = client.get("/manifest.webmanifest").json()
        shortcut_urls = [s.get("url") for s in manifest.get("shortcuts", [])]
        assert "/codelab" in shortcut_urls

        sw_body = client.get("/sw.js").text
        assert "/static/css/codelab.css" in sw_body
        assert "/static/js/codelab.js" in sw_body

    def test_language_registry_honestly_filters_uninstalled_toolchains(self, client, monkeypatch):
        res = client.get("/api/codelab/languages")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        by_id = {entry["id"]: entry for entry in data["languages"]}
        for required in ("python", "java", "c", "cpp", "javascript"):
            assert required in by_id

        # When judge is disabled, NO language may claim to be executable.
        monkeypatch.setenv("ENGINEVERSE_JUDGE", "disabled")
        reload_settings()
        try:
            disabled_data = client.get("/api/codelab/languages").json()
            assert disabled_data["executable"] == []
            assert all(entry["available"] is False for entry in disabled_data["languages"])
            refused = _post_execute(client, {"language": "python", "sourceCode": "print(1)"})
            assert refused.status_code == 503
            body = refused.json()
            assert body["status"] == "service_unavailable"
            assert body["executed"] is False
        finally:
            monkeypatch.undo()
            reload_settings()

    @pytest.mark.skipif(not shutil.which("node"), reason="Node required for frontend JS contract check")
    def test_codelab_frontend_modules_format_and_highlight_cleanly(self):
        script = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const code = fs.readFileSync('backend/static/js/codelab.js', 'utf8');
const context = {
  window: {},
  document: { addEventListener: () => {}, querySelector: () => null, getElementById: () => null },
  localStorage: { getItem: () => null, setItem: () => {} },
  fetch: async () => ({ ok: false, status: 404, headers: { get: () => '' } }),
  URL,
  Blob: class {},
  Worker: class {},
  AbortController,
  console,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  performance,
};
vm.runInNewContext(code, context);
const api = context.window.EngineVerseCodeLab;
for (const key of ['LanguageRegistry', 'ExecutionService', 'LanguageSelector', 'CodeEditor', 'InputPanel', 'OutputConsole', 'CodeLabPage']) {
  if (typeof api[key] !== 'function') throw new Error('Missing module ' + key);
}
const messyC = '#include <stdio.h>\nint main(){\nif(1){\nprintf("ok");\n}\n}';
const formatted = api.formatSourceCode(messyC, { id: 'c', indentSize: 4, syntaxFamily: 'clike' });
if (!formatted.includes('    if(1){') || !formatted.includes('        printf("ok");')) {
  throw new Error('Formatter failed: ' + formatted);
}
const highlighted = api.highlightSource('public class Main { int x = 42; }', { syntaxFamily: 'clike', keywords: ['public', 'class', 'int'] });
if (!highlighted.includes('tok-kw') || !highlighted.includes('tok-num')) {
  throw new Error('Highlighter failed: ' + highlighted);
}
"""
        proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


@requires_sandbox
class TestRealLanguageExecution:
    def test_python_real_execution_and_stdin(self, client):
        if "python" not in judge.runnable_languages():
            pytest.skip("python3 not installed on host")
        res = _post_execute(
            client,
            {
                "language": "python",
                "sourceCode": "import sys\nx = int(sys.stdin.read().strip())\nprint('PY_OUT', x * x)",
                "stdin": "12\n",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["exitCode"] == 0
        assert body["stdout"].strip() == "PY_OUT 144"
        assert body["stderr"] == ""
        assert body["compileOutput"] == ""

    def test_java_real_javac_compile_and_jvm_execution(self, client):
        if "java" not in judge.runnable_languages():
            pytest.skip("JDK not installed on host")
        java_code = (
            "import java.util.Scanner;\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n"
            "        int n = sc.nextInt();\n"
            "        System.out.println(\"JAVA_OUT \" + (n * 3));\n"
            "    }\n"
            "}\n"
        )
        res = _post_execute(client, {"language": "java", "sourceCode": java_code, "stdin": "14\n"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["exitCode"] == 0
        assert body["stdout"].strip() == "JAVA_OUT 42"

    def test_c_real_gcc_compilation_and_binary_execution(self, client):
        if "c" not in judge.runnable_languages():
            pytest.skip("gcc not installed on host")
        c_code = (
            "#include <stdio.h>\n"
            "int main(void) {\n"
            "    int a = 0, b = 0;\n"
            "    scanf(\"%d %d\", &a, &b);\n"
            "    printf(\"C_OUT %d\\n\", a + b);\n"
            "    return 0;\n"
            "}\n"
        )
        res = _post_execute(client, {"language": "c", "sourceCode": c_code, "stdin": "19 23\n"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["exitCode"] == 0
        assert body["stdout"].strip() == "C_OUT 42"

    def test_cpp_real_gpp_compilation_and_binary_execution(self, client):
        if "cpp" not in judge.runnable_languages():
            pytest.skip("g++ not installed on host")
        cpp_code = (
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <numeric>\n"
            "int main() {\n"
            "    std::vector<int> v(3);\n"
            "    std::cin >> v[0] >> v[1] >> v[2];\n"
            "    std::cout << \"CPP_OUT \" << std::accumulate(v.begin(), v.end(), 0) << '\\n';\n"
            "    return 0;\n"
            "}\n"
        )
        res = _post_execute(client, {"language": "cpp", "sourceCode": cpp_code, "stdin": "10 12 20\n"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["exitCode"] == 0
        assert body["stdout"].strip() == "CPP_OUT 42"

    def test_javascript_real_node_execution(self, client):
        if "javascript" not in judge.runnable_languages():
            pytest.skip("node not installed on host")
        js_code = (
            "const fs = require('fs');\n"
            "const n = Number(fs.readFileSync(0, 'utf8').trim());\n"
            "console.log('JS_OUT', n * 7);\n"
        )
        res = _post_execute(client, {"language": "javascript", "sourceCode": js_code, "stdin": "6\n"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert "Node.js" in body["runtime"]
        assert body["stdout"].strip() == "JS_OUT 42"

    def test_cross_language_rejection_never_uses_wrong_runtime(self, client):
        runnable = set(judge.runnable_languages())
        if {"python", "java"} <= runnable:
            # Python source submitted in Java mode MUST fail javac compilation
            py_in_java = _post_execute(
                client,
                {"language": "java", "sourceCode": 'print("Hello from Python")\n'},
            ).json()
            assert py_in_java["status"] == "compilation_error"
            assert py_in_java["stdout"] == ""
            assert py_in_java["stderr"] == ""
            assert py_in_java["compileOutput"] != ""

            # Java source submitted in Python mode MUST fail Python compilation
            java_in_py = _post_execute(
                client,
                {
                    "language": "python",
                    "sourceCode": 'public class Main { public static void main(String[] args) { System.out.println("Hi"); } }\n',
                },
            ).json()
            assert java_in_py["status"] == "compilation_error"
            assert java_in_py["stdout"] == ""
            assert "SyntaxError" in java_in_py["compileOutput"]

    def test_compile_errors_vs_runtime_errors_are_distinct(self, client):
        if "c" in judge.runnable_languages():
            bad_c = _post_execute(
                client,
                {"language": "c", "sourceCode": "#include <stdio.h>\nint main(void) { missing_semicolon return 0; }\n"},
            ).json()
            assert bad_c["status"] == "compilation_error"
            assert bad_c["compileOutput"] != ""
            assert bad_c["stderr"] == ""
            assert "/tmp/evjudge-" not in bad_c["compileOutput"]

        if "java" in judge.runnable_languages():
            rt_java = _post_execute(
                client,
                {
                    "language": "java",
                    "sourceCode": (
                        "public class Main {\n"
                        "  public static void main(String[] args) {\n"
                        "    System.out.println(\"before_crash\");\n"
                        "    int boom = 1 / 0;\n"
                        "    System.out.println(boom);\n"
                        "  }\n"
                        "}\n"
                    ),
                },
            ).json()
            assert rt_java["status"] == "runtime_error"
            assert rt_java["compileOutput"] == ""
            assert "before_crash" in rt_java["stdout"]
            assert "ArithmeticException" in rt_java["stderr"]

    def test_empty_code_large_output_timeout_and_sandbox_isolation(self, client):
        empty = _post_execute(client, {"language": "python", "sourceCode": "   \n"}).json()
        assert empty["emptyCode"] is True
        assert empty["executed"] is False
        assert empty["stdout"] == ""

        oversized = _post_execute(client, {"language": "python", "sourceCode": "x = 1\n" * 20_000})
        assert oversized.status_code == 413

        flood = _post_execute(
            client,
            {"language": "python", "sourceCode": "print('A' * 200_000)"},
        ).json()
        assert len(flood["stdout"]) <= 65_536

        loop = _post_execute(
            client,
            {"language": "python", "sourceCode": "while True:\n    pass\n"},
            timeout_ms=1000,
        ).json()
        assert loop["status"] == "timeout"

        secret_probe = _post_execute(
            client,
            {
                "language": "python",
                "sourceCode": "import os\nprint(os.environ.get('ENGINEVERSE_SECRET', 'CLEAN'))\n",
            },
        ).json()
        assert secret_probe["stdout"].strip() == "CLEAN"


class TestCodeLabSnippetsAndAndroidBuild:
    def test_account_snippets_crud_and_isolation(self, signed_in, app):
        from starlette.testclient import TestClient

        page = signed_in.get("/codelab")
        token = _csrf_token(page.text)

        saved = signed_in.post(
            "/api/codelab/snippets",
            json={
                "title": "Binary Search Template",
                "language": "python",
                "sourceCode": "print('binary search')\n",
                "stdin": "7\n",
            },
            headers={"X-CSRF-Token": token},
        )
        assert saved.status_code == 200
        snippet_id = saved.json()["snippet"]["id"]

        listed = signed_in.get("/api/codelab/snippets").json()
        assert any(s["id"] == snippet_id for s in listed["snippets"])

        # Another signed-in student must NOT see or delete Asha's snippet.
        other = TestClient(app, raise_server_exceptions=False)
        login_html = other.get("/login").text
        m = re.search(r'name="csrf_token" value="([^"]+)"', login_html)
        other.post(
            "/login",
            data={"csrf_token": m.group(1), "identifier": "ravi@example.com", "password": "LearnBuild#2026!"},
            follow_redirects=False,
        )
        other_token = _csrf_token(other.get("/codelab").text)
        assert other.get("/api/codelab/snippets").json()["snippets"] == []
        forbid_del = other.delete(f"/api/codelab/snippets/{snippet_id}", headers={"X-CSRF-Token": other_token})
        assert forbid_del.status_code == 404

        deleted = signed_in.delete(f"/api/codelab/snippets/{snippet_id}", headers={"X-CSRF-Token": token})
        assert deleted.status_code == 200
        assert signed_in.get("/api/codelab/snippets").json()["snippets"] == []
