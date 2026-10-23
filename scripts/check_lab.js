#!/usr/bin/env node
/* EngineVerse Adaptive Lab — answer key and mistake-detector checks.
 *
 *   node scripts/check_lab.js [path/to/lab.js]
 *
 * lab.js is browser code, but every number a learner sees comes from pure
 * functions on window.EngineVerseLab. This file gives it a minimal window and
 * document, then asserts the arithmetic and the feedback text against a fixed
 * key. If a rule changes wording or a resistor combination changes value, this
 * fails rather than the learner finding out during a demo.
 *
 * Wired into .github/workflows/pages.yml alongside the other site checks.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const SOURCE = process.argv[2] || path.join(__dirname, "..", "backend", "static", "js", "lab.js");
const code = fs.readFileSync(SOURCE, "utf8");

// A window/document just complete enough for lab.js to boot without touching
// the DOM: it only wires listeners when it finds its mount points.
const elementStub = () => ({
  dataset: {}, style: {}, classList: { toggle() {}, add() {}, remove() {} },
  addEventListener() {}, setAttribute() {}, appendChild() {}, focus() {},
  querySelector: () => null, querySelectorAll: () => [],
});
const sandbox = {
  document: {
    readyState: "complete",
    addEventListener() {},
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: elementStub,
  },
  localStorage: (() => {
    const store = new Map();
    return {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };
  })(),
};
sandbox.window = sandbox;
new Function("window", "document", "localStorage", code)(sandbox.window, sandbox.document, sandbox.localStorage);

const Lab = sandbox.window.EngineVerseLab;
if (!Lab) throw new Error("lab.js did not register window.EngineVerseLab");

const failures = [];
let passes = 0;
function check(label, condition, detail) {
  if (condition) { passes += 1; return; }
  failures.push(detail ? `${label}: ${detail}` : label);
}
function eq(label, actual, expected) {
  const ok = typeof expected === "number"
    ? (actual === expected || Math.abs(actual - expected) < 1e-9)
    : actual === expected;
  check(label, ok, `expected ${expected}, got ${actual}`);
}

/* ------------------------------------------------------------ 1. Ohm's law */
eq("12 V / 6 ohm = 2 A", Lab.current(12, 6), 2);
eq("12 V / 4 ohm = 3 A", Lab.current(12, 4), 3);
eq("12 V / 12 ohm = 1 A", Lab.current(12, 12), 1);
eq("9 V / 3 ohm = 3 A", Lab.current(9, 3), 3);
eq("3.3 V / 330 ohm = 10 mA", Lab.current(3.3, 330), 0.01);
eq("24 V / 1200 ohm = 20 mA", Lab.current(24, 1200), 0.02);
eq("5 V / 4700 ohm", Math.round(Lab.current(5, 4700) * 1e6) / 1e6, 0.001064);
eq("P = V x I", Lab.power(12, 2), 24);
eq("12 V / 0 ohm is a short", Lab.current(12, 0), Infinity);
eq("series 6 + 6", Lab.series(6, 6), 12);
eq("series 1k + 2k", Lab.series(1000, 2000), 3000);
eq("parallel 12 || 12", Lab.parallel(12, 12), 6);
eq("parallel 60 || 30", Lab.parallel(60, 30), 20);

/* -------------------------------------------------------------- 2. solving */
const solved = Lab.solve(12, 6);
eq("solve: current", solved.i, 2);
eq("solve: power", solved.p, 24);
eq("solve: current text", solved.iText, "2 A");
eq("solve: power text", solved.pText, "24 W");
eq("sub-amp currents are written in mA", Lab.solve(3.3, 330).iText, "10 mA");
eq("sub-watt power is written in mW", Lab.solve(5, 250).pText, "100 mW");
check("a short circuit is flagged", Lab.solve(12, 0).shorted === true);

/* -------------------------------------------------- 3. the required example */
const required = Lab.diagnose({ ask: "current", volts: 12, ohms: 4, answer: 48 });
check("12 V across 4 ohm answered 48 A is wrong", required.correct === false, JSON.stringify(required));
eq("...and names the multiplication", required.kind, "multiplied");
check("...and the message says so in words", /multiplied/i.test(required.message), required.message);
check("...and gives the right working", /12 \/ 4 = 3 A/.test(required.message), required.message);
eq("...and reports the true value", required.truth, 3);

