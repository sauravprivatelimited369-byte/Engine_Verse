#!/usr/bin/env node
/* End-to-end check of the exported Adaptive Lab, in a real DOM.
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   python scripts/export_pages.py --out site --reading-copy
 *   node scripts/check_lab_page.js site
 *
 * check_lab.js proves the arithmetic. This proves the page: it boots the
 * exported /lab and / pages with the shipped lab.js under jsdom and drives them
 * the way a judge would - move a slider, lock in a wrong prediction, read the
 * feedback, start a session, get an easier question after a mistake, and
 * "refresh" to confirm the progress is still there.
 */
"use strict";

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
const deployment = JSON.parse(fs.readFileSync(path.join(SITE, "deployment.json"), "utf8"));
const BASE = deployment.base || "/";
const ORIGIN = "https://example.github.io";
const RUNTIME = fs.readFileSync(path.join(SITE, "static", "js", "lab.js"), "utf8");

const failures = [];
let passes = 0;
function check(label, condition, detail) {
  if (condition) { passes += 1; return; }
  failures.push(detail ? `${label}: ${detail}` : label);
}
function eq(label, actual, expected) {
  const ok = String(actual) === String(expected);
  check(label, ok, `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

function pageFile(route) {
  const rel = route.replace(/^\/+|\/+$/g, "");
  return path.join(SITE, rel, "index.html");
}

/** Boot one exported page with lab.js and a real (in-memory) localStorage. */
function boot(route, storage) {
  const html = fs.readFileSync(pageFile(route), "utf8")
    .replace(/<script\b(?![^>]*type="application\/json")[\s\S]*?<\/script>/g, "");
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => errors.push(String((e && e.message) || e)));
  virtualConsole.on("error", (...a) => errors.push(a.join(" ")));
  const dom = new JSDOM(html, {
    url: `${ORIGIN}${BASE}${route.replace(/^\/+/, "")}`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const w = dom.window;
  if (storage) for (const [k, v] of Object.entries(storage)) w.localStorage.setItem(k, v);
  w.eval(RUNTIME);
  return { dom, w, d: w.document, errors };
}

/** Let the deferred lab.js finish booting, the way a browser would. */
function ready(ctx) {
  return new Promise((resolve) => {
    if (ctx.d.readyState !== "loading") { resolve(ctx); return; }
    ctx.d.addEventListener("DOMContentLoaded", () => resolve(ctx));
  });
}

function fire(el, type) {
  el.dispatchEvent(new el.ownerDocument.defaultView.Event(type, { bubbles: true }));
}
function key(el, keyName) {
  el.dispatchEvent(new el.ownerDocument.defaultView.KeyboardEvent("keydown", {
    key: keyName, bubbles: true, cancelable: true,
  }));
}
function readStorage(w) {
  return JSON.parse(w.localStorage.getItem("engineverse.lab.v1"));
}

async function main() {
/* ============================================ 1. the page is present and clean */
{
  const { d, errors } = await ready(boot("/lab"));
  check("lab page: no console errors", errors.length === 0, errors.join(" | "));
  check("lab page: one h1", d.querySelectorAll("h1").length === 1);
  eq("lab page: h1 text", d.querySelector("h1").textContent.trim(), "Learn. Experiment. Practise.");
  check("lab page: the simulator is wired", Boolean(d.querySelector("[data-ev-lab='mini']")));
  check("lab page: three prediction challenges", d.querySelectorAll("[data-challenge]").length === 3);
  check("lab page: challenge mode is present", Boolean(d.querySelector("#ev-adaptive")));
  check("lab page: aria-live region for predictions",
    Boolean(d.querySelector("#ev-predict-live[aria-live='polite']")));
  check("lab page: aria-live region for challenge mode",
    Boolean(d.querySelector("#ev-adaptive-live[aria-live='polite']")));
  check("lab page: the curriculum link is real",
    Boolean(d.querySelector("a[href*='/subjects/basic-electrical']")));
  check("lab page: no placeholder links", !d.querySelector('a[href="#"]'));
  check("lab page: progress says it is device-local",
    /saved on this device/i.test(d.querySelector("[data-adaptive-storage]").textContent),
    d.querySelector("[data-adaptive-storage]").textContent);
  // The circuit is drawn by JS, so an empty figure means the lab never booted.
  check("lab page: the circuit is drawn", d.querySelector("[data-adaptive-figure]") !== null);
  const figure = d.querySelector("[data-lab-figure]");
  check("lab page: the preview circuit is drawn", Boolean(figure && figure.querySelector("svg")),
    figure ? figure.innerHTML.slice(0, 80) : "no figure element");
}

/* ============================================== 2. the simulator is live */
{
  const { d, errors } = await ready(boot("/lab"));
  check("simulator: no console errors", errors.length === 0, errors.join(" | "));
  const volts = d.querySelector("[data-lab-volts]");
  const ohms = d.querySelector("[data-lab-ohms]");
  const current = d.querySelector("[data-lab-i]");
  const power = d.querySelector("[data-lab-p]");

  eq("simulator: starts at 12 V", volts.value, "12");
  eq("simulator: starts at 6 ohm", ohms.value, "6");
  eq("simulator: 12 V / 6 ohm reads 2 A", current.textContent, "2 A");
  eq("simulator: power reads 24 W", power.textContent, "24 W");

  ohms.value = "12";
  fire(ohms, "input");
  eq("simulator: 12 V / 12 ohm reads 1 A", current.textContent, "1 A");
  eq("simulator: power follows to 12 W", power.textContent, "12 W");

  volts.value = "24";
  fire(volts, "input");
  eq("simulator: 24 V / 12 ohm reads 2 A", current.textContent, "2 A");

  ohms.value = "100";
  fire(ohms, "input");
  eq("simulator: 24 V / 100 ohm reads 240 mA", current.textContent, "240 mA");

  // The diagram must agree with the readouts - they are the same object.
  const svg = d.querySelector("[data-lab-figure] svg").textContent;
  check("simulator: the diagram labels 24 V", svg.includes("24 V"), svg.slice(0, 120));
  check("simulator: the diagram labels 100 ohm", svg.includes("100 \u03a9"));
  check("simulator: the diagram labels 240 mA", svg.includes("240 mA"));
  const progress = d.querySelector(".lab-bar");
  check("simulator: the progressbar exposes a value",
    progress.getAttribute("aria-valuetext") === "240 mA", progress.getAttribute("aria-valuetext"));

  // Keyboard access: a range input responds to arrow keys natively, so all the
  // page has to guarantee is that it is focusable and labelled.
  check("simulator: the voltage slider is focusable", volts.tabIndex >= 0);
  check("simulator: the voltage slider has a label",
    Boolean(d.querySelector("label[for='" + volts.id + "']")));
  check("simulator: the resistance slider has a label",
    Boolean(d.querySelector("label[for='" + ohms.id + "']")));
}

/* ================================ 3. the required 48 A mistake, in the DOM */
{
  const { d, errors } = await ready(boot("/lab"));
  check("predict: no console errors", errors.length === 0, errors.join(" | "));
  const card = d.querySelector("[data-challenge='c2']"); // 12 V across 4 ohm
  const input = card.querySelector("input");
  const submit = card.querySelector("[data-challenge-submit]");
  const reveal = card.querySelector("[data-challenge-reveal]");
  const feedback = card.querySelector("[data-challenge-feedback]");
  const live = d.querySelector("#ev-predict-live");

  check("predict: the answer is covered before submission",
    card.querySelector("[data-challenge-figure] svg").textContent.includes("I = ?"));
  check("predict: the reveal starts hidden", reveal.hidden === true);

  // Submitting nothing must not grade anything.
  fire(submit, "click");
  check("predict: an empty prediction is refused", reveal.hidden === true);
  eq("predict: an empty prediction says so in the live region",
    live.textContent, "Enter a number before checking.");

  // The deliberate mistake from the acceptance criteria.
  input.value = "48";
  fire(submit, "click");
  check("predict: the reveal opens", reveal.hidden === false);
  const message = feedback.textContent;
  check("predict: 48 A is named as a multiplication", /multiplied/i.test(message), message);
  check("predict: the message quotes the real working", /12 \/ 4 = 3 A/.test(message), message);
  check("predict: the verdict says not quite",
    card.querySelector("[data-challenge-verdict]").textContent === "Not quite");
  check("predict: the live region announced it", /multiplied/i.test(live.textContent), live.textContent);
  check("predict: the prediction is locked after the reveal", input.readOnly === true);
  check("predict: the submit button is spent", submit.disabled === true);
  check("predict: the revealed circuit shows the real current",
    card.querySelector("[data-challenge-revealed] svg").textContent.includes("3 A"));
  eq("predict: the tally counts one attempt",
    d.querySelector("[data-predict-tally]").textContent, "0 of 1 predictions correct.");

  // A correct prediction on challenge 1.
  const first = d.querySelector("[data-challenge='c1']");
  first.querySelector("input").value = "2";
  fire(first.querySelector("[data-challenge-submit]"), "click");
  check("predict: 12 V / 6 ohm = 2 A is accepted",
    first.querySelector("[data-challenge-verdict]").textContent === "Correct",
    first.querySelector("[data-challenge-feedback]").textContent);
  eq("predict: the tally now reads 1 of 2",
    d.querySelector("[data-predict-tally]").textContent, "1 of 2 predictions correct.");
}

/* ============================== 4. challenge mode adapts to the mistake */
{
  const { d, w, errors } = await ready(boot("/lab"));
  check("adaptive: no console errors", errors.length === 0, errors.join(" | "));
  const panel = d.querySelector("[data-adaptive-panel]");
  check("adaptive: the session starts closed", panel.hidden === true);

  fire(d.querySelector("[data-adaptive-start]"), "click");
  check("adaptive: the panel opens", panel.hidden === false);
  const question = d.querySelector("[data-adaptive-question]").textContent;
  const meta = d.querySelector("[data-adaptive-meta]").textContent;
  const input = d.querySelector("[data-adaptive-input]");
  check("adaptive: a question is shown", question.length > 20, question);
  check("adaptive: the first question is easy", /^easy/.test(meta), meta);
  check("adaptive: a circuit is drawn", Boolean(d.querySelector("[data-adaptive-figure] svg")));
  check("adaptive: the asked quantity is covered",
    d.querySelector("[data-adaptive-figure] svg").textContent.includes("?"));

  // An empty answer must not be graded.
  fire(d.querySelector("[data-adaptive-submit]"), "click");
  check("adaptive: an empty answer is refused",
    d.querySelector("#ev-adaptive-live").textContent === "Enter a number before checking your answer.");
  check("adaptive: nothing was recorded", readStorage(w) === null);

  // A deliberately wrong answer: the tag and level of the next question are
  // what the adaptive claim rests on.
  const firstTag = meta.split("\u00b7")[1].trim();
  input.value = "99999";
  fire(d.querySelector("[data-adaptive-submit]"), "click");

  const feedback = d.querySelector("[data-adaptive-feedback]").textContent;
  check("adaptive: a wrong answer is marked", feedback.includes("Not quite"), feedback.slice(0, 80));
  check("adaptive: the explanation is specific", feedback.length > 120, feedback.slice(0, 120));
  check("adaptive: it promises an easier question", /easier/i.test(feedback), feedback.slice(0, 200));
  check("adaptive: the input is locked after grading", input.readOnly === true);
  check("adaptive: the live region announced the result",
    d.querySelector("#ev-adaptive-live").textContent.length > 40);

  const saved = readStorage(w);
  check("adaptive: the attempt was saved", saved && saved.attempts === 1, JSON.stringify(saved));
  eq("adaptive: the mistake was recorded against its concept",
    Object.keys(saved.tags)[0] && saved.tags[Object.keys(saved.tags)[0]].wrong, 1);
  eq("adaptive: the level dropped back to easy", saved.level, "easy");
  eq("adaptive: the progress panel shows one attempt",
    d.querySelector("[data-progress-count='attempts']").textContent, "1");
  eq("adaptive: the progress panel shows zero correct",
    d.querySelector("[data-progress-count='correct']").textContent, "0");
  eq("adaptive: accuracy reads 0%", d.querySelector("[data-progress-accuracy]").textContent, "0%");
  eq("adaptive: the weakest concept is named", d.querySelector("[data-progress-weakest]").textContent, firstTag);
  check("adaptive: a recommendation is shown",
    !d.querySelector("[data-adaptive-recommend]").hidden,
    d.querySelector("[data-adaptive-recommend]").textContent);

  // Next question: easier, and on the same concept.
  fire(d.querySelector("[data-adaptive-next]"), "click");
  const secondMeta = d.querySelector("[data-adaptive-meta]").textContent;
  check("adaptive: the next question is still easy", /^easy/.test(secondMeta), secondMeta);
  check("adaptive: the next question is on the same concept",
    secondMeta.includes(firstTag), `${secondMeta} vs ${firstTag}`);
  check("adaptive: the input is unlocked for the next question",
    d.querySelector("[data-adaptive-input]").readOnly === false);

  // Now answer correctly and confirm the ladder moves up.
  const Lab = w.EngineVerseLab;
  const asked = d.querySelector("[data-adaptive-question]").textContent;
  const shown = Lab.BANK.filter((q) => q.prompt === asked)[0];
  check("adaptive: the shown question is in the bank", Boolean(shown), asked);
  const truth = Lab.answerFor(shown).truth;
  d.querySelector("[data-adaptive-input]").value = String(Lab.round(truth, 4));
  fire(d.querySelector("[data-adaptive-submit]"), "click");
  check("adaptive: the key answer is accepted",
    d.querySelector("[data-adaptive-feedback]").textContent.includes("Correct"),
    d.querySelector("[data-adaptive-feedback]").textContent.slice(0, 120));
  eq("adaptive: the level rose to medium", readStorage(w).level, "medium");
  fire(d.querySelector("[data-adaptive-next]"), "click");
  check("adaptive: the next question is harder",
    /^medium/.test(d.querySelector("[data-adaptive-meta]").textContent),
    d.querySelector("[data-adaptive-meta]").textContent);
  eq("adaptive: two attempts recorded", readStorage(w).attempts, 2);
  eq("adaptive: one correct recorded", readStorage(w).correct, 1);
  eq("adaptive: accuracy reads 50%", d.querySelector("[data-progress-accuracy]").textContent, "50%");

  // Finish the session and read the summary.
  fire(d.querySelector("[data-adaptive-finish]"), "click");
  const summary = d.querySelector("[data-adaptive-summary]");
  check("adaptive: the summary is shown", summary.hidden === false);
  check("adaptive: the summary reports the score", /1 of 2 correct \(50%\)/.test(summary.textContent),
    summary.textContent);
  check("adaptive: the summary says the data is on this device",
    /on this device/i.test(summary.textContent), summary.textContent);
  check("adaptive: a retry is offered", d.querySelector("[data-adaptive-retry]").hidden === false);
  check("adaptive: sessions are kept", Array.isArray(readStorage(w).sessions) && readStorage(w).sessions.length === 1);

  /* ------------------------------- 5. progress survives a refresh */
  const storage = { "engineverse.lab.v1": w.localStorage.getItem("engineverse.lab.v1") };
  const second = await ready(boot("/lab", storage));
  check("refresh: no console errors", second.errors.length === 0, second.errors.join(" | "));
  eq("refresh: attempts survived", second.d.querySelector("[data-progress-count='attempts']").textContent, "2");
  eq("refresh: correct survived", second.d.querySelector("[data-progress-count='correct']").textContent, "1");
  eq("refresh: accuracy survived", second.d.querySelector("[data-progress-accuracy]").textContent, "50%");
  check("refresh: the weakest concept survived",
    second.d.querySelector("[data-progress-weakest]").textContent !== "None yet",
    second.d.querySelector("[data-progress-weakest]").textContent);
  check("refresh: the recommendation survived",
    !second.d.querySelector("[data-adaptive-recommend]").hidden);

  // Clearing must actually clear.
  fire(second.d.querySelector("[data-adaptive-reset]"), "click");
  const cleared = readStorage(second.w);
  eq("reset: attempts cleared", cleared.attempts, 0);
  eq("reset: the panel reads zero",
    second.d.querySelector("[data-progress-count='attempts']").textContent, "0");
  eq("reset: accuracy reads an em dash",
    second.d.querySelector("[data-progress-accuracy]").textContent, "\u2014");
}

/* ============================ 6. a brand-new visitor sees an honest empty state */
{
  const { d } = await ready(boot("/lab"));
  eq("new visitor: zero attempts", d.querySelector("[data-progress-count='attempts']").textContent, "0");
  eq("new visitor: no weakest concept",
    d.querySelector("[data-progress-weakest]").textContent, "None yet");
  eq("new visitor: no accuracy claimed",
    d.querySelector("[data-progress-accuracy]").textContent, "\u2014");
  check("new visitor: no recommendation is invented",
    d.querySelector("[data-adaptive-recommend]").hidden === true);
}

/* ===================================== 7. the home page hero preview works */
{
  const { d, errors } = await ready(boot("/"));
  check("home: no console errors", errors.length === 0, errors.join(" | "));
  check("home: the hero CTA points at the lab",
    Boolean(d.querySelector(".hero-actions a[href*='/lab']")));
  eq("home: the hero CTA text",
    d.querySelector(".hero-actions a[href*='/lab']").textContent.replace(/\s+/g, " ").trim(),
    "Try the Adaptive Lab");
  check("home: the secondary CTA points at the notes",
    Boolean(d.querySelector(".hero-actions a[href*='/explore']")));
  const volts = d.querySelector("[data-lab-volts]");
  check("home: the preview simulator is live", Boolean(volts));
  eq("home: the preview reads 2 A at 12 V / 6 ohm", d.querySelector("[data-lab-i]").textContent, "2 A");
  volts.value = "5";
  fire(volts, "input");
  eq("home: the preview responds to the slider", d.querySelector("[data-lab-i]").textContent, "833.3 mA");
  check("home: the preview draws a circuit",
    Boolean(d.querySelector("[data-lab-figure] svg")));
  // The honest status chips.
  const chips = Array.from(d.querySelectorAll(".status-chip")).map((c) => c.textContent.trim());
  check("home: status chips are rendered", chips.length >= 4, chips.join(", "));
  check("home: every chip is one of the three honest labels",
    chips.every((c) => /Working now|Demo data|Coming next/.test(c)), chips.join(" | "));
  // The workspace table must link to real pages.
  const rows = d.querySelectorAll(".ws-table tbody tr");
  check("home: the workspace table has real rows", rows.length >= 8, String(rows.length));
  const rowLinks = Array.from(d.querySelectorAll(".ws-table tbody a"));
  check("home: every table row links somewhere", rowLinks.length === rows.length);
  check("home: no table link is empty",
    rowLinks.every((a) => a.textContent.trim().length > 0));
}

}

/* --------------------------------------------------------------- report */
main().then(() => {
  if (failures.length) {
    console.error(`\n${failures.length} lab page check(s) failed:`);
    for (const failure of failures) console.error(`  - ${failure}`);
    process.exit(1);
  }
  console.log(`lab page: ${passes} checks passed`);
}).catch((error) => {
  console.error(error);
  process.exit(1);
});
