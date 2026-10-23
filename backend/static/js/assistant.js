/* EngineVerse student copilot — the floating panel and the full /assistant page.
 *
 * Talks only to this origin. The n8n webhook URL and its credential live in the
 * server's environment (see backend/engineverse/assistant.py); nothing here
 * knows them, which is what keeps the page's connect-src 'self' CSP intact.
 *
 * Rules this file keeps:
 *   - the reply is rendered with textContent, never innerHTML. n8n is an
 *     external system and its output is untrusted text, not markup.
 *   - one initialisation per element, and one in-flight request per surface:
 *     re-opening the panel or pressing Enter twice must not send twice.
 *   - a failure is shown as a failure, with a retry, and never as an answer.
 *   - the transcript lives in sessionStorage (this tab only) and is cleared
 *     when the tab closes or the student starts a new conversation.
 */
(() => {
  "use strict";

  if (window.EVAssistant) return;  // a second copy of this script must not rewire anything

  const roots = Array.from(document.querySelectorAll("[data-ev-assistant]"));
  if (!roots.length) {
    window.EVAssistant = { version: "1.0.0", surfaces: 0 };
    return;
  }

  const CFG = window.EngineVerse || { csrf: "" };
  const STORE_SESSION = "ev:assistant:session:v1";
  const STORE_LOG = "ev:assistant:log:v1";
  const MAX_STORED_MESSAGES = 24;
  const CLIENT_TIMEOUT_MS = 60000;
  const MAX_INPUT = 1200;

  const store = {
    get(key) {
      try { return window.sessionStorage.getItem(key); } catch (_) { return null; }
    },
    set(key, value) {
      try { window.sessionStorage.setItem(key, value); } catch (_) { /* private mode */ }
    },
    remove(key) {
      try { window.sessionStorage.removeItem(key); } catch (_) { /* private mode */ }
    },
  };

  function newSessionId() {
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(bytes);
    } else {
      for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function sessionId() {
    let id = store.get(STORE_SESSION) || "";
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
      id = newSessionId();
      store.set(STORE_SESSION, id);
    }
    return id;
  }

  function readLog() {
    try {
      const parsed = JSON.parse(store.get(STORE_LOG) || "[]");
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter((item) => item && (item.role === "user" || item.role === "assistant") &&
          typeof item.text === "string" && item.text.trim())
        .slice(-MAX_STORED_MESSAGES)
        .map((item) => ({ role: item.role, text: item.text.slice(0, 12000) }));
    } catch (_) {
      return [];
    }
  }

  function writeLog(items) {
    store.set(STORE_LOG, JSON.stringify(items.slice(-MAX_STORED_MESSAGES)));
  }

  function make(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function surface(root) {
    const q = (sel) => root.querySelector(sel);
    const configured = root.dataset.configured === "true";
    const form = q("[data-ev-assistant-form]");
    const input = q("[data-ev-assistant-input]");
    const send = q("[data-ev-assistant-send]");
    const sendLabel = send ? send.querySelector("[data-ev-assistant-send-label]") : null;
    const log = q("[data-ev-assistant-log]");
    const empty = q("[data-ev-assistant-empty]");
    const suggest = q("[data-ev-assistant-suggest]");
    const counter = q("[data-ev-assistant-counter]");
    const recover = q("[data-ev-assistant-recover]");
    const errorEl = q("[data-ev-assistant-error]");
    const retryBtn = q("[data-ev-assistant-retry]");
    const stateEl = q("[data-ev-assistant-state]");
    const clearBtn = q("[data-ev-assistant-clear]");
    const page = root.dataset.page || window.location.pathname;
    const messages = [];
    let busy = false;
    let lastFailed = "";

    if (!log) return null;

    function setState(text, kind) {
      if (!stateEl) return;
      stateEl.textContent = text;
      stateEl.dataset.tone = kind || "";
    }

    function updateEmpty() {
      if (!empty) return;
      empty.hidden = messages.length > 0;
    }

    function persist() {
      writeLog(messages);
      if (clearBtn) clearBtn.hidden = messages.length === 0;
    }

    function scrollToEnd() {
      log.scrollTop = log.scrollHeight;
    }

    function bubble(role, text) {
      const wrap = make("div", `assistant-msg assistant-msg-${role}`);
      const who = make("span", "assistant-who", role === "user" ? "You" : "Assistant");
      const body = make("div", "assistant-text", text);
      wrap.append(who, body);
      return wrap;
    }

    function append(role, text, { remember = true } = {}) {
      if (role === "user" && suggest) suggest.hidden = true;
      log.appendChild(bubble(role, text));
      if (remember) messages.push({ role, text });
      updateEmpty();
      persist();
      scrollToEnd();
    }

    function pending() {
      const wrap = make("div", "assistant-msg assistant-msg-assistant assistant-pending");
      wrap.append(make("span", "assistant-who", "Assistant"));
      const body = make("div", "assistant-text");
      body.append(make("span", "assistant-dots", "Thinking"));
      wrap.append(body);
      log.appendChild(wrap);
      updateEmpty();
      scrollToEnd();
      return wrap;
    }

    function showError(message, { retry = true } = {}) {
      if (!recover || !errorEl) {
        setState(message, "bad");
        return;
      }
      errorEl.textContent = message;
      recover.hidden = false;
      if (retryBtn) retryBtn.hidden = !retry;
      const first = retry ? retryBtn : errorEl;
      if (first) first.focus({ preventScroll: true });
    }

    function clearError() {
      if (!recover) return;
      recover.hidden = true;
      if (errorEl) errorEl.textContent = "";
      if (retryBtn) retryBtn.hidden = false;
    }

    function setBusy(value) {
      busy = value;
      if (send) {
        send.disabled = value;
        if (sendLabel) sendLabel.textContent = value ? "Sending…" : "Send";
      }
      if (input) input.disabled = value;
      root.setAttribute("aria-busy", value ? "true" : "false");
    }

    function feedbackRow(text) {
      const row = make("div", "assistant-feedback");
      row.append(make("span", "tiny muted", "Was this useful?"));
      const yes = make("button", "chip", "Yes");
      const no = make("button", "chip", "No");
      [yes, no].forEach((b) => { b.type = "button"; });
      const reasons = make("div", "assistant-feedback-reasons");
      reasons.hidden = true;
      const codes = [["wrong", "Wrong"], ["unclear", "Unclear"], ["off_topic", "Off topic"]];
      function vote(helpful, code) {
        row.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        reasons.hidden = true;
        yes.textContent = helpful ? "Thanks" : "Yes";
        no.textContent = helpful ? "No" : "Thanks";
        postFeedback(helpful, code);
      }
      yes.addEventListener("click", () => vote(true, ""));
      no.addEventListener("click", () => {
        reasons.hidden = false;
        yes.disabled = true;
        no.disabled = true;
        reasons.querySelectorAll("button").forEach((b) => { b.disabled = false; });
        const first = reasons.querySelector("button");
        if (first) first.focus({ preventScroll: true });
      });
      codes.forEach(([code, label]) => {
        const b = make("button", "chip", label);
        b.type = "button";
        b.addEventListener("click", () => vote(false, code));
        reasons.append(b);
      });
      row.append(yes, no, reasons);
      return row;
    }

    async function postFeedback(helpful, code) {
      const endpoint = root.dataset.feedbackEndpoint || "/api/assistant/feedback";
      // Aggregate only: no answer text, no account, no session id.
      const body = { helpful, code };
      try {
        await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": CFG.csrf || "" },
          body: JSON.stringify(body),
        });
      } catch (_) {
        /* Feedback is optional; a failed vote must not disturb the answer. */
      }
      // The answer itself is never part of the request.
    }

    function mapFailure(status, data) {
      const code = (data && data.code) || "";
      if (status === 0 || code === "assistant_timeout") {
        return "The assistant took too long to answer. This is usually temporary.";
      }
      if (status === 429) {
        const wait = data && data.retryAfter ? ` Try again in about ${Math.ceil(data.retryAfter / 60)} minute(s).` : " Please wait a little.";
        return `You have asked a lot of questions in a short time.${wait}`;
      }
      if (code === "assistant_not_configured") {
        return "No AI workflow is connected to this instance right now.";
      }
      if (code === "assistant_invalid_request" && data && data.error) return data.error;
      if (status >= 500) {
        return "The assistant service is not responding. Your question was not lost — you can retry.";
      }
      return (data && data.error) || "The assistant could not answer that. Try rephrasing it.";
    }

    async function deliver(text, { appendUser = true } = {}) {
      if (busy) return;  // one request per surface, however the form is triggered
      const question = (text || "").trim();
      if (question.length < 2) {
        showError("Type a question first.", { retry: false });
        return;
      }
      clearError();
      setBusy(true);
      lastFailed = question;
      if (appendUser) append("user", question);
      const placeholder = pending();
      setState("Waiting for the workflow…", "");

      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS);
      const endpoint = root.dataset.endpoint || "/api/assistant/chat";
      let status = 0;
      let data = {};
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": CFG.csrf || "" },
          body: JSON.stringify({ message: question, sessionId: sessionId(), page }),
          signal: controller.signal,
        });
        status = response.status;
        try { data = await response.json(); } catch (_) { data = {}; }
        placeholder.remove();
        if (!response.ok || data.ok === false) {
          setState(status === 429 ? "Rate limited" : "Service error", "bad");
          showError(mapFailure(status, data));
          if (data.code === "assistant_not_configured") setState("Not connected", "bad");
          return;
        }
        if (data.sessionId && /^[A-Za-z0-9_-]{8,64}$/.test(data.sessionId)) {
          store.set(STORE_SESSION, data.sessionId);
        }
        const answer = String(data.reply || "").trim();
        if (!answer) {
          setState("Empty answer", "bad");
          showError("The assistant returned an empty answer. Try rephrasing the question.");
          return;
        }
        append("assistant", answer);
        const row = feedbackRow(answer);
        log.appendChild(row);
        scrollToEnd();
        setState("Answered by an AI workflow", "ok");
      } catch (err) {
        placeholder.remove();
        const aborted = err && err.name === "AbortError";
        setState(aborted ? "Timed out" : "Unavailable", "bad");
        showError(aborted
          ? "The assistant did not answer within a minute. Check your connection and retry."
          : "The assistant could not be reached. Check your connection and retry.");
      } finally {
        window.clearTimeout(timer);
        setBusy(false);
        if (input) {
          input.value = "";
          updateCounter();
          input.focus({ preventScroll: true });
        }
      }
    }

    function updateCounter() {
      if (!counter || !input) return;
      const max = Number(input.getAttribute("maxlength")) || MAX_INPUT;
      counter.textContent = `${input.value.length} / ${max}`;
    }

    async function checkStatus() {
      if (!configured) {
        setState("Not connected", "bad");
        return;
      }
      setState("Configured — not yet tested", "");
      const endpoint = root.dataset.statusEndpoint || "/api/assistant/status";
      try {
        const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok && data.configured) {
          // Deliberately not "connected": only a real answer earns that word.
          setState("Workflow configured — send a question to test it", "");
        } else {
          setState("Not connected", "bad");
          if (form) form.hidden = true;
        }
      } catch (_) {
        // The page itself loaded, so the app is up; the status call may still
        // be blocked. Do not disable the composer on a transient read failure.
        setState("Status unavailable", "");
      }
    }

    // ---------------------------------------------------------------- wire up
    if (form && input) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        deliver(input.value);
      });
      input.addEventListener("input", updateCounter);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (!busy) deliver(input.value);
        }
      });
      updateCounter();
    }

    root.querySelectorAll("[data-ev-assistant-prompt]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const prompt = chip.getAttribute("data-ev-assistant-prompt") || "";
        if (input) input.value = prompt;
        updateCounter();
        deliver(prompt);
      });
    });

    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        if (!lastFailed) return;
        clearError();
        deliver(lastFailed, { appendUser: false });
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        messages.length = 0;
        writeLog([]);
        // A new conversation must not inherit the previous one's memory in the
        // workflow either, so the session id is rotated, not reused.
        store.set(STORE_SESSION, newSessionId());
        Array.from(log.querySelectorAll(".assistant-msg, .assistant-feedback")).forEach((n) => n.remove());
        if (suggest) suggest.hidden = false;
        if (empty) empty.hidden = false;
        clearError();
        setState(configured ? "New conversation" : "Not connected", "");
        lastFailed = "";
        persist();
        if (input && !busy) input.focus({ preventScroll: true });
      });
    }

    // The panel is a native <dialog>: showModal() gives focus trapping, Escape
    // and an inert background without hand-written key handling.
    const launcher = root.querySelector("[data-ev-assistant-launcher]");
    const dialog = root.querySelector("[data-ev-assistant-dialog]");
    const closeBtn = root.querySelector("[data-ev-assistant-close]");
    if (launcher && dialog) {
      const open = () => {
        if (typeof dialog.showModal === "function" && !dialog.open) {
          dialog.showModal();
        } else {
          dialog.setAttribute("open", "");
        }
        launcher.setAttribute("aria-expanded", "true");
        const focusTarget = input || closeBtn;
        if (focusTarget) window.setTimeout(() => focusTarget.focus(), 0);
        if (configured) checkStatus();
      };
      const close = () => {
        if (typeof dialog.close === "function" && dialog.open) dialog.close();
        else dialog.removeAttribute("open");
        launcher.setAttribute("aria-expanded", "false");
        launcher.focus({ preventScroll: true });
      };
      launcher.addEventListener("click", open);
      if (closeBtn) closeBtn.addEventListener("click", close);
      dialog.addEventListener("close", () => launcher.setAttribute("aria-expanded", "false"));
      dialog.addEventListener("click", (event) => {
        // Clicking the backdrop (the dialog box itself, outside its children).
        if (event.target === dialog) close();
      });
    }

    // Replay this tab's transcript so a reload does not look like amnesia.
    readLog().forEach((item) => append(item.role, item.text, { remember: true }));
    updateEmpty();
    if (messages.length) setState("Restored this tab's conversation", "");
    else checkStatus();

    return {
      root,
      open: () => { if (launcher && dialog) launcher.click(); },
    };
  }

  const surfaces = roots
    .filter((root) => {
      if (root.dataset.evAssistantReady === "true") return false;
      root.dataset.evAssistantReady = "true";
      return true;
    })
    .map(surface)
    .filter(Boolean);

  window.EVAssistant = {
    version: "1.0.0",
    surfaces: surfaces.length,
    open() {
      const first = surfaces.find((s) => s.root.querySelector("[data-ev-assistant-launcher]"));
      if (first) first.open();
    },
  };
})();
