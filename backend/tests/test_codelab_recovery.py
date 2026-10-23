"""Regression tests for the CodeLab/compiler failure modes that made it look dead.

Four separate faults produced the same user-visible symptom - "the compiler is
not working at all, only one language runs" - and each one is pinned here so it
cannot come back:

1. ``app.js`` replaced ``window.EV`` wholesale, dropping ``EV.i18n`` (published
   by i18n.js, which loads first). i18n's own init then threw
   ``Cannot set properties of undefined (setting 'picker')`` on every page.
2. A rejected submission (expired CSRF token, expired session, a proxy's HTML
   error page) came back without a ``status`` field, so the console rendered
   "Idle" with three empty tabs and Run looked like a dead button. The client
   now normalises those bodies and retries once against ``GET /api/csrf``.
3. ``/compiler`` read its language list only from the seeded catalogue, so an
   unseeded database produced an empty drop-down and a permanently disabled
   Run. It now falls back to CodeLab's static registry.
4. A host with a working judge but few installed toolchains said only "limited
   runtimes", with no way to find out why or what to install.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engineverse import coding, db

REPO = Path(__file__).resolve().parents[2]
STATIC_JS = REPO / "backend" / "static" / "js"


def _csrf_token(html_text: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text)
    assert match, "expected csrf-token meta tag on /codelab"
    return match.group(1)


class TestCsrfRecovery:
    def test_csrf_endpoint_issues_a_usable_token_for_anonymous_callers(self, client):
        client.cookies.clear()
        issued = client.get("/api/csrf")
        assert issued.status_code == 200
        body = issued.json()
        assert body["ok"] is True
        assert body["header"] == "x-csrf-token"
        token = body["csrfToken"]
        assert len(token) == 97 and token.count(".") == 1
        # The endpoint must also hand out the cookie the token is signed
        # against, otherwise the very next POST is rejected.
        assert "ev_csrf" in client.cookies

        rejected = client.post(
            "/api/execute",
            json={"language": "python", "sourceCode": "print(1)"},
            headers={"X-CSRF-Token": "0" * 32 + "." + "0" * 64},
        )
        assert rejected.status_code == 403

    def test_csrf_rejection_carries_a_status_clients_can_render(self, client):
        rejected = client.post(
            "/api/execute",
            json={"language": "python", "sourceCode": "print(1)"},
            headers={"X-CSRF-Token": "0" * 32 + "." + "0" * 64},
        )
        assert rejected.status_code == 403
        body = rejected.json()
        # CodeLab reads status/stderr. A body with only `error` rendered as
        # "Idle" and three empty tabs, which is the "Run does nothing" report.
        assert body["status"] == "service_unavailable"
        assert body["stderr"]
        assert body["executed"] is False
        assert body["csrfTokenUrl"] == "/api/csrf"

    def test_page_token_still_authorises_a_run(self, client):
        # A host without an installed toolchain has no judge, and /api/execute
        # correctly answers 503 "Code execution is off". That is a different
        # guarantee (covered by TestToolchainDiagnostics), so skip rather than
        # report a CSRF regression that did not happen.
        if not coding.runnable_languages():
            pytest.skip("no runnable toolchain on this host; the judge is disabled")
        page = client.get("/codelab")
        token = _csrf_token(page.text)
        fresh = client.get("/api/csrf").json()["csrfToken"]
        assert fresh  # issuing another token must not invalidate the page's
        # (tokens are stateless MACs over the same subject)
        result = client.post(
            "/api/execute",
            json={"language": "python", "sourceCode": "print(11)"},
            headers={"X-CSRF-Token": token},
        )
        assert result.status_code == 200
        assert result.json()["status"] == "success"


class TestCompilerPageWithoutCatalogue:
    def test_compiler_page_still_lists_every_language_without_seed_data(self, client, monkeypatch):
        # Simulate an unseeded catalogue by emptying the catalogue query, not
        # the table: deleting rows would orphan every module/problem that
        # references a language and poison the rest of the session.
        monkeypatch.setattr(coding, "list_languages", lambda: [])

        rows = coding.terminal_languages()
        assert rows, "an unseeded catalogue must fall back to the static registry"
        slugs = [row["slug"] for row in rows]
        assert "python" in slugs and "java" in slugs and "cpp" in slugs
        # Availability still comes from the judge, never from the table.
        runnable = set(coding.runnable_languages())
        for row in rows:
            assert row["can_run"] == (row["judge_slug"] in runnable)
            assert row["code"].strip(), f"{row['slug']} must have a starter program"

        page = client.get("/compiler")
        assert page.status_code == 200
        assert page.text.count("<option") >= len(rows)
        # The banner is decided by the judge, not by the catalogue: a host with
        # no installed toolchain must say so, and only such a host may say it.
        if runnable:
            assert "Code execution is off" not in page.text
        else:
            assert "Code execution is off" in page.text


class TestToolchainDiagnostics:
    def test_registry_explains_every_disabled_language(self, client):
        payload = client.get("/api/codelab/languages").json()
        assert payload["ok"] is True
        disabled = [lang for lang in payload["languages"] if not lang["available"]]
        if payload["provider"]["available"]:
            for lang in disabled:
                assert lang.get("missingBinary"), f"{lang['id']} should name its missing binary"
                assert lang["installCommand"].endswith(lang["id"])
                assert lang["installCommand"].startswith("python3 scripts/setup_toolchains.py")
            expected = sorted(lang["id"] for lang in disabled)
            assert sorted(item["id"] for item in payload["missingToolchains"]) == expected
        else:
            # Nothing can run: the fix is the sandbox, not a toolchain.
            assert "namespace" in payload["provider"]["hint"].lower() or "judge0" in payload["provider"]["hint"].lower()

    def test_compiler_page_says_how_to_install_missing_compilers(self, client):
        page = client.get("/compiler")
        payload = client.get("/api/codelab/languages").json()
        if payload.get("toolchainHint"):
            assert "setup_toolchains.py" in page.text


class TestClientSideContract:
    """The JS fixes are behavioural, so assert the shipped source carries them."""

    def test_app_js_merges_into_the_shared_namespace(self):
        source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
        assert "window.EV = Object.assign(window.EV || {}, { api, toast, escapeHtml });" in source
        # The wholesale replacement is what broke i18n.
        assert "window.EV = { api, toast, escapeHtml };" not in source

    def test_codelab_js_normalises_and_retries(self):
        source = (STATIC_JS / "codelab.js").read_text(encoding="utf-8")
        assert 'fetch("/api/csrf"' in source
        assert "refreshCsrfToken" in source
        assert "_normalisePayload" in source
        assert "response.status === 403" in source

    def test_console_never_renders_a_blank_result(self):
        source = (STATIC_JS / "codelab.js").read_text(encoding="utf-8")
        assert 'result.status = result.error || result.message ? "service_unavailable" : "runtime_error";' in source
        assert "returned no output" in source


class TestContainerSizedSandbox:
    """Java used to "fail to compile" on a busy host for two reasons.

    Both were limits sized as if the sandbox were the only thing running:
    ``ulimit -u 32`` in the generated script (the JVM alone starts ~24 threads)
    and a javac JVM whose default 1 GB compressed-class-space reservation did
    not fit under the address-space cap. A learner saw "Compilation Error" for
    code that compiles perfectly.
    """

    def test_java_compile_pins_the_javac_jvm(self):
        from engineverse.judge.local import RUNNERS

        compile_argv = RUNNERS["java"]["compile"]
        assert "-J-Xmx256m" in compile_argv
        assert "-J-XX:CompressedClassSpaceSize=64m" in compile_argv
        assert compile_argv[-1] == "Main.java"

    def test_task_budget_is_measured_in_threads_not_processes(self):
        import os

        from engineverse.judge import local

        expected = 0
        if os.path.isdir("/proc"):
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/status", "rb") as handle:
                        owner, threads = None, 1
                        for line in handle:
                            if line.startswith(b"Uid:"):
                                owner = int(line.split()[1])
                            elif line.startswith(b"Threads:"):
                                threads = max(1, int(line.split()[1]))
                    if owner == os.getuid():
                        expected += threads
                except (OSError, ValueError, IndexError):
                    continue
        assert local._processes_for_uid(os.getuid()) == expected

    def test_generated_script_uses_the_computed_task_budget(self):
        source = (REPO / "backend" / "engineverse" / "judge" / "local.py").read_text(encoding="utf-8")
        # The literal 32 here was the bug: it overrode the measured budget.
        assert '"ulimit -u 32' not in source
        assert 'f"ulimit -u {nproc_budget}' in source
        assert "nproc_budget = _processes_for_uid(os.getuid()) + max_processes" in source
