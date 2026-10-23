"""Is this address an email address, and is it somewhere mail can arrive?

Two different questions, and the platform used to ask neither properly. The
old rule was ``^[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}$``, which accepted
``a..b@example.com`` (no such mailbox can be named), ``trailing.@example.com``,
``user@-bad.com``, ``hello@10minutemail.com`` (a burner that deletes its inbox in
ten minutes) and ``fake@gmial.com`` (a domain with no mail servers at all). The
result is accounts nobody can be reached at: password resets bounce, sign-in
codes go nowhere, and the learner blames the site.

Three layers, cheapest first, and each one says what to fix:

1. **Syntax** - what RFC 5321 allows in an address, tightened to the form mail
   providers actually accept: no empty or doubled dots, no hyphen at either end
   of a label, a top-level domain that is alphabetic and at least two
   characters, and length ceilings on the local part, the labels and the whole
   address.
2. **Policy** - disposable inboxes that expire before a learner finishes a
   course, and near-miss spellings of the free providers everyone types
   (``gmial.com``, ``gmai.com``, ``gmail.con``), refused with the correction
   rather than a shrug.
3. **Deliverability** - a DNS ``MX`` lookup, with the ``A`` fallback RFC 5321
   prescribes, so ``someone@nowhere12345.com`` is refused because that domain
   does not exist. Skipped when the environment has no resolver, when the
   lookup times out, or when the deployment switched it off: a learner must
   never be locked out because this process could not reach port 53. Reserved
   domains (``example.com``, ``*.test``, ``*.localhost``, intranet names) are
   always allowed, because seeded demo accounts and self-hosted school
   networks use them on purpose.

Layer 3 runs only where an address is *created* - sign-up and a new number or
address in Settings. Sign-in and password recovery look addresses up instead,
so an account whose domain loses its MX record later can still sign in and
still receive a reset.
"""
from __future__ import annotations

import random
import re
import socket
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path

MAX_EMAIL_LENGTH = 254
MAX_LOCAL_LENGTH = 64
MAX_LABEL_LENGTH = 63
MAX_DOMAIN_LENGTH = 253

#: Dot-atom text as SMTP accepts it. Deliberately stricter than RFC 5321: quoted
#: local parts and special characters are what filters and mail providers reject,
#: so an account that stores one cannot be mailed anyway.
_LOCAL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_TLD_RE = re.compile(r"^[A-Za-z]{2,}$")
_IP_LITERAL_RE = re.compile(r"^\[(?:[0-9.]{7,15}|[0-9A-Fa-f:]{2,45})\]$")

#: Domains that exist only to receive a code and then vanish. Not a full
#: commercial blocklist: an up-to-date list is a subscription, and this
#: repository deliberately has no third-party service. It is the set that
#: actually shows up on a student platform.
_DISPOSABLE_FILE = Path(__file__).with_name("disposable_email_domains.txt")

#: The providers a learner is most likely reaching for, used for both the
#: "you left out the domain" check and typo correction.
KNOWN_PROVIDERS: tuple[str, ...] = (
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "zoho.com", "yandex.com",
    "fastmail.com", "gmx.com", "mail.com", "rediffmail.com",
)

#: Spellings seen often enough to name directly. Anything else within two
#: characters of a known provider is caught by :func:`near_miss` instead.
FREEMAIL_TYPOS: dict[str, str] = {
    "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gnail.com": "gmail.com",
    "gmile.com": "gmail.com", "gmaill.com": "gmail.com", "gmail.co": "gmail.com",
    "gmail.cm": "gmail.com", "gmail.con": "gmail.com", "gmail.vom": "gmail.com",
    "gmail.om": "gmail.com", "gmaill.con": "gmail.com", "gmil.com": "gmail.com",
    "gma.com": "gmail.com", "gmail.com.com": "gmail.com", "gmailm.com": "gmail.com",
    "gnamil.com": "gmail.com", "hotmial.com": "hotmail.com", "hotmai.com": "hotmail.com",
    "hotmil.com": "hotmail.com", "hotmal.com": "hotmail.com", "hotmali.com": "hotmail.com",
    "hotmall.com": "hotmail.com", "hormail.com": "hotmail.com",
    "outlok.com": "outlook.com", "outllok.com": "outlook.com", "outloo.com": "outlook.com",
    "outlin.com": "outlook.com", "yahooo.com": "yahoo.com", "yaho.com": "yahoo.com",
    "yahho.com": "yahoo.com", "yahoo.con": "yahoo.com", "icloud.con": "icloud.com",
    "coloud.com": "icloud.com", "icloude.com": "icloud.com", "protonmall.com": "proton.me",
}

