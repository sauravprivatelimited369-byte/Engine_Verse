"""Server accounts: OTP sign-up, password recovery and change, account topbar.

These cover the FastAPI deployment, which has real accounts (scrypt password
hashes, CSRF, rate limits and one-time codes sent by the server). The static
GitHub Pages copy has no accounts at all; see test_pages_live_contract.py.
Moved here from test_github_sync_and_apk.py when the public learner sync was
removed.
"""
from __future__ import annotations


def _csrf(html: str) -> str:
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def _field(html: str, name: str) -> str:
    import re
    match = re.search(rf'name="{re.escape(name)}" value="([^"]*)"', html)
    assert match, f"missing field {name}"
    return match.group(1)


def test_country_code_phone_normalization_and_validation():
    from engineverse.security.validators import COUNTRY_CODES, normalize_phone_with_country_code

    assert any(code == "+91" for code, _ in COUNTRY_CODES)
    assert any(code == "+1" for code, _ in COUNTRY_CODES)
    assert any(code == "+44" for code, _ in COUNTRY_CODES)
    assert normalize_phone_with_country_code("9876543210", "+91") == "+919876543210"
    assert normalize_phone_with_country_code("09876543210", "+91") == "+919876543210"
    assert normalize_phone_with_country_code("+447911123456", "+91") == "+447911123456"
    assert normalize_phone_with_country_code("415-555-2671", "+1") == "+14155552671"


def test_scoped_otp_signup_only_mode_verifies_new_user_and_skips_otp_on_returning_login(client, seeded, monkeypatch):
    import os
    from engineverse import notify
    from engineverse.config import reload_settings

    monkeypatch.setenv("ENGINEVERSE_LOGIN_OTP", "signup_only")
    monkeypatch.setenv("ENGINEVERSE_SMS_URL", "https://sms.example/send")
    reload_settings()
    try:
        sent_codes: list[str] = []
        monkeypatch.setattr(
            notify,
            "send_phone_otp",
            lambda to, code, minutes=10: sent_codes.append(code) or True,
        )
        monkeypatch.setattr(
            notify,
            "send_login_otp",
            lambda to, code, minutes=10: sent_codes.append(code) or True,
        )

        tag = f"newotp{os.urandom(3).hex()}"
        reg_page = client.get("/register")
        assert 'name="country_code"' in reg_page.text
        assert 'name="otp_channel"' in reg_page.text

        # 1. New user registers with mobile number + country code (+91) and requests SMS OTP
        reg_res = client.post(
            "/register",
            data={
                "csrf_token": _csrf(reg_page.text),
                "full_name": "New Verified Learner",
                "username": tag,
                "email": f"{tag}@gmail.com",
                "country_code": "+91",
                "phone": "9876543210",
                "otp_channel": "phone",
                "password": "StrongOtpPassword#2026",
                "password_confirm": "StrongOtpPassword#2026",
                "branch": "cse",
                "semester": "1",
                "next": "/dashboard",
            },
            follow_redirects=False,
        )
        assert reg_res.status_code == 401
        assert sent_codes, "Expected 6-digit OTP to be sent for new user signup"
        otp_code = sent_codes[-1]
        assert len(otp_code) == 6 and otp_code.isdigit()
        assert "ev_session" not in reg_res.headers.get("set-cookie", "")

        # 2. Complete the 6-digit OTP verification on /login
        token = _field(reg_res.text, "otp_token")
        verify_res = client.post(
            "/login",
            data={
                "csrf_token": _csrf(reg_res.text),
                "identifier": f"{tag}@gmail.com",
                "mfa_token": token,
                "otp": otp_code,
                "next": "/dashboard",
                "remember": "1",
            },
            follow_redirects=False,
        )
        assert verify_res.status_code == 303
        assert verify_res.headers["location"] == "/dashboard"

        # 3. Sign out, then log back in as a returning verified user:
        # must sign in directly with password WITHOUT requiring another OTP!
        dash = client.get("/dashboard")
        client.post("/logout", data={"csrf_token": _csrf(dash.text)}, follow_redirects=False)

        sent_codes.clear()
        login_page = client.get("/login")
        login_res = client.post(
            "/login",
            data={
                "csrf_token": _csrf(login_page.text),
                "identifier": f"{tag}@gmail.com",
                "password": "StrongOtpPassword#2026",
                "next": "/dashboard",
            },
            follow_redirects=False,
        )
        assert login_res.status_code == 303
        assert login_res.headers["location"] == "/dashboard"
        assert sent_codes == [], "Returning verified user must NOT be challenged for OTP on normal login"
    finally:
        os.environ["ENGINEVERSE_LOGIN_OTP"] = "disabled"
        os.environ.pop("ENGINEVERSE_SMS_URL", None)
        reload_settings()


