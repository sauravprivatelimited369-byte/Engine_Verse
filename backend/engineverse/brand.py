"""Configurable branding (spec §1).

The product is FORGE ("Where engineers are made."). The Python package keeps
its original ``engineverse`` codename: a rebrand changes what learners see,
not import paths, environment variables or stored-data formats that existing
deployments depend on. See docs/BRAND.md for the naming rationale.

The product name, tagline and accent colours live in the ``site_config`` table,
so a white-label deployment is a data change rather than a code change.

Key names here must match three places at once: the seeded rows in
``seed_data/library_data.py::SITE_CONFIG``, the ``{{ brand.* }}`` references in
``backend/templates/``, and the admin settings form. They previously drifted
apart (``brand_name``/``accent`` here vs ``site_name``/``accent_color`` in the
seed vs ``brand.site_name`` in the templates), which silently rendered an empty
product name on every page because an unknown key returns an empty string.
"""
from __future__ import annotations

from . import db
from .security.ids import now_ms

DEFAULTS = {
    "site_name": "EngineVerse",
    "tagline": "Don't just learn engineering. Experiment with it.",
    "description": "EngineVerse is a study workspace for engineering students: curriculum notes, interactive engineering labs, practice sheets and progress tracking in one workflow, so the next step is always one click away.",
    "support_email": "support@forge.local",
    "free_tier_note": (
        "All core learning content on this instance is free to read and practise. "
        "EngineVerse is a self-hosted project with no paid plan to buy here; "
        "its certificates are records of completion, not accredited qualifications."
    ),
    "announcement": "",
    "accent_color": "#f97316",
    "accent_color_2": "#fbbf24",
    "accent_color_3": "#f43f5e",
    "theme": "dark",
    "maintenance_mode": "0",
    "registration_open": "1",
}

#: Keys handed to templates as ``brand``. Everything a template reads must be here,
#: otherwise it renders as an empty string instead of failing loudly.
PUBLIC_KEYS = (
    "site_name",
    "tagline",
    "description",
    "support_email",
    "free_tier_note",
    "announcement",
    "accent_color",
    "accent_color_2",
    "accent_color_3",
    "theme",
    "maintenance_mode",
    "registration_open",
)


def get(key: str, default: str | None = None) -> str:
    value = db.scalar("SELECT value AS v FROM site_config WHERE key = ?", key, default=None)
    if value is None or str(value) == "":
        return DEFAULTS.get(key, default or "")
    return str(value)


# Keys whose value is interpolated into CSS. Validated on the way out as well as
# on the way in, so a value written before the check existed - or by any other
# path - still cannot reach a page as anything but a hex colour.
_COLOR_KEYS = {
    "accent_color": "#f97316",
    "accent_color_2": "#fbbf24",
    "accent_color_3": "#f43f5e",
}


def brand() -> dict[str, str]:
    """Every branding key a template may read, always populated."""
    from .security.sanitize import safe_css_color

    values = {key: get(key) for key in PUBLIC_KEYS}
    for key, fallback in _COLOR_KEYS.items():
        values[key] = safe_css_color(values.get(key), fallback)
    return values


def is_maintenance() -> bool:
    return get("maintenance_mode", "0").strip() not in ("", "0", "false", "False")


def registration_open() -> bool:
    return get("registration_open", "1").strip() not in ("", "0", "false", "False")


def set_many(values: dict[str, str]) -> None:
    ts = now_ms()
    for key, value in values.items():
        if not isinstance(value, str):
            continue
        db.execute(
            "INSERT INTO site_config (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            key,
            value[:400],
            ts,
        )


def all_config() -> dict[str, str]:
    rows = db.query("SELECT key, value FROM site_config ORDER BY key")
    return {row["key"]: row["value"] for row in rows}
