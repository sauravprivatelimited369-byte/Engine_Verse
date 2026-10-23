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


#: Query parameters that select a different document rather than a filter on the
#: same one. ``?page=2`` is a later page of a list and ``?card=`` a deep link to
#: one flashcard; both are listed in the sitemap, so they keep their own canonical.
#: Everything else (``?q=``, ``?branch=``, ``?depths=all``) is a view of the page
#: and canonicalises to the bare path.
CANONICAL_QUERY_KEYS = ("page", "card")


def _site_root() -> str:
    """Absolute origin (and base path) of the public site, with no trailing slash.

    The static export lives under a project-Pages base path, so its root is the
    Pages URL rather than the bare origin. Structured data is built from this.
    """
    if _static_export():
        from engineverse import project

        return project.pages_url().rstrip("/")
    return get_settings().site_url.rstrip("/")


def _canonical_url(path: str, query: dict[str, str] | None = None) -> str:
    """Absolute public URL of a page, for <link rel="canonical"> and og:url.

    Filter and search parameters are dropped so that ``/search?q=a`` and
    ``/search?q=b`` do not compete with ``/search``. ``page`` and ``card`` are kept
    because they name a different document.
    """
    clean = "/" + path.lstrip("/")
    if _static_export():
        from engineverse import project

        tail = clean.lstrip("/")
        if tail and not tail.endswith("/"):
            tail += "/"
        base = project.pages_url() + tail
    else:
        base = _site_root() + clean
    query = query or {}
    kept: dict[str, str] = {}
    # Page 1 is the bare list, so only later pages get their own canonical.
    if str(query.get("page", "")).isdigit() and int(query["page"]) > 1:
        kept["page"] = str(int(query["page"]))
    if query.get("card"):
        kept["card"] = str(query["card"])[:128]
    if kept:
        from urllib.parse import urlencode

        base += "?" + urlencode(kept)
    return base


def _meta_description(path: str) -> str:
    """The page's own blurb from the navigation table, if it has one.

    Templates that set a description override the block; the rest used to fall
    back to the tagline, so forty pages shared one description. Every destination
    already carries a one-line blurb, which is a better fit than the tagline.
    """
    from engineverse import navigation

    dest = navigation.find(path)
    if dest is not None and dest.blurb and not dest.pattern:
        return _snippet(dest.blurb)
    return ""


#: Search results show about this many characters of a description before cutting it.
DESCRIPTION_LIMIT = 160


def _snippet(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """``text`` cut to ``limit`` characters at a word boundary, with an ellipsis."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(",;:-–— ") + "…"


def context_brand_description() -> str:
    """The site-wide description, used where a page has no blurb of its own."""
    return _snippet(brand.get("description") or "")


def _organization_schema() -> dict[str, Any]:
    """Organization structured data for the home page.

    Only facts the repository establishes: the name, the public origin, the logo
    and the source repository. No address, telephone or review figures are
    invented here, and the support mailbox is left out because it is a placeholder
    until an operator sets one.
    """
    from engineverse import project

    root = _site_root()
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": brand.get("site_name") or "Meridian",
        "url": root + "/",
        "logo": root + "/static/icons/icon-512.png",
        "description": brand.get("description") or "",
        "sameAs": [project.repo_url()],
    }


def _breadcrumb_schema(crumbs: list) -> dict[str, Any] | None:
    """BreadcrumbList structured data that mirrors the visible trail.

    Items are absolute URLs built from the site root. The current page (the crumb
    with no href) takes the canonical URL of the page itself.
    """
    if not crumbs or len(crumbs) < 2:
        return None
    items = []
    root = _site_root()
    for index, crumb in enumerate(crumbs, start=1):
        href = getattr(crumb, "href", None)
        if href is None:
            url = None
        elif href == "/":
            url = root + "/"
        else:
            url = root + href
        entry: dict[str, Any] = {"@type": "ListItem", "position": index, "name": crumb.label}
        if url is not None:
            entry["item"] = url
        items.append(entry)
    if items and "item" not in items[-1]:
        items[-1]["item"] = None  # filled in by base_context with the canonical URL
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def _public_url(path: str) -> str:
    """Absolute URL of a public asset, for Open Graph and Twitter cards.

    Unlike ``_canonical_url`` this keeps a file path intact: no trailing slash
    is appended, because an og:image that ends in ``/icon-512.png/`` is a 404
    in every social preview.
    """
    clean = path if path.startswith("/") else "/" + path
    return _site_root() + clean


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
        "canonical_url": _canonical_url(request.url.path, dict(request.query_params)),
        "site_root": _site_root(),
        # The social card is 1200x630, the size the large-image Twitter card and
        # the Open Graph previews are designed for. See scripts/gen_social_images.py.
        "og_image": _public_url("/static/img/og-image.png"),
        "og_image_width": 1200,
        "og_image_height": 630,
        "meta_description": _meta_description(request.url.path) or context_brand_description(),
        # Signed-in pages hold private account data and the static copy is only
        # ever rendered anonymously, so only anonymous pages may be indexed.
        "robots": "noindex, nofollow" if viewer is not None else "",
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
    context["organization_ld"] = _organization_schema() if request.url.path == "/" else None
    context["breadcrumb_ld"] = _breadcrumb_schema(context.get("crumbs") or [])
    if context["breadcrumb_ld"] is not None:
        items = context["breadcrumb_ld"]["itemListElement"]
        if items and items[-1].get("item") is None:
            items[-1]["item"] = context["canonical_url"] or None
            if items[-1]["item"] is None:
                items.pop()
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
    # The error handlers pass their status as ``status=`` (it lands in the template
    # context, as the docstring above warns), so look at that too.
    effective_status = max(int(status_code or 0), int(extra.get("status") or 0))
    if effective_status >= 400:
        # An error page answers for a URL that does not exist, so it must neither
        # name itself as canonical nor be indexed.
        context["canonical_url"] = ""
        context["robots"] = "noindex, nofollow"
        context["breadcrumb_ld"] = None
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