/* ------------------------------------------ 4. every documented mistake kind */
const cases = [
  ["multiplied", { ask: "current", volts: 12, ohms: 6, answer: 72 }, false],
  ["inverted", { ask: "current", volts: 12, ohms: 6, answer: 0.5 }, false],
  ["milliamps", { ask: "current", volts: 12, ohms: 6, answer: 2000 }, false],
  ["kiloamps", { ask: "current", volts: 12, ohms: 6, answer: 0.002 }, false],
  ["used-power", { ask: "current", volts: 12, ohms: 6, answer: 24 }, false],
  ["ohm-resistance", { ask: "current", volts: 12, ohms: 6, answer: 6 }, false],
  ["factor", { ask: "current", volts: 12, ohms: 6, answer: 20 }, false],
  ["generic", { ask: "current", volts: 12, ohms: 6, answer: 1.7 }, false],
  // Both correct cases grade to kind "correct" - the id in the first column is
  // what the rule table returned, not a label for the row.
  ["correct", { ask: "current", volts: 12, ohms: 6, answer: 2 }, true],
  ["correct", { ask: "current", volts: 3.3, ohms: 330, answer: 0.01 }, true],
];
for (const [kind, input, expectCorrect] of cases) {
  const result = Lab.diagnose(input);
  const label = `${kind} (${input.volts} V / ${input.ohms} ohm -> ${input.answer})`;
  check(`${label}: correct flag`, result.correct === expectCorrect, JSON.stringify(result));
  eq(`${label}: kind`, result.kind, kind);
  check(`${label}: message is a real sentence`, result.message.length > 25, result.message);
}
check("a correct answer quotes the working", /I = V \/ R/.test(
  Lab.diagnose({ ask: "current", volts: 12, ohms: 6, answer: 2 }).message));
check("a rounded correct answer still passes", Lab.diagnose(
  { ask: "current", volts: 12, ohms: 7, answer: 1.714 }).correct === true);

/* --------------------------------------------------- 5. other quantities */
const volts = Lab.diagnose({ ask: "voltage", volts: 0, ohms: 220, amps: 0.25, answer: 55 });
check("voltage: 250 mA x 220 ohm = 55 V", volts.correct === true, JSON.stringify(volts));
eq("voltage: dividing is caught", Lab.diagnose(
  { ask: "voltage", volts: 0, ohms: 220, amps: 0.25, answer: 0.25 / 220 }).kind, "divided");
const ohms = Lab.diagnose({ ask: "resistance", volts: 12, ohms: 0, amps: 0.04, answer: 300 });
check("resistance: 12 V / 40 mA = 300 ohm", ohms.correct === true, JSON.stringify(ohms));
eq("resistance: multiplying is caught", Lab.diagnose(
  { ask: "resistance", volts: 12, ohms: 0, amps: 0.04, answer: 0.48 }).kind, "multiplied");
const watts = Lab.diagnose({ ask: "power", volts: 12, ohms: 6, answer: 24 });
check("power: 12 V across 6 ohm = 24 W", watts.correct === true, JSON.stringify(watts));
eq("power: reporting the current is caught", Lab.diagnose(
  { ask: "power", volts: 12, ohms: 6, answer: 2 }).kind, "used-current");

/* ------------------------------------------------------- 6. the bank itself */
const bank = Lab.BANK;
check("the bank has at least 12 questions", bank.length >= 12, String(bank.length));
check("every id is unique", new Set(bank.map((q) => q.id)).size === bank.length);
for (const q of bank) {
  check(`${q.id}: has a prompt`, Boolean(q.prompt && q.prompt.length > 20), q.id);
  check(`${q.id}: has an explanation`, Boolean(q.why && q.why.length > 20), q.id);
  check(`${q.id}: valid tag`, Boolean(Lab.TAG_LABEL[q.tag]), q.tag);
  check(`${q.id}: valid difficulty`, Lab.LEVELS.includes(q.difficulty), q.difficulty);
  const key = Lab.answerFor(q);
  check(`${q.id}: answer is finite`, Number.isFinite(key.truth), `${q.id} -> ${key.truth}`);
  check(`${q.id}: grading the key answer is correct`,
    Lab.diagnose({ ask: q.ask, volts: q.volts, ohms: Lab.totalOhms(q), amps: q.amps, answer: key.truth }).correct === true,
    q.id);
}
const byLevel = Lab.LEVELS.map((level) => bank.filter((q) => q.difficulty === level).length);
check("every difficulty level has questions", byLevel.every((n) => n >= 3), JSON.stringify(byLevel));
const byTag = Object.keys(Lab.TAG_LABEL).map((tag) => bank.filter((q) => q.tag === tag).length);
check("every tag has questions", byTag.every((n) => n >= 2), JSON.stringify(byTag));

