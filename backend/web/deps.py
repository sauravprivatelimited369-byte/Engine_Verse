"""Request-scoped helpers shared by the page and API routers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import quote, unquote
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from engineverse.code_format import color_code
from engineverse import assistant, auth, brand, db, markdown, navigation, progress
from engineverse.config import get_settings
from engineverse.security import csrf, phone_rules, validators
from engineverse.security.rbac import is_staff
from engineverse.security.sessions import SESSION_COOKIE, session_from_request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(_ROOT, "templates")
STATIC_DIR = os.path.join(_ROOT, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.autoescape = True
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True
templates.env.filters["code_color"] = color_code


# ---------------------------------------------------------------------------
# The signed-in viewer, flattened for templates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Viewer:
    id: str
    username: str
    email: str
    role: str
    full_name: str
    headline: str
    avatar_seed: str
    branch_id: str | None
    semester_id: int | None
    note_quality: str
    session_id: str
    current_streak: int
    total_xp: int
    level: int
    email_verified: int = 0

    @property
    def is_staff(self) -> bool:
        return is_staff(self.role)

    @property
    def initial(self) -> str:
        return (self.full_name or self.username or "?")[:1].upper()


def _viewer(current: auth.CurrentUser) -> Viewer:
    profile = current.profile
    return Viewer(
        id=current.user.id,
        username=current.user.username,
        email=current.user.email,
        role=current.user.role,
        full_name=profile.get("full_name") or current.user.username,
        headline=profile.get("headline") or "",
        avatar_seed=profile.get("avatar_seed") or current.user.username,
        branch_id=profile.get("branch_id"),
        semester_id=profile.get("semester_id"),
        note_quality=profile.get("note_quality") or "standard",
        session_id=current.session_id,
        current_streak=int(current.streak.get("current_streak") or 0),
        total_xp=int(current.streak.get("total_xp") or 0),
        level=int(current.streak.get("level") or 1),
        email_verified=int(current.user.email_verified or 0),
    )


def current_user(request: Request) -> Viewer | None:
    """Resolves the signed-in viewer from the session cookie, or None."""
    cached = getattr(request.state, "ev_user", "__unset__")
    if cached != "__unset__":
        return cached
    viewer = None
    current = auth.current_user_from_session(session_from_request(request))
    if current is not None:
        viewer = _viewer(current)
    request.state.ev_user = viewer
    return viewer


def require_user(request: Request) -> Viewer:
    viewer = current_user(request)
    if viewer is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return viewer


def session_id(request: Request) -> str:
    viewer = current_user(request)
    return viewer.session_id if viewer else csrf.anonymous_subject(request)


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

def _from_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _phone_example(country_code: Any) -> str:
    """The sample subscriber number for a dialling code, e.g. ``98765 43210``.

    Every phone field used to carry the same hardcoded ``9876543210`` placeholder,
    which is the wrong shape for the eleven other countries in the selector and
    made a learner type a ten-digit number where their plan wants nine.
    """
    plan = phone_rules.plan_for(str(country_code or "").strip() or "+91") or phone_rules.SELECTOR_PLANS[0]
    return plan.example.split(" ", 1)[1]


def _title_case(value: str) -> str:
    return (value or "").replace("-", " ").replace("_", " ").strip().title()


def _ago(ms: int | None) -> str:
    if not ms:
        return ""
    seconds = max(0, int(datetime.now(timezone.utc).timestamp() - int(ms) / 1000))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    if seconds < 2592000:
        return f"{seconds // 604800}w ago"
    return f"{seconds // 2592000}mo ago"


def _plural(count, singular: str, plural: str | None = None) -> str:
    """The word that agrees with ``count``.

    Templates used to write the plural unconditionally, so an instance holding
    one item rendered "1 question types", "1 replies" and "1 steps". Regular
    plurals are derived; irregular ones pass the second argument:
    ``{{ n | plural('reply', 'replies') }}``.
    """
    if plural is None:
        plural = singular + ("es" if singular.endswith(("s", "x", "z", "ch", "sh")) else "s")
    return singular if int(count) == 1 else plural


def register_filters() -> None:
    env = templates.env
    env.filters["plural"] = _plural
    env.filters["fromjson"] = _from_json
    env.filters["titlecase"] = _title_case
    env.filters["phone_example"] = _phone_example
    env.filters["ago"] = _ago
    env.filters["md"] = markdown.render
    env.filters["excerpt"] = markdown.excerpt
    env.filters["today"] = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")


register_filters()


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def navigation_context(path: str, signed_in: bool) -> dict[str, Any]:
    """The navigation, breadcrumbs and footer, from one table.

    Every surface that lists the site's pages - the desktop bar, the mobile menu,
    the bottom bar, the footer, the breadcrumb trail - is built here from
    ``engineverse.navigation``. They used to be written out separately in
    ``base.html`` and had drifted: the bar said "Practice" and the footer said
    "Practise", the bar said "Code" and the footer said "Learn to code" for the
    same URL, and the bottom bar highlighted two items at once because each link
    tested its own overlapping prefixes.

    Computing it here rather than in the template also means the tables are built
    once per request instead of once per include, and the test suite can assert
    on the same object the pages render.
    """
    items = navigation.primary_nav(signed_in)
    mobile = navigation.mobile_nav(signed_in)
    return {
        "nav_signed_in": signed_in,
        "nav_primary": items,
        "nav_mobile": mobile,
        "nav_active_mobile": navigation.active_mobile(path, mobile),
        # The mobile panel shows every group expanded, including the two
        # footer-only ones, so nothing on the site is more than two taps away.
        "nav_sections": navigation.index_sections(signed_in),
        "nav_account": [
            dest for dest in navigation.account_destinations(signed_in) if not dest.minor
        ],
        "footer_columns": navigation.footer_columns(signed_in),
        "footer_account": [
            dest for dest in navigation.account_destinations(signed_in) if not dest.minor
        ],
        "crumbs": navigation.breadcrumb_trail(path, signed_in=signed_in),
    }


def _static_export() -> bool:
    return os.environ.get("ENGINEVERSE_STATIC_EXPORT", "") == "1"


def _voice_api_base() -> str:
    """The public voice API origin baked into the static copy, or "".

    GitHub Pages is static, so calling the FastAPI voice endpoints requires an
    operator-supplied HTTPS origin. It is validated to a bare origin here: no
    path, query, credentials or fragment, so a bad repository variable cannot
    turn the reader into a request to an unrelated URL. Only origins are
    published; the API key stays on the server.
    """
    if not _static_export():
        return ""  # the live app serves /api/voice from its own origin
    raw = os.environ.get("ENGINEVERSE_VOICE_API_URL", "").strip().rstrip("/")
    if not raw:
        return ""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.username or parts.password or parts.query or parts.fragment:
        return ""
    if parts.path not in ("", "/"):
        return ""
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return ""
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1"}:
        return ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


def _issues_url() -> str:
    from engineverse import project

    return project.issues_url()


def _canonical_url(path: str) -> str:
    """Absolute public URL of a page, for <link rel="canonical"> and og:url."""
    clean = "/" + path.lstrip("/")
    if _static_export():
        from engineverse import project

        tail = clean.lstrip("/")
        if tail and not tail.endswith("/"):
            tail += "/"
        return project.pages_url() + tail
    return get_settings().site_url.rstrip("/") + clean


def _public_url(path: str) -> str:
    """Absolute URL of a public asset, for Open Graph and Twitter cards.

    Unlike ``_canonical_url`` this keeps a file path intact: no trailing slash
    is appended, because an og:image that ends in ``/icon-512.png/`` is a 404
    in every social preview.
    """
    clean = path if path.startswith("/") else "/" + path
    if _static_export():
        from engineverse import project

        return project.pages_url().rstrip("/") + clean
    return get_settings().site_url.rstrip("/") + clean


def base_context(request: Request, **extra: Any) -> dict[str, Any]:
    viewer = current_user(request)
    context: dict[str, Any] = {
        "request": request,
        "brand": brand.brand(),
        "user": viewer,
        "is_staff": viewer.is_staff if viewer else False,
        "csrf_token": csrf.issue_token(session_id(request)),
        "path": request.url.path,
        "query": dict(request.query_params),
        "flash": read_flash(request),
        "show_demo_accounts": get_settings().allows_demo_accounts,
        "mail_configured": bool(get_settings().smtp_url),
        "sms_configured": get_settings().sms_configured,
        "recovery_show_on_page": get_settings().recovery_show_on_page,
        "login_otp_required": get_settings().login_otp_required,
        "signin_required": get_settings().signin_required,
        "apk_url": get_settings().approved_apk_url,
        # The GitHub Pages export renders these same templates as a signed-out
        # visitor; this flag swaps account controls for device-local progress.
        "static_export": _static_export(),
        # The live app serves the voice API from its own origin. The static
        # export replaces this with a configured public API URL (see
        # scripts/export_pages.py); an empty value means "no backend pinned",
        # and the voice controls then do not appear at all on Pages.
        "voice_api_base": _voice_api_base(),
        "canonical_url": _canonical_url(request.url.path),
        "og_image": _public_url("/static/icons/icon-512.png"),
        "issues_url": _issues_url(),
        # The study assistant's browser-side description. In proxy mode this
        # names only the same-origin endpoint; the n8n webhook URL never enters
        # the context, and so never enters the HTML. export_pages.py swaps this
        # for the direct (Pages) variant at build time.
        "assistant": assistant.client_config(request.url.path),
        # A signed-out visitor on an instance where sign-in is compulsory can
        # only reach the account pages, so the layout drops the navigation,
        # search and footer links that would each bounce back to /login.
        "gated": get_settings().signin_required and viewer is None,
        "short_session_hours": get_settings().session_short_hours,
        "long_session_days": get_settings().session_max_age_days,
        # The country selector and its rules come from one table, so a form can
        # never offer a dialling code the validator would refuse. See
        # templates/_country_codes.html.
        "phone_countries": validators.COUNTRY_PLANS,
        "due_cards": 0,
        "unread": 0,
        # ``stats`` is the page's own counter bag and pages overwrite it (a
        # subject's topic count, a deck's due cards, the admin totals). The bar
        # needs the learner's numbers, so it reads a key no page writes.
        "stats": None,
        "learner": None,
    }
    # Navigation and breadcrumbs come from one table; see navigation_context().
    # ``crumb_leaf`` is how a page names the item it fetched - a topic title, a
    # sheet title - so the trail can end with "Arrays" instead of stopping one
    # level up. It is consumed here rather than passed to the template.
    leaf = str(extra.pop("crumb_leaf", "") or "")
    parents = extra.pop("crumb_parents", None)
    context.update(navigation_context(request.url.path, viewer is not None))
    if leaf or parents:
        context["crumbs"] = navigation.breadcrumb_trail(
            request.url.path, leaf, parents, signed_in=viewer is not None
        )
    if viewer:
        context["learner"] = progress.user_stats(viewer.id)
        context["stats"] = context["learner"]
        context["due_cards"] = int(
            db.scalar("SELECT count(*) AS c FROM user_flashcards WHERE user_id = ? AND due_at <= ?",
                      viewer.id, auth.now_ms()) or 0
        )
        context["unread"] = int(
            db.scalar("SELECT count(*) AS c FROM notifications WHERE user_id = ? AND read_at IS NULL",
                      viewer.id) or 0
        )
    context.update(extra)
    return context


def render(
    request: Request, template: str, status_code: int = 200, background=None, **extra: Any
):
    """Renders a template.

    ``status_code`` is pulled out of the kwargs on purpose. Every kwarg lands in
    the template context, so passing it through the way the other values do would
    silently bind it as a template variable and the response would still be 200 -
    which is exactly what made the login and register error paths report success
    to clients that check the status code.

    Authenticated pages are marked non-cacheable because they include private
    account data. Anonymous HTML still carries a per-browser CSRF token, so it
    is private to HTTP caches; the service worker may store only responses
    explicitly marked anonymous in that browser's local cache.
    """
    context = base_context(request, **extra)
    response = templates.TemplateResponse(
        request, template, context, status_code=status_code, background=background
    )
    response.headers["Vary"] = "Cookie"
    if context.get("flash"):
        # A flash is shown once. The cookie used to live out its 8 seconds, so
        # "Welcome back" or "Signed out." appeared again on the next page too.
        from engineverse.security.sessions import public_cookie_kwargs

        options = public_cookie_kwargs(0)
        response.delete_cookie("ev_flash", path=options["path"], secure=options["secure"],
                               samesite=options["samesite"])
    if context.get("user") is not None:
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
    else:
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        response.headers["X-Offline-Cache"] = "anonymous"
        anonymous_csrf = getattr(request.state, "ev_anonymous_csrf", None)
        if anonymous_csrf:
            response.set_cookie(
                csrf.cookie_name(), anonymous_csrf, **csrf.cookie_options()
            )
    return response


def flash(response, message: str) -> None:
    """Stores a one-shot message in a short-lived cookie.

    HTTP header values must be latin-1, so the text is percent-encoded first.
    Without that, an em dash or any non-ASCII glyph raises UnicodeEncodeError
    from inside set_cookie and turns the response into a 500.
    """
    from engineverse.security.sessions import public_cookie_kwargs

    encoded = quote(message[:200], safe="")
    response.set_cookie("ev_flash", encoded, **public_cookie_kwargs(8))


def read_flash(request) -> str:
    """Returns and clears the pending flash message, if any."""
    raw = request.cookies.get("ev_flash")
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw
