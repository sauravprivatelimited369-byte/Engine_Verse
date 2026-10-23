#!/usr/bin/env node
/* Verify every vendored in-browser language runtime end-to-end.
 *
 * Serves <siteDir> over HTTP using the exact `Content-Encoding: gzip` wire
 * behaviour of GitHub Pages / Fastly CDN for `.gz` toolchain archives so any
 * double-gunzip, `Content-Length` mismatch, worker boot race, or standard-
 * library regression is caught deterministically before deployment.
 *
 * Covers:
 *   - ev-runtime-worker.js: C (GNU17 + libm), C++ (GNU++20 + bits/stdc++.h),
 *     TypeScript 5.9 (Node fs + ES2023 + strict diagnostics), JavaScript
 *     (Node fs/readline/Buffer/process + browser globals), SQL (SQLite + CTE),
 *     Go 1.24 (GopherJS + full os.Stdin), and Bash (POSIX/Bash + awk/sed/grep)
 *   - runtimes/java/worker-java.js: OpenJDK javac + TeaVM with stdin & classes
 *   - runtimes/rust/worker.iife.js: rustc + Miri stdlib with stdin over gzip
 *   - static/js/csharp-worker.js: Roslyn + .NET Blazor WASM (class & top-level)
 *   - pyodide/ (when present): CPython 3.12 with stdin, stdlib & SyntaxError
 *
 * Usage: node scripts/check_browser_runtimes.js <siteDir> [--only=c,java]
 */
"use strict";

const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { Worker } = require("node:worker_threads");

const siteDir = path.resolve(process.argv[2] || "site");
const onlyArg = (process.argv.find((a) => a.startsWith("--only=")) || "").slice(7);
const only = onlyArg ? new Set(onlyArg.split(",").map((s) => s.trim()).filter(Boolean)) : null;

const MIME = {
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".bin": "application/octet-stream",
  ".gz": "application/octet-stream",
  ".html": "text/html",
  ".zip": "application/zip",
  ".txt": "text/plain",
};

let failures = 0;
let passes = 0;
function check(label, condition, detail) {
  if (condition) {
    passes += 1;
    console.log(`  ok - ${label}`);
  } else {
    failures += 1;
    console.log(`  FAIL - ${label}${detail ? `\n       ${String(detail).slice(0, 400)}` : ""}`);
  }
}

