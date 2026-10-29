"""What can actually be executed on this deployment, and how.

One table, used by every page that talks about running code.

The product has three different things a visitor can mean by "run my code":

* **run a program** - write a complete program, give it stdin, see its stdout;
* **judge a problem** - submit against a fixed set of test cases and get a
  verdict (accepted, wrong answer, compile error);
* **learn a language** - read the path, the reference and the exercises.

Only the first two execute anything, and they execute in different places. A
program can run in the browser (WebAssembly workers: CPython via Pyodide,
Clang, OpenJDK + TeaVM, Roslyn, GopherJS, rustc, SQLite, bash) or on the
server-side judge. Judging needs the server: the browser runs one program
against one stdin, and the hidden test cases and the verdict live on the
server.

The pages used to answer this question three different ways - a warning on
the compiler, a "Supported here:" line on a problem, and a count on the
homepage - and they did not always agree with each other or with the host.
This module is the one place that answers it, so the answer is the same
everywhere and it is true of *this* deployment rather than of the product in
general.

The wording matters as much as the data. "Code execution is off" tells a
student that nothing will happen and leaves them there. "Runs on this server
judge" and "runs in your browser after a one-off download" tell them where
their code will go and what it will cost them.
"""
from __future__ import annotations

import functools
from typing import Any

#: The browser engines the static copy can carry, and the one-off cost of
#: each. The size is the download the browser fetches on first use; after that
#: it is cached by the browser and by the service worker.
#:
#: These are *capabilities*, not promises: a copy that did not vendor a
#: runtime does not have it, and the manifest on disk decides that. The
#: labels are what the page shows the learner.
BROWSER_ENGINES: dict[str, dict[str, str]] = {
    "javascript": {
        "label": "JavaScript in an isolated Web Worker",
        "cost": "no download - it runs in the page",
        "engine": "Node-compatible browser worker",
    },
    "python": {
        "label": "CPython 3.12 in your browser (Pyodide, WebAssembly)",
        "cost": "one-off download of the CPython runtime, then cached",
        "engine": "CPython 3.12 (Pyodide)",
    },
    "c": {
        "label": "Clang 22 (GNU17) in your browser (WebAssembly)",
        "cost": "one-off download of the Clang runtime, then cached",
        "engine": "Clang 22 (GNU17)",
    },
    "cpp": {
        "label": "Clang 22 (GNU++20) in your browser (WebAssembly)",
        "cost": "one-off download of the Clang runtime, then cached",
        "engine": "Clang 22 (GNU++20)",
    },
    "java": {
        "label": "OpenJDK + TeaVM in your browser (WebAssembly)",
        "cost": "one-off download of the JDK runtime, then cached",
        "engine": "OpenJDK + TeaVM",
    },
    "typescript": {
        "label": "TypeScript 5.9 compiler in your browser",
        "cost": "one-off download of the compiler, then cached",
        "engine": "TypeScript 5.9",
    },
    "go": {
        "label": "Go 1.24 in your browser (GopherJS, WebAssembly)",
        "cost": "one-off download of the Go runtime, then cached",
        "engine": "Go 1.24 (GopherJS)",
    },
    "rust": {
        "label": "rustc in your browser (WebAssembly)",
        "cost": "one-off download of the rustc runtime, then cached",
        "engine": "rustc / Miri",
    },
    "csharp": {
        "label": "Roslyn on .NET WebAssembly in your browser",
        "cost": "one-off download of the .NET runtime, then cached",
        "engine": "Roslyn (.NET)",
    },
    "sql": {
        "label": "SQLite in your browser (WebAssembly)",
        "cost": "one-off download of the SQLite runtime, then cached",
        "engine": "SQLite",
    },
    "bash": {
        "label": "Bash in your browser",
        "cost": "one-off download of the shell runtime, then cached",
        "engine": "Bash (POSIX shell)",
    },
}


def _static_copy() -> bool:
    """True when this process is rendering the static GitHub Pages copy.

    The static copy has no server at all: no judge, no accounts, no API. It
    carries the browser runtimes instead, so "what runs here" has a completely
    different answer there.
    """
    import os

    return os.environ.get("ENGINEVERSE_STATIC_EXPORT", "") == "1"


