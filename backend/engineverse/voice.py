"""ElevenLabs voice integration for EngineVerse.

Two independent capabilities share one server-side module:

* **Voice reader** - turns educational text into speech through the ElevenLabs
  text-to-speech API. The browser never sees the API key: it posts text to this
  application, which makes the upstream request and returns ``audio/mpeg``.
* **Voice tutor** - asks ElevenLabs Conversational AI for a short-lived signed
  WebSocket URL. The browser then talks to ElevenLabs directly using that URL;
  the long-lived API key stays on the server.

Everything here is opt-in. With ``ENGINEVERSE_ELEVENLABS_ENABLED`` unset, or
with no API key configured, the module reports an honest "not configured"
status and no upstream request is ever made. Nothing in the rest of EngineVerse
depends on this module: a failure here degrades to the written notes.

Security notes
--------------
* The API key is only ever placed in an ``xi-api-key`` request header to the
  ElevenLabs host. It is never logged, returned to a caller, or included in an
  error message.
* Upstream response bodies are never echoed to the client; only a short,
  fixed message per failure class is returned.
* Requests are bounded by the configured character limit and a per-IP rate
  limit in ``main.py``. Spoken text is not stored anywhere.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any
from urllib.parse import quote

import httpx

from .config import get_settings

#: The only ElevenLabs host this process may contact. The browser never
#: supplies a URL; the path is fixed here so a caller cannot proxy arbitrary
#: requests through the application's credentials.
API_BASE = "https://api.elevenlabs.io"

TTS_PATH = "/v1/text-to-speech/{voice_id}"
#: ElevenLabs has shipped the signed-URL endpoint under a hyphenated and an
#: underscored name. Both are fixed server-side paths; the second is tried only
#: when the first answers 404, so a rename upstream is a one-line fix rather
#: than an outage. The browser can never choose the path.
SIGNED_URL_PATHS = (
    "/v1/convai/conversation/get-signed-url",
    "/v1/convai/conversation/get_signed_url",
)

#: Models that can speak both English and Hindi. The operator may override
#: with ELEVENLABS_TTS_MODEL_ID; an unknown model is rejected upstream and
#: reported as a configuration error rather than silently ignored.
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

#: Output format requested from ElevenLabs. MP3 is playable by every browser
#: that EngineVerse supports and by the Android WebView.
OUTPUT_FORMAT = "mp3_44100_128"

LANGUAGES = ("en", "hi")
LANGUAGE_LABELS = {"en": "English", "hi": "Hindi"}

#: Hard ceiling on the text accepted by one request. The configured limit may
#: be lower, never higher: the browser splits long articles into chunks.
HARD_MAX_CHARS = 3000

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FENCE_RE = re.compile(r"```.*?```", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")
_BLANKS_RE = re.compile(r"\n{3,}")


class VoiceError(Exception):
    """A failure that is safe to show the caller.

    ``code`` is stable and machine-readable, ``message`` is written for a
    student, and neither contains upstream body text or credentials.
    """

    def __init__(self, code: str, message: str, status: int = 502, *, retry_after: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def enabled() -> bool:
    return get_settings().elevenlabs_enabled


def max_chars() -> int:
    limit = get_settings().voice_max_chars
    return max(200, min(HARD_MAX_CHARS, int(limit)))


def _split_list(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _voice_ids(language: str) -> list[str]:
    settings = get_settings()
    raw = settings.elevenlabs_voice_id_hi if language == "hi" else settings.elevenlabs_voice_id_en
    return _split_list(raw)


def _voice_names(language: str) -> list[str]:
    settings = get_settings()
    raw = settings.elevenlabs_voice_name_hi if language == "hi" else settings.elevenlabs_voice_name_en
    return _split_list(raw)


def voices_for(language: str) -> list[dict[str, str]]:
    """The approved voices for one language, as ``{"id", "name"}``.

    A voice ID that is configured is by definition permitted; there is no
    way for a caller to name any other ID, because ``resolve_voice`` refuses
    anything not in this list.
    """
    if language not in LANGUAGES:
        return []
    ids = _voice_ids(language)
    names = _voice_names(language)
    out: list[dict[str, str]] = []
    for index, voice_id in enumerate(ids):
        name = names[index] if index < len(names) else f"{LANGUAGE_LABELS[language]} voice {index + 1}"
        out.append({"id": voice_id, "name": name})
    return out


def resolve_voice(language: str, voice_id: str | None) -> str:
    """Validates the requested voice against the server-side allow list."""
    if language not in LANGUAGES:
        raise VoiceError("unsupported_language", "Only English and Hindi are configured for speech.", 422)
    allowed = voices_for(language)
    if not allowed:
        raise VoiceError("voice_not_configured", f"No {LANGUAGE_LABELS[language]} voice is configured on this server.", 503)
    if not voice_id:
        return allowed[0]["id"]
    for voice in allowed:
        if voice["id"] == voice_id:
            return voice_id
    raise VoiceError("unsupported_voice", "That voice is not available on this server.", 422)


def language_available(language: str) -> bool:
    return language in LANGUAGES and bool(_voice_ids(language))


def status() -> dict[str, Any]:
    """Public, secret-free description of the feature.

    This is safe to serve to anonymous visitors: it names languages, voice
    labels, the character limit and whether each capability can run. It never
    contains the API key, the agent ID or a signed URL.
    """
    settings = get_settings()
    configured = enabled() and bool(settings.elevenlabs_api_key.strip())
    languages = []
    for code in LANGUAGES:
        voices = voices_for(code)
        if voices:
            languages.append({"code": code, "label": LANGUAGE_LABELS[code], "voices": voices})
    tts_available = configured and bool(languages)
    agent_configured = bool(settings.elevenlabs_agent_id.strip())
    conversation_available = configured and agent_configured

    reason = ""
    if not enabled():
        reason = "The voice features are switched off on this server."
    elif not settings.elevenlabs_api_key.strip():
        reason = "The server has no ElevenLabs API key configured."
    elif not languages:
        reason = "No English or Hindi voice is configured on this server."

    return {
        "enabled": enabled(),
        "configured": configured,
        "reason": reason,
        "tts": {
            "available": tts_available,
            "languages": languages,
            "maxChars": max_chars(),
            "defaultLanguage": "en" if language_available("en") else (languages[0]["code"] if languages else "en"),
        },
        "conversation": {
            "available": conversation_available,
            "agentConfigured": agent_configured,
            "reason": (
                ""
                if conversation_available
                else (
                    "The server has no ElevenLabs agent configured."
                    if configured
                    else reason or "Voice conversations are not configured."
                )
            ),
        },
    }


# ---------------------------------------------------------------------------
# Text preparation for speech
# ---------------------------------------------------------------------------

#: Letters used as physical quantities in the notes. Expanded only inside a
#: formula-shaped expression (see ``_speak_math``), never in ordinary prose,
#: because "V" can be volume and "P" can be pressure depending on the subject.
SYMBOL_WORDS = {
    "V": "voltage", "I": "current", "R": "resistance", "P": "power", "F": "force",
    "m": "mass", "a": "acceleration", "E": "energy", "c": "speed of light",
    "T": "temperature", "Q": "charge", "C": "capacitance", "L": "inductance",
    "B": "magnetic flux density", "U": "internal energy", "S": "entropy",
    "A": "area", "d": "distance", "t": "time", "v": "velocity", "f": "frequency",
    "g": "acceleration due to gravity", "k": "spring constant", "n": "number of moles",
    "W": "work", "Z": "impedance", "G": "conductance", "H": "magnetic field strength",
}

#: Units and abbreviations that must not be read letter by letter.
UNIT_WORDS = {
    "kg": "kilograms", "km": "kilometres", "cm": "centimetres", "mm": "millimetres",
    "nm": "nanometres", "ms": "milliseconds", "kPa": "kilopascals", "MPa": "megapascals",
    "GPa": "gigapascals", "kHz": "kilohertz", "MHz": "megahertz", "GHz": "gigahertz",
    "mA": "milliamps", "kWh": "kilowatt hours", "rpm": "revolutions per minute",
    "Hz": "hertz", "Pa": "pascals", "Nm": "newton metres", "kJ": "kilojoules",
    "mol": "moles", "rad": "radians", "dB": "decibels", "ft": "feet",
    # Lower-case metre and second only appear in a formula context here, and
    # "2 m" must not be read as "two mass".
    "m": "metres", "s": "seconds",
}

#: Whole-unit expressions, longest first so "m/s" wins over "m".
UNIT_PHRASES = {
    "km/h": "kilometres per hour",
    "m/s^2": "metres per second squared",
    "m/s": "metres per second",
    "N/m^2": "newtons per square metre",
    "N·m": "newton metres",
    "°C": "degrees Celsius",
    "°F": "degrees Fahrenheit",
    "K": "kelvin",
}

ABBREVIATIONS = {
    "e.g.": "for example", "i.e.": "that is", "etc.": "and so on",
    "vs.": "versus", "approx.": "approximately", "ca.": "approximately",
    "Fig.": "figure", "Eq.": "equation", "Ref.": "reference",
    "AC": "alternating current", "DC": "direct current",
    "RMS": "root mean square", "CPU": "C P U", "GPU": "G P U",
    "API": "A P I", "SQL": "sequel", "HTTP": "H T T P", "HTTPS": "H T T P S",
}

_OPERATORS = {
    "=": " equals ",
    "≈": " approximately equals ",
    "≅": " is approximately equal to ",
    "≠": " is not equal to ",
    "≤": " is less than or equal to ",
    "≥": " is greater than or equal to ",
    "<": " is less than ",
    ">": " is greater than ",
    "±": " plus or minus ",
    "×": " multiplied by ",
    "·": " multiplied by ",
    "÷": " divided by ",
    "→": " gives ",
    "⇒": " implies ",
    "⟹": " implies ",
    "∑": " the sum of ",
    "∏": " the product of ",
    "∫": " the integral of ",
    "∂": " partial ",
    "√": " square root of ",
    "∞": " infinity ",
    "π": " pi ",
    "Ω": " ohms ",
    "Δ": " delta ",
    "µ": " micro ",
    "μ": " micro ",
    "°": " degrees ",
    "%": " per cent ",
    "&": " and ",
}

_SUPERSCRIPT = {"²": " squared", "³": " cubed", "⁻¹": " to the power minus one"}
_EXPR_CHARS = re.compile(r"^[A-Za-z0-9\s+\-*/^().,=<>±×÷·%π√≈≤≥²³_°ΩμµΔ]*$")
_COMMON_WORDS = frozenset("""
a an and are as at be been but by can for from had has have if in into is it its of on or
so than that the then there these they this to too was were when where which while with would
you your not no all any each more most some such only just also very will may might must should
""".split())

#: A symbol that spelled-out context contradicts. "Pressure P = F/A" must not be
#: read as "pressure power equals...", so the letter is left as a letter when
#: the word just before it names a different quantity.
_ALT_MEANINGS = {
    "P": {"pressure", "period", "momentum", "pitch"},
    "T": {"torque", "period", "tension", "thrust"},
    "V": {"volume", "velocity"},
    "A": {"ampere", "amperes", "amplitude"},
    "C": {"coulomb", "coulombs", "concentration"},
    "S": {"siemens"},
    "H": {"henry", "henries"},
    "W": {"watt", "watts", "weight"},
    "G": {"gauge"},
    "U": {"potential"},
    "E": {"electric", "electric field", "young"},
}


def _strip_markup(text: str) -> str:
    """Removes code fences and HTML while keeping reading order."""
    text = _FENCE_RE.sub(" ", text or "")
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("**", "").replace("__", "").replace("==", "")
    return text


def _is_math_token(token: str) -> bool:
    """A whitespace-delimited token that can belong to a formula.

    Tokens with a real English word in them ("Pressure", "equivalence") break
    the run, which is what stops a sentence containing "=" from being read as
    one long equation.
    """
    if not token or token in _COMMON_WORDS:
        return False
    if not _EXPR_CHARS.match(token):
        return False
    return all(len(word) <= 3 for word in re.findall(r"[A-Za-z]+", token))


def _speak_expression(expression: str, context: str = "") -> str:
    """Reads ``V = IR`` as "voltage equals current multiplied by resistance".

    Only called for a run of formula-shaped tokens (it contains a relation such
    as ``=``). A run of one to three letters is expanded when every letter in it
    is a known quantity; otherwise the run is left alone so an unfamiliar symbol
    is spoken as written rather than guessed at.
    """
    previous_word = ""
    match = re.search(r"([A-Za-z]+)\s*$", context)
    if match:
        previous_word = match.group(1).lower()

    def run(match: re.Match[str]) -> str:
        word = match.group(0)
        if word in UNIT_WORDS:
            return f" {UNIT_WORDS[word]} "
        if word in UNIT_PHRASES:
            return f" {UNIT_PHRASES[word]} "
        if word in ABBREVIATIONS:
            return f" {ABBREVIATIONS[word]} "
        if word.lower() in _COMMON_WORDS and word.islower():
            return match.group(0)  # "a" / "an" / "the", not the symbol "A"
        if all(letter in SYMBOL_WORDS for letter in word):
            if len(word) == 1:
                if previous_word == SYMBOL_WORDS[word].lower():
                    return " "  # "...the power P = ..." would repeat the word
                if previous_word in _ALT_MEANINGS.get(word, set()):
                    return word  # the surrounding words already name the quantity
            return " " + " multiplied by ".join(SYMBOL_WORDS[letter] for letter in word) + " "
        return match.group(0)

    spoken = re.sub(r"[A-Za-z]{1,3}", run, expression)
    spoken = re.sub(r"\^2\b", " squared", spoken)
    spoken = re.sub(r"\^3\b", " cubed", spoken)
    spoken = re.sub(r"\^([A-Za-z0-9]+)", r" to the power \1", spoken)
    spoken = re.sub(r"\s*/\s*", " divided by ", spoken)
    spoken = re.sub(r"\s*\*\s*", " multiplied by ", spoken)
    spoken = re.sub(r"\s*\+\s*", " plus ", spoken)
    spoken = re.sub(r"\s+-\s+", " minus ", spoken)
    return spoken


#: A capital letter directly after a number is a unit, not a variable.
_UNIT_AFTER_NUMBER = {
    "V": "volts", "A": "amps", "W": "watts", "N": "newtons", "J": "joules",
    "Hz": "hertz", "Pa": "pascals", "F": "farads", "H": "henries", "T": "teslas",
    "S": "siemens", "C": "coulombs",
    "kg": "kilograms", "km": "kilometres", "cm": "centimetres", "mm": "millimetres",
    "ms": "milliseconds", "mol": "moles", "m": "metres", "s": "seconds", "g": "grams",
}


def _speak_units_after_numbers(text: str) -> str:
    pattern = r"(?<=\d)\s*(" + "|".join(sorted(_UNIT_AFTER_NUMBER, key=len, reverse=True)) + r")\b"

    def repl(match: re.Match[str]) -> str:
        return " " + _UNIT_AFTER_NUMBER[match.group(1)] + " "

    return re.sub(pattern, repl, text)


def _speak_math(text: str) -> str:
    """Converts formula-shaped runs; leaves ordinary prose untouched."""
    parts: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        joined = " ".join(buffer)
        if re.search(r"[=≈≤≥≅≠]", joined) and len(joined) <= 90:
            context = " ".join(parts[-3:]) if parts else ""
            parts.append(_speak_expression(joined, context))
        else:
            parts.append(joined)
        buffer.clear()

    for token in text.split(" "):
        if _is_math_token(token):
            buffer.append(token)
        else:
            flush()
            parts.append(token)
    flush()
    return " ".join(parts)


def prepare_text(text: str) -> str:
    """Turns displayed educational text into speech-ready prose.

    The written notes are never modified - this only builds the string sent
    for synthesis. It preserves order, removes markup and code, and reads
    operators, units and common symbols aloud.
    """
    text = _CONTROL_RE.sub(" ", str(text or ""))
    text = _strip_markup(text)
    # Before NFKC: that normalisation folds "²" into "2", which would turn
    # "r²" into "r2" instead of "r squared".
    for superscript, words in _SUPERSCRIPT.items():
        text = text.replace(superscript, words)
    text = unicodedata.normalize("NFKC", text)

    for phrase in sorted(UNIT_PHRASES, key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", f" {UNIT_PHRASES[phrase]} ", text)

    text = _speak_units_after_numbers(text)
    text = _speak_math(text)

    for symbol, words in _OPERATORS.items():
        text = text.replace(symbol, words)

    for abbreviation, words in ABBREVIATIONS.items():
        text = re.sub(rf"(?<![A-Za-z]){re.escape(abbreviation)}(?![A-Za-z])", f" {words} ", text)

    text = re.sub(r"(?<=\d)\s*[-−]\s*(?=\d)", " minus ", text)
    text = re.sub(r"(?<=\d)\s*/\s*(?=\d)", " divided by ", text)

    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[A-Za-z0-9])", r"\1 ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = _BLANKS_RE.sub("\n\n", text)
    return text.strip()


def validate_request_text(text: Any) -> str:
    """Validates raw submitted text and returns its prepared form."""
    if not isinstance(text, str):
        raise VoiceError("invalid_text", "Send the text to read as a string.", 422)
    raw = text.strip()
    if not raw:
        raise VoiceError("empty_text", "There is nothing to read yet.", 422)
    limit = max_chars()
    if len(raw) > limit:
        raise VoiceError(
            "text_too_long",
            f"Send at most {limit} characters at a time. Long articles are read in parts.",
            413,
        )
    prepared = prepare_text(raw)
    if len(prepared) < 2 or not re.search(r"[A-Za-z\u0900-\u097F0-9]", prepared):
        raise VoiceError("empty_text", "There is nothing readable in that text.", 422)
    if len(prepared) > HARD_MAX_CHARS:
        prepared = prepared[: HARD_MAX_CHARS].rsplit(" ", 1)[0]
    return prepared


# ---------------------------------------------------------------------------
# ElevenLabs calls
# ---------------------------------------------------------------------------

#: Tests install an ``httpx.MockTransport`` here. Production leaves it None.
_TRANSPORT: httpx.AsyncBaseTransport | None = None


def _api_key() -> str:
    key = get_settings().elevenlabs_api_key.strip()
    if not enabled():
        raise VoiceError("disabled", "The voice features are switched off on this server.", 503)
    if not key:
        raise VoiceError("not_configured", "The server has no ElevenLabs API key configured.", 503)
    return key


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    timeout = httpx.Timeout(
        connect=5.0,
        read=float(max(5, settings.voice_timeout_seconds)),
        write=float(max(5, settings.voice_timeout_seconds)),
        pool=5.0,
    )
    # follow_redirects is off on purpose: the only host contacted is fixed here.
    return httpx.AsyncClient(timeout=timeout, transport=_TRANSPORT, follow_redirects=False)


def _retry_after(response: httpx.Response) -> int:
    raw = response.headers.get("retry-after", "")
    try:
        return max(1, min(600, int(float(raw))))
    except (TypeError, ValueError):
        return 30


def _raise_for_upstream(response: httpx.Response) -> None:
    """Maps an ElevenLabs status onto a safe VoiceError."""
    status_code = response.status_code
    if status_code in (401, 403):
        raise VoiceError(
            "upstream_auth",
            "The voice service rejected this server's credentials. Check the ElevenLabs settings.",
            502,
        )
    if status_code == 429:
        raise VoiceError(
            "upstream_quota",
            "The voice service is rate-limiting this deployment. Try again in a moment.",
            429,
            retry_after=_retry_after(response),
        )
    if status_code in (400, 422):
        raise VoiceError(
            "upstream_invalid",
            "The voice service rejected that text or voice setting.",
            400,
        )
    if status_code >= 500:
        raise VoiceError(
            "upstream_unavailable",
            "The voice service is unavailable right now. Try again shortly.",
            502,
        )
    raise VoiceError("upstream_error", "The voice service returned an unexpected response.", 502)


async def synthesize(text: Any, language: str = "en", voice_id: str | None = None) -> tuple[bytes, str]:
    """Returns ``(audio_bytes, mime_type)`` for one bounded piece of text."""
    key = _api_key()
    voice = resolve_voice(language, voice_id)
    prepared = validate_request_text(text)
    settings = get_settings()
    model = (settings.elevenlabs_tts_model_id or DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID
    url = f"{API_BASE}{TTS_PATH.format(voice_id=quote(voice, safe=''))}"
    body = {
        "text": prepared,
        "model_id": model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0},
    }
    try:
        async with _client() as client:
            response = await client.post(
                url,
                params={"output_format": OUTPUT_FORMAT},
                headers={"xi-api-key": key, "accept": "audio/mpeg"},
                json=body,
            )
    except httpx.TimeoutException:
        raise VoiceError("upstream_timeout", "The voice service took too long to answer. Try again.", 504) from None
    except httpx.HTTPError:
        raise VoiceError("upstream_network", "Could not reach the voice service. Check the server's network.", 502) from None

    if response.status_code != 200:
        _raise_for_upstream(response)
    audio = response.content or b""
    if not audio:
        raise VoiceError("upstream_empty", "The voice service returned no audio. Try again.", 502)
    content_type = (response.headers.get("content-type") or "audio/mpeg").split(";")[0].strip()
    if not content_type.startswith("audio/"):
        # A JSON body here would be an upstream error page; do not hand it to
        # the browser labelled as audio.
        raise VoiceError("upstream_error", "The voice service returned an unexpected response.", 502)
    return audio, content_type


async def create_conversation_session(language: str = "en") -> dict[str, Any]:
    """Asks ElevenLabs for a short-lived signed Conversational AI URL.

    The signed URL authorises one conversation and expires quickly. It is
    returned to the browser; the API key is not.
    """
    key = _api_key()
    if language not in LANGUAGES:
        raise VoiceError("unsupported_language", "Only English and Hindi are configured for speech.", 422)
    agent_id = get_settings().elevenlabs_agent_id.strip()
    if not agent_id:
        raise VoiceError(
            "agent_not_configured",
            "No ElevenLabs agent is configured on this server, so a conversation cannot start yet.",
            503,
        )
    try:
        async with _client() as client:
            response = None
            for path in SIGNED_URL_PATHS:
                response = await client.get(
                    f"{API_BASE}{path}",
                    params={"agent_id": agent_id},
                    headers={"xi-api-key": key, "accept": "application/json"},
                )
                if response.status_code != 404:
                    break
    except httpx.TimeoutException:
        raise VoiceError("upstream_timeout", "The voice service took too long to answer. Try again.", 504) from None
    except httpx.HTTPError:
        raise VoiceError("upstream_network", "Could not reach the voice service. Check the server's network.", 502) from None

    if response.status_code != 200:
        _raise_for_upstream(response)
    try:
        data = response.json()
    except ValueError:
        raise VoiceError("upstream_error", "The voice service returned an unexpected response.", 502) from None
    signed = data.get("signed_url") if isinstance(data, dict) else None
    if not isinstance(signed, str) or not signed.startswith("wss://"):
        raise VoiceError("upstream_error", "The voice service did not return a usable session.", 502)
    return {"signedUrl": signed, "language": language}
