"""ElevenLabs voice integration: reader, tutor sessions and safe failures.

Everything here is **mocked**: ``httpx.MockTransport`` stands in for the
ElevenLabs API, so these tests prove request shape, validation, error mapping
and secret handling. They do not prove that a real account, voice or agent
exists - that requires the credentials described in
``docs/ELEVENLABS_INTEGRATION.md``.
"""
from __future__ import annotations

import json

import httpx
import pytest

from engineverse import voice
from engineverse.config import reload_settings

API_KEY = "test-elevenlabs-key-must-never-be-published-0001"
VOICE_EN = "voice-en-test-0001"
VOICE_HI = "voice-hi-test-0002"
AGENT = "agent-test-0003"


@pytest.fixture()
def configured(monkeypatch):
    """Turns on the feature with throwaway values and no real network."""
    monkeypatch.setenv("ENGINEVERSE_ELEVENLABS_ENABLED", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", API_KEY)
    monkeypatch.setenv("ELEVENLABS_TTS_VOICE_ID_EN", VOICE_EN)
    monkeypatch.setenv("ELEVENLABS_TTS_VOICE_ID_HI", VOICE_HI)
    monkeypatch.setenv("ELEVENLABS_TTS_VOICE_NAME_EN", "English test voice")
    monkeypatch.setenv("ELEVENLABS_TTS_VOICE_NAME_HI", "Hindi test voice")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", AGENT)
    monkeypatch.setenv("ENGINEVERSE_VOICE_MAX_CHARS", "1200")
    reload_settings()
    yield
    voice._TRANSPORT = None


@pytest.fixture()
def transport(monkeypatch):
    """Installs a mock upstream and returns a mutable record of the calls."""
    calls: list[httpx.Request] = []
    behaviour = {"status": 200, "body": b"ID3fake-mp3-bytes", "content_type": "audio/mpeg",
                 "raise": None, "json": None, "headers": {}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if behaviour["raise"] is not None:
            raise behaviour["raise"]
        if behaviour["json"] is not None:
            return httpx.Response(
                behaviour["status"], json=behaviour["json"], headers=behaviour["headers"]
            )
        return httpx.Response(
            behaviour["status"],
            content=behaviour["body"],
            headers={"content-type": behaviour["content_type"], **behaviour["headers"]},
        )

    voice._TRANSPORT = httpx.MockTransport(handler)
    behaviour["calls"] = calls
    return behaviour


def _json(client, path, payload, **kwargs):
    return client.post(path, content=json.dumps(payload), headers={"content-type": "application/json"}, **kwargs)


# ---------------------------------------------------------------------------
# Text preparation (no upstream involved)
# ---------------------------------------------------------------------------


class TestSpeechText:
    def test_ohms_law_is_read_as_quantities(self):
        assert voice.prepare_text("V = IR") == "voltage equals current multiplied by resistance"

    def test_energy_mass_relation(self):
        assert voice.prepare_text("E = mc^2") == (
            "energy equals mass multiplied by speed of light squared"
        )

    def test_markup_and_code_fences_are_removed(self):
        text = voice.prepare_text("<p>Water boils at 100°C.</p>\n```python\nprint('x')\n```\nThe loop runs.")
        assert "<p>" not in text and "print" not in text
        assert "100 degrees Celsius" in text
        assert "The loop runs." in text

    def test_units_following_numbers_are_spoken(self):
        assert "5 volts" in voice.prepare_text("The supply is 5 V.")
        assert "20 metres per second" in voice.prepare_text("It travels at 20 m/s.")

    def test_ordinary_prose_is_left_alone(self):
        sentence = "Use a state-of-the-art tool; it is well-known."
        assert voice.prepare_text(sentence) == sentence

    def test_ambiguous_symbol_keeps_the_letter_when_prose_names_another_quantity(self):
        spoken = voice.prepare_text("Pressure P = F/A")
        assert "pressure power" not in spoken.lower()
        assert "force divided by area" in spoken

    def test_abbreviations_are_expanded(self):
        spoken = voice.prepare_text("See e.g. the CPU, approx. 30% faster.")
        assert "for example" in spoken and "per cent" in spoken and "approximately" in spoken


# ---------------------------------------------------------------------------
# Configuration and status
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_disabled_by_default_and_no_upstream_call(self, client, transport):
        payload = client.get("/api/voice/status").json()
        assert payload["enabled"] is False
        assert payload["tts"]["available"] is False
        assert payload["conversation"]["available"] is False
        assert payload["reason"]
        assert transport["calls"] == []

    def test_missing_api_key_is_reported_without_leaking(self, client, monkeypatch):
        monkeypatch.setenv("ENGINEVERSE_ELEVENLABS_ENABLED", "1")
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        monkeypatch.setenv("ELEVENLABS_TTS_VOICE_ID_EN", VOICE_EN)
        reload_settings()
        payload = client.get("/api/voice/status").json()
        assert payload["tts"]["available"] is False
        assert "API key" in payload["reason"]
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en"})
        assert response.status_code == 503
        assert "ELEVENLABS" not in response.text and "xi-api-key" not in response.text

    def test_status_lists_only_configured_languages_and_never_secrets(self, client, configured):
        body = client.get("/api/voice/status").text
        payload = json.loads(body)
        assert [item["code"] for item in payload["tts"]["languages"]] == ["en", "hi"]
        assert payload["tts"]["languages"][0]["voices"] == [
            {"id": VOICE_EN, "name": "English test voice"}
        ]
        assert payload["tts"]["maxChars"] == 1200
        assert API_KEY not in body and AGENT not in body
        assert "signed" not in body.lower()

    def test_only_one_configured_voice_is_offered(self, client, monkeypatch):
        monkeypatch.setenv("ENGINEVERSE_ELEVENLABS_ENABLED", "1")
        monkeypatch.setenv("ELEVENLABS_API_KEY", API_KEY)
        monkeypatch.setenv("ELEVENLABS_TTS_VOICE_ID_EN", VOICE_EN)
        monkeypatch.delenv("ELEVENLABS_TTS_VOICE_ID_HI", raising=False)
        reload_settings()
        payload = client.get("/api/voice/status").json()
        assert [item["code"] for item in payload["tts"]["languages"]] == ["en"]

    def test_voice_api_is_reachable_with_compulsory_sign_in(self, client, configured, monkeypatch):
        # The public Pages copy has no session at all; the reader must still work.
        monkeypatch.setenv("ENGINEVERSE_SIGNIN", "required")
        reload_settings()
        assert client.get("/api/voice/status").status_code == 200

    def test_rate_limit_entries_exist(self):
        from engineverse.security import ratelimit

        assert "voice" in ratelimit.LIMITS and "voice_session" in ratelimit.LIMITS


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------


class TestSpeech:
    def test_successful_synthesis(self, client, configured, transport):
        response = _json(client, "/api/voice/speech", {"text": "V = IR", "language": "en"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/mpeg")
        assert response.headers["cache-control"] == "no-store"
        assert response.content == transport["body"]

        call = transport["calls"][0]
        assert call.method == "POST"
        assert call.url.host == "api.elevenlabs.io"
        assert call.url.path == f"/v1/text-to-speech/{VOICE_EN}"
        assert call.url.params["output_format"] == voice.OUTPUT_FORMAT
        assert call.headers["xi-api-key"] == API_KEY
        sent = json.loads(call.content)
        assert sent["text"] == "voltage equals current multiplied by resistance"
        assert sent["model_id"] == "eleven_multilingual_v2"
        assert API_KEY not in response.text

    def test_hindi_voice_is_selected_by_language(self, client, configured, transport):
        response = _json(client, "/api/voice/speech", {"text": "बल द्रव्यमान गुणा त्वरण है", "language": "hi"})
        assert response.status_code == 200
        assert transport["calls"][0].url.path == f"/v1/text-to-speech/{VOICE_HI}"

    def test_missing_text_and_wrong_type(self, client, configured):
        assert _json(client, "/api/voice/speech", {"language": "en"}).status_code == 422
        assert _json(client, "/api/voice/speech", {"text": 42, "language": "en"}).status_code == 422
        assert _json(client, "/api/voice/speech", {"text": "   ", "language": "en"}).status_code == 422

    def test_text_over_the_limit_is_refused_before_upstream(self, client, configured, transport):
        response = _json(client, "/api/voice/speech", {"text": "a" * 1201, "language": "en"})
        assert response.status_code == 413
        assert response.json()["code"] == "text_too_long"
        assert transport["calls"] == []

    def test_unsupported_language_and_voice(self, client, configured, transport):
        assert _json(client, "/api/voice/speech", {"text": "Hello", "language": "fr"}).status_code == 422
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en", "voiceId": "someone-elses-voice"})
        assert response.status_code == 422
        assert response.json()["code"] == "unsupported_voice"
        assert transport["calls"] == []

    def test_form_posts_are_refused(self, client, configured):
        # A cross-site HTML form can send this content type without a preflight,
        # so accepting it would make a paid endpoint forgeable. The reader is
        # exempt from CSRF only because of this strictness.
        response = client.post("/api/voice/speech", data={"text": "Hello", "language": "en"})
        assert response.status_code == 415

    def test_upstream_authentication_error_is_mapped(self, client, configured, transport):
        transport["status"] = 401
        transport["body"] = b'{"detail":"invalid api key"}'
        transport["content_type"] = "application/json"
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en"})
        assert response.status_code == 502
        assert response.json()["code"] == "upstream_auth"
        assert API_KEY not in response.text
        assert "invalid api key" not in response.text.lower()

    def test_upstream_quota_error_keeps_retry_after(self, client, configured, transport):
        transport["status"] = 429
        transport["headers"] = {"retry-after": "42"}
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en"})
        assert response.status_code == 429
        assert response.json()["code"] == "upstream_quota"
        assert response.headers["retry-after"] == "42"

    def test_upstream_timeout_and_network_failure(self, client, configured, transport):
        transport["raise"] = httpx.ConnectTimeout("timed out")
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en"})
        assert response.status_code == 504
        assert response.json()["code"] == "upstream_timeout"

        transport["raise"] = httpx.ConnectError("no route")
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en"})
        assert response.status_code == 502
        assert response.json()["code"] == "upstream_network"

    def test_non_audio_upstream_body_is_not_served_as_audio(self, client, configured, transport):
        transport["content_type"] = "application/json"
        transport["body"] = b'{"unexpected":true}'
        response = _json(client, "/api/voice/speech", {"text": "Hello", "language": "en"})
        assert response.status_code == 502
        assert response.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# Conversational AI sessions
# ---------------------------------------------------------------------------


class TestConversationSession:
    def test_signed_url_is_returned_without_the_key(self, client, configured, transport):
        transport["json"] = {"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?signed_token=xyz"}
        response = _json(client, "/api/voice/session", {"language": "en"})
        assert response.status_code == 200
        body = response.json()
        assert body["signedUrl"].startswith("wss://")
        assert API_KEY not in response.text
        assert response.headers["cache-control"] == "no-store"

        call = transport["calls"][0]
        assert call.url.path == "/v1/convai/conversation/get-signed-url"
        assert call.url.params["agent_id"] == AGENT
        assert call.headers["xi-api-key"] == API_KEY

    def test_missing_agent_is_a_setup_message(self, client, configured, transport, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_AGENT_ID", "")
        reload_settings()
        response = _json(client, "/api/voice/session", {"language": "en"})
        assert response.status_code == 503
        assert response.json()["code"] == "agent_not_configured"
        assert response.headers.get("x-voice-setup-required") == "1"
        assert transport["calls"] == []

    def test_unusable_upstream_session_is_refused(self, client, configured, transport):
        transport["json"] = {"signed_url": "https://example.com/not-a-websocket"}
        response = _json(client, "/api/voice/session", {"language": "en"})
        assert response.status_code == 502
        assert "signed" not in response.json().get("error", "").lower()

    def test_unsupported_language(self, client, configured):
        assert _json(client, "/api/voice/session", {"language": "ta"}).status_code == 422


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCors:
    def test_pages_origin_preflight_is_allowed(self, client, configured):
        response = client.options(
            "/api/voice/speech",
            headers={
                "origin": "https://sauravprivatelimited369-byte.github.io",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == (
            "https://sauravprivatelimited369-byte.github.io"
        )

    def test_unknown_origin_is_refused(self, client, configured):
        response = client.options(
            "/api/voice/speech",
            headers={
                "origin": "https://attacker.example",
                "access-control-request-method": "POST",
            },
        )
        assert "access-control-allow-origin" not in response.headers


# ---------------------------------------------------------------------------
# The pages that carry the controls, and the response policy around them
# ---------------------------------------------------------------------------


class TestPages:
    def _topic_slug(self):
        from engineverse import db

        row = db.query_one(
            "SELECT slug FROM topics WHERE status = 'published' ORDER BY slug LIMIT 1"
        )
        assert row is not None
        return row["slug"]

    def test_note_page_carries_the_reader_and_its_public_config(self, client, configured):
        slug = self._topic_slug()
        html = client.get(f"/topics/{slug}").text
        assert 'id="ev-voice-config"' in html
        assert "/static/js/voice.js" in html and "/static/css/voice.css" in html
        assert "data-speak" in html
        # The browser configuration is public; no credential may be in the page.
        assert API_KEY not in html and AGENT not in html

    def test_tutor_page_has_the_opt_in_panel_and_hidden_microphone_controls(self, client, configured):
        html = client.get("/tutor").text
        for marker in ("voice-start", "voice-mute", "voice-end", "voice-status", "voice-settings"):
            assert f'id="{marker}"' in html
        assert "Start conversation" in html
        assert API_KEY not in html

    def test_csp_allows_blob_audio_and_the_signed_websocket_when_enabled(self, client, configured):
        headers = client.get("/api/voice/status").headers
        csp = headers.get("content-security-policy", "")
        assert "media-src 'self' blob:" in csp
        assert "wss://api.elevenlabs.io" in csp
        assert "microphone=(self)" in headers.get("permissions-policy", "")

    def test_csp_keeps_the_microphone_closed_when_disabled(self, client):
        headers = client.get("/api/voice/status").headers
        assert "wss://api.elevenlabs.io" not in headers.get("content-security-policy", "")
        assert "microphone=()" in headers.get("permissions-policy", "")

    def test_notes_tutor_can_ask_by_voice_without_an_agent(self, client):
        page = client.get("/tutor")
        assert page.status_code == 200
        assert 'id="voice-ask" hidden' in page.text
        assert 'id="voice-ask-status"' in page.text
        assert "microphone=(self)" in page.headers["permissions-policy"]
        assert "wss://api.elevenlabs.io" not in page.headers["content-security-policy"]
        # No other page gains microphone permission when ElevenLabs is off.
        note = client.get(f"/topics/{self._topic_slug()}")
        assert "microphone=()" in note.headers["permissions-policy"]


class TestStaticExportConfig:
    def test_public_voice_api_url_is_a_bare_origin(self):
        from scripts import export_pages

        assert export_pages.normalise_voice_api_url("https://voice.example.com") == "https://voice.example.com"
        assert export_pages.normalise_voice_api_url("http://localhost:8000") == "http://localhost:8000"
        assert export_pages.normalise_voice_api_url("") == ""
        for bad in ("https://voice.example.com/api", "https://voice.example.com?x=1", "javascript:alert(1)"):
            with pytest.raises(SystemExit):
                export_pages.normalise_voice_api_url(bad)

    def test_static_copy_only_bakes_the_url_into_the_export(self, monkeypatch):
        from web import deps

        monkeypatch.setenv("ENGINEVERSE_VOICE_API_URL", "https://voice.example.com")
        monkeypatch.delenv("ENGINEVERSE_STATIC_EXPORT", raising=False)
        assert deps._voice_api_base() == ""  # the live app is same-origin
        monkeypatch.setenv("ENGINEVERSE_STATIC_EXPORT", "1")
        assert deps._voice_api_base() == "https://voice.example.com"
        monkeypatch.setenv("ENGINEVERSE_VOICE_API_URL", "https://voice.example.com/secret/path")
        assert deps._voice_api_base() == ""


class TestDeploymentVoiceGate:
    """The Pages gate: honest device-only export, validated ElevenLabs origin.

    These are automated checks of the *gate*, not a live ElevenLabs test: no
    request leaves the process. An ElevenLabs-enabled release needs the public
    API origin; a device-only one must never publish a key or signed URL.
    """

    def _site(self, tmp_path, config):
        index = tmp_path / "index.html"
        index.write_text(
            '<script type="application/json" id="ev-voice-config">'
            + json.dumps(config)
            + "</script>",
            encoding="utf-8",
        )
        return tmp_path

    def test_origin_must_be_a_bare_https_origin(self, capsys):
        from scripts import verify_voice_api

        assert verify_voice_api.check_url("https://voice.example.com") == "https://voice.example.com"
        for bad in ("http://voice.example.com", "https://voice.example.com/api/voice",
                    "https://voice.example.com/Engine_Verse/", "not a url"):
            with pytest.raises(SystemExit):
                verify_voice_api.check_url(bad)

    def test_empty_export_is_device_only_not_fake_elevenlabs(self, tmp_path, capsys):
        from scripts import verify_voice_api

        verify_voice_api.check_site(self._site(tmp_path, {"apiBase": "", "staticCopy": True}), "")
        out = capsys.readouterr().out
        assert "device-only" in out and "natural voice is not connected" in out

    def test_configured_export_publishes_exactly_the_origin(self, tmp_path):
        from scripts import verify_voice_api

        site = self._site(tmp_path, {"apiBase": "https://voice.example.com", "staticCopy": True})
        verify_voice_api.check_site(site, "https://voice.example.com")
        with pytest.raises(SystemExit):
            verify_voice_api.check_site(site, "https://other.example.com")
        # An origin must never slip into a disabled export.
        with pytest.raises(SystemExit):
            verify_voice_api.check_site(site, "")

    def test_static_output_may_not_contain_a_key_or_agent(self, tmp_path):
        from scripts import verify_voice_api

        site = self._site(tmp_path, {"apiBase": "https://voice.example.com", "staticCopy": True})
        (site / "notes").mkdir()
        (site / "notes" / "index.html").write_text(
            "<p>key sk_live_should_never_ship</p>", encoding="utf-8")
        with pytest.raises(SystemExit):
            verify_voice_api.check_site(site, "https://voice.example.com")

    def test_a_wildcard_cors_answer_is_refused(self, monkeypatch):
        from scripts import verify_voice_api

        class FakeResponse:
            status = 200
            headers = {"access-control-allow-origin": "*"}

            def read(self):
                return b'{"tts": {"available": true}, "conversation": {"available": false}}'

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(verify_voice_api, "_request", lambda *a, **k: FakeResponse())
        with pytest.raises(SystemExit):
            verify_voice_api.check_status("https://voice.example.com")