#: Real providers one edit away from something in :data:`KNOWN_PROVIDERS`. They
#: must never be "corrected", or a learner with a legitimate address is told
#: their address is a typo.
_LOOKALIKE_EXCEPTIONS = frozenset({
    "mail.com", "gmx.com", "zoho.com", "me.com", "mc.com", "juno.com",
    "proton.me", "fastmail.com", "tutanota.com", "web.de", "gmx.de", "yandex.ru",
})

#: RFC 6761 special-use names. Mail cannot leave the network for these, which is
#: exactly why the seed data and a school intranet use them.
RESERVED_SUFFIXES = ("example", "test", "invalid", "localhost", "local")
#: The RFC 2606 documentation domains, which are real, resolvable and publish
#: "do not mail here" on purpose. The seed data and most of the test suite live
#: on them.
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")

DNS_TYPE_MX = 15
DNS_CLASS_IN = 1
_DNS_TIMEOUT_SECONDS = 0.6
_DNS_SERVERS: tuple[str, ...] = ()
_CACHE_LOCK = threading.Lock()
#: domain -> (expires_at, verdict). Small and TTL-bound: a registration burst
#: from one college repeats the same handful of domains.
_CACHE: dict[str, tuple[float, "Verdict"]] = {}
_CACHE_TTL_SECONDS = 900
_CACHE_NEGATIVE_TTL_SECONDS = 120
_CACHE_MAX_ENTRIES = 2048


