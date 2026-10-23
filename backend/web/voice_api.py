"""Public voice API: ElevenLabs text-to-speech and Conversational AI sessions.

Mounted at ``/api/voice`` by ``main.create_app``.

These two endpoints are deliberately usable **without an account**. The public
GitHub Pages copy of EngineVerse has no sessions and no cookies, and a listening
feature that only works after signing in on a different origin would be
useless. What protects them instead:

* they are POST/GET only with a fixed upstream host chosen on the server;
* the text-to-speech endpoint requires ``Content-Type: application/json``, so a
  cross-site HTML form cannot reach it (a form cannot set that type without a
  CORS preflight, which the allow-list refuses);
* cross-origin requests are checked against ``ENGINEVERSE_VOICE_ORIGINS``;
* per-IP sliding-window limits (``RateLimitMiddleware``) and a hard character
  cap apply before any paid upstream call;
* no cookie is read, so there is no session for a CSRF token to protect.

The API key never leaves this process.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from engineverse import voice
from engineverse.security.audit import record
from engineverse.security.clientip import client_ip

from .deps import current_user

router = APIRouter()


def _fail(code: str, message: str, status: int, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"ok": False, "error": message, "code": code}
    body.update(extra)
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _voice_error(exc: voice.VoiceError) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "X-Voice-Error": exc.code}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        {"ok": False, "error": exc.message, "code": exc.code},
        status_code=exc.status,
        headers=headers,
    )


async def _json_body(request: Request) -> dict[str, Any] | None:
    """Reads a JSON object, refusing form posts.

    Refusing ``application/x-www-form-urlencoded`` is a security control, not a
    convenience: it is the one content type a foreign page can send without a
    preflight, so accepting it would make a paid endpoint forgeable cross-site.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return None
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


@router.get("/voice/status")
async def api_voice_status():
    """Safe feature availability for the reader and the tutor."""
    return JSONResponse(voice.status(), headers={"Cache-Control": "no-store"})


@router.post("/voice/speech")
async def api_voice_speech(request: Request):
    """Synthesises one bounded piece of educational text."""
    data = await _json_body(request)
    if data is None:
        return _fail("invalid_request", "Send a JSON object with the text to read.", 415)

    language = str(data.get("language") or "en").strip().lower()
    if language not in voice.LANGUAGES:
        return _fail("unsupported_language", "Only English and Hindi are configured for speech.", 422)
    voice_id = data.get("voiceId")
    if voice_id is not None and not isinstance(voice_id, str):
        return _fail("unsupported_voice", "That voice is not available on this server.", 422)

    viewer = current_user(request)
    try:
        audio, content_type = await voice.synthesize(data.get("text"), language, voice_id)
    except voice.VoiceError as exc:
        record(
            "voice.speech_failed",
            actor_id=viewer.id if viewer else None,
            ip=client_ip(request),
            meta={"code": exc.code, "language": language, "upstream_status": exc.status},
        )
        return _voice_error(exc)

    record(
        "voice.speech",
        actor_id=viewer.id if viewer else None,
        ip=client_ip(request),
        meta={
            "language": language,
            "chars": len(str(data.get("text") or "")),
            "bytes": len(audio),
        },
    )
    return Response(
        content=audio,
        media_type=content_type,
        headers={
            # Spoken audio is a transient artefact. Nothing here is stored on
            # the server, and the browser is told not to keep a disk copy.
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/voice/session")
async def api_voice_session(request: Request):
    """Returns a short-lived signed URL for a Conversational AI session."""
    data = await _json_body(request)
    if data is None:
        return _fail("invalid_request", "Send a JSON object with the reading language.", 415)
    language = str(data.get("language") or "en").strip().lower()
    if language not in voice.LANGUAGES:
        return _fail("unsupported_language", "Only English and Hindi are configured for speech.", 422)

    viewer = current_user(request)
    try:
        session = await voice.create_conversation_session(language)
    except voice.VoiceError as exc:
        record(
            "voice.session_failed",
            actor_id=viewer.id if viewer else None,
            ip=client_ip(request),
            meta={"code": exc.code, "language": language},
        )
        response = _voice_error(exc)
        if exc.code == "agent_not_configured":
            # The UI shows a setup panel instead of a raw error for this one.
            response.headers["X-Voice-Setup-Required"] = "1"
        return response

    record(
        "voice.session",
        actor_id=viewer.id if viewer else None,
        ip=client_ip(request),
        meta={"language": language},
    )
    return JSONResponse(
        {"ok": True, **session},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
