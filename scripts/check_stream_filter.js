#!/usr/bin/env node
/* Behaviour checks for the global stream (branch) switcher and its filter.
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   python scripts/export_pages.py --out site --reading-copy
 *   node scripts/check_stream_filter.js site
 *
 * The Python suite proves the server side. This runs the *exported* pages and
 * the *shipped* backend/static/js/stream.js under jsdom, and checks the thing a
 * learner actually experiences when they pick their stream:
 *
 *   1. the switcher is on every page, built from the branch catalogue, and its
 *      links point at the deployment's base prefix;
 *   2. choosing a stream hides every subject card of another branch while the
 *      shared first-year core (which belongs to no single branch) stays;
 *   3. the catalogue says it is filtered, names the stream and links to that
 *      stream's hub rather than leaving a silently emptied grid;
 *   4. the home shelf and the streams index filter the same way;
 *   5. clearing the choice restores everything, the choice survives a page
 *      reload through the local profile, and a slug that is not a branch is
 *      refused rather than stored.
 */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.dirname(__dirname);
const { JSDOM } = require(path.join(ROOT, ".toolchain/jsdom/node_modules/jsdom"));

const SITE = process.argv[2];
if (!SITE) {
  console.error("usage: node scripts/check_stream_filter.js <exported-site>");
  process.exit(2);
}
const streamJs = fs.readFileSync(path.join(SITE, "static/js/stream.js"), "utf8");

// Each JSDOM gets its own localStorage, so a "reload" has to be simulated by
// seeding the next document with the previous one's storage - which is exactly
// what a real browser does when it navigates.
function load(page, storage) {
  const html = fs.readFileSync(path.join(SITE, page), "utf8");
  const dom = new JSDOM(html, {
    url: "https://example.com/Engine_Verse/" + page.replace(/index\.html$/, ""),
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  if (storage) {
    for (const key of Object.keys(storage)) dom.window.localStorage.setItem(key, storage[key]);
  }
  dom.window.eval(streamJs);
  return dom;
}

function snapshot(window) {
  const out = {};
  for (let i = 0; i < window.localStorage.length; i++) {
    const key = window.localStorage.key(i);
    out[key] = window.localStorage.getItem(key);
  }
  return out;
}

let checks = 0;
function check(name, fn) {
  checks++;
  try {
    fn();
    console.log("ok   " + name);
  } catch (err) {
    console.log("FAIL " + name + "\n     " + err.message);
    process.exitCode = 1;
  }
}

const MECH = "mechanical-engineering";

// --- explore: the catalogue shelf ---------------------------------
const dom = load("explore/index.html");
const w = dom.window;
const d = w.document;

check("the switcher is on the page with the full branch catalogue", () => {
  assert.ok(w.EVStream, "stream.js did not expose EVStream");
  assert.equal(w.EVStream.list().length, 45, "expected 45 branches");
  assert.equal(d.querySelectorAll("[data-ev-stream-slug]").length, 45);
});

check("the switcher links carry the deployment's base prefix", () => {
  const hrefs = Array.from(d.querySelectorAll("[data-ev-stream-slug]"))
    .map((a) => a.getAttribute("href"));
  assert.ok(hrefs.length > 0);
  for (const href of hrefs) assert.match(href, /^\/Engine_Verse\/stream\/[a-z0-9-]+\/$/);
});

check("nothing is hidden until a stream is chosen", () => {
  assert.equal(d.querySelectorAll(".ev-stream-off").length, 0);
  assert.equal(d.querySelector("[data-ev-stream-notice]").classList.contains("is-on"), false);
});

check("a chosen stream hides every other branch's subject cards", () => {
  w.EVStream.select(MECH);
  const cards = Array.from(d.querySelectorAll(".subject-card"));
  const on = cards.filter((c) => !c.classList.contains("ev-stream-off"));
  const off = cards.filter((c) => c.classList.contains("ev-stream-off"));
  assert.ok(off.length > 0, "no card was filtered out");
  assert.ok(on.length > 0, "no card survived");
  for (const card of on) {
    const value = card.getAttribute("data-ev-stream");
    // Cards with no branch (the shared core) survive too; every card that
    // *does* name a branch and survived must name the chosen one.
    if (value !== null) assert.equal(value, MECH);
  }
});

check("the shared first-year core is not filtered out", () => {
  const shared = Array.from(d.querySelectorAll(".subject-card"))
    .filter((c) => !c.hasAttribute("data-ev-stream"));
  assert.ok(shared.length > 0, "expected subjects with no single branch");
  for (const card of shared) {
    assert.equal(card.classList.contains("ev-stream-off"), false);
  }
});

check("the filtered catalogue says so and links to the stream's hub", () => {
  const notice = d.querySelector("[data-ev-stream-notice]");
  assert.equal(notice.classList.contains("is-on"), true);
  assert.match(notice.querySelector("[data-ev-stream-notice-name]").textContent, /Mechanical/);
  assert.equal(
    notice.querySelector("[data-ev-stream-notice-hub]").getAttribute("href"),
    "/Engine_Verse/stream/mechanical-engineering/"
  );
});

check("a page with no stream shelf reports no filter", () => {
  const fresh = load("index.html");
  assert.equal(fresh.window.document.querySelectorAll(".ev-stream-off").length, 0);
});

// --- home: the branch shelf ---------------------------------------
const home = load("index.html");
const hd = home.window.document;
home.window.EVStream.select(MECH);
check("the home branch shelf keeps only the chosen stream's groups", () => {
  const hidden = hd.querySelectorAll(".mx-branch-group .ev-stream-off");
  assert.ok(hidden.length > 0, "no branch row was filtered out");
  const visible = Array.from(hd.querySelectorAll(".mx-branch-group"))
    .filter((g) => !g.classList.contains("ev-stream-off"));
  assert.ok(visible.length > 0, "the chosen stream's group was hidden too");
  const keeps = visible.some((g) =>
    Array.from(g.querySelectorAll("li")).some((li) => li.getAttribute("data-ev-stream") === MECH));
  assert.equal(keeps, true);
});

// --- streams index ------------------------------------------------
const streams = load("streams/index.html");
const sd = streams.window.document;
streams.window.EVStream.select(MECH);
check("the streams index filters its cards", () => {
  assert.ok(sd.querySelectorAll(".card.ev-stream-off").length > 0);
  const kept = Array.from(sd.querySelectorAll(".card")).filter((c) => !c.classList.contains("ev-stream-off"));
  assert.ok(kept.length > 0);
  for (const card of kept) assert.equal(card.getAttribute("data-ev-stream"), MECH);
});

check("clearing the choice restores every card", () => {
  streams.window.EVStream.select("");
  assert.equal(sd.querySelectorAll(".card.ev-stream-off").length, 0);
});

check("the choice is stored in the local profile and survives a reload", () => {
  streams.window.EVStream.select("civil-engineering");
  const stored = JSON.parse(streams.window.localStorage.getItem("ev:local-profile:v1"));
  assert.equal(stored.branch, "civil-engineering");
  const again = load("streams/index.html", snapshot(streams.window));
  assert.equal(again.window.EVStream.current(), "civil-engineering");
  assert.ok(again.window.document.querySelectorAll(".card.ev-stream-off").length > 0);
});

check("a slug that is not a branch is refused, not stored", () => {
  const target = load("streams/index.html", snapshot(streams.window));
  target.window.EVStream.select("not-a-real-branch");
  assert.equal(target.window.EVStream.current(), "civil-engineering");
  assert.equal(JSON.parse(target.window.localStorage.getItem("ev:local-profile:v1")).branch, "civil-engineering");
});

console.log(`\n${checks} checks`);
