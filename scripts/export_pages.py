#!/usr/bin/env python3
"""Write the public GitHub Pages site.

Pages cannot run accounts, a database or the code judge. Without a configured
host, export the public reading copy with a browser-only streak. Once the full
HTTPS FastAPI app has actually been deployed, export a gateway to that app:
visitors use it without cloning this repository, and old deep links are
preserved. The CI workflow verifies the hosted app before switching modes.

No learner database, credentials or demo accounts are ever exported. A signed
Android APK is only linked after its versioned release URL is configured.
"""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from engineverse import project  # noqa: E402
from engineverse.distribution import normalise_apk_url  # noqa: E402

FORBIDDEN = (
    "LearnBuild#2026!",
    "TeachLearn#2026!",
    "Str0ngPassphrase#42!",
    "engineverse-development-secret-not-for-production",
    "pages-export-not-a-production-secret",
)
SKIP_PREFIXES = (
    "/login",
    "/register",
    "/forgot",
    "/reset",
    "/logout",
    "/admin",
    "/settings",
    "/profile",
    "/notifications",
    "/today",
    "/onboarding",
    "/mistakes",
    "/api/",
    "/certificates",
    "/portfolio",
)
LOCAL_ONLY_PATHS = (
    "/dashboard", "/profile", "/settings", "/today", "/mistakes", "/portfolio", "/certificates",
    "/login", "/register", "/forgot-password", "/reset-password", "/logout", "/notifications",
    "/onboarding", "/hosting",
)
AUTH_TO_HOSTING = (
    "/practice/check",
    "/admin",
)
FILE_SUFFIXES = (
    ".css",
    ".js",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".json",
    ".xml",
    ".txt",
    ".webmanifest",
    ".map",
)
ATTR_URL = re.compile(
    r"""(?P<attr>\b(?:href|src|action)\s*=\s*)(?P<q>["'])(?P<url>/[^"']*)(?P=q)"""
)
REPO = project.repo_url()


def repo_base(explicit: str | None = None) -> str:
    """Project Pages live under /RepoName/. A *.github.io repo is served at /."""
    if explicit is not None:
        text = explicit.strip()
        if text in ("", "/"):
            return "/"
        return "/" + text.strip("/") + "/"
    return project.pages_base()


def join_base(base: str, path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if base == "/":
        return path
    return base.rstrip("/") + path


def is_file_url(path: str) -> bool:
    clean = path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if clean.startswith("/static/") or clean.startswith("/api/"):
        return True
    lower = clean.lower()
    return any(lower.endswith(suffix) for suffix in FILE_SUFFIXES)


def rewrite_url(url: str, base: str) -> str:
    """Map an app-root URL onto the Pages base, with a trailing slash for pages."""
    if not url.startswith("/") or url.startswith("//"):
        return url
    path, query, frag = url, "", ""
    if "#" in path:
        path, frag = path.split("#", 1)
        frag = "#" + frag
    if "?" in path:
        path, query = path.split("?", 1)
        query = "?" + query
    if path != "/" and not is_file_url(path):
        path = path.rstrip("/") + "/"
    return join_base(base, path) + query + frag


def rewrite_html(text: str, base: str) -> str:
    hosting = rewrite_url("/hosting", base)
    auth_targets = [rewrite_url(old, base) for old in AUTH_TO_HOSTING]

    def repl(match: re.Match[str]) -> str:
        url = rewrite_url(match.group("url"), base)
        if "/api/" in url or any(url == target or url.startswith(target) for target in auth_targets):
            url = hosting
        return f"{match.group('attr')}{match.group('q')}{url}{match.group('q')}"

    text = ATTR_URL.sub(repl, text)
    # GitHub Pages answers POST with 405. A form whose server action was
    # redirected to /hosting is handled by pages-live.js when JavaScript runs;
    # without it, a GET still lands on the page that explains what needs a server.
    return re.sub(
        r'<form\b([^>]*?)\bmethod=(["\'])post\2([^>]*\baction=(["\'])' + re.escape(hosting) + r'\4)',
        r'<form\1method=\2get\2\3',
        text,
        flags=re.I,
    )


def output_path(site: Path, url_path: str) -> Path:
    path = url_path.split("?", 1)[0].split("#", 1)[0]
    if path in ("", "/"):
        return site / "index.html"
    return site / path.strip("/") / "index.html"


def prepare_env(db_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    # A developer .env must not redirect this export at a live database.
    env["ENGINEVERSE_ENV"] = "development"
    env["ENGINEVERSE_DB_PATH"] = str(db_path)
    env["ENGINEVERSE_DB_URL"] = ""
    env["ENGINEVERSE_JUDGE"] = "disabled"
    env["ENGINEVERSE_SITE_URL"] = "http://127.0.0.1:8765"
    env["ENGINEVERSE_SECRET"] = "pages-export-local-only-not-published-0001"
    env["ENGINEVERSE_REVEAL_RESET_TOKEN"] = ""
    env["ENGINEVERSE_TRUST_PROXY"] = ""
    # The reading copy is rendered as a signed-out visitor. With the app's
    # default compulsory sign-in every page would be a redirect to /login.
    env["ENGINEVERSE_SIGNIN"] = "optional"
    # Templates render their static variants: no sign-in prompts, no forms that
    # post to a server, the browser Submit button on problem pages, and
    # canonical URLs on the Pages origin rather than the export's loopback host.
    env["ENGINEVERSE_STATIC_EXPORT"] = "1"
    return env


def seed(env: dict[str, str], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "seed.py"), "--fresh", "--no-demo"],
        cwd=ROOT,
        env=env,
    )


def load_app():
    for path in (str(BACKEND), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.chdir(ROOT)
    from main import app  # noqa: WPS433

    return app


def public_paths() -> list[str]:
    from engineverse import catalog, coding, db, library, navigation, projects

    # The static pages come from the navigation table rather than a list written
    # out here. This list was a fifth copy of the site's pages and had drifted
    # from the other four: the nav grew a "Sheets" tab and this function only
    # listed /sheets further down, by hand, in a comment about the nav. Anything
    # navigation.py knows about is exported automatically now, and SKIP_PREFIXES
    # below still strips the pages that are private to one account.
    paths = list(navigation.indexable_paths(public_only=True))
    # /revision and /flashcards are the two faces of the nav's "Revise" group.
    # The exported copy renders anonymously, so its nav points at /flashcards -
    # but /revision is exported too so a bookmark to it resolves.
    paths += ["/revision", "/streaks", "/practice/questions"]
    paths += [f"/branches/{row['slug']}" for row in catalog.list_branches()]
    paths += [f"/subjects/{row['slug']}" for row in catalog.list_subjects(limit=500)]
    paths += [
        f"/topics/{row['slug']}"
        for row in db.query("SELECT slug FROM topics WHERE status = 'published' ORDER BY slug")
    ]
    paths += [f"/projects/{row['slug']}" for row in projects.list_projects(limit=400)]
    problems, _total = coding.list_problems(limit=400)
    paths += [f"/practice/problems/{row['slug']}" for row in problems]
    paths.append("/practice/problems")
    # The nav's "My stream" and "Sheets" entries point here, and the exported
    # copy renders anonymously: /stream answers a signed-out visitor with a
    # redirect, so the stream index and every stream page are exported directly
    # and the nav links resolve to pages rather than to a redirect target.
    paths += ["/streams", "/sheets", "/resources/offsite"]
    paths += [f"/stream/{row['slug']}" for row in catalog.list_branches()]
    paths += [f"/sheets/{row['slug']}" for row in coding.list_sheets(limit=100)]
    # /revision (signed-in) and /flashcards (anonymous) are the two faces of the
    # nav's "Revise" tab; the static copy renders anonymously, so its nav points
    # at /flashcards and that page has to exist or every nav link dangles.
    paths += ["/practice/questions", "/revision", "/flashcards", "/tutor"]
    for row in db.query("SELECT date FROM dpp_sets ORDER BY date"):
        if row["date"]:
            paths.append(f"/dpp/{row['date']}")
    for lang in coding.list_languages():
        slug = lang.get("slug")
        if slug:
            paths.append(f"/programming/{slug}")
            paths += [f"/programming/{slug}/lessons/{row['slug']}" for row in coding.modules_for_language(lang["id"])]
    for roadmap in library.list_roadmaps():
        slug = roadmap.get("slug")
        if slug:
            paths.append(f"/roadmaps/{slug}")
    # First-year filter is a query on the live app. Pages has no query router,
    # so the same list is saved at its own path and the home link is rewritten.
    paths.append("/explore/first-year")
    seen: list[str] = []
    for path in paths:
        if path not in seen and not any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            seen.append(path)
    return seen


def search_index(base: str) -> list[dict[str, str]]:
    from engineverse import db

    rows: list[dict[str, str]] = []

    def add(kind: str, title: str, text: str, path: str) -> None:
        title = (title or "").strip()
        if not title:
            return
        rows.append(
            {
                "kind": kind,
                "title": title,
                "text": (text or "")[:240],
                "url": rewrite_url(path, base),
            }
        )

    for row in db.query(
        "SELECT t.slug, t.title, t.summary, s.name AS subject FROM topics t "
        "JOIN subjects s ON s.id = t.subject_id WHERE t.status = 'published'"
    ):
        add("Topic", row["title"], f"{row['subject']}. {row['summary'] or ''}", f"/topics/{row['slug']}")
    for row in db.query("SELECT slug, name, description FROM subjects"):
        add("Subject", row["name"], row["description"] or "", f"/subjects/{row['slug']}")
    for row in db.query("SELECT slug, title, summary FROM projects"):
        add("Project", row["title"], row["summary"] or "", f"/projects/{row['slug']}")
    for row in db.query("SELECT slug, title, statement FROM coding_problems"):
        add("Problem", row["title"], row["statement"] or "", f"/practice/problems/{row['slug']}")
    for row in db.query("SELECT name, latex, meaning FROM formulas"):
        add("Formula", row["name"], row["meaning"] or row["latex"] or "", "/formulas")
    return rows


def banner(base: str) -> str:
    """GitHub Pages is the public site. Do not put a reading-copy strip above the product."""
    del base
    return ""


def hosting_main(app_url: str = "", apk_url: str = "") -> str:
    """The /hosting page: what this static copy does, and what needs a server."""
    deploy_doc = f"{REPO}/blob/main/docs/DEPLOYMENT.md"
    if app_url:
        server = (
            '<p>A hosted EngineVerse server is available. It adds accounts, progress that follows you between '
            'devices, discussions and server-side code judging where the host has enabled it.</p>'
            f'<p class="row"><a class="btn btn-primary" href="{html.escape(app_url, quote=True)}/">Open the hosted site</a></p>'
        )
    else:
        server = (
            '<p>No hosted EngineVerse server is linked from this copy yet. Anyone can run one: it is a Python '
            'FastAPI application with a SQL database. The deployment guide covers it step by step.</p>'
            f'<p class="row"><a class="btn btn-ghost" href="{html.escape(deploy_doc, quote=True)}" '
            'rel="noopener noreferrer">Deployment guide</a></p>'
        )
    apk = (
        f'<p><a class="btn btn-soft" href="{html.escape(apk_url, quote=True)}" rel="noopener noreferrer">'
        'Download the Android app</a></p>'
        if apk_url else ""
    )
    return f"""
<section class="page-hero">
  <p class="ev-eyebrow">Platform · how this site works</p>
  <h1>Use EngineVerse here</h1>
  <p class="lead">This site is a static copy of EngineVerse that runs entirely in your browser. You do not need to
    download or install anything to use it.</p>
</section>
<div class="grid g2 about-grid">
  <section class="panel">
    <h2>What works on this copy</h2>
    <ul class="about-list">
      <li>Every subject, topic note, formula, flashcard, roadmap and project brief.</li>
      <li>Daily practice and the question bank, with answers checked in your browser.</li>
      <li>Coding problems and the compiler, using in-browser runtimes. Each language page says whether it can
        run here.</li>
      <li>Progress, streaks, the mistake notebook and the study planner, saved on this device only.</li>
    </ul>
    <p class="row"><a class="btn btn-primary" href="/explore">Explore subjects</a>
      <a class="btn btn-ghost" href="/practice/problems">Coding problems</a>
      <a class="btn btn-ghost" href="/install">Install the app</a></p>
    {apk}
  </section>
  <section class="panel">
    <h2>What needs a server</h2>
    <p>Accounts, progress that syncs between devices, posting in discussions, leaderboards with other learners and
      certificates with a verification ID all need a hosted EngineVerse server with a database.</p>
    {server}
  </section>
</div>
""".strip()


def _svg(paths: list[str]) -> str:
    """A stroke icon in the same shape the templates draw, for static HTML."""
    body = "".join(f'<path d="{d}"/>' for d in paths)
    return ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
            f'focusable="false">{body}</svg>')


