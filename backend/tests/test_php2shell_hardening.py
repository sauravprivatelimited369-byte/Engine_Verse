"""Regression tests for the October 2026 PHP2Shell response.

PHP2Shell (CVE-2026-109618 / CVE-2026-109619) is unauthenticated remote
code execution in the PHP runtime itself. EngineVerse is a Python
application and has never served PHP, so the CVEs cannot reach the site
directly - but the audit they triggered found four things worth pinning
down with tests:

* The Judge0 map forwarded PHP (and Kotlin) submissions even though
  neither language is offered anywhere, so ``POST /api/run`` with
  ``language="php"`` executed PHP on the judge host. Execution now goes
  through one allowlist (``judge.KNOWN_LANGUAGES``) enforced at the
  facade, in the Judge0 provider, and by the hosted-deployment gate.
* The Java sandbox bridge copied the server's whole environment (minus
  three names) into the JVM that compiles learner code. It now builds
  an allowlisted environment from nothing and always enables the JVM
  security policy.
* The toolchain installer provisioned .NET Core 3.1 + OpenSSL 1.1,
  both end-of-life and unpatchable, to run learner C#. End-of-life
  runtimes are refused everywhere instead.
* The local sandbox gained ``PR_SET_NO_NEW_PRIVS`` on top of its
  namespaces/rlimits/environment scrubbing.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from engineverse import judge
from engineverse.judge.judge0 import LANGUAGE_IDS, Judge0Provider
from engineverse.judge.local import LocalSandboxProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".toolchain"}


def _repo_files(suffix: str):
    for path in REPO_ROOT.rglob(f"*{suffix}"):
        if _SKIP_DIRS.isdisjoint(path.parts):
            yield path


# ---------------------------------------------------------------------------
# PHP: not present, not executable, not forwardable
# ---------------------------------------------------------------------------

class TestPhpCannotExecute:
    def test_the_repository_contains_no_php_at_all(self):
        offenders = [str(p.relative_to(REPO_ROOT)) for p in _repo_files(".php")]
        assert offenders == [], (
            "EngineVerse serves no PHP (that is the whole point of the "
            f"PHP2Shell response); found: {offenders}"
        )

    def test_judge0_map_is_exactly_the_allowlist(self):
        assert "php" not in LANGUAGE_IDS
        assert "kotlin" not in LANGUAGE_IDS
        assert set(LANGUAGE_IDS) == set(judge.KNOWN_LANGUAGES), (
            "the Judge0 map and KNOWN_LANGUAGES drifted apart: every "
            "executable language must be offered, taught and mapped, "
            "with no silent extras on either side"
        )

    def test_judge0_refuses_php_and_unknown_languages_without_a_network_call(self):
        provider = Judge0Provider()
        provider.base_url = "https://judge0.invalid"  # unroutable on purpose
        assert provider.supports("php") is False
        assert provider.supports("kotlin") is False
        assert provider.supports("python") is True
        # A refusal must come back, not an attempted request to .invalid -
        # and never the old behaviour of running it as Python (id 71).
        for language in ("php", "kotlin", "cobol"):
            result = provider.run(language, "whatever")
            assert result.status == "unsupported_language", (language, result)

    def test_hosted_gate_rejects_a_deployment_reporting_php_runnable(self):
        from scripts.verify_hosted_app import KNOWN_LANGUAGE_SLUGS

        assert "php" not in KNOWN_LANGUAGE_SLUGS
        assert set(KNOWN_LANGUAGE_SLUGS) == set(judge.KNOWN_LANGUAGES)


class _PermissiveProvider:
    """A provider that would run anything - the facade must not let it."""

    name = "permissive-test-double"
    available = True

    def __init__(self):
        self.ran: list[str] = []

    def supports(self, language: str) -> bool:
        return True

    def run(self, language, code, stdin="", *, timeout_ms=None):
        self.ran.append(language)
        return judge.RunResult(status="accepted", stdout="ran")


class TestFacadeAllowlist:
    @pytest.fixture
    def permissive(self, monkeypatch):
        provider = _PermissiveProvider()
        # The documented injection point: a provider with a None
        # fingerprint is trusted as injected (see resolve_provider).
        monkeypatch.setattr(judge, "_provider", provider)
        monkeypatch.setattr(judge, "_provider_fingerprint", None)
        return provider

    def test_run_custom_refuses_php_before_any_provider_is_asked(self, permissive):
        result = judge.run_custom("php", "<?php system($_GET['c']);")
        assert result.status == "unsupported_language"
        assert judge.executed(result.status) is False
        assert permissive.ran == [], "the provider was asked to run PHP"

    def test_evaluate_refuses_php_before_any_provider_is_asked(self, permissive):
        cases = [{"id": "1", "input": "", "expected": ""}]
        result = judge.evaluate("php", "<?php phpinfo();", cases)
        assert result.status == "unsupported_language"
        assert permissive.ran == []

    def test_allowlisted_language_still_reaches_the_provider(self, permissive):
        result = judge.run_custom("python", "print(1)")
        assert result.status == "accepted"
        assert permissive.ran == ["python"]


# ---------------------------------------------------------------------------
# Java bridge: no server secrets cross into the sandbox JVM
# ---------------------------------------------------------------------------

class TestJavaBridgeEnvironment:
    def test_only_an_allowlisted_environment_reaches_the_sandbox(self, tmp_path, monkeypatch):
        from engineverse.judge import java_bridge

        canaries = {
            "ENGINEVERSE_SECRET": "canary-secret",
            "ENGINEVERSE_DB_URL": "postgresql://canary",
            "ENGINEVERSE_JUDGE0_KEY": "canary-judge0-key",
            "ENGINEVERSE_AI_KEY": "canary-ai-key",
            "ENGINEVERSE_SMTP_URL": "smtps://user:canary-password@mail.invalid",
            "GITHUB_TOKEN": "canary-github-token",
        }
        for key, value in canaries.items():
            monkeypatch.setenv(key, value)

        jar = tmp_path / "sandbox.jar"
        jar.write_bytes(b"not a real jar; subprocess is stubbed")
        provider = java_bridge.JavaSandboxProvider()
        provider.java = "/usr/bin/java"
        provider.jar = jar

        captured: dict = {}

        def fake_run(argv, **kwargs):
            captured.update(kwargs)
            return subprocess.CompletedProcess(
                argv, 0, stdout=b'{"status": "accepted", "stdout": "ok"}', stderr=b""
            )

        monkeypatch.setattr(java_bridge.subprocess, "run", fake_run)
        result = provider.run("java", "public class Main {}")
        assert result.status == "accepted"

        env = captured["env"]
        allowed = {"PATH", "HOME", "LANG", "LC_ALL", "ENGINEVERSE_SANDBOX_POLICY", "JAVA_HOME"}
        assert set(env) <= allowed, f"unexpected variables reached the sandbox: {sorted(set(env) - allowed)}"
        for value in canaries.values():
            assert value not in env.values(), "a server secret leaked into the sandbox environment"
        # The JVM security policy (no sockets, workdir-only files) is on by
        # construction now, not by an operator remembering to opt in.
        assert env["ENGINEVERSE_SANDBOX_POLICY"] == "1"


# ---------------------------------------------------------------------------
# End-of-life runtimes stay removed
# ---------------------------------------------------------------------------

class TestNoEndOfLifeRuntimes:
    def test_toolchain_installer_never_provisions_dotnet_31_or_openssl_11(self):
        source = (REPO_ROOT / "scripts" / "setup_toolchains.py").read_text(encoding="utf-8")
        assert "install_dotnet_ssl_libs" not in source
        assert "dotnet-sdk-3.1-linux-x64@" not in source, "the EOL SDK download is back"
        assert "psycopg2-binary==2.9.9" not in source, "the OpenSSL 1.1 vendoring is back"
        assert "ssl11" not in source

    def test_local_judge_never_targets_dotnet_31(self):
        source = (REPO_ROOT / "backend/engineverse/judge/local.py").read_text(encoding="utf-8")
        assert '"ssl11"' not in source
        assert "LD_LIBRARY_PATH" not in source
        assert '"netcoreapp3.1"' not in source


# ---------------------------------------------------------------------------
# Whole-codebase guards
# ---------------------------------------------------------------------------

class TestNoShellExecutionOfInput:
    def test_no_shell_true_anywhere_in_application_code(self):
        pattern = re.compile(r"shell\s*=\s*True")
        offenders = []
        for base in ("backend", "scripts", "services", "seed_data"):
            for path in (REPO_ROOT / base).rglob("*.py"):
                if "tests" in path.parts or "__pycache__" in path.parts:
                    continue
                if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        assert offenders == [], f"shell=True reappeared in: {offenders}"


class TestDeploymentStaysSlimAndPatched:
    def test_web_image_ships_compilers_only_on_request(self):
        dockerfile = (REPO_ROOT / "deploy/Dockerfile.web").read_text(encoding="utf-8")
        assert "ARG INSTALL_JUDGE_TOOLCHAINS=0" in dockerfile, (
            "the production image must default to no compilers/JDK; the "
            "development judge opts in with --build-arg INSTALL_JUDGE_TOOLCHAINS=1"
        )
        guarded = [
            line for line in dockerfile.splitlines()
            if "apt-get install" in line and "INSTALL_JUDGE_TOOLCHAINS" in line
        ]
        assert guarded, "the toolchain install is no longer behind the build arg"

    def test_every_ecosystem_gets_automatic_update_prs(self):
        import yaml

        config = yaml.safe_load((REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
        ecosystems = {entry["package-ecosystem"] for entry in config["updates"]}
        # "docker" left with services/otp: the remaining Dockerfiles use
        # suffixed names Dependabot does not scan (see the note in the config).
        assert {"pip", "github-actions", "docker-compose", "gradle", "maven", "npm"} <= ecosystems
        for entry in config["updates"]:
            directory = REPO_ROOT / entry["directory"].lstrip("/")
            assert directory.is_dir(), f"{entry['package-ecosystem']}: {entry['directory']} does not exist"


# ---------------------------------------------------------------------------
# The sandbox itself: no_new_privs, scrubbed environment
# ---------------------------------------------------------------------------

_PROVIDER = LocalSandboxProvider()

requires_isolation = pytest.mark.skipif(
    not _PROVIDER.available,
    reason="host cannot create the required namespaces; the sandbox refuses "
           "to run submissions, so there is nothing to exercise",
)


@requires_isolation
class TestSandboxHardening:
    def test_submission_runs_with_no_new_privileges_and_no_server_environment(self):
        code = (
            "import os\n"
            "print('ENVKEYS:' + ','.join(sorted(os.environ)))\n"
            "print('SECRET:' + ('LEAKED' if os.environ.get('ENGINEVERSE_SECRET') else 'absent'))\n"
            "print([line.split(':')[1].strip() for line in open('/proc/self/status')\n"
            "       if line.startswith('NoNewPrivs')][0])\n"
        )
        result = _PROVIDER.run("python", code)
        assert result.status == "accepted", result.stderr
        lines = result.stdout.strip().splitlines()
        env_keys = set(lines[0].removeprefix("ENVKEYS:").split(","))
        allowed = {
            "HOME", "LANG", "LC_ALL", "PATH", "PWD", "TMPDIR",
            "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX",
        }
        assert env_keys <= allowed, f"unscrubbed variables in sandbox env: {sorted(env_keys - allowed)}"
        assert lines[1] == "SECRET:absent"
        assert lines[2] == "1", "PR_SET_NO_NEW_PRIVS is not in force for submissions"
