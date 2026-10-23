#!/usr/bin/env node
// EngineVerse Ruby runner — executes Ruby on CRuby 3.3 compiled to WebAssembly
// (@ruby/3.3-wasm-wasi + @ruby/wasm-wasi, installed by scripts/setup_toolchains.py).
//
// Usage: node ruby_wasm_runner.mjs <program.rb>   (stdin piped in; stdio wired)
// Exit:  the Ruby program's exit status, 1 on a Ruby exception.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function fail(msg) {
  process.stderr.write(String(msg) + "\n");
  process.exit(1);
}

const programPath = process.argv[2];
if (!programPath) fail("usage: ruby_wasm_runner.mjs <program.rb>");
const code = fs.readFileSync(programPath, "utf8");

// Locate the vendored ruby.wasm packages (npm -g root, or explicit override).
const nodeModules = process.env.ENGINEVERSE_NODE_MODULES || "/usr/local/lib/node_modules";
const apiEntry = path.join(nodeModules, "@ruby", "wasm-wasi", "dist", "esm", "node.js");
const vmWasm = path.join(nodeModules, "@ruby", "3.3-wasm-wasi", "dist", "ruby+stdlib.wasm");
if (!fs.existsSync(apiEntry)) fail(`ruby wasm API not found at ${apiEntry}`);
if (!fs.existsSync(vmWasm)) fail(`ruby wasm VM not found at ${vmWasm}`);

const { DefaultRubyVM } = await import(pathToFileURLSafe(apiEntry));
const rubyModule = await WebAssembly.compile(fs.readFileSync(vmWasm));
const { vm } = await DefaultRubyVM(rubyModule);

// $stdout/$stderr must be unbuffered: WASI file descriptors are not TTYs, so
// CRuby block-buffers and a program that ends without an explicit flush would
// print nothing. `sync = true` makes output appear as it is written.
const wrapped = `$stdout.sync = true\n$stderr.sync = true\n${code}`;

function pathToFileURLSafe(p) {
  return new URL("file://" + path.resolve(p)).href;
}

try {
  const result = vm.eval(wrapped);
  // `exit(n)` in the program raises SystemExit which the VM surfaces as an
  // error carrying the status; honour it instead of always failing.
  const msg = result && result.toString ? result.toString() : "";
  void msg;
  process.exit(0);
} catch (e) {
  const message = String((e && e.message) || e);
  const match = /exit(?: |\()*(\d+)/.exec(message) || message.match(/SystemExit/);
  if (/SystemExit|exit status|exit\(/.test(message)) {
    const status = match && match[1] ? parseInt(match[1], 10) : 0;
    process.stderr.write(message + "\n");
    process.exit(Number.isFinite(status) ? status : 0);
  }
  process.stderr.write(message + "\n");
  process.exit(1);
}