def reading_copy_install_main(app_url: str = "", apk_url: str = "") -> str:
    """Phone installation page for the static Pages copy.

    Mirrors the template's hero and install-card layout, but describes this
    copy honestly: no accounts, progress on this device, and an APK link only
    when a signed GitHub Release has actually been configured.
    """
    android_ci = f"{REPO}/actions/workflows/android-build.yml"
    hosted = (
        f'<p class="small muted">A hosted EngineVerse server is also available at '
        f'<a href="{html.escape(app_url, quote=True)}/">{html.escape(app_url)}</a>, with accounts that sync '
        'between devices.</p>'
        if app_url else ""
    )
    if apk_url:
        apk_body = (
            '<p>The native EngineVerse Android app is published as a signed GitHub Release. It includes an '
            'offline subject catalogue, the study planner and settings, and opens lessons in a secure in-app '
            'viewer.</p>'
            f'<p><a class="btn btn-primary" href="{html.escape(apk_url, quote=True)}" '
            'rel="noopener noreferrer">Download the signed APK</a></p>'
            '<ol class="steps">'
            '<li>Download the APK from the official GitHub Release.</li>'
            '<li>Open it on your Android phone and allow installation from your browser if asked.</li>'
            '<li>Launch <strong>EngineVerse</strong>.</li>'
            '</ol>'
            '<p class="small muted">Only install the APK from the official release, never from a forwarded '
            'copy. Check the SHA-256 checksum published with the release.</p>'
        )
    else:
        apk_body = (
            '<p>No signed release of the native Android app has been published yet, so there is no APK '
            'download here. Do not install an EngineVerse APK from any other source.</p>'
            f'<p class="small muted">Testers can download unsigned debug builds from the '
            f'<a href="{html.escape(android_ci, quote=True)}" rel="noopener noreferrer">Android build '
            'workflow</a> on GitHub (a GitHub account is required, and builds expire). Debug builds are for '
            'testing only.</p>'
        )

    return f"""
<section class="page-hero">
  <span class="hero-glow hero-glow-a" aria-hidden="true"></span>
  <p class="ev-eyebrow">Install · Android · iPhone</p>
  <h1>Use EngineVerse on your phone</h1>
  <p class="lead">This website works in any modern mobile browser. You can also add it to your home screen so it
    opens like an app. There is no account: your progress is saved in the browser on each device.</p>
  {hosted}
</section>

<div class="stack install-cards">
  <section class="panel install-card">
    <span class="install-mark" aria-hidden="true">{_svg(['M12 4v11.4', 'm7.8 11.4 4.2 4.2 4.2-4.2', 'M5 19.6h14'])}</span>
    <div class="install-body">
      <h2>Android: add to home screen</h2>
      <ol class="steps">
        <li>Open this site in Chrome.</li>
        <li>Tap the ⋮ menu, then <strong>Add to Home screen</strong> or <strong>Install app</strong>.</li>
        <li>Confirm. The icon appears on your home screen.</li>
      </ol>
      <button class="btn btn-primary hide" id="install-btn" type="button">Install web app</button>
      <p class="small muted">Pages you have already opened are cached for offline reading. Pages you have not
        visited yet need a connection.</p>
    </div>
  </section>

  <section class="panel install-card">
    <span class="install-mark" aria-hidden="true">{_svg(['m13.4 6.6 4 4-7.4 7.4H6v-4z', 'm15.4 4.6 4 4', 'M4.6 19.4 8 16'])}</span>
    <div class="install-body">
      <h2>Android app</h2>
      {apk_body}
    </div>
  </section>

  <section class="panel install-card">
    <span class="install-mark" aria-hidden="true">{_svg(['M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z', 'M3 12h18', 'M12 3c5 5 5 13 0 18-5-5-5-13 0-18z'])}</span>
    <div class="install-body">
      <h2>iPhone: Safari</h2>
      <ol class="steps">
        <li>Open this site in Safari.</li>
        <li>Tap Share.</li>
        <li>Choose <strong>Add to Home Screen</strong>.</li>
      </ol>
    </div>
  </section>

  <section class="panel install-card">
    <span class="install-mark" aria-hidden="true">{_svg(['M4 4h6v6H4z', 'M14 4h6v6h-6z', 'M4 14h6v6H4z', 'M14 14h6v6h-6z'])}</span>
    <div class="install-body">
      <h2>Desktop</h2>
      <p>Use your browser menu or the install icon in the address bar. Installed or not, your progress stays in
        that browser. Use <a href="/settings">Settings</a> to export it.</p>
    </div>
  </section>
</div>
""".strip()


def search_script(base: str) -> str:
    index_url = html.escape(rewrite_url("/search-index.json", base), quote=True)
    return f"""
<script>
(function () {{
  var params = new URLSearchParams(location.search);
  var q = (params.get("q") || "").trim().toLowerCase();
  var host = document.getElementById("pages-results");
  if (!host || !q) return;
  fetch("{index_url}").then(function (res) {{ return res.json(); }}).then(function (rows) {{
    var terms = q.split(/\\s+/).filter(Boolean);
    var hits = rows.filter(function (row) {{
      var hay = (row.title + " " + row.text + " " + row.kind).toLowerCase();
      return terms.every(function (term) {{ return hay.indexOf(term) !== -1; }});
    }}).slice(0, 48);
    host.hidden = false;
    var heading = document.createElement("p");
    heading.className = "muted";
    heading.textContent = hits.length + (hits.length === 1 ? " result" : " results");
    host.appendChild(heading);
    var grid = document.createElement("div");
    grid.className = "grid g3";
    hits.forEach(function (row) {{
      var card = document.createElement("a");
      card.className = "card";
      card.href = row.url;
      var title = document.createElement("span");
      title.className = "title";
      title.textContent = row.title;
      var desc = document.createElement("span");
      desc.className = "desc";
      desc.textContent = row.text;
      var tags = document.createElement("div");
      tags.className = "tags";
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = row.kind;
      tags.appendChild(chip);
      card.appendChild(title);
      card.appendChild(desc);
      card.appendChild(tags);
      grid.appendChild(card);
    }});
    host.appendChild(grid);
    if (!hits.length) {{
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Nothing matched. Try a shorter term.";
      host.appendChild(empty);
    }}
  }}).catch(function () {{
    host.hidden = false;
    host.textContent = "Search index did not load.";
  }});
}})();
</script>
"""