@functools.lru_cache(maxsize=2)
def _browser_languages(static: bool) -> frozenset[str]:
    """The languages whose browser runtime this deployment can serve.

    On the static copy that is every engine in ``BROWSER_ENGINES`` - the copy
    either vendored the runtime or it did not, and the manifest on disk is
    what decides.

    On a server deployment the answer is *none*. The workers that execute
    code in the browser live in the static copy (``pages-live.js`` and
    CodeLab's static fallback), and a server deployment serves no
    ``/runtimes/`` directory to fetch a WebAssembly toolchain from. Saying
    "runs in your browser" there would be a promise the page cannot keep: the
    Run button would post to a judge that is switched off.

    This was previously "javascript", on the theory that a pure-JavaScript
    engine needs no file. The worker that would have run it is only
    constructed on the static copy, so the claim was not true of a server
    deployment.

    The flag is a parameter rather than being read inside the function
    because this result is cached: reading the environment inside the cached
    function meant the *first* caller's answer was reused for the whole
    process, so a page rendered for the static export kept claiming the
    static copy's capabilities after the export had finished.
    """
    if static:
        return frozenset(BROWSER_ENGINES)
    return frozenset()


def _server_languages() -> tuple[str, ...]:
    """The languages the judge on this host can execute right now."""
    from . import judge

    try:
        return tuple(judge.runnable_languages())
    except Exception:  # noqa: BLE001 - a capability page must still render
        return ()


def _language_names() -> dict[str, str]:
    """slug -> display name for every language the catalogue teaches."""
    from . import coding

    try:
        return {row["slug"]: row["name"] for row in coding.terminal_languages()}
    except Exception:  # noqa: BLE001
        return {}


def capabilities() -> dict[str, Any]:
    """The execution capabilities of *this* deployment.

    Returns a dictionary with:

    ``languages``
        One entry per catalogue language, in catalogue order, each saying
        whether it runs on the server, whether it runs in the browser, which
        of the two is the mode that actually works here, and what that costs.
    ``server``
        The judge: its name, whether it runs anything at all, and which
        languages it can execute.
    ``browser``
        Whether the browser can execute anything on this deployment.
    ``summary``
        One sentence a page can print without being wrong.
    """
    from . import judge

    names = _language_names()
    server_runnable = set(_server_languages())
    browser_runnable = set(_browser_languages(_static_copy()))

    try:
        info = judge.provider_info()
    except Exception:  # noqa: BLE001
        info = {"name": "disabled", "available": False}
    server_available = bool(info.get("available")) and bool(server_runnable)

    languages: list[dict[str, Any]] = []
    for slug, name in names.items():
        on_server = slug in server_runnable and server_available
        in_browser = slug in browser_runnable
        if on_server:
            mode = "server"
            label = "Runs on this server's judge"
            note = "Compiled by the judge's own toolchain and run against your input."
        elif in_browser:
            mode = "browser"
            engine = BROWSER_ENGINES.get(slug, {})
            label = engine.get("label", "Runs in your browser")
            note = engine.get("cost", "")
        else:
            mode = "unavailable"
            label = "Cannot run on this deployment"
            note = (
                "This deployment has no server judge and no browser runtime for "
                "this language."
            )
        languages.append({
            "slug": slug,
            "name": name,
            "server": on_server,
            "browser": in_browser,
            "mode": mode,
            "label": label,
            "note": note,
            # Judging needs the server: the browser runs one program with one
            # stdin and has no hidden test cases to compare against.
            "can_judge": on_server,
        })

    server_names = [row["name"] for row in languages if row["server"]]
    browser_names = [row["name"] for row in languages if row["browser"]]
    if server_available:
        summary = (
            f"{len(server_names)} language(s) run on this server's judge: "
            + ", ".join(server_names)
            + "."
        )
    elif browser_names:
        summary = (
            "This deployment has no server judge, so nothing is submitted to a "
            "server. " + str(len(browser_names)) + " language(s) run in your own "
            "browser instead: " + ", ".join(browser_names) + "."
        )
    else:
        summary = (
            "This deployment cannot execute code: there is no server judge and "
            "no browser runtime. The code you write here is not run."
        )

    return {
        "languages": languages,
        "server": {
            "name": info.get("name", "disabled"),
            "available": server_available,
            "runnable": sorted(server_runnable),
            "runs_on_this_server": bool(info.get("runs_on_this_server", server_available)),
        },
        "browser": {
            "available": bool(browser_names),
            "languages": sorted(browser_runnable),
        },
        "static_copy": _static_copy(),
        "summary": summary,
    }


def mode_for(slug: str, caps: dict[str, Any] | None = None) -> str:
    """``server``, ``browser`` or ``unavailable`` for one language."""
    caps = caps if caps is not None else capabilities()
    for row in caps["languages"]:
        if row["slug"] == slug:
            return row["mode"]
    return "unavailable"


def can_run(slug: str, caps: dict[str, Any] | None = None) -> bool:
    """True when this deployment can actually execute this language."""
    return mode_for(slug, caps) != "unavailable"


__all__ = [
    "BROWSER_ENGINES",
    "capabilities",
    "can_run",
    "mode_for",
]