function serve(root) {
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.join(root, urlPath);
    if (!file.startsWith(root)) {
      res.writeHead(403);
      res.end();
      return;
    }
    fs.readFile(file, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      const headers = {
        "Content-Type": MIME[path.extname(file)] || "application/octet-stream",
        "Content-Length": String(data.length),
      };
      // Match live GitHub Pages / Fastly CDN behavior on `.gz` artifacts so
      // `fetch()` transparently gunzips them just like Chromium/WebView does.
      if (file.endsWith(".gz") && data.length >= 2 && data[0] === 0x1f && data[1] === 0x8b) {
        headers["Content-Encoding"] = "gzip";
      }
      res.writeHead(200, headers);
      res.end(data);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

function classicWorker(siteRoot, scriptPath, preludeExtra) {
  const source = fs.readFileSync(scriptPath, "utf8");
  const prelude = `
const { parentPort } = require("node:worker_threads");
const fs = require("node:fs");
const path = require("node:path");
globalThis.self = globalThis;
self.postMessage = (msg) => parentPort.postMessage(msg);
parentPort.on("message", (data) => {
  if (typeof self.onmessage === "function") {
    const p = self.onmessage({ data });
    if (p && p.catch) p.catch((e) => parentPort.postMessage({ type: "harness-error", error: String(e && e.stack || e) }));
  }
});
process.on("uncaughtException", (e) => parentPort.postMessage({ type: "harness-uncaught", error: String(e && e.stack || e) }));
process.on("unhandledRejection", (e) => parentPort.postMessage({ type: "harness-unhandled", error: String(e && e.stack || e) }));
const SITE_ROOT = ${JSON.stringify(siteRoot)};
globalThis.importScripts = (...urls) => {
  for (const u of urls) {
    const file = path.join(SITE_ROOT, new URL(String(u)).pathname);
    (0, eval)(fs.readFileSync(file, "utf8"));
  }
};
try {
  globalThis.process = undefined;
  globalThis.require = undefined;
  globalThis.module = undefined;
  globalThis.exports = undefined;
} catch (e) {}
globalThis.XMLHttpRequest = class {
  constructor() { this.readyState = 0; this.status = 0; this.responseType = ""; this._listeners = {}; }
  addEventListener(name, fn) { (this._listeners[name] ||= []).push(fn); }
  removeEventListener() {}
  open(method, url) { this._method = method; this._url = String(url); this.readyState = 1; }
  overrideMimeType(mime) { this._mime = mime; }
  setRequestHeader() {}
  getResponseHeader() { return null; }
  getAllResponseHeaders() { return ""; }
  _fire(name, arg) {
    const fn = this["on" + name];
    if (typeof fn === "function") fn.call(this, arg || { type: name });
    for (const l of this._listeners[name] || []) l.call(this, arg || { type: name });
  }
  send() {
    (async () => {
      try {
        const res = await fetch(this._url, { method: this._method || "GET" });
        this.status = res.status;
        const buf = await res.arrayBuffer();
        if (this.responseType === "blob") this.response = new Blob([buf], { type: this._mime || "application/octet-stream" });
        else if (this.responseType === "arraybuffer") this.response = buf;
        else if (this.responseType === "json") this.response = JSON.parse(new TextDecoder("utf-8").decode(buf));
        else if (this.responseType === "document") this.response = new TextDecoder("utf-8").decode(buf);
        else { const text = new TextDecoder("utf-8").decode(buf); this.response = text; this.responseText = text; }
        this.readyState = 4;
        this._fire("readystatechange");
        this._fire("load");
        this._fire("loadend");
      } catch (err) {
        this._fire("error", err);
        this._fire("loadend");
      }
    })();
  }
};
${preludeExtra || ""}
`;
  return new Worker(prelude + source, { eval: true });
}

function workerClient(worker) {
  let seq = 0;
  const pending = new Map();
  worker.on("message", (msg) => {
    if (msg && msg.type === "harness-error") console.log("  [worker-error]", String(msg.error).slice(0, 300));
    if (msg && msg.id !== undefined && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
    if (msg && (msg.type === "ready" || msg.type === "initialized") && pending.has("__boot__")) {
      pending.get("__boot__")(msg);
      pending.delete("__boot__");
    }
    if (msg && (msg.type === "init-error" || msg.type === "init_error" || msg.type === "error") && pending.has("__boot__")) {
      pending.get("__boot__")(msg);
      pending.delete("__boot__");
    }
    if (msg && msg.type === "result" && msg.id === undefined && pending.has("__run__")) {
      pending.get("__run__")(msg);
      pending.delete("__run__");
    }
  });
  worker.on("error", (err) => console.log("  [worker crashed]", String((err && err.message) || err).slice(0, 300)));
  const request = (msg, key, timeoutMs) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(key);
        reject(new Error(`timeout after ${timeoutMs}ms waiting for ${key}`));
      }, timeoutMs);
      pending.set(key, (m) => {
        clearTimeout(timer);
        resolve(m);
      });
      worker.postMessage(msg);
    });
  return {
    run: (msg, timeoutMs = 150000) => request({ ...msg, id: ++seq }, seq, timeoutMs),
    boot: (msg, timeoutMs = 240000) => request(msg, "__boot__", timeoutMs),
    raw: (msg, timeoutMs = 150000) => request(msg, "__run__", timeoutMs),
  };
}

const CASE_TIMEOUT = 240000;