def retarget_missing_dpp(text: str, base: str, dates: list[str]) -> str:
    """Point calendar days that were not exported at a real set, keeping the day in the query."""
    if not dates:
        return text
    known = set(dates)
    prefix = "" if base == "/" else base.rstrip("/")
    pattern = re.compile(
        rf'href=(["\']){re.escape(prefix)}/dpp/(\d{{4}}-\d{{2}}-\d{{2}})/?\1'
    )

    def repl(match: re.Match[str]) -> str:
        quote, day = match.group(1), match.group(2)
        if day in known:
            return match.group(0)
        try:
            index = date_cls.fromisoformat(day).toordinal() % len(dates)
        except ValueError:
            index = 0
        url = rewrite_url(f"/dpp/{dates[index]}", base) + "?day=" + day
        return f"href={quote}{url}{quote}"

    return pattern.sub(repl, text)


def live_boot(base: str, dates: list[str], apk_url: str = "") -> str:
    payload = {
        "base": base if base.endswith("/") else base + "/",
        "dpp": [rewrite_url(f"/dpp/{day}", base) for day in dates],
        "tutor": rewrite_url("/tutor-corpus.json", base),
        "streaks": rewrite_url("/streaks", base),
        "quizBank": rewrite_url("/quiz-bank.json", base),
        "codingProblems": rewrite_url("/coding-problems.json", base),
        # Same-origin CPython runtime (Pyodide) for the browser Python
        # compiler/judge. Populated by scripts/fetch_pyodide.py in the Pages
        # workflow; absent files make browser Python report NOT RUN.
        "pyodide": rewrite_url("/pyodide/", base),
        # Same-origin real compilers/interpreters (Clang, OpenJDK/TeaVM,
        # rustc/Miri, Roslyn, TypeScript, SQLite, GopherJS) for every other
        # language. Populated by scripts/fetch_browser_runtimes.py in the
        # Pages workflow; its manifest.json decides per language, and a
        # language missing there reports NOT RUN - never a simulation.
        "runtimes": rewrite_url("/runtimes/", base),
        "studioSnapshot": rewrite_url("/studio-snapshot.json", base),
        "workflowsCatalog": rewrite_url("/workflows-catalog.json", base),
        "swarmCorpus": rewrite_url("/swarm-corpus.json", base),
        "apkUrl": apk_url,
        "issues": project.issues_url(),
    }
    blob = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return '<script type="application/json" id="ev-live">' + blob + "</script>"


def _plain(text: str, limit: int = 650) -> str:
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"[#*_`>\[\]]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def write_tutor_corpus(site: Path, base: str) -> None:
    """Notes the browser tutor is allowed to quote. It must not be asked to invent the rest."""
    from engineverse import db

    rows = db.query(
        "SELECT t.slug, t.title, sub.name AS subject, sec.kind, sec.body, n.quality_level "
        "FROM topics t "
        "JOIN subjects sub ON sub.id = t.subject_id "
        "JOIN notes n ON n.topic_id = t.id AND n.status = 'published' "
        "JOIN note_sections sec ON sec.note_id = n.id "
        "WHERE n.quality_level IN ('beginner', 'standard') "
        "AND sec.kind IN ('simple', 'definition', 'intuition', 'example', 'mistakes', 'points') "
        "ORDER BY t.slug, n.quality_level, sec.order_index"
    )
    grouped: dict[str, dict[str, str]] = {}
    for row in rows:
        item = grouped.setdefault(row["slug"], {
            "title": row["title"],
            "subject": row["subject"] or "",
            "url": rewrite_url(f"/topics/{row['slug']}", base),
            "simple": "",
            "definition": "",
            "intuition": "",
            "example": "",
            "mistakes": "",
            "points": "",
        })
        kind = row["kind"]
        if kind not in item:
            continue
        if kind == "simple" and row["quality_level"] != "beginner" and item["simple"]:
            continue
        if kind != "simple" and row["quality_level"] != "standard" and item[kind]:
            continue
        item[kind] = _plain(row["body"] or "")
    modules = db.query(
        "SELECT m.slug, m.title, m.summary, m.body, m.example, m.exercise, l.slug AS language_slug, l.name AS language "
        "FROM language_modules m JOIN programming_languages l ON l.id = m.language_id "
        "ORDER BY l.order_index, m.order_index"
    )
    for row in modules:
        grouped["lang-" + row["slug"]] = {
            "title": f"{row['language']}: {row['title']}",
            "subject": row["language"] or "",
            "url": rewrite_url(f"/programming/{row['language_slug']}", base) + "#" + row["slug"],
            "simple": _plain(row["summary"] or ""),
            "definition": _plain(row["body"] or ""),
            "intuition": "",
            "example": _plain(row["example"] or "", 500),
            "mistakes": _plain(row["exercise"] or "", 300),
            "points": "",
        }
    formulas = db.query("SELECT slug, name, meaning, application FROM formulas")
    for row in formulas:
        grouped["formula-" + row["slug"]] = {
            "title": row["name"],
            "subject": "Formula",
            "url": rewrite_url("/formulas", base),
            "simple": _plain(row["meaning"] or ""),
            "definition": _plain(row["application"] or ""),
            "intuition": "",
            "example": "",
            "mistakes": "",
            "points": "",
        }
    (site / "tutor-corpus.json").write_text(
        json.dumps(list(grouped.values()), ensure_ascii=False),
        encoding="utf-8",
    )


def write_quiz_bank(site: Path, base: str) -> None:
    """Export all active quiz questions, options, correct answers, and explanations for browser grading."""
    from engineverse import db

    questions = db.query(
        "SELECT q.id, q.slug, q.kind, q.difficulty, q.stem, q.explanation, q.answer_text, "
        "t.slug AS topic_slug, t.title AS topic_title, s.name AS subject_name "
        "FROM questions q "
        "LEFT JOIN topics t ON t.id = q.topic_id "
        "LEFT JOIN subjects s ON s.id = q.subject_id "
        "WHERE q.is_active = 1"
    )
    options_rows = db.query(
        "SELECT question_id, label, body, is_correct, rationale, order_index "
        "FROM question_options ORDER BY question_id, order_index"
    )
    by_q: dict[str, list[dict]] = {}
    for opt in options_rows:
        by_q.setdefault(opt["question_id"], []).append(opt)

    bank: dict[str, dict] = {}
    for q in questions:
        qid = q["id"]
        opts = by_q.get(qid, [])
        correct_idx = -1
        correct_label = ""
        pub_opts = []
        for idx, opt in enumerate(opts):
            if opt.get("is_correct"):
                correct_idx = idx
                correct_label = opt.get("label") or ""
            pub_opts.append({
                "index": idx,
                "label": opt.get("label") or "",
                "body": opt.get("body") or "",
                "rationale": opt.get("rationale") or "",
            })
        topic_url = rewrite_url(f"/topics/{q['topic_slug']}", base) if q.get("topic_slug") else ""
        bank[qid] = {
            "id": qid,
            "slug": q.get("slug") or "",
            "kind": q.get("kind") or "mcq",
            "difficulty": q.get("difficulty") or "medium",
            "stem": q.get("stem") or "",
            "explanation": q.get("explanation") or "",
            "answerText": q.get("answer_text") or "",
            "correctIndex": correct_idx,
            "correctLabel": correct_label,
            "topicSlug": q.get("topic_slug") or "",
            "topicTitle": q.get("topic_title") or "",
            "topicUrl": topic_url,
            "subjectName": q.get("subject_name") or "",
            "options": pub_opts,
        }
    (site / "quiz-bank.json").write_text(
        json.dumps(bank, ensure_ascii=False),
        encoding="utf-8",
    )


