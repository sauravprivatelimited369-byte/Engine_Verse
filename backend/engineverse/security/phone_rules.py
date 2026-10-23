"""Which digit strings are phone numbers, and which are only digits.

E.164 asks for a plus sign and at most fifteen digits. It says nothing about
whether the digits are anyone's number, so ``+9112345`` - a country code and a
five-digit stub - cleared the old check and was saved to the ``users`` table.
Learners typing ``1234567890`` or ten nines into the sign-up form got an
account, an SMS challenge that can never be delivered, and a support request
that nobody can answer.

This module holds the second half of the answer: per-country numbering plans,
so a number is checked against the plan of the country its dialling code belongs
to, plus a small "this was invented just now" detector for the shapes people
type when they want the field to go away (one digit repeated, an ascending run).

Plans describe the *national significant number* - the digits after the country
code, with the trunk prefix already removed by
:func:`engineverse.security.validators.normalize_phone_with_country_code`.
They are deliberately ranges of whole shapes rather than prefix tables: an
operator that allocates a new mobile series must not lock learners out of
signing up, while a seven-digit stub in a ten-digit plan still has to fail.

The JavaScript mirror of this table lives in ``backend/static/js/pages-live.js``
between the ``EV-PHONE-RULES`` markers; ``backend/tests/test_identity_validation.py``
runs both sides over the same fixtures and fails when they disagree, because the
exported GitHub Pages copy has no server to fall back on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: E.164 ceiling: country code plus national number.
MAX_E164_DIGITS = 15
#: The shortest number we accept anywhere. The shortest real national numbers
#: (a few Pacific and Caribbean destinations) are 6-7 digits, so eight digits
#: total is the floor that does not refuse a legitimate country.
MIN_E164_DIGITS = 8
#: Longest country code in the ITU list is three digits (+268, +269, +383 ...).
MAX_COUNTRY_CODE_DIGITS = 3

_CODE_RE = re.compile(r"^\+[1-9][0-9]{0,%d}$" % (MAX_COUNTRY_CODE_DIGITS - 1))
_NSN_ALLOWED = re.compile(r"^[0-9]+$")


class PhoneFormatError(ValueError):
    """A number that is well-formed as text but is not a usable phone number."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class PhonePlan:
    """The shape of national numbers for one country code."""

    code: str
    label: str
    nsn: str
    example: str
    #: The dropdown's flag glyph. Presentation only: a missing flag costs an
    #: emoji, never a rejected number.
    flag: str = ""
    #: Offered in the country-code selector. Plans outside the selector are
    #: still validated - learners paste ``+xx`` numbers from anywhere - they
    #: are just not listed in the dropdown, which stays short enough to scan.
    selectable: bool = True

    @property
    def digits(self) -> str:
        return self.code[1:]


#: Compiled once, at import, next to the pattern each plan is described by.
_PATTERNS: dict[str, re.Pattern[str]] = {}


def _plan(
    code: str, label: str, nsn: str, example: str, *, selectable: bool = True, flag: str = ""
) -> tuple[str, PhonePlan]:
    _PATTERNS[code] = re.compile(f"^{nsn}$")
    return code, PhonePlan(
        code=code, label=label, nsn=nsn, example=example, selectable=selectable, flag=flag
    )


