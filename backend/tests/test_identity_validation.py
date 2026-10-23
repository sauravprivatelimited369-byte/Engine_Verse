"""Identity rules: the browser copy and the server copy must agree.

The complaint this file exists for is that sign-in accepted a fake Gmail address
and a made-up mobile number. The fix lives in two places:
``engineverse/security/{email,phone}_rules.py`` for the hosted app, and the
``EV-IDENTITY-RULES`` block in ``static/js/pages-live.js`` for the exported
GitHub Pages copy, which has no server to fall back on. Two implementations of
one rule drift unless something checks, so the parity tests below run the *same
fixtures* through both and compare verdicts, not merely the fact that each side
has a test. The JS block is extracted verbatim rather than paraphrased: a test
that restates the code under test proves nothing.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from engineverse.security import email_rules, phone_rules, validators

JS_PATH = Path(__file__).resolve().parents[2] / "backend" / "static" / "js" / "pages-live.js"
BLOCK_RE = re.compile(
    r"// === BEGIN EV-IDENTITY-RULES ===\n(?P<body>.*?)\n  // === END EV-IDENTITY-RULES ===",
    re.S,
)
requires_node = pytest.mark.skipif(not shutil.which("node"), reason="node required for the JS parity check")

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


def _js_rules_block() -> str:
    match = BLOCK_RE.search(JS_PATH.read_text(encoding="utf-8"))
    assert match, "pages-live.js lost its EV-IDENTITY-RULES markers"
    return match.group("body")


def _policy() -> dict:
    """Exactly what ``scripts/export_pages.py`` puts in the boot blob."""
    return {"email": email_rules.policy(), "phone": phone_rules.policy()}


def _run_node(program: str) -> list[dict]:
    if shutil.which("node") is None:  # pragma: no cover - guarded by the marker too
        pytest.skip("node required")
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"node harness failed: {result.stderr[-3000:]}"
    return json.loads(result.stdout)


def _browser(kind: str, cases: list, policy: dict | None) -> list[dict]:
    """Verdicts from the browser rules for the same fixtures the server gets.

    ``policy=None`` means "no policy was injected", the state of a page cached by
    the service worker next to a newer script, which has to fall back safely.
    """
    call = "IDENTITY.email(item)" if kind == "email" else "IDENTITY.phone(item[0], item[1])"
    return _run_node(
        """
const config = %s;
%s
const cases = %s;
const out = [];
for (const item of cases) {
  const r = %s;
  out.push({ ok: !!r.ok, value: r.ok ? r.value : "", error: r.ok ? "" : (r.error || "") });
}
console.log(JSON.stringify(out));
"""
        % (
            json.dumps({"identity": policy} if policy is not None else {}),
            _js_rules_block(),
            json.dumps(cases),
            call,
        )
    )


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


@pytest.mark.parametrize("value,accepted", EMAIL_CASES)
@requires_node
def test_browser_email_rules_match_the_server(value: str, accepted: bool) -> None:
    verdict = _browser("email", [value], _policy())[0]
    assert verdict["ok"] is accepted, verdict
    if accepted:
        assert verdict["value"] == validators.validate_email(value, "email")
    else:
        # A refusal that does not say why looks like a broken page, and a broken
        # page gets JavaScript switched off - which is how we got here.
        assert verdict["error"].strip()


@pytest.mark.parametrize("number,country_code,accepted", PHONE_CASES)
@requires_node
def test_browser_phone_rules_match_the_server(number: str, country_code: str, accepted: bool) -> None:
    verdict = _browser("phone", [[number, country_code]], _policy())[0]
    assert verdict["ok"] is accepted, verdict
    if accepted:
        assert verdict["value"] == validators.normalize_phone_with_country_code(number, country_code, "phone")
    else:
        assert verdict["error"].strip()


@requires_node
def test_fallback_table_refuses_the_same_fakes() -> None:
    """Without an injected policy the JS uses its own constants - not a stub.

    This is the combination that a stale cache produces: an exported page from
    before this change, run with a newer script or none at all. The fake values
    still have to be refused, or the fix only works on pages that were exported
    after it.
    """
    refused = [value for value, accepted in EMAIL_CASES if not accepted]
    assert all(not v["ok"] for v in _browser("email", refused, None)), "fallback table is too permissive"
    good = [value for value, accepted in EMAIL_CASES if accepted]
    assert all(v["ok"] for v in _browser("email", good, None)), "fallback table locks out real addresses"

    bad = [[number, code] for number, code, accepted in PHONE_CASES if not accepted]
    assert all(not v["ok"] for v in _browser("phone", bad, None)), "fallback table is too permissive"


@requires_node
def test_extracted_block_is_self_contained() -> None:
    """The rules may not quietly grow a dependency on the rest of the runtime.

    The block is what the parity harness can run at all; if it starts calling
    ``toast`` or reading the DOM, the test silently stops comparing anything
    useful. So the block is executed here with no other globals in scope.
    """
    verdicts = _browser("email", ["asha@example.com"], _policy())
    assert verdicts == [{"ok": True, "value": "asha@example.com", "error": ""}]


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


def test_exported_pages_inject_the_policy(tmp_path: Path) -> None:
    """``pages-live.js`` reads ``config.identity``; the export has to provide it.

    Without this the browser falls back to its own table forever and the two
    copies diverge the moment a plan or a domain list is edited on the server.
    """
    import sys

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "scripts"))
    import export_pages  # noqa: PLC0415 - shared with the export, not the app

    blob = export_pages.live_boot("/", [], "")
    payload = json.loads(re.search(r'id="ev-live">(.*?)</script>', blob, re.S).group(1))
    assert payload["identity"]["phone"]["plans"]["+91"]["nsn"] == "^[1-9][0-9]{9}$"
    assert "gmial.com" in payload["identity"]["email"]["typos"]


def test_exported_selectors_are_generated_not_written_by_hand(tmp_path: Path) -> None:
    """Every ``country_code`` select on an exported page offers the selectable plans.

    Five hand-typed lists used to disagree with each other and with the server.
    """
    import sys

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "scripts"))
    import export_pages  # noqa: PLC0415

    markup = export_pages.country_option_markup()
    assert markup.count("<option") == len(phone_rules.SELECTOR_PLANS)
    for plan in phone_rules.SELECTOR_PLANS:
        assert f'value="{plan.code}"' in markup
