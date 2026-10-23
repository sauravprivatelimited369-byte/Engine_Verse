"""Input validation.

Small, explicit validators instead of a schema library - every value that
crosses a trust boundary is checked here, and unknown keys are rejected rather
than silently ignored.

Two of these validators carry real policy, because two fields decide whether the
platform can reach a learner at all:

* :func:`validate_email` delegates to :mod:`.email_rules`, which checks the
  syntax SMTP actually allows, refuses expiring burner inboxes and near-miss
  spellings of Gmail, and (on sign-up, when the deployment asks for it) proves
  the domain accepts mail before an account is created.
* :func:`validate_phone` and :func:`normalize_phone_with_country_code` delegate
  to :mod:`.phone_rules`, which knows that an Indian mobile is ten digits and a
  NANP area code cannot start with 0 or 1. E.164 alone accepted ``+9112345``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import email_rules, phone_rules
from .sanitize import sanitize_text

#: There is deliberately no ``EMAIL_RE`` or ``PHONE_RE`` here. A single regex
#: is how both fields ended up accepting anything with an @@ and eight digits:
#: the answer lives in :mod:`.email_rules` and :mod:`.phone_rules`, and callers
#: have to go through it.
USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,22}[a-z0-9])?$")
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,94}[a-z0-9])?$")
COUNTRY_CODE_RE = re.compile(r"^\+[1-9][0-9]{0,3}$")
_PHONE_ALLOWED = frozenset("0123456789 +-().")

#: The dropdown, generated from the same table the validator checks against, so
#: an option can never appear in a form without a numbering plan behind it.
#: ``COUNTRY_PLANS`` is the same list with the flag and the example number, for
#: the templates that render the selector and its hint.
COUNTRY_CODES: tuple[tuple[str, str], ...] = phone_rules.SELECTOR_CODES
COUNTRY_PLANS = phone_rules.SELECTOR_PLANS

EmailFormatError = email_rules.EmailFormatError
PhoneFormatError = phone_rules.PhoneFormatError

RESERVED_USERNAMES = {
    "admin", "root", "engineverse", "api", "www", "mail", "support", "login",
    "register", "dashboard", "profile", "settings", "null", "undefined",
    "system", "about", "help", "search", "community", "projects", "practice",
}


class ValidationError(Exception):
    status_code = 422

    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.fields = fields or {}


@dataclass
class Errors:
    items: dict[str, str] = field(default_factory=dict)

    def add(self, key: str, message: str) -> None:
        self.items.setdefault(key, message)

    @property
    def ok(self) -> bool:
        return not self.items

    def raise_if_any(self, message: str = "Please fix the highlighted fields.") -> None:
        if not self.ok:
            raise ValidationError(message, self.items)


def normalize_phone(value: Any) -> str:
    """Normalise display punctuation without inventing a country code.

    A plus is allowed anywhere in a pasted number because people commonly copy
    values such as ``(+44) ...``. It is moved to the front; all other allowed
    punctuation is discarded. Letters and every other character are refused,
    rather than silently stripped into a different number.
    """
    raw = str(value or "").strip()
    if not raw or any(char not in _PHONE_ALLOWED for char in raw):
        raise ValidationError("Enter a valid phone number.", {"phone": "Enter a valid phone number."})
    digits = "".join(char for char in raw if char.isdigit())
    if not digits:
        raise ValidationError("Enter a valid phone number.", {"phone": "Enter a valid phone number."})
    return ("+" if "+" in raw else "") + digits


def _report(errors: Errors | None, key: str, message: str) -> str:
    """Collect a field error when a form is being filled, raise when it is not."""
    if errors is not None:
        errors.add(key, message)
        return ""
    raise ValidationError(message, {key: message})


def validate_phone(value: Any, key: str = "phone", errors: Errors | None = None) -> str:
    """Accept a full international number, checked against its country's plan.

    Punctuation is tolerated, digits are not guessed at: ``(+44) 7911 123456``
    is fine, ``+9112345`` is not, and neither is a number that matches the
    format of the wrong country for the dialling code it claims.
    """
    try:
        normalized = normalize_phone(value)
    except ValidationError:
        return _report(
            errors, key,
            "Enter a phone number in international format, for example +91 98765 43210.",
        )
    try:
        return phone_rules.validate_e164(normalized)
    except phone_rules.PhoneFormatError as exc:
        return _report(errors, key, exc.message)


def normalize_phone_with_country_code(
    value: Any,
    country_code: Any = "+91",
    key: str = "phone",
    errors: Errors | None = None,
) -> str:
    """Combine a country dialing code (e.g. ``+91``, ``+1``) with a subscriber number.

    If ``value`` already starts with ``+``, validates it directly as E.164.
    Otherwise strips leading trunk ``0`` and prepends the validated country code.
    """
    raw = str(value or "").strip()
    if not raw:
        return _report(
            errors, key,
            "Enter a mobile number with country code, for example +91 98765 43210 or 98765 43210 with +91.",
        )
    if "+" in raw:
        return validate_phone(raw, key=key, errors=errors)
    cc_raw = str(country_code or "+91").strip().replace(" ", "")
    if cc_raw and not cc_raw.startswith("+"):
        cc_raw = "+" + cc_raw
    if not COUNTRY_CODE_RE.fullmatch(cc_raw):
        return _report(errors, key, "Select a valid country code (for example +91, +1, +44).")
    if any(char not in _PHONE_ALLOWED for char in raw):
        return _report(errors, key, "A mobile number contains digits, spaces, dots, dashes or brackets only.")
    digits = "".join(char for char in raw if char.isdigit())
    if digits.startswith("00"):
        # 00 is the international prefix most of the world dials before a country
        # code, so "0091-98765-43210" is the same number as "+919876543210". It
        # is read as that instead of being mistaken for a trunk-zero typo, which
        # is what the bare lstrip below was for.
        return validate_phone("+" + digits[2:], key=key, errors=errors)
    digits = digits.lstrip("0")
    if not digits:
        return _report(errors, key, "Enter the mobile number that follows the country code.")
    try:
        combined = phone_rules.validate_e164(f"{cc_raw}{digits}")
    except phone_rules.PhoneFormatError as exc:
        return _report(errors, key, exc.message)
    return combined


def validate_email(
    value: Any,
    key: str = "email",
    errors: Errors | None = None,
    *,
    deliverability: str = "off",
) -> str:
    """Normalise and check an address; ``deliverability`` adds the DNS probe.

    ``deliverability`` is off by default on purpose. Sign-in and recovery look an
    address *up*, and an account whose domain loses its mail servers years later
    must still be able to sign in and still get a reset link. Only the paths that
    create or replace an address pass ``"fallback"`` (or ``"mx"``), so the check
    that can refuse a brand-new account is the one that costs nothing to answer.
    """
    try:
        return email_rules.validate(value, deliverability=deliverability)
    except email_rules.EmailFormatError as exc:
        return _report(errors, key, exc.message)


def validate_signin_identifier(value: Any) -> str:
    """Check the *shape* of what was typed into the sign-in field, not its owner.

    The field accepts three different things - an address, a username, or the
    mobile number an SMS code is sent to - so it is checked per shape rather
    than against a union that would accept anything. An address that cannot
    exist and a number with no country behind it are refused here, with the
    reason; a digit-only string is left alone because it is as likely to be a
    numeric username as a badly written number, and the lookup tries both.

    None of this reveals whether an account exists, which is why it can be said
    plainly. The answers that must stay vague are the ones that compare a shape
    against the users table.
    """
    text = str(value or "").strip()
    if not text:
        message = "Enter the email, username or mobile number on your account."
        raise ValidationError(message, {"identifier": message})
    if "@" in text:
        return validate_email(text, "identifier")
    if text.startswith("+"):
        return validate_phone(text, "identifier")
    return text.lower()



def validate_username(value: Any, key: str = "username", errors: Errors | None = None) -> str:
    text = str(value or "").strip().lower()
    if not USERNAME_RE.match(text):
        message = "Use 3-24 characters: letters, numbers, dot, dash or underscore."
    elif text in RESERVED_USERNAMES:
        message = "That username is reserved. Please choose another."
    else:
        message = ""
    if message:
        if errors:
            errors.add(key, message)
        else:
            raise ValidationError(message, {key: message})
        return ""
    return text


def validate_password(value: Any, key: str = "password", errors: Errors | None = None, min_length: int = 10) -> str:
    text = str(value or "")
    if len(text) < min_length:
        message = f"Use at least {min_length} characters."
    elif len(text) > 256:
        message = "Use at most 256 characters."
    else:
        message = ""
    if message:
        if errors:
            errors.add(key, message)
        else:
            raise ValidationError(message, {key: message})
    return text


def validate_slug(value: Any, key: str = "slug", errors: Errors | None = None) -> str:
    text = str(value or "").strip().lower()
    if not SLUG_RE.match(text):
        message = "Use lower-case letters, numbers and dashes."
        if errors:
            errors.add(key, message)
        else:
            raise ValidationError(message, {key: message})
        return ""
    return text


def validate_choice(value: Any, allowed: tuple[str, ...] | list[str], key: str, errors: Errors, default: str | None = None) -> str:
    text = str(value or default or "")
    if text not in allowed:
        if default is not None and not text:
            return default
        errors.add(key, f"Choose one of: {', '.join(allowed)}.")
        return default or ""
    return text


def validate_int(value: Any, key: str, errors: Errors, *, minimum: int, maximum: int, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors.add(key, "Enter a whole number.")
        return default
    if number < minimum or number > maximum:
        errors.add(key, f"Enter a value between {minimum} and {maximum}.")
        return default
    return number


def validate_text(value: Any, key: str, errors: Errors, *, min_length: int = 0, max_length: int = 2000, required: bool = True) -> str:
    text = sanitize_text(str(value or ""), max_length)
    if required and len(text) < min_length:
        errors.add(key, f"Enter at least {min_length} characters.")
        return ""
    if len(text) > max_length:
        errors.add(key, f"Keep it under {max_length} characters.")
    return text


def require_fields(payload: dict, fields: tuple[str, ...]) -> Errors:
    errors = Errors()
    for name in fields:
        if not str(payload.get(name) or "").strip():
            errors.add(name, "This field is required.")
    return errors


def as_dict(payload: Any) -> dict:
    """Rejects non-object JSON bodies outright."""
    if not isinstance(payload, dict):
        raise ValidationError("Expected a JSON object.")
    return payload


Rule = Callable[[Any, Errors], Any]