async function testAdapterWorker(base, manifest) {
  console.log("[ev-runtime-worker] clang / typescript / javascript / sql / go / bash");
  const worker = classicWorker(siteDir, path.join(siteDir, "static/js/ev-runtime-worker.js"));
  const client = workerClient(worker);
  worker.postMessage({
    type: "assets",
    assets: {
      clang: `${base}runtimes/clang/`,
      typescript: `${base}runtimes/typescript/`,
      sql: `${base}runtimes/sql/`,
      go: `${base}runtimes/go/`,
      bash: `${base}runtimes/bash/`,
      tsLibs: (manifest.runtimes.typescript && manifest.runtimes.typescript.libs) || [],
    },
  });
  const langs = new Set(Object.values(manifest.runtimes).flatMap((r) => r.languages));
  langs.add("javascript");
  const want = (lang) => langs.has(lang) && (!only || only.has(lang));

  if (want("c")) {
    const init = await client.run({ type: "init", lang: "c" }, CASE_TIMEOUT);
    check("c compiler warm-boots over gzip", init.type === "ready", JSON.stringify(init).slice(0, 300));
    const t0 = Date.now();
    const okRun = await client.run({
      type: "run",
      lang: "c",
      stdin: "Asha\n",
      code: '#include <stdio.h>\n#include <math.h>\n#include <stdlib.h>\nint cmp(const void *a, const void *b) { return (*(const int*)a) - (*(const int*)b); }\nint main(void) {\n  char n[64];\n  if (scanf("%63s", n) != 1) return 1;\n  int arr[4] = {9, 1, 16, 4};\n  qsort(arr, 4, sizeof(int), cmp);\n  printf("Hello, %s! root=%.0f first=%d\\n", n, sqrt((double)arr[3]), arr[0]);\n  return 0;\n}\n',
    }, CASE_TIMEOUT);
    const elapsed = Date.now() - t0;
    check(`c compiles GNU17 + math.h + qsort in ${elapsed}ms`, okRun.status === "accepted" && okRun.stdout.includes("Hello, Asha! root=4 first=1"), JSON.stringify(okRun).slice(0, 300));
    const bad = await client.run({ type: "run", lang: "c", stdin: "", code: '#include <stdio.h>\nint main(void) { printf("%d\\n", undefined_fn()); return 0; }' }, CASE_TIMEOUT);
    check("c reports clang diagnostics", bad.status === "compile_error" && /error:/.test(bad.compileOutput || ""), JSON.stringify(bad).slice(0, 300));
  }

  if (want("cpp")) {
    const okRun = await client.run({
      type: "run",
      lang: "cpp",
      stdin: "40 2\n",
      code: '#include <bits/stdc++.h>\nusing namespace std;\nint main() {\n  long long a, b;\n  if (!(cin >> a >> b)) return 1;\n  unordered_map<int, int> seen;\n  seen[42] = 1;\n  vector<int> v = {3, 1, 2};\n  sort(v.begin(), v.end());\n  cout << (a + b) << " " << seen.contains(42) << " ";\n  for (int x : v) cout << x;\n  cout << "\\n";\n}\n',
    }, CASE_TIMEOUT);
    check("cpp compiles C++20 STL + bits/stdc++.h with stdin", okRun.status === "accepted" && okRun.stdout.includes("42 1 123"), JSON.stringify(okRun).slice(0, 300));
    const bad = await client.run({ type: "run", lang: "cpp", stdin: "", code: "int main() { UndefinedType x; }" }, CASE_TIMEOUT);
    check("cpp reports clang diagnostics", bad.status === "compile_error" && /error:/.test(bad.compileOutput || ""), JSON.stringify(bad).slice(0, 300));
  }

  if (want("javascript")) {
    const okRun = await client.run({
      type: "run",
      lang: "javascript",
      stdin: "[2, 7, 11, 15]\n9\n",
      code: 'const fs = require("fs");\nconst [l1, l2] = fs.readFileSync(0, "utf8").trim().split("\\n");\nconst nums = JSON.parse(l1);\nconst target = Number(l2);\nconst seen = new Map();\nfor (let i = 0; i < nums.length; i++) {\n  if (seen.has(target - nums[i])) { console.log(JSON.stringify([seen.get(target - nums[i]), i])); break; }\n  seen.set(nums[i], i);\n}\n',
    }, CASE_TIMEOUT);
    check("javascript supports Node fs.readFileSync(0) + Map", okRun.status === "accepted" && okRun.stdout.trim() === "[0,1]", JSON.stringify(okRun).slice(0, 300));
  }

  if (want("typescript")) {
    const okRun = await client.run({
      type: "run",
      lang: "typescript",
      stdin: "hello_world\n",
      code: 'import * as fs from "fs";\nconst raw: string = fs.readFileSync(0, "utf8").trim().replaceAll("_", "-");\nconst nums: number[] = [10, 20, 30];\nconsole.log(raw, nums.at(-1));\n',
    }, CASE_TIMEOUT);
    check("typescript supports import fs + ES2022/2023 + stdin", okRun.status === "accepted" && okRun.stdout.trim() === "hello-world 30", JSON.stringify(okRun).slice(0, 300));
    const bad = await client.run({ type: "run", lang: "typescript", stdin: "", code: 'const n: number = "not a number";\nconsole.log(n);' }, CASE_TIMEOUT);
    check("typescript reports type errors as compile errors", bad.status === "compile_error" && /not assignable/.test(bad.compileOutput || ""), JSON.stringify(bad).slice(0, 300));
  }

  if (want("sql")) {
    const okRun = await client.run({
      type: "run",
      lang: "sql",
      stdin: "CREATE TABLE students(name TEXT, score INT);\nINSERT INTO students VALUES ('Asha', 88), ('Ravi', 74), ('Meena', 91);",
      code: "WITH top_students AS (SELECT name, score FROM students WHERE score >= 80) SELECT name, score FROM top_students ORDER BY score DESC;",
    }, CASE_TIMEOUT);
    check("sql runs setup + CTE query on real SQLite", okRun.status === "accepted" && okRun.stdout.includes("Meena | 91") && okRun.stdout.includes("Asha | 88"), JSON.stringify(okRun).slice(0, 300));
    const bad = await client.run({ type: "run", lang: "sql", stdin: "", code: "SELECT * FROM missing_table;" }, CASE_TIMEOUT);
    check("sql reports SQLite errors", bad.status === "runtime_error" && /SQL error:/.test(bad.stderr || ""), JSON.stringify(bad).slice(0, 300));
  }

  if (want("go")) {
    const okRun = await client.run({
      type: "run",
      lang: "go",
      stdin: "Asha\n3 1 4 2\n",
      code: 'package main\n\nimport (\n\t"bufio"\n\t"fmt"\n\t"os"\n\t"sort"\n\t"strconv"\n\t"strings"\n)\n\nfunc main() {\n\tsc := bufio.NewScanner(os.Stdin)\n\tsc.Scan()\n\tname := strings.TrimSpace(sc.Text())\n\tsc.Scan()\n\tparts := strings.Fields(sc.Text())\n\tnums := make([]int, len(parts))\n\tfor i, p := range parts { nums[i], _ = strconv.Atoi(p) }\n\tsort.Ints(nums)\n\tfmt.Printf("Hello, %s! %v\\n", name, nums)\n}\n',
    }, CASE_TIMEOUT);
    check("go compiles and reads real multi-line os.Stdin", okRun.status === "accepted" && okRun.stdout.includes("Hello, Asha! [1 2 3 4]"), JSON.stringify(okRun).slice(0, 300));
    const bad = await client.run({ type: "run", lang: "go", stdin: "", code: "package main\n\nfunc main() { undefinedFn() }\n" }, CASE_TIMEOUT);
    check("go reports compiler diagnostics", bad.status === "compile_error" && /undeclared name/.test(bad.compileOutput || ""), JSON.stringify(bad).slice(0, 300));
  }

  if (want("bash")) {
    const okRun = await client.run({
      type: "run",
      lang: "bash",
      stdin: "Asha\n10\n20\n12\n",
      code: '#!/usr/bin/env bash\nset -euo pipefail\nread -r name\nsum=0\nwhile read -r n; do\n  (( sum += n ))\ndone\necho "Hello, ${name}! sum=${sum}" | sed "s/sum=/total=/"\n',
    }, CASE_TIMEOUT);
    check("bash runs loops, arithmetic, stdin and sed pipeline", okRun.status === "accepted" && okRun.stdout.trim() === "Hello, Asha! total=42", JSON.stringify(okRun).slice(0, 300));
  }

  await worker.terminate();
}

