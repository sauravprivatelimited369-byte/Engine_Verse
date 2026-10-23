#!/usr/bin/env node
/* Behavioural checks for the study planner (backend/static/js/planner.js).
 *
 *   node scripts/check_planner.js <planner page HTML> <planner.js>
 *
 * Runs the real script in jsdom against the real rendered page: validation,
 * filters, search, edit, done, exam countdowns, timer settings, persistence,
 * sanitising of corrupt or hostile stored data, and delete-all. jsdom is
 * resolved from JSDOM_DIR (default .toolchain/jsdom), as in check_static_site.js.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");
const jsdomDir = process.env.JSDOM_DIR || path.join(__dirname, "..", ".toolchain", "jsdom");
const { JSDOM } = require(path.join(path.resolve(jsdomDir), "node_modules", "jsdom"));
const [htmlPath, srcPath] = process.argv.slice(2);
if (!htmlPath || !srcPath) {
  console.error("usage: node scripts/check_planner.js <planner.html> <planner.js>");
  process.exit(2);
}
const html = fs.readFileSync(htmlPath, "utf8").replace(/<script[\s\S]*?<\/script>/g, "");
const src = fs.readFileSync(srcPath, "utf8");

function boot(storage) {
  const dom = new JSDOM(html, { url: "https://example.test/planner", runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  if (storage) for (const [k, v] of Object.entries(storage)) w.localStorage.setItem(k, v);
  w.confirm = () => true;
  w.eval(src);
  return w;
}
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const day = (off) => iso(new Date(Date.now() + off * 86400000));

let w = boot();
const d = w.document;
const q = (s) => d.querySelector(s);
assert.strictEqual(q("[data-planner]").hidden, false);
assert.strictEqual(q("[data-task-empty]").hidden, false, "empty state shown");

function add(title, subject, due, priority) {
  const f = q("[data-task-form]");
  f.elements.title.value = title; f.elements.subject.value = subject || ""; f.elements.due.value = due || ""; f.elements.priority.value = priority || "normal";
  f.dispatchEvent(new w.Event("submit", { cancelable: true }));
}
add("   ");
assert.strictEqual(q("[data-err=title]").hidden, false, "validation error for empty title");
assert.strictEqual(q("#task-title").getAttribute("aria-invalid"), "true");
add("<img src=x onerror=alert(1)>", "Circuits", day(0), "high");
assert.strictEqual(q("[data-err=title]").hidden, true);
add("Overdue thing", "Maths", day(-2));
add("Later thing", "", day(5), "low");
add("No date thing");
let items = d.querySelectorAll("[data-task-list] li");
assert.strictEqual(items.length, 4, "all active tasks listed");
assert.ok(!d.querySelector("[data-task-list] img"), "user text not parsed as HTML");
assert.strictEqual(items[0].querySelector(".planner-item-title").textContent, "Overdue thing", "sorted by due date");
assert.ok(items[0].classList.contains("is-overdue"));
const count = (k) => q(`[data-count=${k}]`).textContent;
assert.deepStrictEqual([count("all"), count("today"), count("upcoming"), count("overdue")], ["4", "1", "2", "1"]);

q("[data-filter=overdue]").click();
assert.strictEqual(d.querySelectorAll("[data-task-list] li").length, 1);
assert.strictEqual(q("[data-filter=overdue]").getAttribute("aria-pressed"), "true");
q("[data-filter=all]").click();

// toggle done
const cb = d.querySelector("[data-task-list] li input[type=checkbox]");
cb.checked = true; cb.dispatchEvent(new w.Event("change"));
assert.strictEqual(d.querySelectorAll("[data-task-list] li").length, 3, "done tasks leave All");
q("[data-filter=done]").click();
assert.strictEqual(d.querySelectorAll("[data-task-list] li").length, 1);
assert.strictEqual(q("[data-task-foot]").hidden, false);
q("[data-filter=all]").click();

// search
const s = q("#task-search"); s.value = "later"; s.dispatchEvent(new w.Event("input"));
assert.strictEqual(d.querySelectorAll("[data-task-list] li").length, 1);
s.value = "zzz"; s.dispatchEvent(new w.Event("input"));
assert.match(q("[data-task-empty-text]").textContent, /No tasks match/);
s.value = ""; s.dispatchEvent(new w.Event("input"));

// edit
const editBtn = [...d.querySelectorAll("[data-task-list] li button")].find((b) => b.textContent.startsWith("Edit"));
editBtn.click();
assert.strictEqual(q("[data-task-submit]").textContent, "Save changes");
q("#task-title").value = "Edited title";
q("[data-task-form]").dispatchEvent(new w.Event("submit", { cancelable: true }));
assert.ok([...d.querySelectorAll(".planner-item-title")].some((n) => n.textContent === "Edited title"));
assert.strictEqual(d.querySelectorAll("[data-task-list] li").length, 3, "edit did not duplicate");

// exams
const ef = q("[data-exam-form]");
ef.elements.name.value = "Finals"; ef.elements.date.value = day(10);
ef.dispatchEvent(new w.Event("submit", { cancelable: true }));
assert.strictEqual(q(".planner-exam-days").firstChild.textContent, "10");
ef.elements.name.value = ""; ef.dispatchEvent(new w.Event("submit", { cancelable: true }));
assert.strictEqual(q("[data-exam-err]").hidden, false);

// persistence
const stored = JSON.parse(w.localStorage.getItem("ev:planner:v1"));
assert.strictEqual(stored.tasks.length, 4);
assert.strictEqual(stored.exams.length, 1);
const w2 = boot({ "ev:planner:v1": w.localStorage.getItem("ev:planner:v1") });
assert.strictEqual(w2.document.querySelectorAll("[data-task-list] li").length, 3, "reloaded from storage");

// focus timer settings + skip counts nothing, completed session counts
const ff = q("[data-focus-form]");
ff.elements.work.value = "0"; ff.dispatchEvent(new w.Event("submit", { cancelable: true }));
assert.strictEqual(q("[data-focus-err]").hidden, false, "timer validation");
ff.elements.work.value = "50"; ff.elements.brk.value = "10"; ff.dispatchEvent(new w.Event("submit", { cancelable: true }));
assert.strictEqual(q("[data-focus-clock]").textContent, "50:00");
q("[data-focus-skip]").click();
assert.strictEqual(q("[data-focus-phase]").textContent, "Break");
assert.strictEqual(q("[data-focus-clock]").textContent, "10:00");
assert.match(q("[data-focus-count]").textContent, /^0 focus sessions/);

// sanitising import of hostile data via storage
const evil = JSON.stringify({ tasks: [{ title: "x".repeat(500), priority: "urgent", due: "2026-02-31", done: "yes", __proto__: { a: 1 } }, { title: "" }, null, 5],
  exams: [{ name: "bad", date: "nope" }], focus: { work: 9999, sessions: { "bad": 4, [day(0)]: 3 } } });
const w3 = boot({ "ev:planner:v1": evil });
w3.document.querySelector("[data-task-form]").elements.title.value = "trigger";
w3.document.querySelector("[data-task-form]").dispatchEvent(new w3.Event("submit", { cancelable: true }));
const saved = JSON.parse(w3.localStorage.getItem("ev:planner:v1"));
assert.strictEqual(saved.tasks.length, 2);
assert.strictEqual(saved.tasks[0].title.length, 120);
assert.strictEqual(saved.tasks[0].priority, "normal");
assert.strictEqual(saved.tasks[0].due, "");
assert.strictEqual(saved.tasks[0].done, false);
assert.strictEqual(saved.exams.length, 0);
assert.strictEqual(saved.focus.work, 25);
assert.deepStrictEqual(Object.keys(saved.focus.sessions), [day(0)]);
assert.match(w3.document.querySelector("[data-focus-count]").textContent, /^3 focus sessions/);

// corrupt storage does not crash
const w4 = boot({ "ev:planner:v1": "{not json" });
assert.strictEqual(w4.document.querySelector("[data-task-empty]").hidden, false);

// delete-all
q("[data-planner-clear]").click();
assert.strictEqual(w.localStorage.getItem("ev:planner:v1"), null);
assert.strictEqual(d.querySelectorAll("[data-task-list] li").length, 0);
console.log("planner checks passed");
// The planner keeps a midnight-rollover interval alive; end the run explicitly.
process.exit(0);
