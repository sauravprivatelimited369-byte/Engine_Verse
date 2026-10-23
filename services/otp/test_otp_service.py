"""Tests for the standalone OTP delivery service.

Run:  python -m pytest services/otp -q
No real mail/SMS is sent: transports are injected fakes that capture the code
exactly the way a user's inbox/phone would receive it.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("OTP_SECRET", "test-secret-that-is-long-enough-123456")
os.environ.setdefault("SMTP_URL", "smtps://user%40example.com:pw@smtp.example.com:465/")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "tok")
os.environ.setdefault("TWILIO_FROM", "+10000000000")

import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OTP_DB", str(tmp_path / "otp.sqlite3"))
    sent = {}
    monkeypatch.setattr(app, "_sent_capture", sent, raising=False)
    return sent


def capture(sent):
    def fake_mail(to, code, purpose):
        sent["email"] = (to, code)

    def fake_sms(to, code, purpose):
        sent["sms"] = (to, code)

    return fake_mail, fake_sms


def test_email_code_is_sent_not_returned_and_verifies(fresh_db):
    mail, sms = capture(fresh_db)
    out = app.send_code("signup_verify", "email", "Learner@Example.com",
                        "203.0.113.1", mailer=mail, texter=sms)
    assert out["ok"] and "code" not in out  # the response must never carry the code
    to, code = fresh_db["email"]
    assert to == "learner@example.com" and len(code) == 6 and code.isdigit()
    assert app.verify_code("signup_verify", "learner@example.com", code) == {"ok": True}
    with pytest.raises(app.OtpError):  # single use
        app.verify_code("signup_verify", "learner@example.com", code)


def test_sms_code_goes_to_phone_with_country_code(fresh_db):
    mail, sms = capture(fresh_db)
    app.send_code("signup_verify", "phone", "+91 98765-43210", "203.0.113.2",
                  mailer=mail, texter=sms)
    to, code = fresh_db["sms"]
    assert to == "+919876543210"
    assert app.verify_code("signup_verify", "+919876543210", code)["ok"]


def test_wrong_codes_exhaust_and_expired_codes_fail(fresh_db):
    mail, sms = capture(fresh_db)
    app.send_code("password_reset", "email", "a@example.com", "203.0.113.3",
                  mailer=mail, texter=sms)
    _, code = fresh_db["email"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(app.OtpError):
            app.verify_code("password_reset", "a@example.com", wrong)
    with pytest.raises(app.OtpError):  # challenge killed after 5 attempts
        app.verify_code("password_reset", "a@example.com", code)


def test_delivery_failure_stores_no_usable_code(fresh_db):
    def boom(*_a):
        raise RuntimeError("smtp down")

    with pytest.raises(app.OtpError) as exc:
        app.send_code("signup_verify", "email", "b@example.com", "203.0.113.4",
                      mailer=boom, texter=boom)
    assert exc.value.status == 503
    with pytest.raises(app.OtpError):
        app.verify_code("signup_verify", "b@example.com", "123456")


def test_resend_cooldown_and_validation(fresh_db):
    mail, sms = capture(fresh_db)
    with pytest.raises(app.OtpError):
        app.send_code("signup_verify", "email", "not-an-email", "203.0.113.5",
                      mailer=mail, texter=sms)
    with pytest.raises(app.OtpError):
        app.send_code("signup_verify", "phone", "9876543210", "203.0.113.5",
                      mailer=mail, texter=sms)  # missing country code
    app.send_code("signup_verify", "email", "c@example.com", "203.0.113.5",
                  mailer=mail, texter=sms)
    with pytest.raises(app.OtpError) as exc:
        app.send_code("signup_verify", "email", "c@example.com", "203.0.113.5",
                      mailer=mail, texter=sms)
    assert exc.value.status == 429


def test_http_round_trip(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    monkeypatch.setenv("OTP_DB", str(tmp_path / "http.sqlite3"))
    inbox = {}
    monkeypatch.setattr(app, "send_email",
                        lambda to, code, purpose: inbox.update({to: code}))
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, payload):
        req = urllib.request.Request(base + path, method="POST",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    status, health = post("/otp/send", {"purpose": "signup_verify",
                                        "channel": "email",
                                        "destination": "d@example.com"})
    assert status == 200 and "code" not in health
    code = inbox["d@example.com"]
    assert post("/otp/verify", {"purpose": "signup_verify",
                                "destination": "d@example.com",
                                "code": code})[1] == {"ok": True}
    assert post("/otp/verify", {"purpose": "signup_verify",
                                "destination": "d@example.com",
                                "code": code})[0] == 401  # replay refused
    server.shutdown()