async function testJava(base) {
  console.log("[java] javac + TeaVM worker");
  const worker = classicWorker(siteDir, path.join(siteDir, "runtimes/java/worker-java.js"), `
self.location = { href: ${JSON.stringify(`${base}runtimes/java/worker-java.js`)} };
`);
  const client = workerClient(worker);
  const boot = await client.boot({ cmd: "init", baseUrl: `${base}runtimes/java/teavm/`, persistFiles: false }, CASE_TIMEOUT);
  check("java runtime boots", boot.type === "initialized", JSON.stringify(boot).slice(0, 300));
  const runRaw = (msg, timeoutMs) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("java run timeout")), timeoutMs || CASE_TIMEOUT);
      const handler = (m) => {
        if (m.type === "result") {
          clearTimeout(timer);
          worker.off("message", handler);
          resolve(m);
        }
      };
      worker.on("message", handler);
      worker.postMessage(msg);
    });
  const okRun = await runRaw({
    cmd: "run",
    source: 'import java.util.*;\npublic class Main {\n  public static void main(String[] args) throws Exception {\n    Scanner sc = new Scanner(System.in);\n    String name = sc.hasNextLine() ? sc.nextLine() : "world";\n    ArrayList<Integer> v = new ArrayList<>(Arrays.asList(3, 1, 2));\n    Collections.sort(v);\n    System.out.println("Hello, " + name + "! " + v);\n    int s = 0; for (int i = 1; i <= 5; i++) s += i * i;\n    System.out.println("sum=" + s);\n  }\n}',
    input: "Asha\n",
    mainClass: "Main",
  });
  check("java compiles and runs with stdin (javac)", okRun.ok === true && (okRun.stdout || "").includes("Hello, Asha! [1, 2, 3]") && (okRun.stdout || "").includes("sum=55"), JSON.stringify(okRun).slice(0, 300));
  const bad = await runRaw({ cmd: "run", source: "public class Main { public static void main(String[] a) { int x = undefined; } }", input: "", mainClass: "Main" });
  check("java reports javac diagnostics", bad.ok === false && /cannot find symbol/.test(bad.stderr || bad.error || ""), JSON.stringify(bad).slice(0, 300));
  const named = await runRaw({ cmd: "run", source: 'public class Hello { public static void main(String[] a) { System.out.println("named class ok"); } }', input: "", mainClass: "Hello" });
  check("java runs a differently-named public class", named.ok === true && (named.stdout || "").includes("named class ok"), JSON.stringify(named).slice(0, 300));
  await worker.terminate();
}

