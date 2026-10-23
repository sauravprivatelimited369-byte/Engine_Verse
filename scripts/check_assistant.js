#!/usr/bin/env node
/* Behaviour checks for the shipped study-assistant widget.
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   python scripts/export_pages.py --out site --reading-copy
 *   node scripts/check_assistant.js site
 *
 * The Python suite proves the server side. This runs the *exported* page and
 * the *shipped* backend/static/js/assistant.js under jsdom, with fetch stubbed,
 * and checks the things a student actually experiences:
 *
 *   1. the launcher opens one panel, reports aria-expanded, focuses the input
 *      and closes on Escape;
 *   2. sending posts the n8n chat contract and renders the reply as text -
 *      formatting bold and code, never executing embedded HTML;
 *   3. a 500 shows a message and a working Retry, a 429 says the assistant is
 *      busy, and an offline browser refuses before calling fetch;
 *   4. the reload guard stops a second script evaluation from adding a second
 *      panel or a second submit handler.
 *
 * The page's configuration block is rewritten to "direct" mode against a fake
 * endpoint: the exported copy is normally unconfigured unless the operator set
 * ENGINEVERSE_ASSISTANT_PUBLIC_URL, and this check must not need their n8n.
 */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const jsdomDir = process.env.JSDOM_DIR || path.join(__dirname, "..", ".toolchain", "jsdom");
let jsdom;
try {
  jsdom = require(path.join(path.resolve(jsdomDir), "node_modules", "jsdom"));
} catch (_) {
  jsdom = require("jsdom");
}
const { JSDOM, VirtualConsole } = jsdom;

const SITE = path.resolve(process.argv[2] || "site");
const ENDPOINT = "https://n8n.test/webhook/engineverse/chat";
const ORIGIN = "https://example.github.io";

const assistantJs = fs.readFileSync(path.join(SITE, "static", "js", "assistant.js"), "utf8");

const failures = [];
let passes = 0;
function check(label, condition, detail) {
  if (condition) passes += 1;
  else failures.push(detail ? `${label}: ${detail}` : label);
}

function configFor(mode) {
  return {
    mode,
    endpoint: mode === "direct" ? ENDPOINT : "",
    statusEndpoint: "",
    timeoutMs: 2500,
    maxChars: 800,
    prompts: ["Explain pointers", "Plan my revision"],
    welcome: "I am the study assistant.",
    disclosure: "AI-generated answer.",
    identity: "EngineVerse study assistant",
  };
}

