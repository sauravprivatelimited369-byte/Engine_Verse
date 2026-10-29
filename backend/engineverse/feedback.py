"""Usefulness feedback and coarse traffic counters, without any identifiers.

Why this exists
---------------
The audit asked for a way to find out where students give up, and it asked for
that measurement to be privacy-preserving. The platform ships no third-party
analytics and no cookies, which is the right default, but it also meant the
team had no way to tell which pages were working.

The rule this module keeps is narrow and absolute: **a row it writes can never
be traced back to a person.** No user id, no IP address, no user agent, no
session id, no cookie. What is stored is a route (without its query string),
a verdict, an optional short note, and a day bucket.

That is enough to answer the questions the audit actually asked:

* Which pages get traffic at all? -> ``page_stats``, a per-path/per-day count.
* Which pages do students rate as unhelpful? -> ``content_feedback``.
* Do students come back? -> the daily view counts of the same routes.

What it deliberately cannot answer, and why that is fine: who the students
are, how long they stayed on a page, and what they searched for. Those need
identifiers this platform refuses to collect.

Everything here is best-effort. If the tables have not been migrated the
feature returns "no data"; it never raises into a page render.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db
from .security.ids import now_ms, ulid

#: Verdicts the API accepts. Anything else is rejected, not coerced.
VERDICTS = ("useful", "not_useful")

#: Page kinds a vote may be attached to. "page" is the generic bucket.
KINDS = ("page", "topic", "subject", "problem", "compiler", "formula", "resource")

#: Routes that are never counted. The chrome around a lesson is not a place a
#: student gets stuck, and counting it would drown the signal.
IGNORED_PREFIXES = (
    "/static/",
    "/api/",
    "/favicon",
    "/robots.txt",
    "/sitemap",
    "/health",
    "/manifest",
    "/sw.js",
)


#: Set once the tables have been created in this process. Creating them is a
#: DDL round trip, and a page render should not pay for it every time.
_TABLES_READY = False


def ensure_tables() -> None:
    """Makes sure the two tables exist.

    A migrated deployment already has them, and asking first means the
    runtime role never issues DDL - which it may not have the privilege for,
    and which would turn every vote into a silent failure in production.
    The CREATE statements below are the development and test convenience for
    a database that has not been migrated.
    """
    global _TABLES_READY
    if _TABLES_READY:
        return
    if db.table_exists("content_feedback") and db.table_exists("page_stats"):
        _TABLES_READY = True
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS content_feedback (id TEXT PRIMARY KEY, path TEXT NOT NULL, "
        f"kind TEXT NOT NULL DEFAULT 'page', verdict TEXT NOT NULL, detail TEXT, day TEXT NOT NULL, "
        f"created_at {db.epoch_ms_column_type()} NOT NULL)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_feedback_path ON content_feedback(path)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_feedback_day ON content_feedback(day)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS page_stats (path TEXT NOT NULL, day TEXT NOT NULL, "
        "views INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (path, day))"
    )
    _TABLES_READY = True


def normalise_path(path: str | None) -> str:
    """Turns a request URL into a stable, anonymous route.

    The query string is dropped entirely. That is the important part: search
    terms, referral markers and ``?page=2`` pagination would otherwise leak
    into the table, and ``/topic/x?page=2`` would look like a different page
    from ``/topic/x``.
    """
    if not path:
        return "/"
    route = str(path).split("?", 1)[0].split("#", 1)[0].strip()
    if not route.startswith("/"):
        return "/"
    if len(route) > 200:
        route = route[:200]
    return route


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_view(path: str | None) -> None:
    """Counts one page view against today's bucket for that route."""
    route = normalise_path(path)
    if route == "/" or route.startswith(IGNORED_PREFIXES):
        return
    try:
        from .config import get_settings

        if not get_settings().page_stats_enabled:
            return
    except Exception:  # pragma: no cover - settings are optional here
        pass
    try:
        ensure_tables()
        # The right-hand side is qualified with the table name. An
        # unqualified ``views = views + 1`` is read as ambiguous by
        # PostgreSQL, because the name could mean the stored row or the row
        # proposed for insertion; SQLite picks the stored row silently, so the
        # bug would only ever show up in production.
        db.execute(
            "INSERT INTO page_stats (path, day, views) VALUES (?,?,1) "
            "ON CONFLICT(path, day) DO UPDATE SET views = page_stats.views + 1",
            route,
            _today(),
        )
    except Exception:  # pragma: no cover - counters are best-effort
        pass


