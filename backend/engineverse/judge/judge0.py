"""Client for a self-hosted Judge0-compatible API.

This map must never name a language outside ``KNOWN_LANGUAGES``. It used to
also forward PHP (68) and Kotlin (78): neither is in the taught runnable
catalogue, so no editor offered them, but a caller could still POST
``language="php"`` to /api/run and have PHP executed on the Judge0 host.
PHP is removed outright, not merely hidden - PHP2Shell (CVE-2026-109618 /
CVE-2026-109619, October 2026) is unauthenticated remote code execution in
the PHP runtime itself, and a runtime the platform does not even teach as
runnable has no business being reachable from an execution endpoint. The
facade in ``judge/__init__.py`` enforces the same allowlist again, so a
future provider cannot quietly widen the set of executable languages.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..config import get_settings
from . import KNOWN_LANGUAGES, RunResult

LANGUAGE_IDS = {
    "python": 71, "javascript": 63, "c": 50, "cpp": 54,
    "java": 62, "bash": 46, "csharp": 51, "go": 60, "rust": 73,
    "typescript": 74, "sql": 82, "ruby": 72,
}

STATUS_MAP = {
    "Accepted": "accepted",
    "Wrong Answer": "wrong_answer",
    "Time Limit Exceeded": "timeout",
    "Memory Limit Exceeded": "memory_limit",
    "Compilation Error": "compile_error",
}


class Judge0Provider:
    name = "judge0"

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.judge0_url.rstrip("/")
        self.api_key = settings.judge0_key

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    def supports(self, language: str) -> bool:
        return self.available and language in LANGUAGE_IDS and language in KNOWN_LANGUAGES

    def run(self, language: str, code: str, stdin: str = "", *, timeout_ms: int | None = None) -> RunResult:
        if not self.available:
            return RunResult(status="internal_error", stderr="ENGINEVERSE_JUDGE0_URL is not configured.")
        if language not in LANGUAGE_IDS or language not in KNOWN_LANGUAGES:
            # Refuse, never substitute. An unknown language used to fall back
            # to the Python id, which runs the submission as a different
            # language than the caller asked for - fail closed instead.
            return RunResult(
                status="unsupported_language",
                stderr=f'"{language}" is not available on the judge0 runner.',
            )
        settings = get_settings()
        timeout_ms = timeout_ms or settings.judge_timeout_ms
        body = json.dumps(
            {
                "language_id": LANGUAGE_IDS[language],
                "source_code": code,
                "stdin": stdin or "",
                "cpu_time_limit": min(10, timeout_ms / 1000),
                "memory_limit": settings.judge_memory_kb,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/submissions?base64_encoded=false&wait=true", data=body, headers=headers, method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=(timeout_ms + 8000) / 1000) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
            return RunResult(status="internal_error", stderr=f"Judge0 responded {exc.code}", runtime_ms=_ms(started))
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover
            return RunResult(status="internal_error", stderr=f"Judge0 unreachable: {exc}", runtime_ms=_ms(started))

        description = (payload.get("status") or {}).get("description", "")
        compile_output = (payload.get("compile_output") or "")[:65_536]
        return RunResult(
            status=STATUS_MAP.get(description, "runtime_error"),
            stdout=(payload.get("stdout") or "")[:65_536],
            stderr=(payload.get("stderr") or compile_output)[:65_536],
            compile_output=compile_output,
            exit_code=payload.get("exit_code"),
            runtime_ms=int(float(payload.get("time") or 0) * 1000),
            memory_kb=payload.get("memory"),
        )


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__ = ["Judge0Provider", "LANGUAGE_IDS"]