async function testRust(base) {
  console.log("[rust] rustc/Miri worker (with CDN Content-Encoding: gzip)");
  const worker = classicWorker(siteDir, path.join(siteDir, "runtimes/rust/worker.iife.js"), `
const _evCacheStore = new Map();
self.caches = {
  open: async () => ({
    match: async (url) => _evCacheStore.has(String(url)) ? new Response(_evCacheStore.get(String(url))) : undefined,
    put: async (url, res) => { try { _evCacheStore.set(String(url), await res.clone().arrayBuffer()); } catch (e) {} },
    delete: async () => true,
  }),
  delete: async () => true,
  keys: async () => [],
};
self.location = { href: ${JSON.stringify(`${base}runtimes/rust/worker.iife.js`)} };
`);
  const client = workerClient(worker);
  const boot = await client.boot({ type: "init", toolchain: { baseUrl: `${base}runtimes/rust/toolchain/`, gzipped: true } }, CASE_TIMEOUT);
  check("rust toolchain boots over Content-Encoding: gzip", boot.type === "ready", JSON.stringify(boot).slice(0, 300));
  const runRaw = (msg, timeoutMs) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("rust run timeout")), timeoutMs || CASE_TIMEOUT);
      const handler = (m) => {
        if (m.type === "result" && m.id === msg.id) {
          clearTimeout(timer);
          worker.off("message", handler);
          resolve(m);
        }
      };
      worker.on("message", handler);
      worker.postMessage(msg);
    });
  const okRun = await runRaw({
    type: "run",
    id: 1,
    code: 'use std::collections::HashMap;\nuse std::io::Read;\nfn main() {\n    let mut input = String::new();\n    std::io::stdin().read_to_string(&mut input).unwrap();\n    let name = input.trim();\n    let mut map = HashMap::new();\n    map.insert("score", 55);\n    let mut v = vec![3, 1, 2];\n    v.sort();\n    println!("Hello, {}! {:?} sum={}", name, v, map["score"]);\n}',
    input: "Asha\n",
  });
  check("rust compiles and runs with stdlib + stdin (Miri)", okRun.exitCode === 0 && (okRun.stdout || "").includes("Hello, Asha! [1, 2, 3] sum=55"), JSON.stringify(okRun).slice(0, 300));
  const bad = await runRaw({ type: "run", id: 2, code: 'fn main() { let x: i32 = "oops"; }', input: "" });
  check("rust reports rustc diagnostics", bad.exitCode !== 0 && /error\[E0308\]/.test(bad.stderr || ""), JSON.stringify(bad).slice(0, 300));
  await worker.terminate();
}