#: One entry per country code. ``nsn`` matches the digits after the code.
#: Selectable entries lead, in the order the site's dropdown has always shown
#: them, because this insertion order *is* the order the selector renders.
PLANS: dict[str, PhonePlan] = dict([
    _plan("+91", "India", r"[1-9][0-9]{9}", "+91 98765 43210", flag="🇮🇳"),
    _plan("+1", "United States / Canada", r"[2-9][0-9]{2}[2-9][0-9]{6}", "+1 415 555 2671", flag="🇺🇸"),
    _plan("+44", "United Kingdom", r"(?:1[0-9]{8,9}|2[23478][0-9]{7,8}|7[1-9][0-9]{8})", "+44 7911 123456", flag="🇬🇧"),
    _plan("+61", "Australia", r"[2-9][0-9]{8}", "+61 412 345 678", flag="🇦🇺"),
    _plan("+49", "Germany", r"[1-9][0-9]{5,11}", "+49 151 23456789", flag="🇩🇪"),
    _plan("+33", "France", r"[1-9][0-9]{8}", "+33 6 12 34 56 78", flag="🇫🇷"),
    _plan("+65", "Singapore", r"[3689][0-9]{7}", "+65 8123 4567", flag="🇸🇬"),
    _plan("+971", "United Arab Emirates", r"[2-9][0-9]{7,8}", "+971 50 123 4567", flag="🇦🇪"),
    _plan("+81", "Japan", r"[5789][0-9]{8,9}", "+81 90 1234 5678", flag="🇯🇵"),
    _plan("+82", "South Korea", r"[1-6][0-9]{7,9}", "+82 10 1234 5678", flag="🇰🇷"),
    _plan("+86", "China", r"[1-9][0-9]{9,10}", "+86 138 1234 5678", flag="🇨🇳"),
    _plan("+55", "Brazil", r"[1-9][0-9]{8,10}", "+55 11 96123 4567", flag="🇧🇷"),
    _plan("+27", "South Africa", r"[1-9][0-9]{8}", "+27 82 123 4567", flag="🇿🇦"),
    _plan("+234", "Nigeria", r"[1-9][0-9]{7,9}", "+234 801 234 5678", flag="🇳🇬"),
    _plan("+7", "Russia / Kazakhstan", r"[3489][0-9]{9}", "+7 912 345 67 89", flag="🇷🇺"),
    _plan("+20", "Egypt", r"1[0125][0-9]{8}", "+20 100 123 4567", selectable=False),
    _plan("+31", "Netherlands", r"[1-9][0-9]{8}", "+31 6 12345678", selectable=False),
    _plan("+34", "Spain", r"[5-9][0-9]{8}", "+34 612 345 678", selectable=False),
    _plan("+39", "Italy", r"[03][0-9]{8,10}", "+39 333 123 4567", selectable=False),
    _plan("+60", "Malaysia", r"[13-9][0-9]{7,9}", "+60 12 345 6789", selectable=False),
    _plan("+62", "Indonesia", r"[1-9][0-9]{7,11}", "+62 812 3456 7890", selectable=False),
    _plan("+63", "Philippines", r"[2-9][0-9]{7,9}", "+63 917 123 4567", selectable=False),
    _plan("+64", "New Zealand", r"[2-9][0-9]{7,9}", "+64 21 123 4567", selectable=False),
    _plan("+90", "Turkey", r"[2-9][0-9]{9}", "+90 532 123 45 67", selectable=False),
    _plan("+92", "Pakistan", r"[2-9][0-9]{8,10}", "+92 300 1234567", selectable=False),
    _plan("+94", "Sri Lanka", r"[1-9][0-9]{8,9}", "+94 71 234 5678", selectable=False),
    _plan("+353", "Ireland", r"[1-9][0-9]{8,9}", "+353 85 123 4567", selectable=False),
    _plan("+966", "Saudi Arabia", r"[1-9][0-9]{8}", "+966 50 123 4567", selectable=False),
    _plan("+977", "Nepal", r"[1-9][0-9]{7,9}", "+977 98 1234567", selectable=False),
    _plan("+880", "Bangladesh", r"[1-9][0-9]{7,9}", "+880 17 1234 5678", selectable=False),
])


#: The selector list, in the order the dropdown shows it.
SELECTOR_PLANS: tuple[PhonePlan, ...] = tuple(plan for plan in PLANS.values() if plan.selectable)
SELECTOR_CODES: tuple[tuple[str, str], ...] = tuple(
    (plan.code, f"{plan.label} ({plan.code})") for plan in SELECTOR_PLANS
)

#: Numbers nobody was ever issued: one digit typed ten times, or a short run
#: such as ``1234567``. Whole-NSN runs are only refused while they are short,
#: because ``9876543210`` - a real, assignable Indian mobile - is the example
#: number in half the telecom documentation in the world, including this
#: repository's own tests. A shape heuristic that rejects the sample number
#: rejects learners, so ownership stays the job of the 6-digit code.
_REPEATED = re.compile(r"^([0-9])\1{3,}$")


