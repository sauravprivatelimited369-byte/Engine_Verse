#!/usr/bin/env node
/* End-to-end checks for the exported GitHub Pages copy.
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   python scripts/export_pages.py --out site --reading-copy
 *   node scripts/check_static_site.js site
 *
 * The static copy has no server and no accounts. This runs the shipped pages
 * with the shipped runtime (backend/static/js/pages-live.js, copied into the
 * export) under jsdom and checks what a learner depends on:
 *
 *   1. data left by older versions (password digest, GitHub token, OTP state,
 *      session cookie) is migrated to the local profile and then deleted;
 *   2. the settings page saves a profile, exports it without sensitive fields,
 *      and imports a file only after validating it (hostile links dropped);
 *   3. the dashboard, profile, mistakes and portfolio pages render that
 *      profile, writing learner text as text, never as HTML;
 *   4. every exported page is honest about the copy: no forms that post to a
 *      server, no "#" links, no sign-in prompts outside the explainer pages,
 *      no references to the old repository and no OTP or vault wording.
 *
 * Replaces scripts/check_auth_flow.js, which tested the removed browser-side
 * password/OTP accounts.
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

const failures = [];
let passes = 0;
function check(label, condition, detail) {
  if (condition) {
    passes += 1;
  } else {
    failures.push(detail ? `${label}: ${detail}` : label);
  }
}

function pageFile(route) {
  const rel = route.replace(/^\/+|\/+$/g, "");
  return path.join(SITE, rel, "index.html");
}

// Boots one exported page with pages-live.js. `storage` pre-seeds
// localStorage/sessionStorage; `cookie` pre-seeds document.cookie.
function boot(route, { storage = {}, session = {}, cookie = "", confirm = true } = {}) {
  const html = fs.readFileSync(pageFile(route), "utf8").replace(/<script\b(?![^>]*type="application\/json")[\s\S]*?<\/script>/g, "");
  const virtualConsole = new VirtualConsole();
  const errors = [];
  virtualConsole.on("jsdomError", (e) => errors.push(String(e && e.message || e)));
  virtualConsole.on("warn", (...a) => errors.push(a.join(" ")));
  const dom = new JSDOM(html, {
    url: `${ORIGIN}${BASE}${route.replace(/^\/+/, "")}`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const w = dom.window;
  for (const [k, v] of Object.entries(storage)) w.localStorage.setItem(k, v);
  for (const [k, v] of Object.entries(session)) w.sessionStorage.setItem(k, v);
  if (cookie) w.document.cookie = cookie;
  w.confirm = () => confirm;
  w.print = () => { w.__printed = true; };
  w.URL.createObjectURL = () => "blob:test";
  w.URL.revokeObjectURL = () => {};
  w.eval(RUNTIME);
  return { w, d: w.document, errors };
}

const $ = (d, sel) => d.querySelector(sel);

// ----------------------------------------------------------------- 1. migration
{
  const legacy = {
    currentUser: "asha",
    githubToken: "ghp_exampletokenthatmustbedeleted0000",
    webhookUrl: "https://hooks.example/forward",
    otpChallenges: { signup: { code: "123456" } },
    accounts: {
      asha: {
        username: "asha", display_name: "Asha", email: "asha@example.com", phone: "+919876543210",
        password_sha256: "deadbeef", otp_verified: true, branch: "Computer Science", year_of_study: 2,
        xp: 310, completed_topics: ["arrays", "linked-lists"], solved_problems: ["two-sum"],
        bookmarks: ["topic:arrays"], quiz_attempts: 4, quiz_correct: 3,
        mistakes: [{ id: "q1", stem: "<img src=x onerror=alert(1)>", correctLabel: "B", topicUrl: "javascript:alert(1)" }],
      },
    },
  };
  const { w, d } = boot("/dashboard/", {
    storage: { "ev:learner-store:v2": JSON.stringify(legacy), "ev:otp_api_url": "https://otp.example" },
    session: { "ev:session:user": "asha", "ev:explicit_logout": "1" },
    cookie: "ev_live_user=asha; path=/",
  });
  const stored = w.localStorage.getItem("ev:local-profile:v1") || "";
  check("migration: legacy store removed", w.localStorage.getItem("ev:learner-store:v2") === null);
  check("migration: OTP service key removed", w.localStorage.getItem("ev:otp_api_url") === null);
  check("migration: session keys removed", w.sessionStorage.getItem("ev:session:user") === null &&
    w.sessionStorage.getItem("ev:explicit_logout") === null);
  check("migration: session cookie expired", !/ev_live_user=asha/.test(d.cookie), d.cookie);
  check("migration: progress kept", /"arrays"/.test(stored) && /"two-sum"/.test(stored) && /"xp":310/.test(stored), stored);
  for (const secret of ["ghp_", "deadbeef", "asha@example.com", "9876543210", "123456", "hooks.example", "password", "email", "phone"]) {
    check(`migration: "${secret}" not kept`, !stored.includes(secret));
  }
  check("dashboard: greeting uses migrated name", $(d, "#ev-dash-greeting").textContent === "Asha's progress",
    $(d, "#ev-dash-greeting").textContent);
  check("dashboard: XP shown", $(d, "#ev-stat-xp").textContent === "310");
  check("dashboard: topics counted", $(d, "#ev-stat-topics").textContent === "2");
  check("dashboard: recent list rendered", d.querySelectorAll("#ev-dash-activity li").length === 3);
  check("dashboard: bookmark rendered", d.querySelectorAll("#ev-dash-bookmarks li a").length === 1);

  const m = boot("/mistakes/", { storage: { "ev:local-profile:v1": stored } });
  const items = m.d.querySelectorAll("#ev-mistakes-list li");
  check("mistakes: rendered", items.length === 1);
  check("mistakes: stem is text, not HTML", !m.d.querySelector("#ev-mistakes-list img") &&
    /<img/.test(items[0] ? items[0].textContent : ""));
  check("mistakes: javascript: link dropped", !m.d.querySelector('#ev-mistakes-list a[href^="javascript"]'));
  m.d.querySelector("#ev-mistakes-list button").click();
  check("mistakes: mark as understood removes it", m.d.querySelectorAll("#ev-mistakes-list li").length === 0 &&
    !m.d.querySelector('[data-ev-empty="ev-mistakes-list"]').hidden);
}

// ------------------------------------------------------------------ 2. settings
{
  const { w, d } = boot("/settings/");
  const form = $(d, "#ev-profile-form");
  check("settings: profile form present", Boolean(form));
  check("settings: no password or contact fields",
    !d.querySelector('main input[type="password"], main input[type="email"], main input[type="tel"]'));
  form.elements.display_name.value = "someone@example.com";
  form.dispatchEvent(new w.Event("submit", { cancelable: true }));
  check("settings: email rejected as display name", !(w.localStorage.getItem("ev:local-profile:v1") || "").includes("someone@"));
  form.elements.display_name.value = "Ravi <b>K</b>";
  form.elements.branch.value = "Mechanical";
  form.elements.year_of_study.value = "3";
  form.dispatchEvent(new w.Event("submit", { cancelable: true }));
  const saved = JSON.parse(w.localStorage.getItem("ev:local-profile:v1"));
  check("settings: profile saved", saved.display_name === "Ravi <b>K</b>" && saved.branch === "Mechanical" && saved.year_of_study === 3,
    JSON.stringify(saved));

  // Export: capture the Blob written by the click handler.
  let exported = null;
  const RealBlob = w.Blob;
  w.Blob = function (parts, opts) { exported = parts.join(""); return new RealBlob(parts, opts); };
  $(d, "#ev-export-json").click();
  w.Blob = RealBlob;
  const payload = exported ? JSON.parse(exported) : {};
  check("export: format and version", payload.format === "engineverse-local-progress" && payload.version === 1);
  check("export: no sensitive keys", exported && !/password|email|phone|token|otp/i.test(Object.keys(payload.profile || {}).join(" ")));

  const p = boot("/profile/", { storage: { "ev:local-profile:v1": JSON.stringify(saved) } });
  check("profile: name rendered as text", p.d.querySelector("#ev-profile-name").textContent === "Ravi <b>K</b>" &&
    !p.d.querySelector("#ev-profile-name b"));
  check("profile: branch and year", p.d.querySelector("#ev-profile-branch").textContent === "Mechanical · 3rd year",
    p.d.querySelector("#ev-profile-branch").textContent);
}

// ---------------------------------------------------- 2b. import is validated
async function importCheck() {
  const { w, d } = boot("/settings/");
  const input = $(d, "#ev-import-json");
  const status = () => $(d, "#ev-settings-status").textContent;
  // FileReader and the import handler are asynchronous. Poll for the expected
  // line instead of sleeping for a fixed time: a fixed sleep is a race that
  // failed on a loaded CI runner and passed on a laptop.
  const waitFor = (pattern) => new Promise((resolve) => {
    const started = Date.now();
    const poll = () => {
      if (pattern.test(status()) || Date.now() - started > 3000) resolve();
      else setTimeout(poll, 15);
    };
    poll();
  });
  const feed = async (text, pattern) => {
    const file = new w.File([text], "progress.json", { type: "application/json" });
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    input.dispatchEvent(new w.Event("change"));
    await waitFor(pattern);
  };
  await feed("{not json", /not valid JSON/);
  check("import: invalid JSON reported", /not valid JSON/.test($(d, "#ev-settings-status").textContent));
  await feed(JSON.stringify({ hello: "world" }), /not a Forge progress export/);
  check("import: foreign file refused", /not a Forge progress export/.test($(d, "#ev-settings-status").textContent));
  await feed(JSON.stringify({
    format: "engineverse-local-progress", version: 1,
    profile: {
      display_name: "Imported", xp: 99, completed_topics: ["arrays", "<script>", "../../etc"],
      password_sha256: "x", githubToken: "ghp_x",
      mistakes: [{ id: "q9", stem: "Why?", topicUrl: "https://evil.example/" }],
    },
    streak_days: ["2026-01-01", "not-a-date"],
  }), /Imported/);
  const after = w.localStorage.getItem("ev:local-profile:v1") || "";
  check("import: valid file applied", /"Imported"/.test(after) && /"xp":99/.test(after), after);
  check("import: unsafe slugs dropped", !after.includes("<script>") && !after.includes("../"));
  check("import: unknown keys dropped", !/password|githubToken|ghp_/.test(after));
  check("import: off-site link dropped", !after.includes("evil.example"));
  check("import: invalid dates dropped", !(w.localStorage.getItem("ev:streak:v1") || "").includes("not-a-date"));

  $(d, "#ev-clear-data").click();
  check("clear: profile deleted", w.localStorage.getItem("ev:local-profile:v1") === null ||
    !/"Imported"/.test(w.localStorage.getItem("ev:local-profile:v1")));
}

// ------------------------------------------- 2c. topic completion and saving
{
  const { w, d } = boot("/topics/arrays/");
  const done = d.querySelector('[data-complete-topic="arrays"]');
  const save = d.querySelector('[data-bookmark="topic"][data-id="arrays"]');
  check("topic: Mark complete button present", Boolean(done));
  check("topic: Save button present", Boolean(save));
  if (done && save) {
    done.click();
    save.click();
    const p = JSON.parse(w.localStorage.getItem("ev:local-profile:v1") || "{}");
    check("topic: completion recorded", (p.completed_topics || []).includes("arrays") && p.xp === 25, JSON.stringify(p));
    check("topic: bookmark recorded", (p.bookmarks || []).includes("topic:arrays"));
    check("topic: button reflects state", /Completed/.test(done.textContent) && save.getAttribute("aria-pressed") === "true");
  }
}

// ----------------------------------------------------- 3. portfolio and topbar
{
  const profile = JSON.stringify({ display_name: "Priya", xp: 500, completed_topics: ["arrays"], solved_problems: ["two-sum"] });
  const { w, d } = boot("/portfolio/", { storage: { "ev:local-profile:v1": profile, "ev:streak:v1": JSON.stringify({ days: [] }) } });
  check("portfolio: unverified label", /not\s+verified/i.test(d.querySelector("main").textContent));
  check("portfolio: title", $(d, "#ev-portfolio-title").textContent.startsWith("Priya"));
  $(d, "#ev-portfolio-print").click();
  check("portfolio: print button works", w.__printed === true);
  check("topbar: local progress button present", Boolean(d.querySelector("[data-ev-local-progress]")));
  check("topbar: no sign-in button", !d.querySelector('.topbar a[href$="/login/"], .topbar a[href$="/register/"]'));
}

// ------------------------------------------------------- 4. whole-site scan
function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!["static", "pyodide", "runtimes"].includes(entry.name)) walk(full, out);
    } else if (entry.name.endsWith(".html")) {
      out.push(full);
    }
  }
  return out;
}
{
  const explainers = new Set(["login", "register", "forgot-password", "reset-password", "logout", "notifications", "onboarding"]
    .map((r) => path.join(SITE, r, "index.html")));
  const pages = walk(SITE);
  const problems = { postForms: [], hashLinks: [], signIn: [], oldRepo: [], vault: [], blankTarget: [] };
  for (const file of pages) {
    const html = fs.readFileSync(file, "utf8");
    const rel = path.relative(SITE, file);
    if (/<form\b[^>]*method=["']?post/i.test(html)) problems.postForms.push(rel);
    if (/<a\b[^>]*href=["']#["']/i.test(html)) problems.hashLinks.push(rel);
    if (!explainers.has(file) && /href="[^"]*\/(login|register)\/"/.test(html)) problems.signIn.push(rel);
    if (/authorsauravkushwaha/i.test(html)) problems.oldRepo.push(rel);
    if (/learner vault|registry\.json|GitHub Vault/i.test(html)) problems.vault.push(rel);
    for (const m of html.matchAll(/<a\b[^>]*target="_blank"[^>]*>/g)) {
      if (!/rel="[^"]*noopener/.test(m[0])) { problems.blankTarget.push(rel); break; }
    }
  }
  check(`scan: ${pages.length} pages exported`, pages.length > 500);
  for (const [name, list] of Object.entries(problems)) {
    check(`scan: no ${name}`, list.length === 0, list.slice(0, 8).join(", "));
  }
  for (const route of ["planner", "opportunities", "support", "dashboard", "settings", "404.html"]) {
    const file = route.endsWith(".html") ? path.join(SITE, route) : pageFile(`/${route}/`);
    check(`scan: ${route} exported`, fs.existsSync(file));
  }
  const sitemap = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");
  check("sitemap: planner listed", /\/planner\/<\/loc>/.test(sitemap));
  check("sitemap: no private pages", !/\/(dashboard|settings|login)\/<\/loc>/.test(sitemap));
}

importCheck().then(() => {
  if (failures.length) {
    console.error(`static site checks: ${failures.length} failed, ${passes} passed`);
    for (const f of failures) console.error(`  FAIL ${f}`);
    process.exit(1);
  }
  console.log(`static site checks: all ${passes} passed`);
  process.exit(0);
}).catch((e) => {
  console.error(e);
  process.exit(1);
});