async function testCSharp(base) {
  console.log("[csharp] Roslyn/Blazor worker");
  const workerFile = path.join(siteDir, "static/js/csharp-worker.js");
  const tmpFile = path.join(siteDir, "static/js/.csharp-worker.check.mjs");
  const hooksFile = path.join(siteDir, "static/js/.ev-loader-hooks.mjs");
  fs.writeFileSync(hooksFile, `
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
const SITE_ROOT = ${JSON.stringify(siteDir)};
export async function resolve(specifier, context, nextResolve) {
  if (/^https?:\\/\\//.test(specifier)) {
    try {
      const file = path.join(SITE_ROOT, decodeURIComponent(new URL(specifier).pathname));
      if (fs.existsSync(file)) return nextResolve(pathToFileURL(file).href, context);
    } catch (e) {}
  }
  return nextResolve(specifier, context);
}
`);
  const prelude = `
import { parentPort } from "node:worker_threads";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import module from "node:module";
module.register("./.ev-loader-hooks.mjs", import.meta.url);
globalThis.self = globalThis;
self.postMessage = (msg) => parentPort.postMessage(msg);
parentPort.on("message", (data) => {
  if (typeof self.onmessage === "function") {
    const p = self.onmessage({ data });
    if (p && p.catch) p.catch((e) => parentPort.postMessage({ type: "harness-error", error: String(e && e.stack || e) }));
  }
});
process.on("uncaughtException", (e) => parentPort.postMessage({ type: "harness-uncaught", error: String(e && e.stack || e) }));
process.on("unhandledRejection", (e) => parentPort.postMessage({ type: "harness-unhandled", error: String(e && e.stack || e) }));
const SITE_ROOT = ${JSON.stringify(siteDir)};
self.__EV_IMPORT__ = (url) => {
  const file = path.join(SITE_ROOT, new URL(String(url)).pathname);
  return import(pathToFileURL(file).href);
};
import path from "node:path";
globalThis.XMLHttpRequest = class {
  constructor() { this.readyState = 0; this.status = 0; this.response = null; this.responseText = ""; this.responseType = ""; this._headers = {}; }
  open(method, url) { this._method = method; this._url = String(url); this.readyState = 1; }
  setRequestHeader(k, v) { this._headers[k] = v; }
  getAllResponseHeaders() { return "content-type: application/octet-stream\\r\\n"; }
  getResponseHeader(k) { return String(k).toLowerCase() === "content-type" ? "application/octet-stream" : null; }
  addEventListener(type, fn) { this["on" + type] = fn; }
  removeEventListener() {}
  abort() {}
  send() {
    (async () => {
      try {
        const res = await fetch(this._url, { method: this._method || "GET", headers: this._headers });
        this.status = res.status;
        this.readyState = 4;
        if (this.responseType === "arraybuffer") this.response = await res.arrayBuffer();
        else { this.responseText = await res.text(); this.response = this.responseText; }
        if (this.onreadystatechange) this.onreadystatechange();
        if (this.onload) this.onload({ target: this });
      } catch (err) {
        this.status = 0;
        this.readyState = 4;
        if (this.onerror) this.onerror(err);
        if (this.onreadystatechange) this.onreadystatechange();
      }
    })();
  }
};
`;
  fs.writeFileSync(tmpFile, prelude + fs.readFileSync(workerFile, "utf8"));
  let worker;
  try {
    worker = new Worker(tmpFile);
    const client = workerClient(worker);
    const boot = await client.boot({ type: "init", baseUrl: `${base}runtimes/csharp/` }, CASE_TIMEOUT);
    check("csharp runtime boots (Blazor/Roslyn)", boot.type === "ready", JSON.stringify(boot).slice(0, 300));
    const okRun = await client.run({
      type: "run",
      baseUrl: `${base}runtimes/csharp/`,
      stdin: "Asha\n",
      code: 'using System;\nusing System.Linq;\nclass Program {\n  static void Main() {\n    string name = Console.ReadLine() ?? "world";\n    var v = new[]{3,1,2}.OrderBy(x => x);\n    Console.WriteLine($"Hello, {name}! [{string.Join(", ", v)}]");\n    Console.WriteLine($"sum={Enumerable.Range(1,5).Sum(i => i*i)}");\n  }\n}',
    }, CASE_TIMEOUT);
    check("csharp compiles and runs with stdin (Roslyn)", okRun.status === "accepted" && (okRun.stdout || "").includes("Hello, Asha! [1, 2, 3]") && (okRun.stdout || "").includes("sum=55"), JSON.stringify(okRun).slice(0, 300));
    const topLevel = await client.run({
      type: "run",
      baseUrl: `${base}runtimes/csharp/`,
      stdin: "Ravi\n",
      code: 'using System;\n\nstring name = Console.ReadLine()?.Trim() ?? "";\nif (name.Length == 0) name = "engineer";\nConsole.WriteLine($"Hello, {name}!");',
    }, CASE_TIMEOUT);
    check("csharp runs top-level statements", topLevel.status === "accepted" && (topLevel.stdout || "").includes("Hello, Ravi!"), JSON.stringify(topLevel).slice(0, 300));
    const bad = await client.run({ type: "run", baseUrl: `${base}runtimes/csharp/`, stdin: "", code: "class P { static void Main() { int x = undefined; } }" }, CASE_TIMEOUT);
    check("csharp reports Roslyn diagnostics", bad.status === "compile_error" && /CS0103/.test(bad.compileOutput || ""), JSON.stringify(bad).slice(0, 300));
  } finally {
    if (worker) await worker.terminate();
    fs.rmSync(tmpFile, { force: true });
    fs.rmSync(hooksFile, { force: true });
  }
}