def test_forgot_and_reset_password_via_6_digit_otp_email_and_phone(client, seeded, monkeypatch):
    import os
    from engineverse import auth, notify

    sent: dict[str, str] = {}
    monkeypatch.setattr(
        notify,
        "send_phone_otp",
        lambda to, code, minutes=10: sent.update(to=to, code=code, channel="phone") or True,
    )
    monkeypatch.setattr(
        notify,
        "send_login_otp",
        lambda to, code, minutes=10: sent.update(to=to, code=code, channel="email") or True,
    )

    tag = f"resetotp{os.urandom(3).hex()}"
    user = auth.register(
        email=f"{tag}@gmail.com",
        username=tag,
        password="InitialPassword#2026",
        full_name="Reset Learner",
        phone="9876543211",
        country_code="+91",
    )
    assert user["phone"] == "+919876543211"

    # Request 6-digit password reset OTP via mobile number with country code
    forgot_page = client.get("/forgot-password")
    assert 'name="country_code"' in forgot_page.text
    forgot_res = client.post(
        "/forgot-password",
        data={
            "csrf_token": _csrf(forgot_page.text),
            "email": "",
            "otp_channel": "phone",
            "country_code": "+91",
            "phone": "9876543211",
        },
        follow_redirects=False,
    )
    assert forgot_res.status_code == 200
    assert sent.get("code") and len(sent["code"]) == 6
    assert 'name="otp_code"' in forgot_res.text

    # Submit the 6-digit OTP + new password to /reset-password
    reset_res = client.post(
        "/reset-password",
        data={
            "csrf_token": _csrf(forgot_res.text),
            "otp_token": _field(forgot_res.text, "otp_token"),
            "otp_code": sent["code"],
            "password": "UpdatedViaOtpPassword#2026",
            "confirm_password": "UpdatedViaOtpPassword#2026",
        },
        follow_redirects=False,
    )
    assert reset_res.status_code == 303
    assert reset_res.headers["location"] == "/login?error=reset"

    # Log in directly with the new password
    login_page = client.get("/login")
    login_res = client.post(
        "/login",
        data={
            "csrf_token": _csrf(login_page.text),
            "identifier": f"{tag}@gmail.com",
            "password": "UpdatedViaOtpPassword#2026",
            "next": "/dashboard",
        },
        follow_redirects=False,
    )
    assert login_res.status_code == 303


def test_change_password_via_6_digit_otp_in_settings(client, seeded, monkeypatch):
    import os
    from engineverse import auth, notify

    sent: dict[str, str] = {}
    monkeypatch.setattr(
        notify,
        "send_login_otp",
        lambda to, code, minutes=10: sent.update(to=to, code=code, channel="email") or True,
    )

    tag = f"chgpwd{os.urandom(3).hex()}"
    auth.register(
        email=f"{tag}@gmail.com",
        username=tag,
        password="BeforeChange#2026",
        full_name="Settings OTP Learner",
        phone="9876543212",
        country_code="+91",
    )

    login_page = client.get("/login")
    login_res = client.post(
        "/login",
        data={
            "csrf_token": _csrf(login_page.text),
            "identifier": tag,
            "password": "BeforeChange#2026",
        },
        follow_redirects=False,
    )
    assert login_res.status_code == 303

    settings_page = client.get("/settings")
    assert settings_page.status_code == 200
    assert "/settings/password/otp" in settings_page.text
    assert 'name="country_code"' in settings_page.text

    # 1. Request 6-digit OTP to change password via Gmail
    otp_req = client.post(
        "/settings/password/otp",
        data={
            "csrf_token": _csrf(settings_page.text),
            "channel": "email",
            "country_code": "+91",
            "phone": "9876543212",
        },
        follow_redirects=False,
    )
    assert otp_req.status_code == 200
    assert sent.get("code") and len(sent["code"]) == 6

    # 2. Verify 6-digit OTP and set new password
    chg_res = client.post(
        "/settings/password",
        data={
            "csrf_token": _csrf(otp_req.text),
            "otp_token": _field(otp_req.text, "otp_token"),
            "otp_code": sent["code"],
            "new_password": "AfterOtpChange#2026",
            "confirm_password": "AfterOtpChange#2026",
        },
        follow_redirects=False,
    )
    assert chg_res.status_code == 303
    assert chg_res.headers["location"] == "/settings"


def test_topbar_shows_the_account_menu_on_every_tab_when_signed_in(signed_in):
    # Signed-in pages show the account menu, never "Sign in / Start free" or
    # anonymous "Sign in to..." prompts.
    for tab_path in ("/", "/explore", "/revision", "/sheets", "/dpp", "/community", "/settings"):
        res = signed_in.get(tab_path)
        assert res.status_code == 200, tab_path
        assert 'class="avatar"' in res.text, f"Missing account avatar icon on {tab_path}"
        assert 'class="whoami"' in res.text, f"Missing account menu on {tab_path}"
        assert 'data-ev-anon-auth' not in res.text, f"Anonymous Sign in / Start free still rendered on {tab_path}"
        assert "Sign in to start revising" not in res.text, f"Anonymous revision prompt rendered on {tab_path}"
        assert "Sign in to have your progress on this sheet tracked" not in res.text
