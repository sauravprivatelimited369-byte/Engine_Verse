#!/usr/bin/env node
/* Behaviour checks for the question bank's topic filter on the static copy.
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   python scripts/export_pages.py --out site --reading-copy
 *   node scripts/check_question_bank.js site
 *
 * The Python suite (test_question_bank_topics.py) proves the hosted bank.
 * This runs the *exported* /practice/questions page and the *shipped*
 * backend/static/js/pages-live.js under jsdom, with fetch serving the real
 * exported quiz-bank.json, and checks what a learner on the GitHub Pages
 * copy actually experiences when they ask for one topic's MCQs:
 *
 *   1. the page takes over from the baked-in first screen: the full bank is
 *      filterable, 24 at a time, and the server pager (which links to a
 *      page 2 this copy does not have) is replaced by Show more;
 *   2. choosing a subject shows only that subject's questions and narrows
 *      the topic list to that subject's topics;
 *   3. choosing a topic shows exactly that topic's MCQs - the thing that
 *      used to change nothing at all;
 *   4. the choice lands in the URL, so a ?topic= deep link (or a reload)
 *      opens already filtered, and an unknown topic matches nothing
 *      rather than everything;
 *   5. the stem search and a ?slug= deep link narrow the same way;
 *   6. a card the filter rendered still grades: the right option lights
 *      up (the .opt class the markup really uses) and the verdict shows.
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
const deployment = JSON.parse(fs.readFileSync(path.join(SITE, "deployment.json"), "utf8"));
const BASE = deployment.base || "/";
const ORIGIN = "https://example.github.io";
const RUNTIME = fs.readFileSync(path.join(SITE, "static", "js", "pages-live.js"), "utf8");
const BANK = JSON.parse(fs.readFileSync(path.join(SITE, "quiz-bank.json"), "utf8"));
const ENTRIES = Object.values(BANK);
const PAGE = fs.readFileSync(path.join(SITE, "practice", "questions", "index.html"), "utf8");

const failures = [];
let passes = 0;
function check(label, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => { passes += 1; console.log("ok   " + label); })
    .catch((err) => { failures.push(label + ": " + err.message); console.log("FAIL " + label + "\n     " + err.message); });
}

const tick = (ms = 25) => new Promise((r) => setTimeout(r, ms));
async function until(fn, label) {
  for (let i = 0; i < 120; i += 1) {
    if (fn()) return;
    await tick(25);
  }
  throw new Error("timed out waiting for " + label);
}

// Boots the exported question bank with the shipped runtime, like
// check_static_site.js: the page's own scripts are stripped, the #ev-live
// boot data stays, and fetch answers with the exported quiz bank.
function boot(query = "") {
  const html = PAGE.replace(/<script\b(?![^>]*type="application\/json")[\s\S]*?<\/script>/g, "");
  const virtualConsole = new VirtualConsole();
  const dom = new JSDOM(html, {
    url: `${ORIGIN}${BASE}practice/questions/${query}`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const w = dom.window;
  w.fetch = async (url) => ({
    ok: true,
    json: async () => (String(url).includes("quiz-bank") ? BANK : {}),
  });
  w.eval(RUNTIME);
  return { w, d: w.document };
}

const cards = (d) => Array.from(d.querySelectorAll("#qb-list [data-quiz]"));
const cardIds = (d) => cards(d).map((c) => c.getAttribute("data-quiz"));
const takenOver = (d) => {
  const pager = d.querySelector(".pager");
  return !pager || pager.hidden === true;
};
function choose(w, sel, value) {
  sel.value = value;
  sel.dispatchEvent(new w.Event("change", { bubbles: true }));
}

// A subject small enough to fit on one screen but with a topic of 2+ MCQs,
// worked out from the exported bank so the seed can grow without breaking this.
const bySubject = new Map();
for (const item of ENTRIES) {
  if (!item.subjectId) continue;
  if (!bySubject.has(item.subjectId)) bySubject.set(item.subjectId, []);
  bySubject.get(item.subjectId).push(item);
}
const byTopic = new Map();
for (const item of ENTRIES) {
  if (!item.topicSlug) continue;
  if (!byTopic.has(item.topicSlug)) byTopic.set(item.topicSlug, []);
  byTopic.get(item.topicSlug).push(item);
}
let SUBJECT = null;
let TOPIC = null;
for (const [subjectId, items] of bySubject) {
  if (items.length < 2 || items.length > 24) continue;
  const topic = items.find((i) => i.topicSlug && (byTopic.get(i.topicSlug) || []).length >= 2);
  if (topic) { SUBJECT = subjectId; TOPIC = topic.topicSlug; break; }
}
assert.ok(SUBJECT && TOPIC, "exported bank has no subject with a 2+ MCQ topic to test with");

(async () => {
  // --- 1. takeover -----------------------------------------------------------
  const { w, d } = boot();
  await until(() => takenOver(d) && cards(d).length > 0, "question bank takeover");
  await check("the static bank takes over and pages 24 at a time", () => {
    assert.equal(cards(d).length, Math.min(24, ENTRIES.length));
    for (const id of cardIds(d)) assert.ok(BANK[id], `rendered card ${id} is not in the bank`);
    assert.match(d.getElementById("qb-count").textContent, new RegExp(`^${ENTRIES.length} questions`));
  });

  await check("show more reveals the next screen of the bank", async () => {
    if (ENTRIES.length <= 24) return;
    const btn = Array.from(d.querySelectorAll("button")).find((b) => /Show more questions/.test(b.textContent));
    assert.ok(btn, "no Show more button");
    btn.click();
    await until(() => cards(d).length === Math.min(48, ENTRIES.length), "second screen");
  });

  // --- 2 + 3. subject, then topic -------------------------------------------
  const subjectSel = d.getElementById("subject");
  const topicSel = d.getElementById("topic");
  choose(w, subjectSel, SUBJECT);
  await until(() => cardIds(d).every((id) => BANK[id].subjectId === SUBJECT) && cards(d).length === bySubject.get(SUBJECT).length, "subject filter");
  await check("choosing a subject shows only its questions and narrows the topics", () => {
    assert.match(d.getElementById("qb-count").textContent, new RegExp(`^${bySubject.get(SUBJECT).length} matching`));
    assert.ok(w.location.search.includes(`subject=${SUBJECT}`), "subject not in URL: " + w.location.search);
    const foreign = Array.from(topicSel.querySelectorAll("optgroup[data-subject]"))
      .filter((g) => g.getAttribute("data-subject") !== SUBJECT);
    assert.ok(foreign.length > 0 && foreign.every((g) => g.disabled), "other subjects' topics stay selectable");
  });

  choose(w, topicSel, TOPIC);
  const wantTopicIds = byTopic.get(TOPIC).map((i) => i.id).sort();
  await until(() => cardIds(d).slice().sort().join() === wantTopicIds.join(), "topic filter");
  await check("choosing a topic shows exactly that topic's MCQs", () => {
    assert.ok(w.location.search.includes(`topic=${TOPIC}`), "topic not in URL: " + w.location.search);
    for (const card of cards(d)) {
      assert.match(card.textContent, new RegExp(BANK[card.getAttribute("data-quiz")].topicTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    }
  });

  // --- 6. grading a rendered card --------------------------------------------
  await check("a filtered-in card grades and lights the right option", async () => {
    const card = cards(d)[0];
    const item = BANK[card.getAttribute("data-quiz")];
    assert.ok(item.correctIndex >= 0, "test question has no correct option");
    const radio = card.querySelector(`input[name='option'][value='${item.correctIndex}']`);
    radio.checked = true;
    card.querySelector("form").dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
    await until(() => /Correct/.test(card.querySelector(".verdict-inline").textContent), "verdict");
    assert.ok(card.querySelector(".opt.correct"), "the correct .opt did not light up");
  });

  // --- 5. stem search ---------------------------------------------------------
  await check("the stem search narrows by question text", async () => {
    const counts = new Map();
    for (const item of ENTRIES) {
      for (const word of new Set(String(item.stem).toLowerCase().match(/[a-z]{6,}/g) || [])) {
        counts.set(word, (counts.get(word) || 0) + 1);
      }
    }
    const word = Array.from(counts).find(([, n]) => n >= 1 && n <= 10)?.[0];
    assert.ok(word, "no suitably rare stem word to search for");
    // Searching starts a fresh question, so clear subject/topic first.
    choose(w, topicSel, "");
    choose(w, subjectSel, "");
    const q = d.getElementById("qb-q");
    q.value = word;
    q.dispatchEvent(new w.Event("input", { bubbles: true }));
    const want = ENTRIES.filter((i) => i.stem.toLowerCase().includes(word)).length;
    await until(() => cards(d).length === want, "search results");
    for (const id of cardIds(d)) assert.ok(BANK[id].stem.toLowerCase().includes(word), `card ${id} does not mention "${word}"`);
  });

  // --- 4. deep links ------------------------------------------------------------
  const deep = boot(`?topic=${TOPIC}`);
  await until(() => takenOver(deep.d) && cardIds(deep.d).length > 0, "topic deep link takeover");
  await check("a ?topic= deep link opens on that topic's MCQs", () => {
    assert.deepEqual(cardIds(deep.d).slice().sort(), wantTopicIds);
    assert.equal(deep.d.getElementById("topic").value, TOPIC);
    assert.equal(deep.d.getElementById("subject").value, SUBJECT);
  });

  const slugItem = ENTRIES.find((i) => i.slug);
  const bySlug = boot(`?slug=${encodeURIComponent(slugItem.slug)}`);
  await until(() => takenOver(bySlug.d) && cardIds(bySlug.d).length === 1, "slug deep link");
  await check("a ?slug= deep link opens on that one question", () => {
    assert.equal(cardIds(bySlug.d)[0], slugItem.id);
  });

  const unknown = boot("?topic=not-a-real-topic");
  await until(() => takenOver(unknown.d) && /No questions match that filter/.test(unknown.d.getElementById("qb-list").textContent), "unknown topic empty state");
  await check("an unknown topic matches nothing, not everything", () => {
    assert.equal(cardIds(unknown.d).length, 0);
    assert.match(unknown.d.getElementById("qb-count").textContent, /^0 matching/);
  });

  console.log(`\n${passes} passed, ${failures.length} failed`);
  if (failures.length) process.exitCode = 1;
})();
