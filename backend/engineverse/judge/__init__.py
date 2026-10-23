"""Code execution facade (spec §17, §71).

The web server NEVER interprets user code in-process. Three interchangeable
providers exist and are selected by ``ENGINEVERSE_JUDGE``:

``java``    the Java sandbox service in ``sandbox-java/`` (a separate JVM
            process per submission, with a SecurityManager-style policy,
            thread/CPU/memory caps and no network).
``python``  the built-in runner: a fresh OS process per submission inside a
            new network+user namespace (``unshare -rn``), with rlimits and a
            wall-clock kill.
``judge0``  forwards to a self-hosted Judge0 API. Isolation is whatever that
            host provides; this process does not verify it.
``disabled`` refuses every submission. This is the production default.
``auto``    the built-in runner for the whole catalogue (including java),
            with the Java sandbox service as a java-only fallback. Refused
            in production: it executes code on this host.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..config import get_settings

MAX_OUTPUT = 65_536

# Every language the platform offers. Whether one is actually runnable depends on
# the host toolchain; `runnable_languages()` answers that at runtime. This list
# covers the whole taught catalogue (seed_data LANGUAGES, including C# and SQL -
# both were missing here, which silently kept them un-runnable even on a Judge0
# host that maps them) plus the shell/script extras the local judge has always
# been able to run.
#
# This tuple is also the security allowlist for code execution: `run_custom`
# and `evaluate` refuse anything outside it before a provider is even asked,
# so no provider (present or future) can widen what an execution endpoint
# will run. PHP is deliberately absent. The site itself is Python and has
# never served PHP, so PHP2Shell (CVE-2026-109618 / CVE-2026-109619) cannot
# reach it directly - but the Judge0 map used to forward PHP submissions to
# the judge host, which put an untaught, unneeded runtime one API call away
# from any signed-in learner. Teaching *about* a language in lesson text is
# unrelated; executing it is what this list governs.
KNOWN_LANGUAGES = (
    "python", "java", "javascript", "typescript", "cpp", "c", "go", "rust",
    "csharp", "sql", "bash", "ruby",
)

STATUSES = (
    "accepted", "wrong_answer", "runtime_error", "timeout",
    "compile_error", "memory_limit", "unsupported_language",
    "sandbox_unavailable", "internal_error",
)

#: Verdicts that mean the submission never executed: no test ran, so there is
#: no pass/fail signal. Anything that consumes a verdict must treat these as
#: "not run" - no XP, no attempt/solve counts, and no result presented as if
#: the code had been graded.
NOT_EXECUTED_STATUSES = frozenset({
    "unsupported_language", "sandbox_unavailable", "internal_error",
})


def executed(status: str) -> bool:
    """Whether ``status`` describes code that actually ran."""
    return status not in NOT_EXECUTED_STATUSES


@dataclass
class RunResult:
    status: str
    stdout: str = ""
    stderr: str = ""
    compile_output: str = ""
    exit_code: int | None = None
    runtime_ms: int = 0
    memory_kb: int | None = None


@dataclass
class CaseOutcome:
    id: str
    input: str
    expected: str
    actual: str
    passed: bool
    runtime_ms: int
    is_sample: bool = False
    explanation: str | None = None


@dataclass
class Evaluation:
    status: str
    passed: int = 0
    total: int = 0
    runtime_ms: int = 0
    memory_kb: int | None = None
    stderr: str = ""
    cases: list[CaseOutcome] = field(default_factory=list)


class Provider(Protocol):
    name: str

    def supports(self, language: str) -> bool: ...

    def run(self, language: str, code: str, stdin: str = "", *, timeout_ms: int | None = None) -> RunResult: ...


class CompositeProvider:
    """Local sandbox for the full catalogue, with a language-scoped fallback.

    ``LocalSandboxProvider`` answers for every catalogue language; the Java
    sandbox service (``JavaSandboxProvider``) speaks *only* java. Auto mode
    used to swap the whole provider for the Java one whenever it was
    available, which silently broke every non-java language. This routes each
    submission to the local sandbox first and lets unsupported languages fall
    through to the scoped fallback only where that fallback actually speaks
    them - never letting one provider answer for another's languages.
    """

    def __init__(self, primary: Provider, fallback: Provider | None = None, fallback_languages: tuple[str, ...] = ("java",)):
        self.primary = primary
        self.fallback = fallback
        self.fallback_languages = tuple(fallback_languages)

    @property
    def name(self) -> str:
        # Report as the primary provider: composite routing is an
        # implementation detail, and consumers gate features (runtime
        # versions, isolation claims) on the provider that actually runs code.
        return self.primary.name

    @property
    def available(self) -> bool:
        return bool(getattr(self.primary, "available", False) or getattr(self.fallback, "available", False))

    def supports(self, language: str) -> bool:
        if self.primary.supports(language):
            return True
        return bool(
            self.fallback is not None
            and language in self.fallback_languages
            and self.fallback.supports(language)
        )

    def run(self, language: str, code: str, stdin: str = "", *, timeout_ms: int | None = None) -> RunResult:
        if self.primary.supports(language):
            return self.primary.run(language, code, stdin, timeout_ms=timeout_ms)
        if self.fallback is not None and language in self.fallback_languages and self.fallback.supports(language):
            return self.fallback.run(language, code, stdin, timeout_ms=timeout_ms)
        # Let the primary produce its standard refusal (unsupported language
        # or unisolated host) so the message stays the operator-relevant one.
        return self.primary.run(language, code, stdin, timeout_ms=timeout_ms)

    def __getattr__(self, item: str):
        # Isolation probes (_have_namespace, ...) live on the primary; surface
        # them so provider_info() keeps reporting what this host enforces.
        return getattr(self.primary, item)


class DisabledProvider:
    """Refuses every submission.

    Production uses this unless the operator has pointed ``ENGINEVERSE_JUDGE``
    at a separately deployed Judge0. A subprocess runner in this container is
    not a second machine, so the safe default is to run nothing.
    """

    name = "disabled"
    available = False

    def supports(self, language: str) -> bool:
        return False

    def run(self, language: str, code: str, stdin: str = "", *, timeout_ms: int | None = None) -> RunResult:
        return RunResult(
            status="unsupported_language",
            stderr=(
                "Code execution is disabled on this server. Submitted code is not run here. "
                "An administrator can point ENGINEVERSE_JUDGE at a separately deployed Judge0 "
                "instance; this process will not execute it locally."
            ),
        )


_provider: Provider | None = None
_provider_fingerprint: tuple | None = None


def _settings_fingerprint(settings) -> tuple:
    """The settings fields that decide which provider is correct.

    The cache used to be process-lifetime unconditionally, so after a
    settings reload (tests do this routinely; an operator SIGHUP-style
    reload would too) the process kept serving the *old* provider - for
    example refusing every submission as "disabled" long after the judge
    had been re-enabled, with ``provider_info()`` computed at import time
    saying the opposite. Keying the cache on the fields that matter makes
    a reload actually take effect, without re-probing namespaces on every
    submission while the configuration is unchanged.
    """
    return (
        (settings.judge or "auto").lower(),
        settings.judge0_url.strip(),
        bool(settings.is_production),
        settings.java_sandbox_jar,
        settings.java_home,
    )


def resolve_provider() -> Provider:
    """Picks a provider, caching the decision while settings are unchanged.

    In production, ``auto``, ``python`` and ``java`` resolve to the disabled
    provider even if startup validation was bypassed. Failing open would run
    learner code on the web server.
    """
    global _provider, _provider_fingerprint
    settings = get_settings()
    fingerprint = _settings_fingerprint(settings)
    # A None fingerprint with a provider present means the provider was
    # injected directly (tests do this); trust it rather than rebuilding.
    if _provider is not None and _provider_fingerprint in (None, fingerprint):
        return _provider
    _provider_fingerprint = fingerprint
    choice = (settings.judge or "auto").lower()
    local = choice in {"", "auto", "python", "java", "local"}
    if choice == "disabled" or (settings.is_production and local):
        _provider = DisabledProvider()
    elif choice == "judge0":
        if settings.is_production and not settings.judge0_url.strip():
            _provider = DisabledProvider()
        else:
            from .judge0 import Judge0Provider

            _provider = Judge0Provider()
    elif choice == "java":
        from .java_bridge import JavaSandboxProvider

        _provider = JavaSandboxProvider()
    elif choice == "python":
        from .local import LocalSandboxProvider

        _provider = LocalSandboxProvider()
    else:  # auto, development and test only
        from .java_bridge import JavaSandboxProvider
        from .local import LocalSandboxProvider

        # Local sandbox first for every language (including java - the local
        # runner has a real javac on modern JDKs); the Java sandbox service is
        # only a java-scoped fallback for hosts where the local run lacks java.
        _provider = CompositeProvider(LocalSandboxProvider(), JavaSandboxProvider())
    return _provider


def reset_provider() -> None:
    global _provider, _provider_fingerprint
    _provider = None
    _provider_fingerprint = None


def provider_info() -> dict:
    """Describes the active provider, including what it actually isolates.

    Reporting only the name invites an operator to assume a hard boundary. The
    containment flags come from the provider itself so they reflect the host
    rather than what the code hopes for - a kernel with unprivileged user
    namespaces disabled simply reports fewer guarantees.
    """
    provider = resolve_provider()
    info: dict = {"name": provider.name, "available": getattr(provider, "available", True)}
    for flag in ("_have_namespace", "_have_pid_ns", "_have_mount_ns"):
        if hasattr(provider, flag):
            info[flag.lstrip("_")] = bool(getattr(provider, flag))
    if hasattr(provider, "_have_namespace"):
        info["network_isolated"] = bool(provider._have_namespace)
        info["pid_isolated"] = bool(getattr(provider, "_have_pid_ns", False))
        info["filesystem_isolated"] = bool(getattr(provider, "_have_mount_ns", False))
    if provider.name == "disabled":
        info["runs_on_this_server"] = False
        info["isolation"] = "execution refused; this process does not run submitted code"
    elif provider.name == "judge0":
        info["runs_on_this_server"] = False
        info["isolation_verified"] = False
        info["isolation"] = (
            "delegated to ENGINEVERSE_JUDGE0_URL; this process does not verify that host's isolation"
        )
    else:
        can_run_here = bool(info["available"])
        info["runs_on_this_server"] = can_run_here
        if can_run_here:
            info["isolation"] = "subprocess on this host; not a separate container"
        else:
            info["isolation"] = "execution refused; required local isolation is unavailable"
    return info


def runnable_languages() -> list[str]:
    """Languages the active provider can actually execute right now.

    The UI uses this to disable (never silently accept) languages whose toolchain
    is missing on this host, so a student is never told their Java submission was
    "submitted" when no JVM exists.
    """
    provider = resolve_provider()
    return [lang for lang in KNOWN_LANGUAGES if provider.supports(lang)]


def as_dict(result) -> dict:
    """Serialises a RunResult or Evaluation (and its nested cases) for JSON."""
    from dataclasses import asdict, is_dataclass

    if not is_dataclass(result):
        return dict(result)
    payload = asdict(result)
    if "cases" in payload:
        payload["cases"] = [asdict(case) if is_dataclass(case) else dict(case) for case in result.cases]
    return payload


def run_custom(
    language: str,
    code: str,
    stdin: str = "",
    *,
    timeout_ms: int | None = None,
) -> RunResult:
    if language not in KNOWN_LANGUAGES:
        # The allowlist is enforced here, at the facade every caller goes
        # through, not only inside each provider's supports(). A provider
        # that (again) maps a language the platform does not offer - PHP was
        # reachable this way through Judge0 - must not make it executable.
        return RunResult(
            status="unsupported_language",
            stderr=f'"{language}" is not a language this platform runs.',
        )
    provider = resolve_provider()
    if provider.name == "disabled":
        return provider.run(language, code, stdin, timeout_ms=timeout_ms)
    if not provider.supports(language):
        return RunResult(
            status="unsupported_language",
            stderr=f'"{language}" is not available on the {provider.name} runner.',
        )
    return provider.run(language, code, stdin, timeout_ms=timeout_ms)


def normalise_output(value: str) -> str:
    """Trailing-whitespace/newline insensitive comparison form."""
    lines = (value or "").replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")


def outputs_match(actual: str, expected: str) -> bool:
    return normalise_output(actual) == normalise_output(expected)


def evaluate(language: str, code: str, cases: list[dict], *, stop_on_compile_error: bool = True) -> Evaluation:
    """Runs the submission against every test case."""
    if language not in KNOWN_LANGUAGES:
        # Same facade allowlist as run_custom: never let a provider decide
        # alone which languages are executable.
        return Evaluation(
            status="unsupported_language",
            total=len(cases),
            stderr=f'"{language}" is not a language this platform runs.',
        )
    provider = resolve_provider()
    if not provider.supports(language):
        probe = provider.run(language, "", "")
        return Evaluation(
            status=probe.status if probe.status in ("unsupported_language", "internal_error") else "internal_error",
            total=len(cases),
            stderr=probe.stderr,
        )

    outcomes: list[CaseOutcome] = []
    total_ms = 0
    hard_failure: str | None = None

    for case in cases:
        result = provider.run(language, code, case.get("input", ""))
        total_ms += result.runtime_ms
        if result.status != "accepted":
            hard_failure = result.status
            outcomes.append(
                CaseOutcome(
                    id=case.get("id", ""),
                    input=case.get("input", ""),
                    expected=case.get("expected", ""),
                    actual=result.stderr or result.stdout,
                    passed=False,
                    runtime_ms=result.runtime_ms,
                    is_sample=bool(case.get("is_sample")),
                    explanation=case.get("explanation"),
                )
            )
            if stop_on_compile_error and result.status in ("compile_error", "internal_error", "unsupported_language"):
                break
            continue
        passed = outputs_match(result.stdout, case.get("expected", ""))
        outcomes.append(
            CaseOutcome(
                id=case.get("id", ""),
                input=case.get("input", ""),
                expected=case.get("expected", ""),
                actual=result.stdout,
                passed=passed,
                runtime_ms=result.runtime_ms,
                is_sample=bool(case.get("is_sample")),
                explanation=case.get("explanation"),
            )
        )
        if not passed and hard_failure is None:
            hard_failure = "wrong_answer"

    passed_count = sum(1 for o in outcomes if o.passed)
    status = hard_failure or ("accepted" if passed_count == len(cases) and cases else "wrong_answer")
    return Evaluation(
        status=status,
        passed=passed_count,
        total=len(cases),
        runtime_ms=total_ms,
        stderr=next((o.actual for o in outcomes if not o.passed), ""),
        cases=outcomes,
    )
