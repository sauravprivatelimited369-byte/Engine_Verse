/* Forge front-end.
 * Vanilla JS, no dependencies, no CDN. Everything here is progressive
 * enhancement: every feature has a working no-JS path via plain HTML forms.
 */
(() => {
  "use strict";

  const cfg = window.EngineVerse || { csrf: "", user: false };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // Only the server knows whether a session exists: base.html sets
  // window.EngineVerse.user from the authenticated request. The static Pages
  // copy has no accounts (#ev-live pages are handled by pages-live.js), so no
  // browser-side value - localStorage, cookies, attributes - is trusted here.
  function isSignedIn() {
    return Boolean(cfg.user);
  }

  // ---------------------------------------------------------------- API ----
  async function api(path, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    opts.headers["X-CSRF-Token"] = cfg.csrf;
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok || data.ok === false) {
      let message = data.error || `Request failed (${res.status})`;
      if (res.status === 403 && /csrf/i.test(message)) {
        // The page's token belongs to a session that has since changed - a
        // sign-in or sign-out in another tab, or a page restored from cache.
        message = "This page is out of date. Reload it and try again.";
      }
      const err = new Error(message);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // Where to send someone whose session is missing or has expired: the
  // sign-in form, coming back to this exact page afterwards.
  function signInUrl() {
    const here = location.pathname + location.search;
    return here === "/" ? "/login" : `/login?next=${encodeURIComponent(here)}`;
  }

  function toast(message, kind = "ok") {
    let box = $("#toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "toast";
      box.setAttribute("role", "status");
      box.style.cssText = "position:fixed;left:50%;bottom:var(--toast-bottom, 26px);transform:translateX(-50%);" +
        "background:var(--surface);border:1px solid var(--edge);border-radius:999px;padding:10px 20px;" +
        "box-shadow:var(--neu-lg);z-index:200;font-size:.9rem;max-width:90vw;color:var(--text);transition:opacity .3s";
      document.body.appendChild(box);
    }
    box.textContent = message;
    box.style.borderColor = kind === "bad" ? "var(--bad)" : "var(--ok)";
    box.style.opacity = "1";
    clearTimeout(box._t);
    box._t = setTimeout(() => { box.style.opacity = "0"; }, 3200);
  }

  // ------------------------------------------------------- mobile nav + menu
  // The panel is generated from the same navigation table as the desktop bar, so
  // it lists every group expanded rather than ten flat links. It is `hidden` in
  // the markup and this only flips that attribute: with scripting off the panel
  // stays hidden and the footer carries the same links, so nothing is lost.
  const toggle = $("#navtoggle");
  const panel = $("#mobilenav");
  const closeNav = () => {
    if (!panel || !toggle) return;
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    $(".topbar")?.classList.remove("open");
  };
  if (toggle && panel) {
    toggle.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = panel.hidden;
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      $(".topbar")?.classList.toggle("open", open);
    });
    // Tapping anywhere outside closes it, matching the account menu below.
    document.addEventListener("click", (e) => {
      if (!panel.hidden && !panel.contains(e.target) && e.target !== toggle) closeNav();
    });
  }
  document.addEventListener("click", (e) => {
    const menuBtn = e.target.closest("[data-menu] > button");
    if (menuBtn) {
      e.stopPropagation();
      const menu = menuBtn.closest("[data-menu]");
      const open = menu.hasAttribute("data-open");
      $$("[data-menu]").forEach((m) => {
        m.removeAttribute("data-open");
        const b = $("button", m);
        if (b) b.setAttribute("aria-expanded", "false");
      });
      if (!open) menu.setAttribute("data-open", "");
      menuBtn.setAttribute("aria-expanded", String(!open));
      return;
    }
    if (!e.target.closest("[data-menu]")) {
      $$("[data-menu]").forEach((m) => {
        m.removeAttribute("data-open");
        const b = $("button", m);
        if (b) b.setAttribute("aria-expanded", "false");
      });
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    $$("[data-menu]").forEach((m) => m.removeAttribute("data-open"));
    $$("[data-menu] button").forEach((b) => b.setAttribute("aria-expanded", "false"));
    closeNav();
  });

  // --------------------------------------------------- jump-to-stream picker
  // The picker inside a <form> already works without JavaScript because the
  // server accepts the same value (see /stream?to=). This just saves the extra
  // click when scripting is available.
  $$("select[data-navigate]").forEach((select) => {
    select.addEventListener("change", () => {
      const target = select.value;
      if (target && target.startsWith("/")) window.location.assign(target);
    });
  });

  // --------------------------------------------------------- live search box
  const searchInput = $("#global-search");
  const suggestBox = $("#suggest");
  if (searchInput && suggestBox) {
    let timer = null;
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim();
      clearTimeout(timer);
      if (q.length < 2) { suggestBox.hidden = true; return; }
      timer = setTimeout(async () => {
        try {
          const data = await api(`/api/search/suggest?q=${encodeURIComponent(q)}`);
          if (!data.suggestions.length) { suggestBox.hidden = true; return; }
          suggestBox.innerHTML = data.suggestions
            .map((s) => `<a href="/search?q=${encodeURIComponent(s.title)}">
              <span class="t">${escapeHtml(s.type)}</span><span>${escapeHtml(s.title)}</span></a>`)
            .join("");
          suggestBox.hidden = false;
        } catch (_) { suggestBox.hidden = true; }
      }, 180);
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".searchbox")) suggestBox.hidden = true;
    });
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // -------------------------------------------------------------- bookmarks
  $$("[data-bookmark]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (document.getElementById("ev-live")) return;
      if (!isSignedIn()) { location.href = signInUrl(); return; }
      const type = btn.dataset.type || btn.dataset.bookmark;
      const id = btn.dataset.id;
      try {
        const res = await api("/api/bookmarks", { method: "POST", body: { entityType: type, entityId: id } });
        btn.classList.toggle("on", res.bookmarked);
        btn.setAttribute("aria-pressed", String(res.bookmarked));
        btn.textContent = res.bookmarked ? "★ Saved" : "☆ Save";
        toast(res.bookmarked ? "Saved to your bookmarks" : "Removed from bookmarks");
      } catch (err) { toast(err.message, "bad"); }
    });
  });

  // ------------------------------------------------------------- MCQ quiz
  // The answer key never ships in the page: options render without the
  // correct flag and the explanation div starts empty. The graded response
  // from /api/practice/answer carries correct, correctLabel, explanation and
  // xp, and only then does the card reveal which option was right, why, and
  // what the answer earned. XP is knowledge-based: only the first correct
  // answer to a question pays; wrong attempts earn no XP and land in the
  // mistake notebook like any other question.
  $$("[data-quiz]").forEach((card) => {
    const qid = card.dataset.quiz;
    const form = $("form", card);
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      if (document.getElementById("ev-live")) return;
      e.preventDefault();
      if (!isSignedIn()) { location.href = signInUrl(); return; }
      const picked = form.querySelector("input[name=option]:checked");
      if (!picked) { toast("Pick an answer first", "bad"); return; }
      const index = Number(picked.value);
      const submit = $("button[type=submit]", form);
      submit.disabled = true;
      try {
        const res = await api("/api/practice/answer", {
          method: "POST",
          body: { questionId: qid, optionIndex: index, setId: card.dataset.set || null },
        });
        const correctLabel = String(res.correctLabel || "").trim();
        $$(".opt", card).forEach((opt) => {
          opt.classList.add("locked");
          const key = $(".k", opt);
          const label = key ? key.textContent.trim() : "";
          if (correctLabel && label === correctLabel) opt.classList.add("correct");
          else if (Number(opt.dataset.index) === index) opt.classList.add("wrong");
          $$("input", opt).forEach((inp) => { inp.disabled = true; });
        });
        const explain = $(".explain", card);
        if (explain) {
          // Built with DOM nodes, not innerHTML: an explanation is authored
          // content, and this path stays injection-proof even if that ever
          // changes.
          explain.replaceChildren();
          const lead = document.createElement("strong");
          if (res.explanation) {
            lead.textContent = "Why.";
            explain.append(lead, ` ${res.explanation}`);
          } else {
            lead.textContent = res.correct ? "Correct." : `The answer is ${correctLabel || "marked above"}.`;
            explain.append(lead);
          }
          if (!res.correct) {
            const more = document.createElement("span");
            more.className = "small muted";
            more.textContent = " Saved to your mistake notebook.";
            explain.append(more);
          }
          explain.classList.add("on");
        }
        const badge = $(".verdict-inline", card);
        if (badge) {
          badge.textContent = res.correct ? "Correct" : "Not quite";
          badge.className = `verdict-inline chip ${res.correct ? "ok" : "bad"}`;
          badge.style.display = "inline-block";
        }
        if (res.xp) {
          toast(`+${res.xp} XP`);
        } else if (res.correct && res.alreadySolved) {
          toast("Already solved before — XP is earned on your first correct answer");
        }
      } catch (err) {
        if (err.status === 401) {
          toast("Your session ended. Sign in again to keep practising.", "bad");
          setTimeout(() => { location.href = signInUrl(); }, 900);
          return;
        }
        toast(err.message, "bad");
        submit.disabled = false;
      }
    });
  });

  // ---------------------------------------------------------- code editor
  const editor = $("#code-editor");
  if (editor) {
    const langSelect = $("#lang-select");
    const stubs = JSON.parse(editor.dataset.stubs || "{}");
    const problemSlug = editor.dataset.problem || "";
    const output = $("#run-output");
    const customInput = $("#custom-input");
    const STORAGE = `ev:code:${problemSlug}`;
    const storageKeyFor = (lang) => `${STORAGE}:${lang || "python"}`;
    const activeLang = () => (langSelect ? langSelect.value : "python");
    const resolveStub = (lang) => {
      const fromLive = window.EV_STUBS && window.EV_STUBS[lang];
      const fromData = stubs[lang];
      return (fromData && (fromData.stub || fromData)) || fromLive || "";
    };

    const initialLang = activeLang();
    const saved = localStorage.getItem(storageKeyFor(initialLang)) || localStorage.getItem(STORAGE);
    if (saved) editor.value = saved;

    editor.addEventListener("input", () => {
      localStorage.setItem(storageKeyFor(activeLang()), editor.value);
    });

    // Real tab handling instead of losing focus.
    editor.addEventListener("keydown", (e) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const start = editor.selectionStart;
        editor.value = editor.value.slice(0, start) + "    " + editor.value.slice(editor.selectionEnd);
        editor.selectionStart = editor.selectionEnd = start + 4;
        localStorage.setItem(storageKeyFor(activeLang()), editor.value);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        $("#btn-run")?.click();
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        $("#btn-submit")?.click();
      }
    });

    // Run and Submit stay disabled while the selected language has no runtime
    // on this server, so a click can never imply code ran when it did not.
    function selectedRunnable() {
      if (!langSelect) return true;
      const picked = langSelect.selectedOptions && langSelect.selectedOptions[0];
      return !picked || !picked.disabled;
    }

    function syncRunButtons() {
      const runnable = selectedRunnable();
      const hint = runnable ? "" : "This language has no runtime on this server — nothing would be executed.";
      ["#btn-run", "#btn-submit"].forEach((sel) => {
        const btn = $(sel);
        if (!btn) return;
        // A click handler disables its own button while a request is in
        // flight; only re-enable here when the language can actually run.
        if (btn.dataset.busy !== "1") btn.disabled = !runnable;
        btn.title = hint;
      });
      return runnable;
    }

    if (langSelect) {
      langSelect.addEventListener("change", () => {
        const lang = langSelect.value;
        const stored = localStorage.getItem(storageKeyFor(lang));
        if (stored) {
          editor.value = stored;
        } else {
          const nextStub = resolveStub(lang);
          if (nextStub) editor.value = nextStub;
        }
        $("#stub-signature")?.replaceChildren(
          Object.assign(document.createElement("code"), { textContent: ((stubs[lang] && stubs[lang].signature) || "") }));
        syncRunButtons();
      });
      syncRunButtons();
    }

    // Plain-language reasons for verdicts where no code ran. The keys match
    // the judge statuses the API returns with executed=false.
    const NOT_RUN_REASONS = {
      unsupported_language: "This language has no runtime on this server.",
      sandbox_unavailable: "Code execution is unavailable on this host.",
      internal_error: "The judge failed before running the code.",
    };

    function notRunPanel(result, verb) {
      const status = result.status || "internal_error";
      const judgeName = (result.judge && result.judge.name) || (langSelect && langSelect.dataset.judge) || "disabled";
      const reason = NOT_RUN_REASONS[status] || "The code was not run.";
      const lines = [`${verb} — nothing was executed (judge: ${judgeName}).`, "", reason];
      if (result.stderr) lines.push("", result.stderr.slice(0, 4000));
      return `<div class="verdict ${status}">Not run</div>` +
        `<pre class="console">${escapeHtml(lines.join("\n"))}</pre>`;
    }

    function renderRun(result) {
      if (!output) return;
      if (result.executed === false) {
        output.innerHTML = notRunPanel(result, "Run refused");
        return;
      }
      const status = result.status || "internal_error";
      const lines = [`status: ${status}`];
      const runtimeMs = result.runtimeMs != null ? result.runtimeMs : result.runtime_ms;
      if (runtimeMs != null) lines.push(`time: ${runtimeMs} ms`);
      if (result.stdout) lines.push("", "--- stdout ---", result.stdout);
      if (result.stderr) lines.push("", "--- stderr ---", result.stderr.slice(0, 4000));
      output.innerHTML = `<div class="verdict ${status}">${status.replace(/_/g, " ")}</div>` +
        `<pre class="console">${escapeHtml(lines.join("\n"))}</pre>`;
    }

    function renderEvaluation(result) {
      if (!output) return;
      if (result.executed === false) {
        output.innerHTML = notRunPanel(result, "Submission not judged");
        return;
      }
      const parts = [`<div class="verdict ${result.status}">${result.status.replace(/_/g, " ")} — ` +
        `${result.passed}/${result.total} tests</div>`];
      parts.push('<pre class="console">' + escapeHtml(
        `time: ${result.runtimeMs} ms` + (result.stderr ? `\n\n${result.stderr.slice(0, 3000)}` : "")) + "</pre>");
      (result.cases || []).forEach((c, i) => {
        parts.push(`<div class="testcase ${c.passed ? "pass" : "fail"}">
          <div class="lbl">${c.passed ? "✓" : "✗"} Test ${i + 1}${c.is_sample ? " (sample)" : ""}</div>
          <pre>input:    ${escapeHtml(c.input || "(none)")}
expected: ${escapeHtml(c.expected)}
actual:   ${escapeHtml(c.actual)}</pre></div>`);
      });
      output.innerHTML = parts.join("");
    }

    $("#btn-run")?.addEventListener("click", async () => {
      const btn = $("#btn-run");
      btn.dataset.busy = "1";
      btn.disabled = true;
      btn.innerHTML = '<span class="spin"></span> Running';
      try {
        const lang = langSelect ? langSelect.value : "python";
        localStorage.setItem(`${STORAGE}:${lang}`, editor.value);
        const res = await api("/api/coding/run", {
          method: "POST",
          body: { language: lang, code: editor.value, input: customInput ? customInput.value : "",
                  problemSlug: problemSlug || null },
        });
        renderRun(res.result);
      } catch (err) { toast(err.message, "bad"); }
      btn.dataset.busy = "";
      btn.textContent = "Run";
      syncRunButtons();
    });

    $("#btn-submit")?.addEventListener("click", async () => {
      if (document.getElementById("ev-live")) return;
      if (!isSignedIn()) { location.href = signInUrl(); return; }
      const btn = $("#btn-submit");
      btn.dataset.busy = "1";
      btn.disabled = true;
      btn.innerHTML = '<span class="spin"></span> Judging';
      try {
        const lang = langSelect ? langSelect.value : "python";
        const res = await api("/api/coding/submit", {
          method: "POST",
          body: { problemSlug, language: lang, code: editor.value },
        });
        renderEvaluation(res.result);
        if (res.result.executed !== false && res.result.status === "accepted") {
          toast(res.result.xp ? `Accepted — +${res.result.xp} XP`
                               : "Accepted — first solve already earned its XP");
          const solved = $("#solved-chip");
          if (solved) solved.classList.remove("hide");
        }
      } catch (err) { toast(err.message, "bad"); }
      btn.dataset.busy = "";
      btn.textContent = "Submit";
      syncRunButtons();
    });

    $("#btn-reset")?.addEventListener("click", () => {
      const lang = langSelect ? langSelect.value : "python";
      const nextStub = resolveStub(lang);
      if (nextStub) editor.value = nextStub;
      localStorage.removeItem(storageKeyFor(lang));
      if (lang === "python") localStorage.removeItem(STORAGE);
    });
  }

  // ---------------------------------------------------------- compiler page
  // The website compiler/terminal: a complete program per language, run
  // verbatim by the judge through POST /api/coding/run (no problem attached).
  // On the static Pages copy there is no judge to post to, so pages-live.js
  // supplies window.EV_BROWSER_TERMINAL (JavaScript in a worker, CPython via
  // Pyodide) and this handler prefers it there; everything else reports
  // "not run" rather than faking output.
  const cplEditor = $("#cpl-editor");
  if (cplEditor) {
    const cplLang = $("#cpl-lang");
    const cplInput = $("#cpl-input");
    const cplOutput = $("#cpl-output");
    const cplRunBtn = $("#cpl-run");
    let cplRows = [];
    try { cplRows = JSON.parse(document.getElementById("cpl-data")?.textContent || "[]"); }
    catch (_) { cplRows = []; }
    const cplBySlug = Object.fromEntries(cplRows.map((row) => [row.slug, row]));
    const cplStore = (kind, slug) => `ev:compiler:${kind}:${slug}`;

    function cplRow() { return cplBySlug[cplLang ? cplLang.value : "python"] || {}; }

    function cplSyncRun() {
      if (!cplRunBtn || !cplLang) return;
      const picked = cplLang.selectedOptions && cplLang.selectedOptions[0];
      const runnable = !picked || !picked.disabled;
      if (cplRunBtn.dataset.busy !== "1") cplRunBtn.disabled = !runnable;
      cplRunBtn.title = runnable ? "" : "This language has no runtime here — nothing would be executed.";
    }

    function cplPaintMeta() {
      const row = cplRow();
      const runtimeEl = $("#cpl-runtime");
      if (runtimeEl) runtimeEl.textContent = row.runtime || "";
      const noteEl = $("#cpl-note");
      if (noteEl) noteEl.textContent = row.note || "";
      cplSyncRun();
    }

    function cplLoad(slug, forceStarter) {
      const row = cplBySlug[slug] || {};
      const stored = forceStarter ? null : localStorage.getItem(cplStore("code", slug));
      cplEditor.value = stored != null ? stored : (row.code || "");
      if (cplInput) {
        const storedInput = forceStarter ? null : localStorage.getItem(cplStore("input", slug));
        cplInput.value = storedInput != null ? storedInput : (row.sample_input || "");
      }
      cplPaintMeta();
      if (typeof window.EV_BROWSER_PREWARM === "function") {
        window.EV_BROWSER_PREWARM(slug);
      }
    }

    function cplRender(result) {
      if (!cplOutput) return;
      const row = cplRow();
      if (!result || result.executed === false) {
        const status = (result && result.status) || "internal_error";
        const judgeName = (result && result.judge && result.judge.name) ||
          (result && result.via) || (cplLang && cplLang.dataset.judge) || "disabled";
        const lines = [`Run refused — nothing was executed (${judgeName}).`];
        if (status === "unsupported_language") {
          lines.push("", `${row.name || "This language"} has no runtime in this copy of Forge.`);
        }
        if (result && result.stderr) lines.push("", String(result.stderr).slice(0, 4000));
        cplOutput.innerHTML = `<div class="verdict ${status}">Not run</div>` +
          `<pre class="console">${escapeHtml(lines.join("\n"))}</pre>`;
        return;
      }
      const status = result.status || "internal_error";
      const via = result.via || (result.judge && result.judge.name) || row.runtime || "";
      const lines = [`status: ${status}${via ? ` · via ${via}` : ""}`];
      const runtimeMs = result.runtimeMs != null ? result.runtimeMs : result.runtime_ms;
      if (runtimeMs != null) lines.push(`time: ${runtimeMs} ms`);
      const exitCode = result.exitCode != null ? result.exitCode : result.exit_code;
      if (exitCode != null) lines.push(`exit code: ${exitCode}`);
      lines.push("", "--- stdout ---", result.stdout ? String(result.stdout) : "(no output)");
      if (result.stderr) lines.push("", "--- stderr ---", String(result.stderr).slice(0, 4000));
      cplOutput.innerHTML = `<div class="verdict ${status}">${status.replace(/_/g, " ")}</div>` +
        `<pre class="console">${escapeHtml(lines.join("\n"))}</pre>`;
    }

    cplEditor.addEventListener("input", () => {
      localStorage.setItem(cplStore("code", cplRow().slug || "python"), cplEditor.value);
    });
    cplInput?.addEventListener("input", () => {
      localStorage.setItem(cplStore("input", cplRow().slug || "python"), cplInput.value);
    });
    cplEditor.addEventListener("keydown", (e) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const start = cplEditor.selectionStart;
        cplEditor.value = cplEditor.value.slice(0, start) + "    " + cplEditor.value.slice(cplEditor.selectionEnd);
        cplEditor.selectionStart = cplEditor.selectionEnd = start + 4;
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        cplRunBtn?.click();
      }
    });
    cplLang?.addEventListener("change", () => cplLoad(cplLang.value, false));
    $("#cpl-reset")?.addEventListener("click", () => {
      const slug = cplLang ? cplLang.value : "python";
      localStorage.removeItem(cplStore("code", slug));
      localStorage.removeItem(cplStore("input", slug));
      cplLoad(slug, true);
    });

    cplRunBtn?.addEventListener("click", async () => {
      const row = cplRow();
      const slug = row.slug || (cplLang ? cplLang.value : "python");
      cplRunBtn.dataset.busy = "1";
      cplRunBtn.disabled = true;
      cplRunBtn.innerHTML = '<span class="spin"></span> Running';
      const unsub = typeof window.EV_ON_RUNTIME_STATUS === "function"
        ? window.EV_ON_RUNTIME_STATUS((ev) => {
            if (!ev || (ev.lang && ev.lang !== slug) || !cplOutput || cplRunBtn.dataset.busy !== "1") return;
            cplOutput.innerHTML = `<pre class="console">${escapeHtml(ev.message || "Preparing compiler runtime…")}</pre>`;
          })
        : null;
      try {
        if (document.getElementById("ev-live") && typeof window.EV_BROWSER_TERMINAL === "function") {
          cplRender(await window.EV_BROWSER_TERMINAL(slug, cplEditor.value, cplInput ? cplInput.value : ""));
        } else {
          const res = await api("/api/coding/run", {
            method: "POST",
            body: { language: row.judge_slug || slug, code: cplEditor.value,
                    input: cplInput ? cplInput.value : "", problemSlug: null },
          });
          cplRender(res.result);
        }
      } catch (err) { toast(err.message, "bad"); }
      if (typeof unsub === "function") unsub();
      cplRunBtn.dataset.busy = "";
      cplRunBtn.textContent = "Run";
      cplSyncRun();
    });

    cplLoad(cplLang ? cplLang.value : "python", false);
  }

  // ---------------------------------------------------------- flashcards
  const deck = $("#flashdeck");
  if (deck) {
    const cards = JSON.parse(deck.dataset.cards || "[]");
    let i = Number(deck.dataset.start || 0);
    const face = $("#card-face");
    const counter = $("#card-counter");

    function paint() {
      if (!cards.length) {
        deck.innerHTML = '<div class="empty"><span class="em">🎉</span>Nothing due right now. Come back later.</div>';
        return;
      }
      i = ((i % cards.length) + cards.length) % cards.length;
      const card = cards[i];
      face.querySelector(".front .txt").textContent = card.front;
      face.querySelector(".back .txt").textContent = card.back;
      face.classList.remove("flip");
      counter.textContent = `Card ${i + 1} of ${cards.length}`;
      deck.dataset.current = card.id;
    }

    face.addEventListener("click", () => face.classList.toggle("flip"));
    deck.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); face.classList.toggle("flip"); }
    });
    $$(".rate", deck).forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rating = btn.dataset.rate;
        try {
          await api("/api/revision/review", {
            method: "POST", body: { cardId: deck.dataset.current, rating },
          });
          const stats = await api("/api/revision/due?limit=1");
          const remaining = $("#due-count");
          if (remaining && stats.stats) remaining.textContent = stats.stats.due;
          cards.splice(i, 1);
          paint();
          toast(rating === "again" ? "Card will come back sooner" : "Reviewed");
        } catch (err) { toast(err.message, "bad"); }
      });
    });
    paint();
  }

  // ------------------------------------------------------------- voting
  $$("[data-vote]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (document.getElementById("ev-live")) return;
      if (!isSignedIn()) { location.href = signInUrl(); return; }
      try {
        const res = await api("/api/community/vote", {
          method: "POST",
          body: { entityType: btn.dataset.type, entityId: btn.dataset.id, value: Number(btn.dataset.vote) },
        });
        const box = btn.closest(".votebox");
        box.querySelector(".n").textContent = res.score;
        $$("button", box).forEach((b) => b.classList.remove("on"));
        btn.classList.add("on");
      } catch (err) { toast(err.message, "bad"); }
    });
  });

  // ---------------------------------------------------- mark topic complete
  $$("[data-complete-topic]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (document.getElementById("ev-live")) return;
      if (!isSignedIn()) { location.href = signInUrl(); return; }
      btn.disabled = true;
      try {
        const res = await api("/api/me/progress/topic", {
          method: "POST", body: { topicId: btn.dataset.id, status: "completed" },
        });
        btn.textContent = "Completed ✓";
        btn.classList.remove("btn-primary");
        btn.classList.add("btn-soft");
        const lvl = $(".xpchip .lvl");
        if (lvl && res.stats) lvl.textContent = res.stats.level;
        toast("Topic marked complete — +20 XP");
      } catch (err) { toast(err.message, "bad"); btn.disabled = false; }
    });
  });

  // ------------------------------------------------------- diagram hotspots
  $$("[data-diagram]").forEach((wrap) => {
    const spots = JSON.parse(wrap.dataset.hotspots || "[]");
    const note = $(".hotspot-note", wrap);
    const svg = $("svg", wrap);
    if (!svg || !spots.length) return;
    const vb = svg.viewBox.baseVal;
    spots.forEach((spot) => {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", spot.x); rect.setAttribute("y", spot.y);
      rect.setAttribute("width", spot.w); rect.setAttribute("height", spot.h);
      rect.setAttribute("fill", "rgba(56,189,248,.10)");
      rect.setAttribute("stroke", "#38bdf8"); rect.setAttribute("stroke-width", "1.5");
      rect.setAttribute("rx", "6");
      rect.style.cursor = "pointer";
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = spot.label;
      rect.appendChild(title);
      rect.addEventListener("click", () => {
        note.innerHTML = `<strong>${escapeHtml(spot.label)}.</strong> ${escapeHtml(spot.explain)}`;
        note.classList.add("on");
      });
      svg.appendChild(rect);
    });
    void vb;
  });

  // -------------------------------------------------------------- PWA
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => { /* offline support optional */ });
    });
  }
  let deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const btn = $("#install-btn");
    if (btn) btn.classList.remove("hide");
  });
  $("#install-btn")?.addEventListener("click", async () => {
    if (!deferredPrompt) { toast("Use your browser menu → Add to Home Screen"); return; }
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
  });

  // -------------------------------------------------- auto-dismiss flash
  const flash = $(".flash");
  if (flash) setTimeout(() => { flash.style.transition = "opacity .5s"; flash.style.opacity = "0";
    setTimeout(() => flash.remove(), 500); }, 4200);

  // Tile lift is CSS. A pointer-driven 3D tilt fights the clay shadow.

  // ------------------------------------------------- data-json-form forms
  // Progressive enhancement only. Every one of these forms is a real HTML form
  // that posts urlencoded and is handled server-side, so with scripting off the
  // browser submits it natively and follows the 303 back. This handler just
  // upgrades that to a fetch so the page does not reload on every save.
  $$("form[data-json-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const payload = {};
      new FormData(form).forEach((value, key) => {
        // The community forms take tags as a list; the field is comma-separated.
        payload[key] = key === "tags"
          ? String(value).split(",").map((t) => t.trim()).filter(Boolean)
          : value;
      });
      const button = $("button[type=submit]", form);
      if (button) button.disabled = true;
      try {
        const data = await api(form.action, { method: "POST", body: payload });
        toast(data.message || "Saved.");
        if (data.url) { window.location.href = data.url; return; }
        setTimeout(() => window.location.reload(), 700);
      } catch (err) {
        toast(err.message || "That did not work.", "bad");
        if (button) button.disabled = false;
      }
    });
  });

  // ------------------------------------------------------------ AI tutor
  // Renders only what the server returned, escaped. The answer is assembled
  // from platform notes, but nothing goes into innerHTML unescaped: the tutor
  // is a surface like any other, and a note body is still user-authored data.
  const tutorForm = $("#tutor-form");
  if (tutorForm) {
    const questionEl = $("#tutor-question");
    const resultEl = $("#tutor-result");
    const answerEl = $("#tutor-answer");
    const messageEl = $("#tutor-message");
    const sourcesEl = $("#tutor-sources");
    const sourceList = $("#tutor-source-list");
    const disclosureEl = $("#tutor-disclosure");
    const emptyEl = $("#tutor-empty");
    const sendBtn = $("#tutor-send");

    // The server sends a small markdown subset: **bold**, `code`, and
    // paragraphs. Anything else is treated as text.
    const inline = (text) => escapeHtml(text)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

    const render = (data) => {
      emptyEl.hidden = true;
      resultEl.hidden = false;
      if (data.disclosure && disclosureEl) disclosureEl.textContent = data.disclosure;

      if (data.message) {
        messageEl.hidden = false;
        messageEl.textContent = data.message;
      } else {
        messageEl.hidden = true;
        messageEl.textContent = "";
      }

      answerEl.innerHTML = (data.answer || "")
        .split(/\n{2,}/)
        .map((para) => `<p>${inline(para).replace(/\n/g, "<br>")}</p>`)
        .join("");
      answerEl.hidden = !data.answer;

      const sources = data.sources || [];
      if (sources.length) {
        sourcesEl.hidden = false;
        sourceList.innerHTML = sources
          .map((src) => `<li><a href="${escapeHtml(src.url)}">${escapeHtml(src.title)}</a>
            <span class="tiny muted">${escapeHtml(src.type)}</span></li>`)
          .join("");
      } else {
        sourcesEl.hidden = true;
        sourceList.innerHTML = "";
      }
    };

    const ask = async (question) => {
      if (!question || !question.trim()) { toast("Type a question first.", "bad"); return; }
      questionEl.value = question;
      sendBtn.disabled = true;
      const previous = sendBtn.textContent;
      sendBtn.textContent = "Thinking\u2026";
      try {
        render(await api("/api/tutor/ask", { method: "POST", body: { question } }));
      } catch (err) {
        toast(err.message, "bad");
      } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = previous;
      }
    };

    tutorForm.addEventListener("submit", (event) => {
      event.preventDefault();
      ask(questionEl.value);
    });
    $$("[data-tutor-prompt]").forEach((chip) => {
      chip.addEventListener("click", () => ask(chip.textContent.trim()));
    });
  }

  // ------------------------------------------------------------- share
  // A "copy link" that degrades honestly. navigator.share exists on phones and
  // is offered only there; clipboard access is not available on every desktop
  // browser (or over plain HTTP), so the fallback selects the visible URL and
  // says what happened instead of pretending the copy succeeded.
  const share = $("[data-ev-share]");
  if (share) {
    const native = share.querySelector("[data-ev-share-native]");
    const copy = share.querySelector("[data-ev-share-copy]");
    const status = share.querySelector("[data-ev-share-status]");
    const canonical = $('link[rel="canonical"]');
    const url = (canonical && canonical.href) || location.href;
    const say = (message) => {
      if (!status) return;
      status.textContent = message;
      clearTimeout(status._t);
      status._t = setTimeout(() => { status.textContent = ""; }, 4000);
    };

    if (native && typeof navigator.share === "function") native.hidden = false;
    if (native) {
      native.addEventListener("click", async () => {
        try {
          await navigator.share({ title: document.title, url });
          say("Shared.");
        } catch (err) {
          if (err && err.name !== "AbortError") say("Sharing is not available. Use Copy link.");
        }
      });
    }
    if (copy) {
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(url);
          say("Link copied.");
        } catch (_) {
          say("Could not copy automatically — the address bar has the link.");
        }
      });
    }
  }

  // --------------------------------------------------------- theme toggle
  // The [data-theme="light"] variable set in app.css was unreachable: base.html
  // hard-coded dark, so neither the admin setting nor any user preference could
  // take effect. The server default is applied on the <html> element and an
  // inline script in <head> restores the stored choice before first paint.
  const themeBtn = $("#theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const root = document.documentElement;
      const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("ev-theme", next); } catch (e) { /* private mode */ }
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute("content", next === "light" ? "#f3f5fa" : "#070b14");
    });
  }

  // Merge into the namespace instead of replacing it. i18n.js loads before
  // this file and publishes `window.EV.i18n`; replacing the object dropped
  // that member, so i18n's own DOMContentLoaded init threw
  // "Cannot set properties of undefined (setting 'picker')" on every page and
  // the language picker was never built. Anything another script added to EV
  // (i18n today, the browser terminal on the static copy) must survive.
  window.EV = Object.assign(window.EV || {}, { api, toast, escapeHtml });
})();