async function testPython(base) {
  const pyJs = path.join(siteDir, "pyodide/pyodide.js");
  if (!fs.existsSync(pyJs)) return;
  console.log("[python] CPython 3.12 (Pyodide WebAssembly)");
  const { loadPyodide } = require(pyJs);
  const pyodide = await loadPyodide({ indexURL: path.join(siteDir, "pyodide") + path.sep });
  check("python Pyodide runtime boots", Boolean(pyodide));

  const runPy = async (code, stdin) => {
    const outBytes = [];
    const errBytes = [];
    const bytes = new TextEncoder().encode(String(stdin || ""));
    let pos = 0;
    pyodide.setStdin({ stdin: () => (pos < bytes.length ? bytes[pos++] : null) });
    pyodide.setStdout({ raw: (ch) => { outBytes.push(ch & 255); } });
    pyodide.setStderr({ raw: (ch) => { errBytes.push(ch & 255); } });
    const decode = (arr) => new TextDecoder("utf-8").decode(new Uint8Array(arr));
    try {
      await pyodide.runPythonAsync(String(code));
      await pyodide.runPythonAsync("import sys as _ev_s; _ev_s.stdout.flush(); _ev_s.stderr.flush()");
      return { ok: true, stdout: decode(outBytes), stderr: decode(errBytes) };
    } catch (err) {
      return { ok: false, errorType: String((err && err.type) || ""), error: String(err), stdout: decode(outBytes), stderr: decode(errBytes) };
    }
  };

  const okRun = await runPy(
    'import heapq, collections\nname = input().strip()\nnums = list(map(int, input().split()))\nheapq.heapify(nums)\nprint(f"Hello, {name}! min={nums[0]} cnt={collections.Counter(nums)[1]}", end="")\n',
    "Asha\n3 1 4 1\n"
  );
  check("python runs CPython stdlib + raw streaming stdout", okRun.ok === true && okRun.stdout === "Hello, Asha! min=1 cnt=2", JSON.stringify(okRun).slice(0, 300));
  const synErr = await runPy("def broken(:\n  pass\n", "");
  check("python classifies SyntaxError cleanly", synErr.ok === false && synErr.errorType === "SyntaxError", JSON.stringify(synErr).slice(0, 300));
}

async function main() {
  const manifestPath = path.join(siteDir, "runtimes/manifest.json");
  if (!fs.existsSync(manifestPath)) {
    console.log(`no ${manifestPath} - browser runtimes were not vendored; the site degrades honestly. Skipping.`);
    return 0;
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const langs = new Set(Object.values(manifest.runtimes || {}).flatMap((r) => r.languages));
  console.log(`manifest languages: ${[...langs].sort().join(", ") || "none"}`);
  const { server, port } = await serve(siteDir);
  const base = `http://127.0.0.1:${port}/`;
  try {
    const has = (k) => Boolean(manifest.runtimes[k]) && (!only || only.has(k));
    if (!only || ["c", "cpp", "typescript", "javascript", "sql", "go", "bash"].some((l) => only.has(l))) {
      await testAdapterWorker(base, manifest);
    }
    if (has("java")) await testJava(base);
    if (has("rust")) await testRust(base);
    if (has("csharp")) await testCSharp(base);
    if (!only || only.has("python")) await testPython(base);
  } finally {
    server.close();
  }
  console.log(`browser runtime checks: ${passes} passed, ${failures} failed`);
  return failures ? 1 : 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