def write_coding_problems(site: Path) -> None:
    """Export all coding problem wrappers, stubs, and test cases for in-browser execution & judging."""
    from engineverse import coding, db, drivers

    problems = db.query("SELECT id, slug, title, difficulty, wrapper, topics FROM coding_problems ORDER BY slug")
    out: dict[str, dict] = {}
    for p in problems:
        pid = p["id"]
        stubs = coding.stubs_for(pid)
        cases = coding.testcases_for(pid, samples_only=False)
        py_sig = ""
        stub_map: dict[str, dict] = {}
        for s in stubs:
            lang_slug = s.get("slug") or ""
            if lang_slug == "python":
                py_sig = s.get("signature") or ""
            if lang_slug:
                stub_map[lang_slug] = {
                    "stub": s.get("stub") or "",
                    "signature": s.get("signature") or "",
                    "name": s.get("name") or lang_slug,
                }
        entry = drivers.entrypoint(py_sig, fallback="solution")
        out[p["slug"]] = {
            "id": pid,
            "slug": p["slug"],
            "title": p["title"],
            "difficulty": p["difficulty"],
            "wrapper": p.get("wrapper") or "raw",
            "entry": entry,
            # The exact harness source the server judge appends to a Python
            # submission (drivers.python_driver). The browser runs real
            # CPython (Pyodide) on code + this driver, so stdin/stdout
            # semantics are identical by construction instead of reimplemented
            # (the old regex transpiler approximated them and graded wrong).
            "driverPython": drivers.python_driver(p.get("wrapper") or "raw", entry),
            "stubs": stub_map,
            "testcases": [
                {
                    "input": tc.get("input") or "",
                    "expected": tc.get("expected") or "",
                    "isSample": bool(tc.get("is_sample")),
                }
                for tc in cases
            ],
        }
    (site / "coding-problems.json").write_text(
        json.dumps(out, ensure_ascii=False),
        encoding="utf-8",
    )


