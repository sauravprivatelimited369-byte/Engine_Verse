/* Global stream (branch) selector and site-wide filter.
 *
 * The selector lives in the top bar of every page. Choosing a stream does two
 * things at once, because "only that stream comes" has to hold both on the
 * page a learner is reading and on the pages they navigate to next:
 *
 *   1. It is remembered in this browser's local profile (the same record the
 *      progress and settings pages use), so the choice survives navigation.
 *   2. Every element marked ``data-ev-stream="<slug>"`` that belongs to a
 *      different stream is hidden, and containers marked
 *      ``data-ev-stream-scope`` collapse to their ``data-ev-stream-empty``
 *      placeholder when nothing inside them matches. Elements marked
 *      ``data-ev-stream-shared`` (shared subjects) are never hidden and count
 *      as a match. Elements with no attribute are chrome - navigation, footer,
 *      the note itself - and are never touched.
 *
 * The menu itself is rendered by ``base.html`` (with real links, so it works
 * without JavaScript and so the GitHub Pages export can rewrite the URLs);
 * this script only adds behaviour: the current selection, the dropdown, and
 * the filter. It never invents a stream that is not in ``#ev-streams``.
 */
(() => {
  "use strict";

  const PROFILE_KEY = "ev:local-profile:v1";
  const LEGACY_KEY = "ev:stream:v1";

  const bootNode = document.getElementById("ev-streams");
  if (!bootNode) return;
  let payload = {};
  try {
    payload = JSON.parse(bootNode.textContent || "{}");
  } catch (_) {
    return;
  }
  // ``base`` is the path prefix the deployment serves from (empty on the live
  // app, "/Engine_Verse" on the project-Pages copy). Links written into the
  // markup are rewritten at export time; the ones this script builds are not,
  // so they carry it here.
  const BASE = typeof payload.base === "string" ? payload.base.replace(/\/+$/, "") : "";
  const streams = Array.isArray(payload.streams) ? payload.streams : [];
  if (!streams.length) return;

  const url = (path) => BASE + path;

  const bySlug = new Map();
  for (const row of streams) {
    if (row && typeof row.slug === "string" && row.slug) bySlug.set(row.slug, row);
  }
  if (!bySlug.size) return;

  const list = () => Array.from(bySlug.values());
  const find = (slug) => bySlug.get(String(slug || ""));

  function readProfile() {
    try {
      const raw = localStorage.getItem(PROFILE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function writeProfile(profile) {
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    } catch (_) {
      /* storage blocked: the choice still applies for this page */
    }
  }

  // The local profile is the single source of truth. A separate key is kept
  // only to read a choice made by an earlier build that had no profile record.
  function current() {
    const profile = readProfile();
    const slug = profile && typeof profile.branch === "string" ? profile.branch : "";
    if (slug && bySlug.has(slug)) return slug;
    try {
      const legacy = localStorage.getItem(LEGACY_KEY);
      if (legacy && bySlug.has(legacy)) return legacy;
    } catch (_) { /* ignore */ }
    return "";
  }

  // Refuses a slug that is not one of the site's branches rather than storing
  // it: a stray value from a bookmark, an old build or a hand-edited profile
  // must not silently turn the filter off. Only an explicit empty choice - the
  // "All streams" entry - clears it.
  function store(slug) {
    if (slug && !bySlug.has(slug)) return false;
    const clean = slug || "";
    const profile = readProfile();
    profile.branch = clean;
    writeProfile(profile);
    try {
      if (clean) localStorage.setItem(LEGACY_KEY, clean);
      else localStorage.removeItem(LEGACY_KEY);
    } catch (_) { /* ignore */ }
    return true;
  }

  function control() {
    return document.getElementById("ev-stream-btn");
  }

  function paint() {
    const slug = current();
    const row = slug ? bySlug.get(slug) : null;
    const btn = control();
    if (btn) {
      const label = btn.querySelector(".ev-stream-label");
      if (label) label.textContent = row ? row.short || row.name : "Stream";
      btn.setAttribute("title", row ? `Your stream: ${row.name}` : "Choose your stream");
      btn.setAttribute(
        "aria-label",
        row ? `Your stream is ${row.name}. Choose another stream.` : "Choose your stream"
      );
      btn.classList.toggle("is-set", Boolean(row));
    }
    document.querySelectorAll("[data-ev-stream-slug]").forEach((el) => {
      const on = el.getAttribute("data-ev-stream-slug") === slug;
      el.classList.toggle("on", on);
      if (on) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    });
    const all = document.querySelector("[data-ev-stream-all]");
    if (all) all.classList.toggle("on", !slug);
  }

  function apply() {
    const slug = current();
    document.querySelectorAll("[data-ev-stream]").forEach((el) => {
      const value = el.getAttribute("data-ev-stream") || "";
      el.classList.toggle("ev-stream-off", Boolean(slug) && value !== slug);
    });
    document.querySelectorAll("[data-ev-stream-scope]").forEach((scope) => {
      // Shared items (data-ev-stream-shared, such as the first-year core) belong
      // to every stream, so they keep a scope open even when no branch item is
      // left. Without this a first-year page filtered by stream showed nothing.
      const visible = scope.querySelectorAll(
        "[data-ev-stream]:not(.ev-stream-off), [data-ev-stream-shared]"
      ).length > 0;
      const empty = scope.querySelector("[data-ev-stream-empty]");
      // Only a *chosen* stream collapses a shelf. With no choice, everything
      // shows exactly as it was rendered.
      const isEmpty = !visible && Boolean(slug);
      scope.classList.toggle("is-filtered-empty", isEmpty);
      if (empty) empty.classList.toggle("is-on", isEmpty);
    });
    // A grouping heading with no surviving members goes with them, rather than
    // leaving a category name above an empty list.
    document.querySelectorAll("[data-ev-stream-group]").forEach((group) => {
      const visible = group.querySelectorAll("[data-ev-stream]:not(.ev-stream-off)").length > 0;
      group.classList.toggle("ev-stream-off", Boolean(slug) && !visible);
    });
    // A filter that hides the whole catalogue should say so rather than leave a
    // grid of nothing. Only pages that asked for it (data-ev-stream-notice)
    // react; the attribute keeps the banner off pages that have no list.
    const notice = document.querySelector("[data-ev-stream-notice]");
    if (notice) {
      const row = slug ? bySlug.get(slug) : null;
      notice.classList.toggle("is-on", Boolean(row));
      const name = notice.querySelector("[data-ev-stream-notice-name]");
      if (name && row) name.textContent = row.name;
      const hub = notice.querySelector("[data-ev-stream-notice-hub]");
      if (hub) {
        const href = row ? url(`/stream/${row.slug}/`) : "/streams";
        if (hub.getAttribute("href") !== href) hub.setAttribute("href", href);
      }
    }
  }

  function select(slug) {
    store(slug);
    apply();
    paint();
    document.dispatchEvent(new CustomEvent("ev:stream-change", { detail: { stream: slug } }));
  }

  function wire() {
    // The menu itself is opened and closed by app.js's generic [data-menu]
    // handler; here we only turn a choice into a stored filter and, because
    // the hub *is* that stream, into the page the learner lands on.
    document.querySelectorAll("[data-ev-stream-all]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        select("");
        // A cleared choice has a real destination: the index of every stream.
        window.location.assign(link.getAttribute("href"));
      });
    });
    document.querySelectorAll("[data-ev-stream-slug]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const slug = link.getAttribute("data-ev-stream-slug");
        select(slug);
        const href = link.getAttribute("href");
        if (href) window.location.assign(href);
      });
    });
  }

  // The profile can change on another tab or through the settings page.
  window.addEventListener("storage", () => {
    apply();
    paint();
  });
  window.addEventListener("ev:local-profile", () => {
    apply();
    paint();
  });

  wire();
  apply();
  paint();

  window.EVStream = {
    list,
    find,
    current,
    select,
    apply,
    paint,
    store,
  };
})();