/* ----------------------------------------------------- 7. the three fixed
   prediction challenges agree with the simulator */
eq("three prediction challenges", Lab.CHALLENGES.length, 3);
for (const c of Lab.CHALLENGES) {
  const key = Lab.diagnose({ ask: c.ask, volts: c.volts, ohms: c.ohms, answer: NaN });
  check(`challenge ${c.id}: finite answer`, Number.isFinite(key.truth), key.truthText);
  check(`challenge ${c.id}: grading the key is correct`,
    Lab.diagnose({ ask: c.ask, volts: c.volts, ohms: c.ohms, answer: key.truth }).correct === true);
}
eq("challenge 1 is 12 V / 6 ohm", Lab.CHALLENGES[0].volts / Lab.CHALLENGES[0].ohms, 2);
eq("challenge 2 is 12 V / 4 ohm", Lab.CHALLENGES[1].volts / Lab.CHALLENGES[1].ohms, 3);
eq("challenge 3 is 24 V / 1.2 kohm", Lab.CHALLENGES[2].volts / Lab.CHALLENGES[2].ohms, 0.02);

/* ------------------------------------------------- 8. adaptive sequencing */
// A correct answer must move the learner up a level.
eq("easy -> medium on a correct answer", Lab.stepLevel("easy", 1), "medium");
eq("medium -> hard", Lab.stepLevel("medium", 1), "hard");
eq("hard stays hard", Lab.stepLevel("hard", 1), "hard");
eq("easy stays easy", Lab.stepLevel("easy", -1), "easy");
eq("hard -> medium on a wrong answer", Lab.stepLevel("hard", -1), "medium");

// A correct answer at easy must serve a harder question next.
let answered = {};
let pick = Lab.pickNext({ level: "easy", focus: null, answered });
check("first pick is easy", pick.difficulty === "easy", pick.difficulty);
answered[pick.id] = { correct: true };
let harder = Lab.pickNext({ level: "medium", focus: null, answered });
check("after a correct answer the next question is medium", harder.difficulty === "medium", harder.difficulty);

// A wrong answer must serve an easier question on the SAME tag.
answered = {};
const hard = bank.filter((q) => q.difficulty === "hard" && q.tag === "formula")[0];
answered[hard.id] = { correct: false };
const easier = Lab.pickNext({ level: "medium", focus: "formula", answered });
check("after a wrong answer the next question is easier",
  Lab.LEVELS.indexOf(easier.difficulty) < Lab.LEVELS.indexOf(hard.difficulty), easier.difficulty);
eq("...and stays on the same concept", easier.tag, "formula");

// Exhausting the bank must end the session, not throw.
answered = {};
for (const q of bank) answered[q.id] = { correct: true };
check("an exhausted bank returns null", Lab.pickNext({ level: "hard", focus: null, answered }) === null);
// ...but an unanswered question must never be skipped while others remain.
for (let i = 0; i < bank.length - 1; i += 1) delete answered[bank[i].id];
check("the last unanswered question is still offered",
  Lab.pickNext({ level: "hard", focus: "units", answered }) !== null);