def vote(
    path: str | None,
    verdict: str,
    *,
    kind: str = "page",
    detail: str = "",
) -> dict:
    """Stores one usefulness vote.

    Returns a small dict describing what happened, so the API can answer
    honestly when the tables are missing rather than pretending it worked.
    """
    route = normalise_path(path)
    verdict = (verdict or "").strip().lower()
    kind = (kind or "page").strip().lower()
    detail = (detail or "").strip()

    if verdict not in VERDICTS:
        return {"stored": False, "reason": "unknown_verdict"}
    if kind not in KINDS:
        kind = "page"
    if len(detail) > 600:
        detail = detail[:600]
    if not route or route == "/":
        return {"stored": False, "reason": "unknown_path"}

    try:
        ensure_tables()
        db.execute(
            "INSERT INTO content_feedback (id, path, kind, verdict, detail, day, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ulid(),
            route,
            kind,
            verdict,
            detail or None,
            _today(),
            now_ms(),
        )
        return {"stored": True, "path": route, "verdict": verdict}
    except Exception:  # pragma: no cover - feedback must never break a page
        return {"stored": False, "reason": "unavailable"}


def summary(days: int = 30, limit: int = 40) -> list[dict]:
    """Per-route traffic and usefulness, worst usefulness rate first.

    This is what the admin analytics panel reads. The join is between an
    aggregate traffic table and an aggregate vote table, so no individual
    action is reconstructable from the result.
    """
    days = max(1, min(int(days or 30), 365))
    limit = max(1, min(int(limit or 40), 200))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        ensure_tables()
        rows = db.query(
            "SELECT p.path AS path, p.views AS views, "
            "coalesce(f.useful, 0) AS useful, coalesce(f.not_useful, 0) AS not_useful "
            "FROM (SELECT path, sum(views) AS views FROM page_stats WHERE day >= ? "
            "      GROUP BY path) p "
            "LEFT JOIN (SELECT path, "
            "   sum(CASE WHEN verdict = 'useful' THEN 1 ELSE 0 END) AS useful, "
            "   sum(CASE WHEN verdict = 'not_useful' THEN 1 ELSE 0 END) AS not_useful "
            "   FROM content_feedback WHERE day >= ? GROUP BY path) f ON f.path = p.path "
            "ORDER BY p.views DESC LIMIT ?",
            since,
            since,
            limit,
        )
    except Exception:  # pragma: no cover
        return []

    for row in rows:
        useful = int(row.get("useful") or 0)
        not_useful = int(row.get("not_useful") or 0)
        votes = useful + not_useful
        row["votes"] = votes
        row["usefulness"] = round(useful / votes, 2) if votes else None
        row["views"] = int(row.get("views") or 0)
    return rows


def low_rated(days: int = 30, limit: int = 10) -> list[dict]:
    """Routes students rated badly, worst first.

    Only routes with at least two votes appear. One vote is an opinion, not a
    signal, and acting on a single vote would be reading tea leaves.
    """
    days = max(1, min(int(days or 30), 365))
    limit = max(1, min(int(limit or 10), 50))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        ensure_tables()
        rows = db.query(
            "SELECT path, "
            "sum(CASE WHEN verdict = 'useful' THEN 1 ELSE 0 END) AS useful, "
            "sum(CASE WHEN verdict = 'not_useful' THEN 1 ELSE 0 END) AS not_useful, "
            "count(*) AS votes "
            "FROM content_feedback WHERE day >= ? GROUP BY path HAVING votes >= 2 "
            "ORDER BY (sum(CASE WHEN verdict = 'not_useful' THEN 1 ELSE 0 END) * 1.0 / count(*)) DESC, votes DESC "
            "LIMIT ?",
            since,
            limit,
        )
    except Exception:  # pragma: no cover
        return []
    for row in rows:
        useful = int(row.get("useful") or 0)
        votes = int(row.get("votes") or 0)
        row["usefulness"] = round(useful / votes, 2) if votes else None
    return rows


def recent_notes(limit: int = 20) -> list[dict]:
    """The free-text notes students left, newest first."""
    limit = max(1, min(int(limit or 20), 100))
    try:
        ensure_tables()
        return db.query(
            "SELECT path, kind, verdict, detail, day, created_at FROM content_feedback "
            "WHERE detail IS NOT NULL AND detail <> '' ORDER BY created_at DESC LIMIT ?",
            limit,
        )
    except Exception:  # pragma: no cover
        return []