def looks_invented(digits: str) -> bool:
    """True for the placeholder shapes people type to dismiss the field."""
    if len(digits) < 4:
        return True
    if _REPEATED.fullmatch(digits):
        return True
    if len(digits) <= 8:
        ascending = "0123456789"[: len(digits)]
        descending = "9876543210"[9 - len(digits):]
        if digits in (ascending, descending):
            return True
        steps = [int(digits[i + 1]) - int(digits[i]) for i in range(len(digits) - 1)]
        if steps and (all(step == 1 for step in steps) or all(step == -1 for step in steps)):
            return True
    return False


_INVENTED_HINT = (
    "That looks like a placeholder rather than a phone number. Type the number as it is written "
    "on your SIM; we will send a 6-digit code to it to prove it is yours."
)


def policy() -> dict:
    """The numbering plans as JSON-safe values, for the browser mirror.

    See :func:`email_rules.policy` for why the exported copy is given the table
    rather than a second handwritten list. Patterns are anchored here because
    JavaScript tests them against the whole string.
    """
    return {
        "minDigits": MIN_E164_DIGITS,
        "maxDigits": MAX_E164_DIGITS,
        "plans": {
            plan.code: {"label": plan.label, "nsn": f"^{plan.nsn}$", "example": plan.example}
            for plan in PLANS.values()
        },
    }


def plan_for(country_code: str) -> PhonePlan | None:
    return PLANS.get(country_code)


def split_e164(normalized: str) -> tuple[str, str] | None:
    """Split ``+919876543210`` into ``("+91", "9876543210")``.

    The country code is matched greedily against the codes we know, then
    against the one-, two- and three-digit lengths, because an unlisted code
    still has to be split before it can be checked.
    """
    if not normalized.startswith("+"):
        return None
    digits = normalized[1:]
    if not digits or not _NSN_ALLOWED.fullmatch(digits):
        return None
    candidates = [digits[:length] for length in range(1, MAX_COUNTRY_CODE_DIGITS + 1)]
    for candidate in candidates:
        if f"+{candidate}" in PLANS:
            return f"+{candidate}", digits[len(candidate):]
    for candidate in candidates:
        code = f"+{candidate}"
        if _CODE_RE.fullmatch(code) and len(digits) > len(candidate):
            return code, digits[len(candidate):]
    return None


def validate_e164(normalized: str) -> str:
    """Check a ``+``-prefixed number against E.164 and the country's plan."""
    total = len(normalized) - 1
    if not normalized.startswith("+") or not _NSN_ALLOWED.fullmatch(normalized[1:]):
        raise PhoneFormatError("Enter a phone number in international format, for example +91 98765 43210.")
    if total < MIN_E164_DIGITS or total > MAX_E164_DIGITS:
        raise PhoneFormatError(
            f"A phone number has between {MIN_E164_DIGITS} and {MAX_E164_DIGITS} digits including the "
            "country code. Count the digits you typed."
        )
    parts = split_e164(normalized)
    if parts is None:
        raise PhoneFormatError("That country code is not recognised. Start the number with + and its code, for example +91.")
    code, nsn = parts
    plan = PLANS.get(code)
    if plan is None:
        # Unlisted destination: E.164 length plus the invented-number guard is
        # all we can honestly say about it.
        if looks_invented(nsn):
            raise PhoneFormatError(_INVENTED_HINT)
        return normalized
    if not _PATTERNS[plan.code].fullmatch(nsn):
        raise PhoneFormatError(
            f"{_length_hint(plan, nsn)}",
            hint=plan.example,
        )
    if looks_invented(nsn):
        raise PhoneFormatError(_INVENTED_HINT, hint=plan.example)
    return normalized


def _length_hint(plan: PhonePlan, nsn: str) -> str:
    """Say what is missing, in digits, rather than repeating "invalid format"."""
    typed = len(nsn)
    if not nsn:
        return f"Enter the national number after {plan.code}."
    digits = f"{typed} digit{'s' if typed != 1 else ''}"
    if plan.code in ("+1", "+7"):
        return (
            f"{plan.label} numbers are 10 digits and the area code cannot start with 0 or 1. "
            f"You typed {digits} after {plan.code}; a valid example is {plan.example}."
        )
    return (
        f"{plan.label} numbers look like {plan.example}. The {digits} you typed after "
        f"{plan.code} do not match that plan."
    )