def write_studio_snapshot(site: Path) -> None:
    """Export the seeded catalogue tables so the browser SQL Studio can execute any SELECT query."""
    from engineverse import db, studio

    tables_data: dict[str, dict] = {}
    schema_info = studio.schema()
    for table_info in schema_info["tables"]:
        tname = table_info["name"]
        rows = db.query(studio._projection_sql(tname) + " LIMIT 400")
        tables_data[tname] = {
            "columns": table_info["columns"],
            "rowCount": table_info["row_count"],
            "rows": rows,
        }
    payload = {
        "tables": tables_data,
    }
    (site / "studio-snapshot.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def write_workflows_catalog(site: Path, base: str) -> None:
    """Export workflow templates and sample execution payloads for browser-native workflow runs."""
    from dataclasses import asdict
    from engineverse import db, workflows

    templates = [asdict(w) for w in workflows.WORKFLOWS]
    topics = db.query(
        "SELECT t.slug, t.title, t.difficulty, t.est_minutes, t.summary, s.name AS subject_name, b.name AS branch_name "
        "FROM topics t JOIN subjects s ON s.id = t.subject_id JOIN branches b ON b.id = s.branch_id "
        "WHERE t.status = 'published' ORDER BY t.order_index, t.title LIMIT 80"
    )
    for row in topics:
        row["url"] = rewrite_url(f"/topics/{row['slug']}", base)
    questions = db.query(
        "SELECT q.slug, q.stem, q.difficulty, t.slug AS topic_slug, t.title AS topic_title "
        "FROM questions q LEFT JOIN topics t ON t.id = q.topic_id WHERE q.is_active = 1 LIMIT 80"
    )
    problems = db.query(
        "SELECT slug, title, difficulty, expected_time FROM coding_problems ORDER BY title LIMIT 60"
    )
    payload = {
        "templates": templates,
        "topics": topics,
        "questions": questions,
        "problems": problems,
    }
    (site / "workflows-catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def write_swarm_corpus(site: Path, base: str) -> None:
    """Export personas and enriched topic/formula/problem corpus for browser MiroFish Swarm simulation."""
    from engineverse import db, swarm

    topics = db.query(
        "SELECT t.id, t.slug, t.title, t.summary, t.prerequisites, "
        "s.name AS subject_name, b.name AS branch_name "
        "FROM topics t JOIN subjects s ON s.id = t.subject_id JOIN branches b ON b.id = s.branch_id "
        "WHERE t.status = 'published' ORDER BY t.title"
    )
    sections_rows = db.query(
        "SELECT n.topic_id, sec.kind, sec.title, sec.body "
        "FROM notes n JOIN note_sections sec ON sec.note_id = n.id "
        "WHERE n.status = 'published' AND n.quality_level = 'standard' "
        "ORDER BY n.topic_id, sec.order_index"
    )
    by_topic: dict[str, dict[str, str]] = {}
    for sec in sections_rows:
        bucket = by_topic.setdefault(sec["topic_id"], {})
        kind = sec["kind"]
        if kind not in bucket:
            bucket[kind] = _plain(sec["body"] or "", 420)

    topic_items = []
    for t in topics:
        secs = by_topic.get(t["id"], {})
        topic_items.append({
            "slug": t["slug"],
            "title": t["title"],
            "subject": t.get("subject_name") or "",
            "branch": t.get("branch_name") or "",
            "summary": _plain(t.get("summary") or "", 320),
            "url": rewrite_url(f"/topics/{t['slug']}", base),
            "definition": secs.get("definition", ""),
            "intuition": secs.get("intuition", ""),
            "derivation": secs.get("derivation", ""),
            "example": secs.get("example", ""),
            "mistakes": secs.get("mistakes", ""),
            "applications": secs.get("applications", ""),
            "points": secs.get("points", ""),
        })
    formulas = db.query("SELECT slug, name, latex, meaning, application FROM formulas ORDER BY name")
    problems = db.query("SELECT slug, title, difficulty, expected_time, expected_space FROM coding_problems ORDER BY title LIMIT 60")
    for p in problems:
        p["url"] = rewrite_url(f"/practice/problems/{p['slug']}", base)
    payload = {
        "personas": swarm.roster(),
        "topics": topic_items,
        "formulas": formulas,
        "problems": problems,
    }
    (site / "swarm-corpus.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


STATIC_RUNNER_NOTICE = (
    '<div class="callout info mb"><span class="label">Static-copy runner</span>'
    " On this public static copy, every language runs right in your browser with "
    "its real compiler or interpreter - JavaScript (isolated worker), Python "
    "(CPython/WebAssembly), C/C++ (Clang), Java (OpenJDK), Rust (rustc), C# "
    "(Roslyn), TypeScript, Go and SQL (SQLite) - each downloaded once, only when "
    "first used. A language whose runtime files are missing from this copy is "
    "<strong>not executed</strong> and is never marked as passed; the hosted "
    "EngineVerse compiler runs every language through its configured judge.</div>"
)


def enable_problem_editor(body: str) -> str:
    """Make every starter stub selectable and expose Submit on problem pages.

    Selectable is not the same as runnable: options stay enabled so a learner
    can read each starter, while pages-live.js labels the languages this
    static copy cannot execute and refuses to grade them. The server page's
    "Code execution is off" warning is *replaced* with the static-runner
    notice rather than deleted - deleting it made the exported page imply
    full multi-language execution that never happened.
    """
    def _enable_select(match: re.Match[str]) -> str:
        select_html = match.group(0)
        select_html = re.sub(r'\s+disabled(?=[>\s])', "", select_html)
        select_html = select_html.replace(" (starter only)", "")
        return select_html

    body = re.sub(r'<select id="lang-select">.*?</select>', _enable_select, body, count=1, flags=re.S)
    body, replaced = re.subn(
        r'<div class="callout warning mb">\s*<span class="label">Code execution is off</span>.*?</div>',
        STATIC_RUNNER_NOTICE,
        body,
        count=1,
        flags=re.S,
    )
    if not replaced and 'id="btn-run"' in body:
        body = body.replace(
            '<button class="btn btn-ghost" id="btn-run" type="button">Run</button>',
            STATIC_RUNNER_NOTICE + '\n        <button class="btn btn-ghost" id="btn-run" type="button">Run</button>',
            1,
        )
    if 'id="btn-submit"' not in body and 'id="btn-run"' in body:
        body = body.replace(
            '<button class="btn btn-ghost" id="btn-run" type="button">Run</button>',
            '<button class="btn btn-ghost" id="btn-run" type="button">Run</button>\n'
            '        <button class="btn btn-primary" id="btn-submit" type="button">Submit</button>',
            1,
        )
    return body


def _no_accounts_main(heading: str, intro: str) -> str:
    """Body of the old sign-in URLs, kept so existing bookmarks still resolve."""
    return f"""
<section class="page-hero" data-ev-page="no-accounts">
  <p class="ev-eyebrow">This device · no account needed</p>
  <h1>{html.escape(heading)}</h1>
  <p class="lead">{html.escape(intro)}</p>
</section>
<div class="grid g2 about-grid">
  <section class="panel">
    <h2>Your progress stays on this device</h2>
    <p>This public copy of EngineVerse runs entirely in your browser. There are no accounts or passwords, and nothing
      you do here is uploaded. Streaks, completed topics, solved problems, bookmarks and your study planner are
      saved in this browser's local storage.</p>
    <p class="row"><a class="btn btn-primary btn-sm" href="/dashboard">My progress</a>
      <a class="btn btn-ghost btn-sm" href="/explore">Explore subjects</a></p>
  </section>
  <section class="panel">
    <h2>Moving to another device</h2>
    <p>Export your progress as a JSON file from <a href="/settings">Settings</a>, then import it on the other
      device. Clearing this browser's site data deletes your progress, so export first if you want to keep it.</p>
    <p>Accounts, synced progress, discussions and certificates with a verification ID need a hosted EngineVerse
      server. The <a href="/hosting">hosting page</a> explains how to run one.</p>
  </section>
</div>
""".strip()


def write_account_pages(site: Path, base: str, home_html: str, apk_url: str = "",
                        branches: list[tuple[str, str]] | None = None) -> int:
    """Write the static copy's personal pages, driven by pages-live.js.

    The Pages copy has no accounts. These pages read and write one local
    profile record in this browser (``ev:local-profile:v1``) and never send it
    anywhere. Earlier versions exported password, OTP and "GitHub vault" pages
    here; their URLs now explain the local model so old bookmarks resolve.
    """
    branch_options = "\n".join(
        f'            <option value="{html.escape(slug, quote=True)}">{html.escape(name)}</option>'
        for slug, name in (branches or [])
    )
    apk_link = (
        f'<a class="btn btn-soft btn-sm" href="{html.escape(apk_url, quote=True)}" rel="noopener noreferrer">'
        'Download the Android app</a>'
        if apk_url else
        '<a class="btn btn-soft btn-sm" href="/install">Install the app</a>'
    )
    stats = """
  <div class="grid g4 dash-stats" aria-label="Your progress">
    <div class="stat dash-stat"><div class="n" id="ev-stat-xp">0</div><div class="l">XP · <span id="ev-stat-level">Level 1</span></div></div>
    <div class="stat dash-stat"><div class="n" id="ev-stat-streak">0</div><div class="l">Day streak · <span id="ev-stat-longest">best 0</span></div></div>
    <div class="stat dash-stat"><div class="n" id="ev-stat-topics">0</div><div class="l">Topics completed</div></div>
    <div class="stat dash-stat"><div class="n" id="ev-stat-problems">0</div><div class="l">Problems solved · <span id="ev-stat-quizzes">0 questions answered</span></div></div>
  </div>""".strip()
    local_note = ('<p class="chips-row"><span class="chip ok">Saved on this device only</span>'
                  '<span class="chip">Nothing is uploaded</span></p>')
    pages_spec: dict[str, tuple[str, str]] = {
        "/dashboard": ("My progress - EngineVerse", f"""
<div data-ev-page="dashboard">
  <section class="page-hero">
    <p class="ev-eyebrow">This device · progress</p>
    <h1 id="ev-dash-greeting">My progress</h1>
    <p class="lead">Everything you complete in this browser is counted here.</p>
    {local_note}
    <p class="row"><a class="btn btn-primary btn-sm" href="/today">Today's plan</a>
      <a class="btn btn-ghost btn-sm" href="/planner">Study planner</a>
      <a class="btn btn-ghost btn-sm" href="/settings">Settings and export</a></p>
  </section>
  {stats}
  <div class="grid g2 mt">
    <section class="panel">
      <h2>Recently completed</h2>
      <ul class="ev-local-list" id="ev-dash-activity"></ul>
      <p class="muted" data-ev-empty="ev-dash-activity">Nothing yet. Open a topic and mark it complete, answer a
        <a href="/dpp">daily practice</a> question or solve a <a href="/practice/problems">coding problem</a>.</p>
    </section>
    <section class="panel">
      <h2>Saved for later</h2>
      <ul class="ev-local-list" id="ev-dash-bookmarks"></ul>
      <p class="muted" data-ev-empty="ev-dash-bookmarks">Use the save button on a topic, video or book to keep it here.</p>
      <p class="row"><a class="btn btn-ghost btn-sm" href="/mistakes">Mistake notebook</a>
        <a class="btn btn-ghost btn-sm" href="/streaks">Streak heatmap</a>
        <a class="btn btn-ghost btn-sm" href="/portfolio">Portfolio</a></p>
    </section>
  </div>
</div>"""),
        "/profile": ("My profile - EngineVerse", f"""
<div data-ev-page="profile">
  <section class="page-hero">
    <p class="ev-eyebrow">This device · profile</p>
    <h1 id="ev-profile-name">EngineVerse learner</h1>
    <p class="lead"><span id="ev-profile-branch">Branch not set</span> · <span id="ev-profile-xp">0 XP</span></p>
    <p id="ev-profile-bio" class="muted"></p>
    {local_note}
    <p class="row"><a class="btn btn-ghost btn-sm" href="/settings">Edit profile</a>
      <a class="btn btn-ghost btn-sm" href="/portfolio">Portfolio view</a></p>
  </section>
  <div class="grid g2">
    <section class="panel">
      <h2>Completed topics</h2>
      <ul class="ev-local-list" id="ev-profile-topics"></ul>
      <p class="muted" data-ev-empty="ev-profile-topics">No topics completed yet.</p>
    </section>
    <section class="panel">
      <h2>Solved problems</h2>
      <ul class="ev-local-list" id="ev-profile-problems"></ul>
      <p class="muted" data-ev-empty="ev-profile-problems">No problems solved yet.</p>
    </section>
  </div>
</div>"""),
        "/settings": ("Settings - EngineVerse", f"""
<div data-ev-page="settings">
  <section class="page-hero">
    <p class="ev-eyebrow">This device · settings</p>
    <h1>Settings and your data</h1>
    <p class="lead">This copy has no accounts. Your profile and progress are stored in this browser only.</p>
    {local_note}
  </section>
  <p class="callout info mb" id="ev-settings-status" role="status" aria-live="polite" hidden></p>
  <div class="grid g2">
    <section class="panel">
      <h2>Profile</h2>
      <form id="ev-profile-form" novalidate>
        <div class="field"><label for="ev-set-display">Display name</label>
          <input type="text" id="ev-set-display" name="display_name" maxlength="60" autocomplete="nickname"
            placeholder="Shown on your progress and portfolio pages"></div>
        <div class="grid g2">
          <div class="field"><label for="ev-set-branch">Branch</label>
            <input type="text" id="ev-set-branch" name="branch" maxlength="60" list="ev-branch-options"
              placeholder="e.g. Computer Science">
            <datalist id="ev-branch-options">
{branch_options}
            </datalist></div>
          <div class="field"><label for="ev-set-year">Year of study</label>
            <select id="ev-set-year" name="year_of_study">
              <option value="0">Not set</option>
              <option value="1">1st year</option><option value="2">2nd year</option>
              <option value="3">3rd year</option><option value="4">4th year</option>
              <option value="5">5th year or later</option>
            </select></div>
        </div>
        <div class="field"><label for="ev-set-bio">Goal <span class="muted">(optional)</span></label>
          <input type="text" id="ev-set-bio" name="bio" maxlength="240" placeholder="e.g. Preparing for GATE"></div>
        <p class="small muted">Do not enter contact details: this page has no reason to store them.</p>
        <button class="btn btn-primary btn-sm" type="submit">Save profile</button>
      </form>
    </section>
    <section class="panel">
      <h2>Back up or move your progress</h2>
      <p class="muted">Download your progress as a JSON file, then import it in another browser or on another
        device. Importing replaces the progress stored here.</p>
      <p class="row">
        <button class="btn btn-soft btn-sm" type="button" id="ev-export-json">Export progress (.json)</button>
        <label class="btn btn-ghost btn-sm planner-import">Import progress
          <input type="file" id="ev-import-json" accept="application/json,.json" class="sr-only"></label>
      </p>
      <p class="small muted">The study planner has its own export on the <a href="/planner">planner page</a>.</p>
      <h2 class="mt">Delete your data</h2>
      <p class="muted">Removes your profile, streak, progress, mistakes and saved items from this browser.</p>
      <button class="btn btn-danger btn-sm" type="button" id="ev-clear-data">Delete my progress from this browser</button>
      <h2 class="mt">Install</h2>
      <p class="row">{apk_link}</p>
    </section>
  </div>
</div>"""),
        "/today": ("Today's plan - EngineVerse", """
<div data-ev-page="today">
  <section class="page-hero">
    <p class="ev-eyebrow">Progress · today</p>
    <h1>Today's plan</h1>
    <p class="lead">Four steps for a focused study day. Your streak counts any day you complete one.</p>
  </section>
  <div class="grid g2">
    <section class="panel"><h2>1. Learn one topic</h2>
      <p class="muted">Read a topic's explanation and worked example, then mark it complete.</p>
      <p><a class="btn btn-primary btn-sm" href="/explore">Browse topics</a></p></section>
    <section class="panel"><h2>2. Daily practice</h2>
      <p class="muted">Answer today's practice set. Answers are checked in your browser.</p>
      <p><a class="btn btn-primary btn-sm" href="/dpp">Open today's set</a></p></section>
    <section class="panel"><h2>3. Solve a coding problem</h2>
      <p class="muted">Write and run code in the browser against the problem's tests.</p>
      <p><a class="btn btn-primary btn-sm" href="/practice/problems">Open the problem bank</a></p></section>
    <section class="panel"><h2>4. Review mistakes</h2>
      <p class="muted">Re-read the questions you missed and the explanation for each.</p>
      <p class="row"><a class="btn btn-ghost btn-sm" href="/mistakes">Mistake notebook</a>
        <a class="btn btn-ghost btn-sm" href="/planner">Plan tomorrow</a></p></section>
  </div>
</div>"""),
        "/mistakes": ("Mistake notebook - EngineVerse", f"""
<div data-ev-page="mistakes">
  <section class="page-hero">
    <p class="ev-eyebrow">Practice · mistakes</p>
    <h1>Mistake notebook</h1>
    <p class="lead">Questions you answered incorrectly in this browser, with the correct answer and explanation.</p>
    {local_note}
  </section>
  <ul class="ev-local-list ev-mistakes" id="ev-mistakes-list"></ul>
  <p class="panel muted" data-ev-empty="ev-mistakes-list">No mistakes recorded. Answer questions in the
    <a href="/practice/questions">question bank</a> or <a href="/dpp">daily practice</a>.</p>
</div>"""),
        "/portfolio": ("Portfolio - EngineVerse", """
<div data-ev-page="portfolio">
  <section class="page-hero">
    <p class="ev-eyebrow">This device · portfolio</p>
    <h1 id="ev-portfolio-title">Learning portfolio</h1>
    <p class="lead" id="ev-portfolio-summary">A summary of what you have completed in this browser.</p>
    <p class="callout info">This page is generated from progress saved in this browser. It is not public and not
      verified by anyone. You can print it or save it as a PDF.</p>
    <p class="row"><button class="btn btn-soft btn-sm" type="button" id="ev-portfolio-print">Print or save as PDF</button>
      <a class="btn btn-ghost btn-sm" href="/settings">Edit name and branch</a></p>
  </section>
  <div class="grid g2">
    <section class="panel"><h2>Topics completed</h2>
      <ul class="ev-local-list" id="ev-portfolio-topics"></ul>
      <p class="muted" data-ev-empty="ev-portfolio-topics">No topics completed yet.</p></section>
    <section class="panel"><h2>Problems solved</h2>
      <ul class="ev-local-list" id="ev-portfolio-problems"></ul>
      <p class="muted" data-ev-empty="ev-portfolio-problems">No problems solved yet.</p></section>
  </div>
</div>"""),
        "/certificates": ("Certificates - EngineVerse", """
<div data-ev-page="certificates">
  <section class="page-hero">
    <p class="ev-eyebrow">Platform · certificates</p>
    <h1>Certificates</h1>
    <p class="lead">Certificates carry a verification ID that anyone can check. That needs completion records on a
      server, so this public copy cannot issue or verify them.</p>
  </section>
  <section class="panel">
    <h2>What you can do here</h2>
    <ul class="about-list">
      <li>Track completed topics and solved problems on <a href="/dashboard">My progress</a>.</li>
      <li>Print a summary of your work from the <a href="/portfolio">portfolio page</a>. It is clearly marked as
        unverified.</li>
      <li>Run your own EngineVerse server to issue verifiable certificates. See the <a href="/hosting">hosting page</a>.</li>
    </ul>
  </section>
</div>"""),
        "/login": ("Sign in - EngineVerse", _no_accounts_main(
            "No sign-in needed", "This public copy of EngineVerse has no accounts.")),
        "/register": ("Create an account - EngineVerse", _no_accounts_main(
            "No account needed", "This public copy of EngineVerse has no accounts. Start learning straight away.")),
        "/forgot-password": ("Password help - EngineVerse", _no_accounts_main(
            "There are no passwords here", "This public copy of EngineVerse has no accounts, so there is nothing to reset.")),
        "/reset-password": ("Password help - EngineVerse", _no_accounts_main(
            "There are no passwords here", "This public copy of EngineVerse has no accounts, so there is nothing to reset.")),
        "/logout": ("Sign out - EngineVerse", _no_accounts_main(
            "Nothing to sign out of", "This public copy of EngineVerse has no accounts. To remove your progress from this browser, use Settings.")),
        "/notifications": ("Notifications - EngineVerse", _no_accounts_main(
            "No notifications on this copy", "Notifications need an account on a hosted EngineVerse server.")),
        "/onboarding": ("Get started - EngineVerse", _no_accounts_main(
            "Get started", "Set your branch in Settings, then open your stream to see the subjects for it.")),
    }
    count = 0
    for path, (title, main_raw) in pages_spec.items():
        rewritten_main = rewrite_html(main_raw.strip(), base)
        page_html = fill_shell(home_html, title, rewritten_main)
        target = output_path(site, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page_html, encoding="utf-8")
        count += 1
    return count


def reading_copy_controls(text: str) -> str:
    """Do not leave backend-only lab forms looking executable on Pages.

    Server-rendered examples and JSON downloads remain readable. Controls are
    disabled in HTML as well as JS, so a no-script visitor cannot accidentally
    POST to a static host. The form action has already been rewritten to the
    hosting explanation; change its method to GET as a final fallback.
    """
    text = re.sub(
        r'(<form\b[^>]*\bdata-live-only\b[^>]*>)',
        lambda match: match.group(0).replace('method="post"', 'method="get"'),
        text,
    )
    text = re.sub(
        r'(<(?:button|input|textarea|select)\b[^>]*\bdata-live-control\b[^>]*)(>)',
        lambda match: match.group(1) + ' disabled aria-disabled="true"' + match.group(2),
        text,
    )
    return text.replace("data-lab-mode-notice hidden", "data-lab-mode-notice")


def inject(text: str, base: str, *, search: bool, dpp_dates: list[str] | None = None, apk_url: str = "") -> str:
    text = reading_copy_controls(rewrite_html(text, base))
    text = text.replace('href="/explore?year=1"', f'href="{rewrite_url("/explore/first-year", base)}"', 1)
    # The year link may already have been rewritten before this replacement.
    year = rewrite_url("/explore", base)
    text = text.replace(f'href="{year}?year=1"', f'href="{rewrite_url("/explore/first-year", base)}"')
    text = text.replace(f"href='{year}?year=1'", f"href='{rewrite_url('/explore/first-year', base)}'")
    notice = banner(base)
    text = text.replace("<header class=\"topbar\">", notice + "\n<header class=\"topbar\">", 1)
    if search:
        slot = '<div id="pages-results" hidden></div>\n' + search_script(base)
        text = text.replace("</main>", slot + "\n</main>", 1)
    text = text.replace("Runnable here", "Examples to copy")
    if dpp_dates:
        text = retarget_missing_dpp(text, base, dpp_dates)
    if "</body>" in text:
        boot = live_boot(base, dpp_dates or [], apk_url=apk_url)
        text = text.replace("</body>", boot + "\n" + mirror_script() + "\n</body>", 1)
    return text


def patch_app_js(text: str, base: str) -> str:
    sw_url = join_base(base, "/sw.js")
    text = text.replace(
        'navigator.serviceWorker.register("/sw.js")',
        f'navigator.serviceWorker.register("{sw_url}")',
    )
    for old in ("/login", "/register", "/api/"):
        text = text.replace(f'"{old}', f'"{join_base(base, old)}')
        text = text.replace(f"'{old}", f"'{join_base(base, old)}")
    text = text.replace('"/search?q=', f'"{rewrite_url("/search", base)}?q=')
    return text


def patch_sw_js(text: str, base: str) -> str:
    if base == "/":
        return text
    prefix = base.rstrip("/")
    text = text.replace('"/static/', f'"{prefix}/static/')
    text = text.replace('"/manifest.webmanifest"', f'"{prefix}/manifest.webmanifest"')
    return text


def copy_static(site: Path, base: str) -> None:
    src = BACKEND / "static"
    dest = site / "static"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    sw = dest / "sw.js"
    if sw.exists():
        sw_text = patch_sw_js(sw.read_text(encoding="utf-8"), base)
        (site / "sw.js").write_text(sw_text, encoding="utf-8")
        sw.unlink()
    app_js = dest / "js" / "app.js"
    app_js.write_text(patch_app_js(app_js.read_text(encoding="utf-8"), base), encoding="utf-8")
    # Static HTML (the offline fallback page) is copied verbatim from the app,
    # where its links are root-absolute ("/static/...", "/") and correct at the
    # app root. Under a Pages base prefix those resolve outside the base and
    # 404, so rewrite them exactly as rendered pages are rewritten. Only the
    # exported copy becomes base-aware; the live app keeps its root-absolute
    # links. This is a no-op when base is "/".
    for html_file in dest.rglob("*.html"):
        html_file.write_text(
            rewrite_html(html_file.read_text(encoding="utf-8"), base), encoding="utf-8"
        )
    manifest = {
        "name": "EngineVerse",
        "short_name": "EngineVerse",
        "description": "EngineVerse: Engineering notes, coding practice, labs, Android app and GitHub sync.",
        "start_url": rewrite_url("/", base),
        "scope": rewrite_url("/", base),
        "display": "standalone",
        "background_color": "#e4e9f1",
        "theme_color": "#e4e9f1",
        "icons": [
            {
                "src": rewrite_url("/static/icons/icon-192.png", base),
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": rewrite_url("/static/icons/icon-512.png", base),
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
    (site / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def mirror_script() -> str:
    """Delegate quiz grading to the browser quiz engine, with an offline fallback."""
    return """
<script>
(function () {
  document.querySelectorAll("[data-quiz] form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof window.EV_GRADE_QUIZ === "function") {
        window.EV_GRADE_QUIZ(form);
        return;
      }
      var card = form.closest("[data-quiz]");
      if (!card) return;
      var explain = card.querySelector(".explain");
      var badge = card.querySelector(".verdict-inline");
      if (explain) {
        explain.classList.add("on");
      }
      if (badge) {
        badge.textContent = "Checked in browser";
        badge.className = "verdict-inline chip";
        badge.style.display = "inline-block";
      }
    }, true);
  });
})();
</script>
"""


def assert_links(site: Path, base: str) -> None:
    prefix = "" if base == "/" else base.rstrip("/")
    missing: list[str] = []
    checked = 0
    for page in site.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="replace")
        for url in re.findall(r'(?:href|src|action)="([^"]+)"', text):
            target = _link_target(page, url, site, prefix)
            if target is None:
                continue
            checked += 1
            if not target.exists():
                missing.append(f"{page.relative_to(site)} -> {url}")
    if missing:
        sample = "\n".join(missing[:25])
        raise SystemExit(f"Refusing to publish. {len(missing)} links do not resolve:\n{sample}")
    print(f"Checked {checked} local URL references: 0 broken links")


def assert_heading_outlines(site: Path) -> None:
    offenders = []
    checked = 0
    for page in site.rglob("*.html"):
        previous = 0
        checked += 1
        for raw in re.findall(r"<h([1-6])\b", page.read_text(encoding="utf-8"), re.I):
            level = int(raw)
            if previous and level > previous + 1:
                offenders.append(f"{page.relative_to(site)}: h{previous} -> h{level}")
                break
            previous = level
    if offenders:
        raise SystemExit("Refusing to publish invalid heading outlines:\n" + "\n".join(offenders[:25]))
    print(f"Checked {checked} HTML heading outlines: 0 skipped levels")


def _link_target(page: Path, url: str, site: Path, prefix: str) -> Path | None:
    raw = url.strip()
    if not raw or raw.startswith(("#", "mailto:", "javascript:", "data:", "http://", "https://")):
        return None
    path = raw.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    if path.startswith("/"):
        if prefix and path != prefix and not path.startswith(prefix + "/"):
            return site / "__outside_base__"
        rel = path[len(prefix):].lstrip("/") if prefix else path.lstrip("/")
        if not rel:
            return site / "index.html"
        candidate = site / rel
    else:
        candidate = (page.parent / path).resolve()
        try:
            candidate.relative_to(site.resolve())
        except ValueError:
            return site / "__outside_tree__"
    if candidate.is_dir() or path.endswith("/") or not candidate.suffix:
        if candidate.suffix:
            return candidate
        return candidate / "index.html"
    return candidate


def assert_clean(site: Path) -> None:
    bad: list[str] = []
    for path in site.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for secret in FORBIDDEN:
            if secret in text:
                bad.append(f"{path.relative_to(site)} contains a forbidden token")
                break
    if bad:
        raise SystemExit("Refusing to publish:\n" + "\n".join(bad))


def fill_shell(home_html: str, title: str, main: str, *, private: bool = True) -> str:
    """A page built from the home shell. Its canonical/og:url would still name
    the home page, so they are removed and the page is marked noindex: these
    are personal or explanatory pages, not search content."""
    text = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", home_html, count=1, flags=re.S)
    if not private:
        return re.sub(
            r'(<main id="main" class="wrap">).*?(</main>)',
            lambda match: match.group(1) + "\n" + main + "\n" + match.group(2),
            text, count=1, flags=re.S,
        )
    text = re.sub(r'\s*<link rel="canonical"[^>]*>', "", text, count=1)
    text = re.sub(r'\s*<meta property="og:url"[^>]*>', "", text, count=1)
    if 'name="robots"' not in text:
        text = text.replace("</title>", '</title>\n  <meta name="robots" content="noindex">', 1)
    text = re.sub(
        r'(<main id="main" class="wrap">).*?(</main>)',
        lambda match: match.group(1) + "\n" + main + "\n" + match.group(2),
        text,
        count=1,
        flags=re.S,
    )
    return text


def export(site: Path, base: str, app_url: str = "", apk_url: str = "") -> int:
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    copy_static(site, base)

    from fastapi.testclient import TestClient

    app = load_app()
    client = TestClient(app, follow_redirects=False)
    written = 0
    failed: list[str] = []
    home_html = ""
    from engineverse import db as export_db

    dpp_dates = [
        row["date"]
        for row in export_db.query("SELECT date FROM dpp_sets WHERE published = 1 ORDER BY date")
        if row["date"]
    ]
    for path in public_paths():
        fetch = "/explore" if path == "/explore/first-year" else path
        if path == "/explore/first-year":
            response = client.get("/explore", params={"year": "1"})
        elif path.startswith("/topics/") and path.count("/") == 2:
            response = client.get(fetch, params={"depths": "all"})
        else:
            response = client.get(fetch)
        if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
            failed.append(f"{path} -> {response.status_code}")
            continue
        body = inject(response.text, base, search=(path == "/search"), dpp_dates=dpp_dates, apk_url=apk_url)
        if path.startswith("/practice/problems/") and path.count("/") == 3:
            body = enable_problem_editor(body)
        if path == "/install":
            body = fill_shell(body, "Install EngineVerse", rewrite_html(reading_copy_install_main(app_url, apk_url), base), private=False)
        # First-year page should not keep a query-string link to itself as the only year view.
        if path == "/explore/first-year":
            body = body.replace("<title>", "<title>First year - ", 1)
        target = output_path(site, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written += 1
        if path == "/":
            home_html = body

    if not home_html:
        raise SystemExit("Home page did not render. Nothing was published.")

    from engineverse import catalog

    branch_list = [(row["slug"], row["name"]) for row in catalog.list_branches()]
    written += write_account_pages(site, base, home_html, apk_url=apk_url, branches=branch_list)

    hosting = fill_shell(home_html, "Use EngineVerse", rewrite_html(hosting_main(app_url, apk_url), base))
    hosting_path = output_path(site, "/hosting")
    hosting_path.parent.mkdir(parents=True, exist_ok=True)
    hosting_path.write_text(hosting, encoding="utf-8")
    written += 1

    missing = client.get("/this-page-is-not-in-the-catalogue")
    not_found = inject(missing.text, base, search=False, apk_url=apk_url) if missing.text else home_html
    (site / "404.html").write_text(not_found, encoding="utf-8")

    index = search_index(base)
    (site / "search-index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    write_tutor_corpus(site, base)
    write_quiz_bank(site, base)
    write_coding_problems(site)
    write_studio_snapshot(site)
    write_workflows_catalog(site, base)
    write_swarm_corpus(site, base)

    origin = project.pages_origin() + ("" if base == "/" else base.rstrip("/"))
    locs = [origin + "/"]
    # Personal pages (driven by this browser's local profile) and the old
    # sign-in URLs that now only explain the local model are not search content.
    private = {p.strip("/") for p in LOCAL_ONLY_PATHS}
    for path in sorted(site.rglob("index.html")):
        rel = path.relative_to(site).as_posix()
        if rel == "index.html" or rel[: -len("/index.html")] in private:
            continue
        locs.append(origin + "/" + rel[: -len("index.html")])
    xml = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += [f"<url><loc>{html.escape(loc)}</loc></url>" for loc in locs]
    xml.append("</urlset>")
    (site / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")
    if failed:
        raise SystemExit("Refusing to publish. These pages did not render:\n" + "\n".join(failed))
    assert_clean(site)
    assert_links(site, base)
    assert_heading_outlines(site)
    revision = os.environ.get("GITHUB_SHA", "") or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    (site / "deployment.json").write_text(json.dumps({
        "revision": revision, "mode": "reading-copy", "base": base, "pages": written,
        "capabilities": [rewrite_url(path, base) for path in ("/apis", "/studio", "/workflows", "/swarm")],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {written} pages and {len(index)} search rows to {site}")
    return written


# ---------------------------------------------------------------------------
# Full-app gateway (only after an HTTPS app origin has been configured)
# ---------------------------------------------------------------------------

_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")


def normalise_app_url(value: str | None) -> str:
    """Only a public HTTPS origin (or localhost HTTP for local testing).

    The backend is mounted at /, not at an arbitrary path. Fail closed before
    a bad repository variable can redirect all of Pages to an unrelated host.
    Never echo rejected input: it might contain accidental credentials.
    """
    text = (value or "").strip().rstrip("/")
    if not text:
        return ""
    error = SystemExit("ENGINEVERSE_APP_URL must be a public HTTPS origin (localhost HTTP only for development).")
    if not re.fullmatch(r"https?://[A-Za-z0-9.:-]+", text):
        raise error
    try:
        parts = urlsplit(text)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        raise error from None
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise error
    if parts.scheme == "http" and host in {"localhost", "127.0.0.1"}:
        if port == 0 or parts.netloc != host + (f":{port}" if port is not None else ""):
            raise error
        return text
    if parts.scheme != "https" or port is not None or parts.netloc != host:
        raise error
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # A real DNS name is required for a public HTTPS origin.
    else:
        raise error
    if (len(host) > 253 or "." not in host or host.endswith((".local", ".internal", ".localhost"))
            or not all(_DNS_LABEL.fullmatch(label) for label in host.split("."))):
        raise error
    return text


def gateway_page(base: str, app_url: str, site_name: str, *, not_found: bool = False,
                 apk_url: str = "") -> str:
    """A small public doorway to the full app, with a deep-link-preserving 404."""
    css = html.escape(join_base(base, "/static/css/app.css"), quote=True)
    icon = html.escape(join_base(base, "/static/icons/favicon.svg"), quote=True)
    name = html.escape(site_name)
    repo = html.escape(REPO, quote=True)
    if app_url:
        home = html.escape(app_url + "/", quote=True)
        login = html.escape(app_url + "/login", quote=True)
        register = html.escape(app_url + "/register", quote=True)
        install = html.escape(app_url + "/install", quote=True)
        actions = (
            '<p class="row" style="justify-content:center;gap:12px">'
            f'<a class="btn btn-primary" href="{home}" id="gateway-open">Open full website</a>'
            f'<a class="btn btn-ghost" href="{login}" id="gateway-signin">Sign in</a>'
            f'<a class="btn btn-ghost" href="{register}">Create account</a></p>'
            f'<p><a href="{install}">Use EngineVerse on your phone</a></p>'
            '<p class="small muted">Accounts and progress live on the hosted app, not on GitHub Pages. '
            'Code execution is available only if that host has a judge configured.</p>'
        )
        if apk_url:
            actions += (
                f'<p><a class="btn btn-soft" href="{html.escape(apk_url, quote=True)}" '
                'rel="noopener noreferrer">Download signed EngineVerse.apk</a></p>'
            )
        # GitHub Pages serves its 404.html for old bookmarked catalogue paths.
        # Route those to the same path on the app (not blindly to /login). The
        # app itself decides whether a particular page needs authentication.
        script = (
            "<script>(function(){var app=" + json.dumps(app_url) + ";"
            "var base=" + json.dumps(base.rstrip("/")) + ";"
            "var path=location.pathname;"
            "if(base&&path!==base&&path.indexOf(base+'/')!==0)return;"
            "if(base)path=path.slice(base.length)||'/';"
            "path=path.replace(/\\/index\\.html$/,'/');"
            "if(!/^\\/[A-Za-z0-9._~%\\/-]*$/.test(path)||path.indexOf('//')===0"
            "||path.indexOf('..')!==-1)path='/';"
            "location.replace(app+path+location.search+location.hash);})();</script>"
            if not_found else
            "<script>location.replace(" + json.dumps(app_url + "/") + ");</script>"
        )
        lead = (
            "That link has moved to the full website. Taking you to the same page there..."
            if not_found else
            "The full website is online. No source download is needed. Opening it now..."
        )
        refresh = f'<meta http-equiv="refresh" content="3;url={home}">'
    else:
        actions = (
            '<div class="callout warning" style="text-align:left"><span class="label">Not hosted yet</span>'
            'GitHub Pages cannot store accounts or run a judge. The operator has not configured '
            'a public HTTPS app origin.</div>'
            f'<p><a class="btn btn-ghost" href="{repo}/blob/main/docs/DEPLOYMENT.md">'
            'How to host the full website</a></p>'
        )
        script = ""
        refresh = ""
        lead = "The public reading copy is available until the full app is deployed."
    title = "Page moved" if not_found else "Open the full site"
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{title} - {name}</title>
  {refresh}
  <link rel="icon" href="{icon}" type="image/svg+xml">
  <link rel="stylesheet" href="{css}">
</head>
<body>
<main id="main" class="wrap" style="min-height:80vh;display:grid;place-items:center">
  <div class="form-panel panel" style="text-align:center;max-width:560px">
    <h1>{name}</h1>
    <p class="muted">{html.escape(lead)}</p>
    {actions}
    <p class="tiny muted mt">This Pages address has no account database.
      <a href="{repo}">Source</a> · <a href="{html.escape(app_url + '/privacy' if app_url else repo, quote=True)}">Privacy</a></p>
  </div>
</main>
{script}
</body>
</html>
"""


def export_gateway(site: Path, base: str, app_url: str, site_name: str = "EngineVerse",
                   apk_url: str = "") -> int:
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    static = site / "static"
    (static / "css").mkdir(parents=True)
    (static / "icons").mkdir(parents=True)
    shutil.copy2(BACKEND / "static" / "css" / "app.css", static / "css" / "app.css")
    shutil.copy2(BACKEND / "static" / "icons" / "favicon.svg", static / "icons" / "favicon.svg")
    (site / "index.html").write_text(gateway_page(base, app_url, site_name, apk_url=apk_url), encoding="utf-8")
    (site / "404.html").write_text(gateway_page(base, app_url, site_name, not_found=True,
                                                apk_url=apk_url), encoding="utf-8")
    (site / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    revision = os.environ.get("GITHUB_SHA", "") or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    (site / "deployment.json").write_text(json.dumps({
        "revision": revision, "mode": "gateway", "base": base, "app_url": app_url,
    }, indent=2) + "\n", encoding="utf-8")
    assert_clean(site)
    assert_links(site, base)
    print(f"Wrote the full-app gateway to {site}")
    return 2


def self_check() -> None:
    assert rewrite_url("/topics/ohm", "/EngineVerse/") == "/EngineVerse/topics/ohm/"
    assert rewrite_url("/static/css/app.css", "/EngineVerse/") == "/EngineVerse/static/css/app.css"
    assert rewrite_url("/search?q=beam", "/") == "/search/?q=beam"
    assert rewrite_url("https://example.com", "/EngineVerse/") == "https://example.com"
    sample = '<a href="/login">Sign in</a><a href="/topics/a">A</a><a href="/api/docs">API</a>'
    rewritten = rewrite_html(sample, "/EngineVerse/")
    assert 'href="/EngineVerse/login/"' in rewritten
    assert 'href="/EngineVerse/hosting/"' in rewritten
    assert 'href="/EngineVerse/topics/a/"' in rewritten
    assert "LearnBuild#2026!" not in rewritten
    assert "data-theme" not in mirror_script()
    assert normalise_app_url("https://learn.example.org/") == "https://learn.example.org"
    assert normalise_app_url("http://localhost:8000/") == "http://localhost:8000"
    assert normalise_app_url("") == ""
    for bad in ('https://x.org/"><script>', "javascript:alert(1)", "http://example.org",
                "https://x.org/?a=b", "https://127.0.0.1", "https://x.org/private",
                "https://x.org:8443", "https://x.org:", "https://x.internal", "https://a..b.org"):
        try:
            normalise_app_url(bad)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"accepted {bad!r}")
    gate = gateway_page("/EngineVerse/", "https://learn.example.org", "EngineVerse")
    assert 'href="https://learn.example.org/login"' in gate and "/EngineVerse/static/css/app.css" in gate
    assert 'id="gateway-open"' in gate and "location.replace" in gate
    assert "Not hosted yet" in gateway_page("/EngineVerse/", "", "EngineVerse")
    assert "Download signed" not in gate
    assert "Download signed" in gateway_page(
        "/EngineVerse/", "https://learn.example.org", "EngineVerse",
        apk_url=project.release_download_prefix() + "android-v1.0.0/EngineVerse.apk"
    )
    # /apis is a page, not part of /api/. This boundary once silently dropped
    # the directory while exporting navigation links to it on every page.
    assert "/api/" in SKIP_PREFIXES and "/api" not in SKIP_PREFIXES
    assert not any("/apis".startswith(prefix) for prefix in SKIP_PREFIXES)
    assert any("/api/public-apis".startswith(prefix) for prefix in SKIP_PREFIXES)
    controls = reading_copy_controls(
        '<form method="post" data-live-only><button data-live-control>Run</button></form>'
        '<p data-lab-mode-notice hidden>Backend required</p>'
    )
    assert 'method="get"' in controls and ' disabled ' in controls
    assert 'data-lab-mode-notice hidden' not in controls
    assert 'href="/EngineVerse/apis/"' in rewrite_html('<a href="/apis">APIs</a>', "/EngineVerse/")
    print("self-check ok (API/page boundary, base URLs, backend-only controls)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the public reading copy or a gateway to the hosted app.")
    parser.add_argument("--out", default="site", help="output directory, relative to the repo root")
    parser.add_argument("--base", default=None, help="URL prefix, for example /EngineVerse/ or /")
    parser.add_argument("--self-check", action="store_true", help="check URL rewriting and exit")
    parser.add_argument("--skip-seed", action="store_true", help="reuse ENGINEVERSE_DB_PATH")
    parser.add_argument("--app-url", default=None,
                        help="full app HTTPS origin (default: $ENGINEVERSE_APP_URL)")
    parser.add_argument("--apk-url", default=None,
                        help="versioned signed GitHub Release APK URL (default: $ENGINEVERSE_APK_URL)")
    parser.add_argument("--gateway", action="store_true",
                        help="publish a gateway to the hosted app instead of the reading copy")
    parser.add_argument("--reading-copy", action="store_true",
                        help="publish the public reading copy (the default unless --gateway or an app URL is set)")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    base = repo_base(args.base)
    app_url = normalise_app_url(
        args.app_url if args.app_url is not None else os.environ.get("ENGINEVERSE_APP_URL", "")
    )
    try:
        apk_url = normalise_apk_url(
            args.apk_url if args.apk_url is not None else os.environ.get("ENGINEVERSE_APK_URL", "")
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.gateway and not app_url:
        raise SystemExit("Refusing to publish a gateway without a hosted full app origin.")
    if (args.gateway or app_url) and not args.reading_copy:
        export_gateway(ROOT / args.out, base, app_url, apk_url=apk_url)
        return 0
    db_path = ROOT / "data" / "pages-export.sqlite"
    env = prepare_env(db_path)
    os.environ.update(env)
    if not args.skip_seed:
        seed(env, db_path)
    export(ROOT / args.out, base, app_url=app_url, apk_url=apk_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