/* ----------------------------------------------------- 9. recommendations */
eq("no mistakes, no recommendation", Lab.recommend({}), null);
eq("no attempts, no recommendation", Lab.recommend({ formula: { seen: 2, wrong: 0 } }), null);
const rec = Lab.recommend({ formula: { seen: 3, wrong: 1 }, units: { seen: 4, wrong: 3 } });
eq("the weakest concept wins", rec.tag, "units");
eq("the weakest concept is named for the learner", rec.label, "Units and prefixes");
check("the recommendation tells the learner what to do", /try|revise|practise/i.test(rec.message), rec.message);
check("the recommendation quotes the real counts", /3 of 4/.test(rec.message), rec.message);
eq("units advice mentions conversion", /mA/.test(Lab.recommend({ units: { seen: 1, wrong: 1 } }).message), true);

/* ------------------------------------------------------------- 10. storage */
const blank = Lab.load();
eq("a blank store has no attempts", blank.attempts, 0);
eq("a blank store starts at easy", blank.level, "easy");
blank.attempts = 5; blank.correct = 4; blank.tags.units = { seen: 2, wrong: 1 };
check("saving works", Lab.save(blank) === true);
const reread = Lab.load();
eq("attempts survive a save/load round trip", reread.attempts, 5);
eq("correct survives a save/load round trip", reread.correct, 4);
eq("tag mistakes survive a save/load round trip", reread.tags.units.wrong, 1);
eq("accuracy is a whole percent", Lab.accuracy(reread), 80);
eq("accuracy is null with nothing attempted", Lab.accuracy(blank.attempts && { attempts: 0 }), null);
// Corrupt or hostile data must degrade to a blank state, not throw.
sandbox.localStorage.setItem("engineverse.lab.v1", "{not json");
eq("corrupt storage degrades quietly", Lab.load().attempts, 0);
sandbox.localStorage.setItem("engineverse.lab.v1", JSON.stringify({ attempts: "many", level: "impossible", tags: 7 }));
const hostile = Lab.load();
eq("hostile numbers are coerced", hostile.attempts, 0);
eq("hostile levels fall back to easy", hostile.level, "easy");
check("hostile tags are replaced", typeof hostile.tags === "object" && hostile.tags !== null);
Lab.clear();
eq("clearing empties the store", Lab.load().attempts, 0);

/* --------------------------------------------------------------- 11. input */
eq("parseNumber: plain", Lab.parseNumber("2"), 2);
eq("parseNumber: decimal", Lab.parseNumber("0.02"), 0.02);
eq("parseNumber: with a unit", Lab.parseNumber("3 A"), 3);
eq("parseNumber: with a space", Lab.parseNumber("  20 mA "), 20);
eq("parseNumber: negative", Lab.parseNumber("-1.5"), -1.5);
check("parseNumber: junk is NaN", Number.isNaN(Lab.parseNumber("abc")));
check("parseNumber: empty is NaN", Number.isNaN(Lab.parseNumber("")));
check("parseNumber: null is NaN", Number.isNaN(Lab.parseNumber(null)));

/* ---------------------------------------------------------- 12. the diagram */
const svg = Lab.circuitSVG(Lab.solve(12, 6), { showPower: true });
check("the diagram is an svg", svg.startsWith("<svg") && svg.endsWith("</svg>"));
check("the diagram labels the supply", svg.includes("12 V"));
check("the diagram labels the resistor", svg.includes("6 \u03a9"));
check("the diagram labels the current", svg.includes("I = 2 A"));
check("the diagram labels the power", svg.includes("P = 24 W"));
check("the diagram has an accessible name", /role="img"[^>]*aria-label=/.test(svg));
check("a covered current is drawn as a question mark",
  Lab.circuitSVG(Object.assign(Lab.solve(12, 6), { iText: "?" })).includes("I = ?"));
const twoResistors = Lab.circuitSVG(Lab.solve(9, 3000), {
  resistors: [1000, 2000], arrangement: "series",
});
check("a series circuit draws both resistors",
  twoResistors.includes("1000 \u03a9") && twoResistors.includes("2000 \u03a9"));
check("a series circuit says so in its accessible name", /in series with/.test(twoResistors));
const parallelSvg = Lab.circuitSVG(Lab.solve(24, 20), {
  resistors: [60, 30], arrangement: "parallel",
});
check("a parallel circuit says so in its accessible name", /in parallel with/.test(parallelSvg));

/* ----------------------------------------------------------------- report */
if (failures.length) {
  console.error(`\n${failures.length} lab check(s) failed:`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`lab.js: ${passes} checks passed`);
