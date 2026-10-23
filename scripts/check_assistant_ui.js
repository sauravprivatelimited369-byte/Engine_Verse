#!/usr/bin/env node
/* Behavioural check for the assistant UI, run under jsdom.
 *
 * The page is rendered by scripts/render_assistant_page.py from the real
 * template, and backend/static/js/assistant.js is evaluated against it. A
 * stubbed fetch lets the check drive the states a student will actually hit:
 * a successful answer, an upstream failure with retry, a spent rate limit, and
 * a double submit. The last check is the important one: n8n's reply must be
 * inserted as text, never parsed as HTML.
 *
 * Usage: node scripts/check_assistant_ui.js /tmp/assistant-page.html
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SITE = path.resolve(__dirname, "..");
const JS = path.join(SITE, "backend", "static", "js", "assistant.js");
const htmlPath = process.argv[2];
if (!htmlPath) {
  console.error("usage: node scripts/check_assistant_ui.js <rendered-assistant-page.html>");
  process.exit(2);
}

let jsdom;
try {
  jsdom = require(path.join(SITE, ".toolchain", "jsdom", "node_modules", "jsdom"));
} catch (_) {
  console.error("jsdom is not installed. Run: npm install --prefix .toolchain/jsdom jsdom@26");
  process.exit(2);
}

const html = fs.readFileSync(htmlPath, "utf8");
const source = fs.readFileSync(JS, "utf8");

const failures = [];
let passes = 0;
function check(label, condition, detail) {
  if (condition) { passes += 1; return; }
  failures.push(`${label}${detail ? ` — ${detail}` : ""}`);
}
const tick = () => new Promise((resolve) => setTimeout(resolve, 8));
async function settle(rounds = 8) {
  for (let i = 0; i < rounds; i += 1) await tick();
}

function loadPage(fetchImpl) {
  const dom = new jsdom.JSDOM(html, {
    url: "https://engineverse.test/assistant",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  window.EngineVerse = { csrf: "test-csrf", user: false, staticCopy: false };
  window.fetch = fetchImpl(window);
  window.eval(source);
  return { dom, window, document: window.document };
}

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
  text: async () => JSON.stringify(body),
});

function composer(document) {
  return document.querySelector("[data-ev-assistant-form]");
}
function input(document) {
  return document.querySelector("[data-ev-assistant-input]");
}
function submit(window, document, value) {
  const field = input(document);
  field.value = value;
  composer(document).dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
}

(async () => {
  // ---------------------------------------------------------------- success
  {
    let chatCalls = 0;
    const { window, document } = loadPage(() => async (url) => {
      if (String(url).includes("/status")) return jsonResponse(200, { ok: true, configured: true });
      chatCalls += 1;
      return jsonResponse(200, {
        ok: true,
        reply: "A stack is LIFO; a queue is FIFO.",
        sessionId: "abc123def456",
        latencyMs: 120,
      });
    });
    await settle();
    check("page: the script initialises one surface", window.EVAssistant && window.EVAssistant.surfaces === 1,
      String(window.EVAssistant && window.EVAssistant.surfaces));

    submit(window, document, "What is the difference between a stack and a queue?");
    await settle();
    const text = document.querySelector("[data-ev-assistant-log]").textContent;
    check("success: the question appears", text.includes("What is the difference"));
    check("success: the reply appears", text.includes("A stack is LIFO"));
    check("success: one request was sent", chatCalls === 1, String(chatCalls));
    check("success: the state says it was answered",
      /Answered by an AI workflow/.test(document.querySelector("[data-ev-assistant-state]").textContent));
    check("success: feedback controls appear", Boolean(document.querySelector(".assistant-feedback")));
    check("success: the session id is stored", window.sessionStorage.getItem("ev:assistant:session:v1") === "abc123def456");
    check("success: the composer is enabled again", input(document).disabled === false);
    check("success: the input is cleared", input(document).value === "");
  }

  // ------------------------------------------------------------------ error
  {
    let attempts = 0;
    const { window, document } = loadPage(() => async (url) => {
      if (String(url).includes("/status")) return jsonResponse(200, { ok: true, configured: true });
      attempts += 1;
      if (attempts === 1) return jsonResponse(502, { ok: false, code: "assistant_unavailable", error: "The assistant returned an error." });
      return jsonResponse(200, { ok: true, reply: "Second time lucky.", sessionId: "abc123def456" });
    });
    await settle();
    submit(window, document, "Explain pointers");
    await settle();
    const recover = document.querySelector("[data-ev-assistant-recover]");
    check("error: the error region is shown", recover && recover.hidden === false);
    check("error: the message is the server's, not a stack trace",
      /not responding/.test(document.querySelector("[data-ev-assistant-error]").textContent));
    check("error: the failed question stays in the transcript",
      document.querySelector("[data-ev-assistant-log]").textContent.includes("Explain pointers"));

    document.querySelector("[data-ev-assistant-retry]").click();
    await settle();
    check("retry: a second request was sent", attempts === 2, String(attempts));
    check("retry: the answer replaces the error",
      document.querySelector("[data-ev-assistant-log]").textContent.includes("Second time lucky"));
    check("retry: the error region is hidden again", recover.hidden === true);
    const userMessages = Array.from(document.querySelectorAll("[data-ev-assistant-log] .assistant-msg-user .assistant-text"))
      .map((node) => node.textContent.trim());
    check("retry: the question was not duplicated",
      userMessages.length === 1 && userMessages[0] === "Explain pointers", JSON.stringify(userMessages));
  }

  // ------------------------------------------------------------- rate limit
  {
    const { window, document } = loadPage(() => async (url) => {
      if (String(url).includes("/status")) return jsonResponse(200, { ok: true, configured: true });
      return jsonResponse(429, { ok: false, code: "assistant_rate_limited", error: "Too many requests.", retryAfter: 120 });
    });
    await settle();
    submit(window, document, "One more question");
    await settle();
    const message = document.querySelector("[data-ev-assistant-error]").textContent;
    check("rate limit: the wait is explained", /2 minute/.test(message), message);
    check("rate limit: the state is shown honestly",
      /Rate limited/.test(document.querySelector("[data-ev-assistant-state]").textContent));
  }

  // ---------------------------------------------------------- double submit
  {
    let chatCalls = 0;
    const { window, document } = loadPage(() => async (url) => {
      if (String(url).includes("/status")) return jsonResponse(200, { ok: true, configured: true });
      chatCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 30));
      return jsonResponse(200, { ok: true, reply: "Only once.", sessionId: "abc123def456" });
    });
    await settle();
    submit(window, document, "Explain recursion");
    submit(window, document, "Explain recursion");
    await settle(12);
    check("duplicate: a double submit sends one request", chatCalls === 1, String(chatCalls));
  }

  // -------------------------------------------------------------- injection
  {
    const { window, document } = loadPage(() => async (url) => {
      if (String(url).includes("/status")) return jsonResponse(200, { ok: true, configured: true });
      return jsonResponse(200, {
        ok: true,
        reply: '<img src=x onerror="window.__pwned = true"> <b>not bold</b>',
        sessionId: "abc123def456",
      });
    });
    await settle();
    submit(window, document, "Render this");
    await settle();
    check("injection: no element was created from the reply",
      document.querySelectorAll("[data-ev-assistant-log] img, [data-ev-assistant-log] b").length === 0);
    check("injection: the markup is shown as text",
      document.querySelector("[data-ev-assistant-log]").textContent.includes("<img src=x"));
    check("injection: no script ran", window.__pwned === undefined);
  }

  // ------------------------------------------------------------ small input
  {
    let chatCalls = 0;
    const { window, document } = loadPage(() => async (url) => {
      if (String(url).includes("/status")) return jsonResponse(200, { ok: true, configured: true });
      chatCalls += 1;
      return jsonResponse(200, { ok: true, reply: "ok", sessionId: "abc123def456" });
    });
    await settle();
    submit(window, document, "a");
    await settle();
    check("validation: a one-character question is refused locally",
      /Type a question first/.test(document.querySelector("[data-ev-assistant-error]").textContent));
    check("validation: nothing was sent", chatCalls === 0, String(chatCalls));
  }

  if (failures.length) {
    console.error(`assistant UI checks: ${failures.length} failed, ${passes} passed`);
    for (const failure of failures) console.error(`  FAIL ${failure}`);
    process.exit(1);
  }
  console.log(`assistant UI checks: all ${passes} passed`);
  process.exit(0);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