class EmailFormatError(ValueError):
    """The address is not one we can mail, with the reason a learner can act on."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion


@dataclass(frozen=True)
class Verdict:
    """What the deliverability probe concluded. ``unknown`` means "do not refuse"."""

    state: str  # "deliverable" | "no-mail" | "unknown"
    detail: str = ""

    @property
    def refuses(self) -> bool:
        return self.state == "no-mail"


@dataclass(frozen=True)
class ParsedEmail:
    local: str
    domain: str

    @property
    def text(self) -> str:
        return f"{self.local}@{self.domain}"


class BadDnsResponse(Exception):
    """The reply was truncated, mismatched, or otherwise not usable."""


# ---------------------------------------------------------------------------
# Layer 1: syntax
# ---------------------------------------------------------------------------

def policy() -> dict:
    """The rules the browser mirror needs, as JSON-safe values.

    ``pages-live.js`` enforces the same checks on the exported (serverless) copy
    of the site. Duplicating the *algorithm* there is a deliberate trade;
    duplicating the *data* would be a bug waiting to happen, so the exported
    pages read this blob instead and the JS keeps only one set of constants as a
    fallback for a cached page paired with a newer script.
    """
    return {
        "maxLength": MAX_EMAIL_LENGTH,
        "localMaxLength": MAX_LOCAL_LENGTH,
        "localRe": _LOCAL_RE.pattern,
        "labelRe": _LABEL_RE.pattern,
        "tldRe": _TLD_RE.pattern,
        "reservedTlds": list(RESERVED_SUFFIXES),
        "reservedDomains": list(RESERVED_DOMAINS),
        "providers": list(KNOWN_PROVIDERS),
        "lookalikes": sorted(_LOOKALIKE_EXCEPTIONS),
        "typos": {key: FREEMAIL_TYPOS[key] for key in sorted(FREEMAIL_TYPOS)},
        "disposable": sorted(disposable_domains()),
    }


def parse(value: object) -> ParsedEmail:
    """Return the normalised address or raise :class:`EmailFormatError`.

    Normalising here (lower-case, trimmed) is what makes ``Asha@Example.COM``
    and ``asha@example.com`` the same account; the lookup path lower-cases too,
    and the column is ``CITEXT`` on Postgres, so all three have to agree.
    """
    text = str(value or "").strip()
    if not text:
        raise EmailFormatError("Enter your Gmail or email address.")
    if len(text) > MAX_EMAIL_LENGTH:
        raise EmailFormatError(
            f"An email address is at most {MAX_EMAIL_LENGTH} characters. Yours is {len(text)}."
        )
    if text.count("@") != 1:
        raise EmailFormatError(
            "An email address has one @ sign, for example you@gmail.com. "
            "Check for a missing or extra one."
        )
    local, _, domain = text.lower().partition("@")
    # Trailing dots are how some address books write a fully-qualified name, and
    # the local part is lower-cased deliberately: mail delivery treats the
    # mailbox case-insensitively in practice, this platform's lookups
    # lower-case, and users.email must therefore store what the lookup expects.
    domain = domain.strip().rstrip(".")
    local = local.strip()
    if not local:
        raise EmailFormatError("Add the part before the @, for example saurav@gmail.com.")
    if len(local) > MAX_LOCAL_LENGTH:
        raise EmailFormatError(
            f"The part before the @ is limited to {MAX_LOCAL_LENGTH} characters; yours has {len(local)}."
        )
    if not _LOCAL_RE.match(local):
        raise EmailFormatError(
            "The part before the @ has a character an email address cannot start or end with, "
            f"or two dots in a row: {local}"
        )
    if not domain:
        raise EmailFormatError("Add the domain after the @, for example gmail.com.")
    if _IP_LITERAL_RE.match(domain):
        return ParsedEmail(local, domain.lower())
    if "@" in domain or any(char.isspace() for char in domain):
        raise EmailFormatError("An email address cannot contain spaces or a second @ sign.")
    if domain.startswith("[") or "]" in domain:
        raise EmailFormatError("That address ends in a mail-server bracket this site cannot deliver to.")
    if len(domain) > MAX_DOMAIN_LENGTH:
        raise EmailFormatError("The part after the @ is too long to be a real domain.")

    labels = domain.split(".")
    for label in labels:
        if not label:
            raise EmailFormatError(
                f"There is an empty piece in {domain}. Remove the extra dot and try again."
            )
        if len(label) > MAX_LABEL_LENGTH:
            raise EmailFormatError(f"Each part of a domain is at most {MAX_LABEL_LENGTH} characters.")
        if not _LABEL_RE.match(label):
            raise EmailFormatError(
                f"'{label}' is not a valid domain part: it must be letters, digits and single "
                "dashes, and cannot start or end with a dash or underscore."
            )
    if len(labels) == 1:
        raise EmailFormatError(
            _single_label_message(labels[0])
        )
    if not _TLD_RE.match(labels[-1]):
        raise EmailFormatError(
            f"'{labels[-1]}' is not a domain extension. A Gmail address ends in gmail.com, "
            "a college address ends in .edu or the country's suffix."
        )
    return ParsedEmail(local, domain)


def _single_label_message(domain: str) -> str:
    provider = next((name for name in KNOWN_PROVIDERS if name.split(".")[0] == domain), "")
    if provider:
        return f"Did you mean {provider}? A {domain} address needs its domain after the dot."
    if domain in RESERVED_SUFFIXES:
        return (
            f"'{domain}' on its own is not an address this site can mail. Use the full form, "
            "for example name@gmail.com or name@college.edu."
        )
    return (
        f"'{domain}' is not a domain the internet can route mail to. Use the full address, "
        "for example name@gmail.com or name@college.edu."
    )


# ---------------------------------------------------------------------------
# Layer 2: known-bad domains and typos
# ---------------------------------------------------------------------------

_disposable_cache: frozenset[str] | None = None


def disposable_domains() -> frozenset[str]:
    """The blocklist, loaded once from the file next to this module.

    A line that is not a plain domain is dropped instead of honoured, so a
    stray space or a bracketed form in that file cannot quietly become a rule
    that blocks - or fails to block - a real provider.
    """
    global _disposable_cache
    if _disposable_cache is None:
        names: set[str] = set()
        try:
            lines = _DISPOSABLE_FILE.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:  # pragma: no cover - packaging guard
            lines = []
        for raw in lines:
            line = raw.strip().lower().rstrip(".")
            if not line or line.startswith("#"):
                continue
            labels = line.split(".")
            if (
                len(labels) >= 2
                and all(_LABEL_RE.match(label) for label in labels)
                and _TLD_RE.match(labels[-1])
            ):
                names.add(line)
        _disposable_cache = frozenset(names)
    return _disposable_cache


def is_disposable(domain: str) -> bool:
    return domain in disposable_domains()


def edit_distance(left: str, right: str, limit: int = 2) -> int:
    """Bounded Levenshtein distance; ``limit + 1`` means "further apart than limit"."""
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, char in enumerate(left, start=1):
        current = [i]
        best = i
        for j, other in enumerate(right, start=1):
            cost = 0 if char == other else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            best = min(best, value)
        if best > limit:
            return limit + 1
        previous = current
    return previous[-1]


def near_miss(domain: str) -> str:
    """A known provider within two edits of ``domain``, or an empty string.

    Only used to explain a domain that cannot receive mail: a well-formed but
    unusual address such as ``kmail.com`` is never refused on a hunch.
    """
    if domain in _LOOKALIKE_EXCEPTIONS or domain in KNOWN_PROVIDERS:
        return ""
    best, best_distance = "", 3
    for provider in KNOWN_PROVIDERS:
        distance = edit_distance(domain, provider, limit=2)
        if distance and distance < best_distance:
            best, best_distance = provider, distance
    return best


def is_reserved(domain: str) -> bool:
    """Test, example and intranet names, plus IP literals. Never probed by DNS.

    ``example.com`` publishes an explicit "no mail here" record and ``*.test``
    cannot be resolved at all, so probing them would refuse the seeded demo
    accounts and every school network that runs EngineVerse offline. That is
    the trade this function makes deliberately: the reserved names are believed
    rather than checked, and only on the *lookup* side of the check -
    :func:`parse` still demands they be shaped like addresses.
    """
    if _IP_LITERAL_RE.match(domain):
        return True
    if "." not in domain:
        return True
    if domain in RESERVED_DOMAINS:
        return True
    if domain.rsplit(".", 1)[-1] in RESERVED_SUFFIXES:
        return True
    # ".co.in"-style public suffixes are not special; ".mail.internal" is.
    return domain.endswith((".local", ".internal", ".intranet", ".lan", ".home", ".corp"))


def policy_check(parsed: ParsedEmail) -> None:
    """Layer 2. Raises :class:`EmailFormatError` for burners and typos."""
    domain = parsed.domain
    if is_disposable(domain):
        raise EmailFormatError(
            "That is a temporary inbox, which stops working before your course does. "
            "Use an address you will still have next month - your password reset goes there."
        )
    correction = FREEMAIL_TYPOS.get(domain, "")
    if correction:
        raise EmailFormatError(
            f"'{domain}' is not a mail provider - did you mean {correction}?",
            suggestion=correction,
        )


# ---------------------------------------------------------------------------
# Layer 3: can mail arrive?
# ---------------------------------------------------------------------------

def _resolvers() -> tuple[str, ...]:
    global _DNS_SERVERS
    if _DNS_SERVERS:
        return _DNS_SERVERS
    servers: list[str] = []
    try:
        for raw in Path("/etc/resolv.conf").read_text(encoding="utf-8").splitlines():
            parts = raw.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                address = parts[1].split("%", 1)[0]
                if ":" in address:
                    continue  # IPv6-only resolvers are rare here; v4 keeps the packet simple.
                socket.inet_aton(address)
                servers.append(address)
    except (OSError, ValueError):
        servers = []
    if not servers:
        servers = ["8.8.8.8", "1.1.1.1"]  # documented fallbacks, not a preference
    _DNS_SERVERS = tuple(servers[:2])
    return _DNS_SERVERS


def _encode_name(name: str) -> bytes:
    out = bytearray()
    for label in name.split("."):
        if not label:
            continue
        encoded = label.encode("idna", "strict") if not label.isascii() else label.encode("ascii")
        out.append(len(encoded))
        out.extend(encoded)
    out.append(0)
    return bytes(out)


def _read_name(data: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    labels: list[str] = []
    while True:
        if offset >= len(data):
            raise BadDnsResponse("name ran past the end of the packet")
        length = data[offset]
        if length == 0:
            return ".".join(labels), offset + 1
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise BadDnsResponse("truncated compression pointer")
            if depth > 4:
                raise BadDnsResponse("compression loop")
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            tail, _ = _read_name(data, pointer, depth + 1)
            if tail:
                labels.extend(tail.split("."))
            return ".".join(labels), offset + 2
        if length & 0xC0:
            raise BadDnsResponse("unsupported label label type")
        if offset + 1 + length > len(data):
            raise BadDnsResponse("label runs past the end of the packet")
        labels.append(data[offset + 1:offset + 1 + length].decode("ascii", "replace"))
        offset += 1 + length


def _mx_exchanges(domain: str, resolver: str) -> list[tuple[int, str]] | None:
    """Ask one resolver for MX records. ``None`` means "no answer from it"."""
    try:
        transaction = random.randrange(0, 0xFFFF)
        header = struct.pack(">HHHHHH", transaction, 0x0100, 1, 0, 0, 0)
        question = _encode_name(domain) + struct.pack(">HH", DNS_TYPE_MX, DNS_CLASS_IN)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(_DNS_TIMEOUT_SECONDS)
            sock.sendto(header + question, (resolver, 53))
            data, _peer = sock.recvfrom(4096)
        if len(data) < 12:
            raise BadDnsResponse("short header")
        got_id, flags, questions, answers, _authority, _additional = struct.unpack(">HHHHHH", data[:12])
        if got_id != transaction:
            raise BadDnsResponse("transaction id mismatch")
        rcode = flags & 0x000F
        if rcode == 3:
            return []  # NXDOMAIN is a real answer: this domain does not exist.
        if rcode:
            return None  # SERVFAIL and friends say nothing about the domain
        offset = 12
        for _ in range(questions):
            _name, offset = _read_name(data, offset)
            offset += 4
        records: list[tuple[int, str]] = []
        for _ in range(answers):
            _name, offset = _read_name(data, offset)
            if offset + 10 > len(data):
                raise BadDnsResponse("truncated record header")
            rtype, rclass, _ttl, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
            offset += 10
            if offset + rdlength > len(data):
                raise BadDnsResponse("truncated record data")
            rdata = data[offset:offset + rdlength]
            if rtype == DNS_TYPE_MX and rclass == DNS_CLASS_IN and len(rdata) >= 3:
                preference = struct.unpack(">H", rdata[:2])[0]
                exchange, _ = _read_name(data, offset + 2)
                records.append((preference, exchange.rstrip(".").lower()))
            offset += rdlength
        return sorted(records)
    except (OSError, struct.error, BadDnsResponse, UnicodeError, IndexError, ValueError):
        return None


def has_mail_route(domain: str) -> bool:
    """RFC 5321 fallback: a host with an address but no MX can still receive."""
    try:
        socket.getaddrinfo(domain, None, socket.AF_INET)
        return True
    except (socket.gaierror, UnicodeError, OSError):
        return False


def _cached(domain: str) -> Verdict | None:
    with _CACHE_LOCK:
        entry = _CACHE.get(domain)
        if entry is None:
            return None
        expires, verdict = entry
        if expires < time.monotonic():
            _CACHE.pop(domain, None)
            return None
        return verdict


def _store(domain: str, verdict: Verdict) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX_ENTRIES:
            _CACHE.clear()
        ttl = _CACHE_TTL_SECONDS if verdict.state != "unknown" else _CACHE_NEGATIVE_TTL_SECONDS
        _CACHE[domain] = (time.monotonic() + ttl, verdict)


def probe(domain: str, *, mode: str = "fallback") -> Verdict:
    """Does this domain accept mail?

    ``mode``:

    ``off``
        Never asked - the caller decides this (the test suite, or an operator
        whose network has no resolver).
    ``fallback``
        Refuse only when neither MX nor A exists, which is the shape of a
        domain that was typed rather than read out loud.
    ``mx``
        Require at least one usable MX record. Stricter, and it does refuse
        some real domains that publish only an A record, so it is opt-in.
    """
    if mode in {"", "off", "none", "false"}:
        return Verdict("unknown", "deliverability check disabled")
    if is_reserved(domain):
        return Verdict("deliverable", "reserved or private domain, not probed")
    cached = _cached(domain)
    if cached is not None:
        return cached

    resolved = False
    exchanges: list[tuple[int, str]] = []
    for resolver in _resolvers():
        answer = _mx_exchanges(domain, resolver)
        if answer is None:
            continue
        resolved = True
        exchanges = answer
        break
    if not resolved:
        # No answer at all is this process's problem, not the learner's.
        return Verdict("unknown", "no DNS responder answered")

    usable = [exchange for _pref, exchange in exchanges if exchange]
    if usable:
        verdict = Verdict("deliverable", f"{len(usable)} mail server(s)")
    elif exchanges:
        verdict = Verdict("no-mail", "the domain publishes a 'no mail here' record")
    elif mode == "mx":
        verdict = Verdict("no-mail", "the domain publishes no MX record")
    elif has_mail_route(domain):
        verdict = Verdict("deliverable", "no MX record; the host itself answers for mail")
    else:
        verdict = Verdict("no-mail", "the domain resolves to neither a mail server nor a host")
    _store(domain, verdict)
    return verdict


def require_deliverable(parsed: ParsedEmail, *, mode: str = "fallback") -> None:
    """Layer 3, phrased for the person who typed the address."""
    domain = parsed.domain
    verdict = probe(domain, mode=mode)
    if not verdict.refuses:
        return
    provider = near_miss(domain)
    if provider:
        raise EmailFormatError(
            f"{domain} cannot receive email - did you mean {provider}?", suggestion=provider
        )
    raise EmailFormatError(
        f"{domain} cannot receive email ({verdict.detail}). Use the address exactly as it was "
        "given to you, for example name@gmail.com."
    )


def validate(value: object, *, deliverability: str = "off") -> str:
    """Full check: syntax, policy, and optionally deliverability.

    Returns the normalised address. Kept independent of
    :mod:`engineverse.security.validators` so this module can be imported by
    the seed script and by tests without dragging the form-error machinery in.
    """
    parsed = parse(value)
    policy_check(parsed)
    if deliverability != "off":
        require_deliverable(parsed, mode=deliverability)
    return parsed.text
