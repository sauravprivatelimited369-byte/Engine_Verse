"""Identity rules for the hosted app's sign-up and sign-in.

The complaint this file exists for is that sign-in accepted a fake Gmail address
and a made-up mobile number. The rules live in
``engineverse/security/{email,phone}_rules.py``.

The static GitHub Pages copy used to carry a JavaScript copy of these rules for
its browser-side accounts. Those accounts were removed (the copy keeps progress
on the device and asks for no email or phone), so there is one implementation
and the last test checks that the browser copy did not quietly come back.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engineverse.security import email_rules, phone_rules, validators

JS_PATH = Path(__file__).resolve().parents[2] / "backend" / "static" / "js" / "pages-live.js"

# (value, accepted). Accepted rows are what real learners type and must never be
# refused; refused rows are what the single-regex check used to wave through.
EMAIL_CASES = [
    ("asha@example.com", True),
    ("Asha@Example.COM", True),            # folded, not rejected
    ("saurav.k+notes@gmail.com", True),
    ("student@iit.ac.in", True),
    ("ops@example.test", True),            # RFC 6761: believed, never probed
    ("user@[127.0.0.1]", True),            # intranet literal
    ("a@b.co", True),
    ("kmail.user@mail.com", True),         # looks like a typo, is a real provider
    ("support@fastmail.com", True),
    ("nobody@gnail.com", False),           # one keystroke from gmail.com
    ("nobody@gmial.com", False),
    ("nobody@gmail", False),               # no domain after the dot
    ("a..b@example.com", False),
    (".leading@example.com", False),
    ("trailing.@example.com", False),
    ("nobody@example..com", False),
    ("nobody@-bad.com", False),
    ("two@@at.com", False),
    ("hello@10minutemail.com", False),     # temporary inbox
    ("", False),
]

# (number as typed, selected country code, accepted).
PHONE_CASES = [
    ("9876543210", "+91", True),           # the seeded learner's number
    ("98765 43210", "+91", True),
    ("+91 98765-43210", "+91", True),      # already international
    ("0091-98765-43210", "+91", True),     # 00 is the international prefix
    ("9876501234", "+91", True),           # what the Pages harness types
    ("4155552671", "+1", True),           # 555 is fiction, not an invalid range
    ("7911123456", "+44", True),
    ("81234567", "+65", True),
    ("1234567", "+91", False),            # right characters, wrong plan
    ("987654321", "+91", False),          # nine digits is not an Indian number
    ("9876543210", "+1", True),           # unassigned-looking, but a valid NANP shape
    ("12345", "+91", False),
    ("1111111111", "+91", False),          # one digit repeated
    ("078888888", "+44", False),
    ("abc", "+91", False),
    ("", "+91", False),
]


# --- the rules themselves ---------------------------------------------------


@pytest.mark.parametrize("value,accepted", EMAIL_CASES)
def test_email_rules(value: str, accepted: bool) -> None:
    if accepted:
        assert validators.validate_email(value, "email") == value.strip().lower()
    else:
        with pytest.raises(validators.ValidationError):
            validators.validate_email(value, "email")


@pytest.mark.parametrize("value,accepted", EMAIL_CASES)
def test_refusals_do_not_depend_on_the_network(value: str, accepted: bool) -> None:
    """Nobody should get a stricter sign-up because their wifi can reach a DNS server.

    The DNS layer only ever *adds* refusals in ``mx`` mode; the rules that matter
    for "is this a real address" answer the same way offline, which is the state
    of a learner on a school network with no outbound UDP.
    """
    if accepted:
        assert validators.validate_email(value, "email", deliverability="off")
    else:
        with pytest.raises(validators.ValidationError):
            validators.validate_email(value, "email", deliverability="off")


@pytest.mark.parametrize("number,country_code,accepted", PHONE_CASES)
def test_phone_plan_rules(number: str, country_code: str, accepted: bool) -> None:
    if accepted:
        normalized = validators.normalize_phone_with_country_code(number, country_code, "phone")
        assert normalized.startswith("+") and normalized[1:].isdigit()
    else:
        with pytest.raises(validators.ValidationError):
            validators.normalize_phone_with_country_code(number, country_code, "phone")


def test_the_same_number_is_the_same_value_however_it_is_typed() -> None:
    forms = ["9876543210", "+91 98765 43210", "0091-98765-43210", "98765-43210", "(98765) 43210"]
    values = {validators.normalize_phone_with_country_code(form, "+91", "phone") for form in forms}
    assert values == {"+919876543210"}


@pytest.mark.parametrize("value", ["asha@gmail", "a..b@example.com", "nobody@gnail.com"])
def test_signin_identifier_refuses_shapes_that_cannot_belong_to_an_account(value: str) -> None:
    with pytest.raises(validators.ValidationError):
        validators.validate_signin_identifier(value)


def test_signin_identifier_accepts_all_three_forms() -> None:
    assert validators.validate_signin_identifier("Asha@Example.com") == "asha@example.com"
    assert validators.validate_signin_identifier("asha_007") == "asha_007"
    assert validators.validate_signin_identifier("+919876543210") == "+919876543210"
    # Digits on their own stay a username: somebody may own the name 2026, and a
    # check that guessed "that is a badly typed phone number" would lock them out.
    assert validators.validate_signin_identifier("2026") == "2026"


def test_blank_identifier_is_refused_with_a_message() -> None:
    with pytest.raises(validators.ValidationError):
        validators.validate_signin_identifier("   ")


# --- the two copies agree ---------------------------------------------------


# --- wiring -----------------------------------------------------------------


def test_policy_blob_covers_everything_the_templates_offer() -> None:
    """The dropdown and the validator cannot disagree, because they read one table."""
    policy = phone_rules.policy()
    offered = {code for code, _label in validators.COUNTRY_CODES}
    assert offered <= set(policy["plans"]), offered - set(policy["plans"])
    for code in offered:
        # Anchored, or a number that merely *contains* a valid one passes.
        assert policy["plans"][code]["nsn"].startswith("^") and policy["plans"][code]["nsn"].endswith("$")


def test_email_policy_carries_the_lists_a_browser_cannot_rebuild() -> None:
    policy = email_rules.policy()
    assert "example.com" in policy["reservedDomains"]
    assert "gmail.com" in policy["typos"].values()
    assert "mail.com" in policy["lookalikes"], "a real provider must not be refused as a typo"
    assert policy["disposable"], "the burner list is the only layer that catches a well-formed temp inbox"


def test_the_static_runtime_collects_no_identity() -> None:
    """The Pages copy has no accounts, so it has no email or phone rules either."""
    source = JS_PATH.read_text(encoding="utf-8")
    assert "EV-IDENTITY-RULES" not in source
    assert "country_code" not in source