function boot({ mode = "direct" } = {}) {
  const file = path.join(SITE, "assistant", "index.html");
  let html = fs.readFileSync(file, "utf8");
  html = html.replace(
    /<script\b(?![^>]*type="application\/json")[\s\S]*?<\/script>/g,
    "",
  );
  html = html.replace(
    /<script type="application\/json" id="ev-assistant-config">[\s\S]*?<\/script>/,
    `<script type="application/json" id="ev-assistant-config">${JSON.stringify(configFor(mode))}</script>`,
  );
  const virtualConsole = new VirtualConsole();
  const errors = [];
  virtualConsole.on("jsdomError", (e) => errors.push(String((e && e.message) || e)));
  const dom = new JSDOM(html, {
    url: `${ORIGIN}/EngineVerse/assistant/`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const w = dom.window;
  const calls = [];
  let responder = () => ({ ok: true, status: 200, body: { output: "**Bold** and `code`." } });
  w.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    const result = responder(String(url), options);
    if (result.reject) throw new TypeError("Failed to fetch");
    return {
      ok: result.ok !== false,
      status: result.status || 200,
      text: async () => (typeof result.body === "string" ? result.body : JSON.stringify(result.body)),
      json: async () => result.body,
    };
  };
  w.eval(assistantJs);
  return { dom, w, calls, errors, setResponder: (fn) => { responder = fn; } };
}

const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

function typeAndSend(w, text) {
  // The page mount and the launcher mount both exist on /assistant; these
  // checks drive the launcher, so the selector is scoped to its panel.
  const input = w.document.querySelector("#ev-assistant-panel textarea");
  const form = input.closest("form");
  input.value = text;
  form.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
  return { input, form };
}

async function main() {
  if (!fs.existsSync(path.join(SITE, "assistant", "index.html"))) {
    console.error(`No exported page at ${SITE}/assistant/index.html — run scripts/export_pages.py first.`);
    return 1;
  }

  // ---------------------------------------------------------------- launcher
  {
    const { w, dom } = boot();
    const root = w.document.getElementById("ev-assistant-root");
    const button = w.document.getElementById("ev-assistant-launcher");
    const panel = w.document.getElementById("ev-assistant-panel");
    check("launcher is shown when configured", root && !root.hidden);
    check("panel starts closed", panel && panel.hidden);
    check("launcher reports collapsed state", button.getAttribute("aria-expanded") === "false");
    button.click();
    check("launcher opens the panel", panel.hidden === false);
    check("launcher reports expanded state", button.getAttribute("aria-expanded") === "true");
    await tick(30); // focus is applied on the next animation frame
    check("focus moves to the question box",
      w.document.activeElement === w.document.querySelector("#ev-assistant-panel textarea"));
    button.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    dom.window.close();
  }

  // ------------------------------------------------------------ a real reply
  {
    const { w, calls, dom } = boot();
    const launcher = w.document.getElementById("ev-assistant-launcher");
    launcher.click();
    const { input } = typeAndSend(w, "What is a pointer?");
    await tick(10);
    check("one request was sent", calls.length === 1, `${calls.length} calls`);
    const body = calls.length ? JSON.parse(calls[0].options.body) : {};
    check("request uses the n8n chat contract",
      body.action === "sendMessage" && typeof body.sessionId === "string" && body.chatInput === "What is a pointer?",
      JSON.stringify(body));
    check("request goes to the configured endpoint", calls.length && calls[0].url === ENDPOINT);

    const log = w.document.querySelector("#ev-assistant-panel [role=log]");
    const bubbles = Array.from(log.querySelectorAll(".ev-asst-assistant .ev-asst-bubble"));
    const last = bubbles[bubbles.length - 1];
    check("the answer is rendered", last && /Bold and/.test(last.textContent), last && last.textContent);
    check("markdown bold becomes <strong>", last && last.querySelector("strong") !== null);
    check("inline code becomes <code>", last && last.querySelector("code") !== null);
    check("input is cleared after sending", input.value === "");
    check("send button is usable again", w.document.querySelector("#ev-assistant-panel button[type=submit]").disabled === false);
    dom.window.close();
  }

  // ------------------------------------------------------------------- XSS
  {
    const { w, setResponder, dom } = boot();
    setResponder(() => ({ ok: true, status: 200, body: { output: '<img src=x onerror="window.__pwned = 1">ok' } }));
    w.document.getElementById("ev-assistant-launcher").click();
    typeAndSend(w, "hello there");
    await tick(10);
    const log = w.document.querySelector("#ev-assistant-panel [role=log]");
    check("assistant HTML is not executed", w.__pwned === undefined);
    check("assistant HTML is not inserted", log.querySelector("img") === null);
    check("the text is still shown", /<img src=x/.test(log.textContent));
    dom.window.close();
  }

  // ------------------------------------------------------- error and retry
  {
    const { w, calls, setResponder, dom } = boot();
    setResponder(() => ({ ok: false, status: 500, body: { ok: false, error: "upstream exploded" } }));
    w.document.getElementById("ev-assistant-launcher").click();
    typeAndSend(w, "Explain recursion");
    await tick(10);
    const error = w.document.querySelector("#ev-assistant-panel .ev-asst-error");
    check("a failure is announced", error && !error.hidden);
    check("the failure does not leak the upstream body",
      error && !/upstream exploded/.test(error.textContent), error && error.textContent);
    const retry = w.document.querySelector("#ev-assistant-panel .ev-asst-body > button");
    check("a retry control is offered", retry && !retry.hidden);

    setResponder(() => ({ ok: true, status: 200, body: { output: "Recursion calls itself." } }));
    if (retry) retry.click();
    await tick(10);
    check("retry sends the same question again", calls.length === 2, `${calls.length} calls`);
    check("the error clears after success", w.document.querySelector("#ev-assistant-panel .ev-asst-error").hidden);
    dom.window.close();
  }

  // ------------------------------------------------------------- 429 state
  {
    const { w, setResponder, dom } = boot();
    setResponder(() => ({ ok: false, status: 429, body: { ok: false, error: "too many" } }));
    w.document.getElementById("ev-assistant-launcher").click();
    typeAndSend(w, "hello again");
    await tick(10);
    const error = w.document.querySelector("#ev-assistant-panel .ev-asst-error");
    check("a rate limit is explained", error && /lot of questions/i.test(error.textContent), error && error.textContent);
    dom.window.close();
  }

  // --------------------------------------------------------------- offline
  {
    const { w, calls, dom } = boot();
    Object.defineProperty(w.navigator, "onLine", { value: false, configurable: true });
    w.document.getElementById("ev-assistant-launcher").click();
    typeAndSend(w, "Are you there?");
    await tick(10);
    check("offline refuses before calling fetch", calls.length === 0);
    const error = w.document.querySelector("#ev-assistant-panel .ev-asst-error");
    check("offline is explained", error && /offline/i.test(error.textContent), error && error.textContent);
    dom.window.close();
  }

  // ------------------------------------------------------- duplicate mount
  {
    const { w, dom } = boot();
    w.eval(assistantJs); // a second copy of the file, as a double-include would
    const panels = w.document.querySelectorAll("#ev-assistant-panel");
    const sends = w.document.querySelectorAll("#ev-assistant-panel button[type=submit]");
    check("a second script evaluation adds no panel", panels.length === 1, `${panels.length} panels`);
    check("a second script evaluation adds no second send button", sends.length === 1, `${sends.length} buttons`);
    dom.window.close();
  }

  // ---------------------------------------------------- unconfigured is honest
  {
    const { w, dom } = boot({ mode: "off" });
    const root = w.document.getElementById("ev-assistant-root");
    const note = w.document.querySelector("[data-ev-asst-fallback]");
    check("no launcher bubble is left when unconfigured", root === null, "launcher still present");
    check("the page says it is not connected", note && /not connected/i.test(note.textContent));
    dom.window.close();
  }

  if (failures.length) {
    console.error(`assistant checks: ${failures.length} failed, ${passes} passed`);
    for (const failure of failures) console.error(`  - ${failure}`);
    return 1;
  }
  console.log(`assistant checks: all ${passes} passed`);
  return 0;
}

main().then((code) => process.exit(code)).catch((error) => {
  console.error(error);
  process.exit(1);
});
