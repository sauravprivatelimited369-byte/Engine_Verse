/* Study assistant — the browser side of the n8n Chat Trigger.
 *
 * Two mounts share one implementation:
 *   - the floating launcher included by base.html on every page;
 *   - the full-page assistant at /assistant.
 *
 * Two transports, chosen by the server (never by the visitor):
 *   - "proxy": POST /api/assistant/chat on this origin. The n8n webhook stays
 *     server-side, so connect-src 'self' still holds and the URL is not
 *     published. The server derives the conversation id.
 *   - "direct": POST the configured Chat Trigger URL. Used only by the static
 *     GitHub Pages export, which has no server. That endpoint is public by
 *     design; the workflow's Allowed Origins and rate limits are its controls.
 *
 * No dependency, no CDN, no innerHTML for untrusted text: assistant output is
 * escaped before a deliberately small markdown subset is applied.
 */
(() => {
  "use strict";

  if (window.__evAssistantLoaded) return;
  window.__evAssistantLoaded = true;

  const configNode = document.getElementById("ev-assistant-config");
  let config = null;
  try {
    config = JSON.parse(configNode ? configNode.textContent || "{}" : "{}");
  } catch (_) {
    config = null;
  }
  if (!config || typeof config !== "object") return;

  const MODE = config.mode === "proxy" || config.mode === "direct" ? config.mode : "off";
  const MAX = Math.max(40, Math.min(Number(config.maxChars) || 800, 2000));
  const TIMEOUT = Math.max(5000, Math.min(Number(config.timeoutMs) || 25000, 120000)) + 6000;
  const PROMPTS = Array.isArray(config.prompts) ? config.prompts.slice(0, 4).filter((p) => typeof p === "string") : [];
  const WELCOME = typeof config.welcome === "string" && config.welcome ? config.welcome : "Ask me a study question.";
  const DISCLOSURE = typeof config.disclosure === "string" ? config.disclosure : "AI-generated; it can be wrong.";
  const LABEL_OPEN = typeof config.launcherLabel === "string" && config.launcherLabel ? config.launcherLabel : "Open the study assistant";
  const LABEL_CLOSE = typeof config.launcherCloseLabel === "string" && config.launcherCloseLabel ? config.launcherCloseLabel : "Close the study assistant";

  const launcherRoot = document.getElementById("ev-assistant-root");
  const pageRoot = document.getElementById("ev-assistant-page");
  if (!launcherRoot && !pageRoot) return;

  // ---------------------------------------------------------------- helpers
  const escapeHtml = (value) =>
    String(value == null ? "" : value).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const el = (tag, attrs = {}, text = "") => {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value === true) node.setAttribute(key, "");
      else if (value !== false && value != null) node.setAttribute(key, String(value));
    });
    if (text) node.textContent = text;
    return node;
  };

  // A deliberately tiny markdown subset: fenced code, **bold**, `inline code`,
  // "- " bullets and blank-line paragraphs. Everything is escaped first, so a
  // reply that contains <script> is displayed as text. Links are not turned
  // into anchors: an AI-generated URL is not a source we can vouch for.
  function formatReply(text) {
    const parts = String(text || "").split(/```[a-zA-Z0-9#+._-]*\n?/);
    return parts.map((part, index) => {
      if (index % 2 === 1) {
        return `<pre class="ev-asst-code"><code>${escapeHtml(part.replace(/\n$/, ""))}</code></pre>`;
      }
      const lines = escapeHtml(part).split("\n");
      const out = [];
      let list = null;
      let para = [];
      const flushPara = () => {
        if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; }
      };
      const flushList = () => {
        if (list) { out.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`); list = null; }
      };
      lines.forEach((line) => {
        const trimmed = line.trim();
        const bullet = /^[-*]\s+(.*)$/.exec(trimmed);
        if (!trimmed) { flushPara(); flushList(); return; }
        if (bullet) { flushPara(); (list = list || []).push(bullet[1]); return; }
        flushList();
        para.push(trimmed);
      });
      flushPara();
      flushList();
      return out.join("");
    }).join("");
  }

  function inline(escaped) {
    return escaped.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  const sessionKey = "ev:assistant:session";
  function directSessionId() {
    try {
      let id = sessionStorage.getItem(sessionKey);
      if (id && /^[A-Za-z0-9-]{8,64}$/.test(id)) return id;
      id = (window.crypto && typeof window.crypto.randomUUID === "function")
        ? window.crypto.randomUUID()
        : "ev-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      sessionStorage.setItem(sessionKey, id);
      return id;
    } catch (_) {
      // Storage blocked (private mode, embedded webview): a fresh id per page
      // still works; context is simply not carried between pages.
      return "ev-tab-" + Math.random().toString(36).slice(2);
    }
  }

  const csrf = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  };

  const pagePath = () => location.pathname;

  function offline() { return navigator.onLine === false; }

  async function sendProxy(question) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT);
    try {
      const res = await fetch(config.endpoint || "/api/assistant/chat", {
        method: "POST",
        credentials: "same-origin",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf(),
          "X-EngineVerse-Page": pagePath(),
        },
        body: JSON.stringify({ question }),
      });
      let data = {};
      try { data = await res.json(); } catch (_) { data = {}; }
      if (!res.ok || data.ok === false) {
        const error = new Error(typeof data.error === "string" && data.error ? data.error : "The assistant could not answer that.");
        error.retryable = data.retryable !== false;
        error.status = res.status;
        error.unavailable = Boolean(data.unavailable);
        throw error;
      }
      return { answer: String(data.answer || ""), disclosure: data.disclosure || DISCLOSURE };
    } catch (error) {
      if (error.name === "AbortError") {
        const timeout = new Error("The assistant took too long to answer. Please try again.");
        timeout.retryable = true;
        throw timeout;
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async function sendDirect(question) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT);
    try {
      const res = await fetch(config.endpoint, {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ action: "sendMessage", sessionId: directSessionId(), chatInput: question }),
      });
      if (res.status === 429) {
        const limited = new Error("The assistant is handling a lot of questions. Try again in a minute.");
        limited.retryable = true;
        throw limited;
      }
      if (!res.ok) {
        const down = new Error(res.status >= 500
          ? "The assistant is temporarily unavailable. Please try again."
          : "The assistant is not accepting questions right now.");
        down.retryable = res.status >= 500;
        down.unavailable = true;
        throw down;
      }
      const raw = await res.text();
      let data = raw;
      try { data = JSON.parse(raw); } catch (_) { /* a workflow may reply in plain text */ }
      const answer = textOf(data).trim();
      if (!answer) {
        const empty = new Error("The assistant returned an empty answer. Please rephrase your question.");
        empty.retryable = true;
        throw empty;
      }
      return { answer, disclosure: DISCLOSURE };
    } catch (error) {
      if (error.name === "AbortError") {
        const timeout = new Error("The assistant took too long to answer. Please try again.");
        timeout.retryable = true;
        throw timeout;
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function textOf(value) {
    if (!value) return "";
    if (typeof value === "string") return value.trim();
    if (Array.isArray(value)) {
      for (const item of value) { const t = textOf(item); if (t) return t; }
      return "";
    }
    if (typeof value === "object") {
      for (const key of ["output", "text", "answer", "message", "response"]) {
        const t = textOf(value[key]);
        if (t) return t;
      }
    }
    return "";
  }

  // ------------------------------------------------------------------ mount
  let mountCount = 0;

  function mount(root, { variant }) {
    if (!root || root.dataset.evAssistantReady === "1") return null;
    const body = root.querySelector("[data-ev-asst-body]") || root;
    const fallback = root.querySelector("[data-ev-asst-fallback]");
    if (fallback) fallback.remove();

    const id = `ev-asst-${variant}-${++mountCount}`;
    body.innerHTML = "";
    body.classList.add("ev-asst-body");

    const log = el("div", { class: "ev-asst-log", role: "log", "aria-live": "polite", "aria-relevant": "additions text", "aria-label": "Conversation with the study assistant" });
    const suggestions = el("div", { class: "ev-asst-suggest" });
    const form = el("form", { class: "ev-asst-form", novalidate: true });
    const label = el("label", { class: "ev-asst-label", for: `${id}-input` }, "Your question");
    const input = el("textarea", {
      id: `${id}-input`, class: "ev-asst-input", rows: 2,
      maxlength: MAX, placeholder: "Ask about a topic, an error, a plan or a project…",
      "aria-describedby": `${id}-help`, required: true,
    });
    const help = el("p", { class: "ev-asst-help", id: `${id}-help` },
      `AI-generated. Up to ${MAX} characters. Do not paste passwords or personal data.`);
    const actions = el("div", { class: "ev-asst-actions" });
    const note = el("span", { class: "ev-asst-meta" }, "AI · may be wrong");
    const send = el("button", { class: "btn btn-primary btn-sm ev-asst-send", type: "submit" }, "Send");
    actions.append(note, send);
    form.append(label, input, help, actions);

    const error = el("p", { class: "ev-asst-error", role: "alert", hidden: true });
    const retry = el("button", { class: "btn btn-ghost btn-sm", type: "button", hidden: true }, "Try again");

    body.append(log, suggestions, form, error, retry);

    function addMessage(role, text) {
      const wrap = el("div", { class: `ev-asst-msg ev-asst-${role}` });
      const who = el("span", { class: "ev-asst-who" }, role === "user" ? "You" : "Assistant");
      const bubble = el("div", { class: "ev-asst-bubble" });
      if (role === "assistant") bubble.innerHTML = formatReply(text);
      else bubble.textContent = text;
      wrap.append(who, bubble);
      log.append(wrap);
      if (log.children.length > 60) log.firstElementChild.remove();
      log.scrollTop = log.scrollHeight;
      return wrap;
    }

    addMessage("assistant", WELCOME);

    const chips = [];
    PROMPTS.forEach((prompt) => {
      const chip = el("button", { type: "button", class: "chip ev-asst-chip" }, prompt);
      chip.addEventListener("click", () => ask(prompt));
      chips.push(chip);
      suggestions.append(chip);
    });
    if (!PROMPTS.length) suggestions.hidden = true;

    let pending = false;
    let lastQuestion = "";

    function setPending(state) {
      pending = state;
      send.disabled = state;
      send.setAttribute("aria-busy", state ? "true" : "false");
      send.textContent = state ? "Sending…" : "Send";
      input.readOnly = state;
      chips.forEach((chip) => { chip.disabled = state; });
      if (state) {
        error.hidden = true;
        retry.hidden = true;
        const thinking = addMessage("assistant", "Thinking…");
        thinking.dataset.evPending = "1";
        thinking.setAttribute("aria-hidden", "true");
      } else {
        const spinner = log.querySelector('[data-ev-pending="1"]');
        if (spinner) spinner.remove();
      }
    }

    function fail(message, canRetry) {
      error.hidden = false;
      error.textContent = message;
      retry.hidden = !canRetry;
    }

    async function ask(question) {
      const text = String(question || "").trim();
      if (pending) return;
      if (!text) { input.focus(); return; }
      if (text.length > MAX) { fail(`Keep your question under ${MAX} characters.`, false); return; }
      if (offline()) {
        addMessage("user", text);
        fail("You appear to be offline. Reconnect, then try again.", true);
        lastQuestion = text;
        return;
      }
      lastQuestion = text;
      input.value = "";
      addMessage("user", text);
      setPending(true);
      try {
        const result = MODE === "proxy" ? await sendProxy(text) : await sendDirect(text);
        addMessage("assistant", result.answer);
        error.hidden = true;
        retry.hidden = true;
      } catch (err) {
        fail(err && err.message ? err.message : "The assistant could not answer that. Please try again.",
          !(err && err.retryable === false));
      } finally {
        setPending(false);
        if (variant === "launcher" && !root.hidden) input.focus();
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      ask(input.value);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        ask(input.value);
      }
    });

    retry.addEventListener("click", () => { if (lastQuestion) ask(lastQuestion); });

    function announceChoice() { input.focus(); }

    root.dataset.evAssistantReady = "1";
    return { root, input, ask, announceChoice };
  }

  // --------------------------------------------------------------- launcher
  let launcher = null;
  if (launcherRoot && MODE !== "off") {
    const button = launcherRoot.querySelector("#ev-assistant-launcher");
    const panel = launcherRoot.querySelector("#ev-assistant-panel");
    const close = launcherRoot.querySelector("#ev-assistant-close");
    launcher = mount(launcherRoot.querySelector("[data-ev-asst-body]") || launcherRoot, { variant: "launcher" });
    launcherRoot.hidden = false;

    let open = false;
    const setOpen = (next) => {
      open = next;
      panel.hidden = !next;
      launcherRoot.classList.toggle("is-open", next);
      button.setAttribute("aria-expanded", next ? "true" : "false");
      button.setAttribute("aria-label", next ? LABEL_CLOSE : LABEL_OPEN);
      if (next && launcher) requestAnimationFrame(() => launcher.input.focus());
      else button.focus();
    };

    button.addEventListener("click", () => setOpen(!open));
    if (close) close.addEventListener("click", () => setOpen(false));
    launcherRoot.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && open) { event.stopPropagation(); setOpen(false); }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && open) setOpen(false);
    });
  } else if (launcherRoot) {
    // Not configured or switched off: no dead bubble on the page.
    launcherRoot.remove();
  }

  // ------------------------------------------------------------- full page
  if (pageRoot) {
    if (MODE === "off") {
      // The template rendered an honest "not connected" panel; leave it alone.
      const status = document.querySelector("[data-ev-asst-status]");
      if (status) { status.textContent = "Not connected"; status.classList.add("warn"); }
    } else {
      const full = mount(pageRoot, { variant: "page" });
      const status = document.querySelector("[data-ev-asst-status]");
      if (status) {
        status.textContent = MODE === "proxy" ? "Ready" : "Ready (direct)";
        status.classList.add("ok");
      }
      if (full) {
        pageRoot.dataset.evAssistantMode = "ready";
      }
    }
  }

  // Tell the user when the connection drops mid-conversation, rather than
  // letting the next send fail with a generic message.
  window.addEventListener("offline", () => {
    const status = document.querySelector("[data-ev-asst-status]");
    if (status) { status.textContent = "Offline"; status.classList.remove("ok"); status.classList.add("warn"); }
  });
  window.addEventListener("online", () => {
    const status = document.querySelector("[data-ev-asst-status]");
    if (status && MODE !== "off") { status.textContent = "Ready"; status.classList.add("ok"); status.classList.remove("warn"); }
  });
})();
