/* Optional browser smoke test. Use the toolchain described in check_academy_browser.js.
 * node scripts/check_atlas_notebook.mjs http://127.0.0.1:8000
 */
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const {
  chromium,
} = require("../.toolchain/browser/node_modules/playwright-core");
const binary = require("../.toolchain/browser/node_modules/@sparticuz/chromium");
const browser = await chromium.launch({
  args: binary.args,
  executablePath: await binary.executablePath(),
  headless: true,
});
import assert from "node:assert/strict";
import fs from "node:fs/promises";
try {
  const p = await browser.newPage({
    viewport: { width: 360, height: 780 },
    reducedMotion: "reduce",
  });
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(process.argv[2] || "http://127.0.0.1:8000");
  await p.locator("#prev").click();
  assert.equal(await p.locator("#model").innerText(), "Möbius Band");
  await p.locator("#wire").click();
  await p.locator("#open-notebook").click();
  await p.getByRole("button", { name: "Capture A", exact: true }).click();
  await p.keyboard.press("Escape");
  await p.locator("#parameter").focus();
  await p.keyboard.press("ArrowRight");
  assert.match(await p.locator("#derived").innerText(), /Two sides/);
  await p.locator("#open-notebook").click();
  await p.getByRole("button", { name: "Capture B", exact: true }).click();
  assert.match(
    await p.locator("#difference").innerText(),
    /One side.*Two sides/,
  );
  await p.locator("#observation").fill("The edge count changes.");
  await p.reload();
  await p.locator("#open-notebook").click();
  assert.equal(
    await p.locator("#observation").inputValue(),
    "The edge count changes.",
  );
  assert.equal(await p.locator(".book-slot.filled").count(), 2);
  const [dl] = await Promise.all([
    p.waitForEvent("download"),
    p.locator("#download-plate").click(),
  ]);
  assert.equal(dl.suggestedFilename(), "form-atlas-study.png");
  const buf = await fs.readFile(await dl.path());
  assert.equal(buf.toString("ascii", 1, 4), "PNG");
  assert.ok(buf.length > 10000);
  await p.locator(".restore").first().click();
  assert.equal(await p.locator("#parameter").inputValue(), "1");
  assert.equal(await p.locator("#wire").getAttribute("aria-pressed"), "true");
  assert.equal(await p.locator("#model").innerText(), "Möbius Band");
  assert.equal(
    await p.locator("#pause").getAttribute("aria-label"),
    "Play rotation",
  );
  await p.locator("#open-notebook").click();
  await p.locator(".remove").first().click();
  assert.equal(await p.locator(".book-slot.filled").count(), 1);
  assert.ok(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  );
  assert.deepEqual(errors, []);
  console.log(
    "Mobile notebook capture, comparison, saved observation, reload, restore, clear and PNG export passed.",
  );
} finally {
  await browser.close();
}
