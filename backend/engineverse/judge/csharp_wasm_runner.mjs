#!/usr/bin/env node
// EngineVerse C# runner — compiles and executes modern C# (top-level statements,
// string interpolation, generics, async...) with real Roslyn, entirely offline,
// via the @live-codes/blazor-wasm WebAssembly bundle.
//
// Usage: node csharp_wasm_runner.mjs <program.cs>   (source of program on argv[2],
//        stdin piped in; program stdout -> stdout; diagnostics -> stderr)
// Exit:  0 = compiled and ran (program output printed), 1 = compile/runner error.
//
// The bundle lives next to this script (installed by scripts/setup_toolchains.py):
//   <bundle>/blazor-wasm.js, _framework/, refs.zip, razor.zip, node_modules/
// with a small compatibility patch applied to _framework/dotnet.js (see
// install_csharp_wasm in scripts/setup_toolchains.py).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.ENGINEVERSE_CSHARP_WASM || HERE;
const SERVE_PREFIXES = [BASE];

// ---- keep stdout clean: everything except the program output goes to stderr ----
// The bundle logs boot progress and Blazor render diagnostics to the console.
// Keep genuine boot failures visible (Blazor exits through console.error on
// them) but drop the known noise so a clean run reports a clean stderr.
const NOISE = /Not a valid logical element|Unhandled exception rendering component|MONO_WASM:|ExperimentalWarning|trace-warnings|MODULE_TYPELESS|Reparsing as ES module|add "type": "module"/;
for (const level of ["log", "info", "warn", "debug", "trace"]) console[level] = () => {};
const realError = console.error.bind(console);
console.error = (...args) => {
  const text = args.map((a) => String((a && a.message) || a)).join(" ");
  if (!NOISE.test(text)) realError(...args);
};
process.on("uncaughtException", (e) => {
  const text = String((e && e.message) || e);
  if (!NOISE.test(text)) process.stderr.write(text + "\n");
});

function fail(msg) {
  process.stderr.write(String(msg) + "\n");
  process.exit(1);
}

const programPath = process.argv[2];
if (!programPath) fail("usage: csharp_wasm_runner.mjs <program.cs>");
const source = fs.readFileSync(programPath, "utf8");
let stdinText = "";
try { stdinText = fs.readFileSync(0, "utf8"); } catch { /* no stdin */ }

// ---- DOM environment -------------------------------------------------------
const doc = El("#document", 9);
function El(tag, type = 1) {
  return {
    nodeType: type,
    nodeName: String(tag).toUpperCase(),
    tagName: String(tag).toUpperCase(),
    childNodes: [],
    get children() { return this.childNodes; },
    attributes: [],
    style: { setProperty() {}, getPropertyValue() { return ""; }, removeProperty() {} },
    dataset: {},
    hasChildNodes() { return this.childNodes.length > 0; },
    appendChild(c) { if (c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.childNodes.push(c); } return c; },
    removeChild(c) { const i = this.childNodes.indexOf(c); if (i >= 0) this.childNodes.splice(i, 1); c.parentNode = null; return c; },
    insertBefore(c, ref) { if (!ref) return this.appendChild(c); const i = this.childNodes.indexOf(ref); c.parentNode = this; this.childNodes.splice(i < 0 ? this.childNodes.length : i, 0, c); return c; },
    setAttribute(k, v) { const a = this.attributes.find((x) => x.name === k); if (a) a.value = String(v); else this.attributes.push({ name: k, value: String(v) }); if (k === "id") this.id = String(v); },
    getAttribute(k) { const a = this.attributes.find((x) => x.name === k); return a ? a.value : null; },
    hasAttribute(k) { return this.attributes.some((x) => x.name === k); },
    removeAttribute(k) { this.attributes = this.attributes.filter((x) => x.name !== k); },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
    focus() {}, blur() {}, click() {}, scrollIntoView() {}, setSelectionRange() {},
    getRootNode() { return doc; },
    cloneNode(deep) { const c = El(this.tagName, this.nodeType); c.textContent = this.textContent; if (deep) for (const ch of this.childNodes) c.appendChild(ch.cloneNode(true)); return c; },
    get isConnected() { return true; },
    get ownerDocument() { return doc; },
    get nextSibling() { const p = this.parentNode; if (!p) return null; const i = p.childNodes.indexOf(this); return p.childNodes[i + 1] || null; },
    get previousSibling() { const p = this.parentNode; if (!p) return null; const i = p.childNodes.indexOf(this); return i > 0 ? p.childNodes[i - 1] : null; },
    get parentElement() { return this.parentNode; },
    matches() { return false; }, closest() { return null; }, normalize() {},
    insertAdjacentHTML() {}, getElementsByClassName() { return []; }, get elements() { return []; },
    querySelector(sel) { return findIn(this, selPred(sel)); },
    querySelectorAll(sel) { const h = this.querySelector(sel); return h ? [h] : []; },
    get value() { return this._value || ""; }, set value(v) { this._value = v; },
    get checked() { return !!this._checked; }, set checked(v) { this._checked = v; },
    remove() { this.parentNode && this.parentNode.removeChild(this); },
    get textContent() { return this._text || ""; }, set textContent(v) { this._text = v == null ? "" : String(v); this.childNodes.length = 0; },
    get innerHTML() { return this._text || ""; }, set innerHTML(v) { this._text = String(v); },
    get innerText() { return this._text || ""; }, set innerText(v) { this._text = String(v); },
  };
}
function selPred(sel) {
  if (!sel) return () => false;
  if (sel.startsWith("#")) return (n) => n.id === sel.slice(1);
  if (sel.startsWith(".")) return (n) => (n.className || "").split(/\s+/).includes(sel.slice(1));
  return (n) => n.tagName === String(sel).toUpperCase();
}
function findIn(node, pred) {
  if (!node) return null;
  if (pred(node)) return node;
  for (const c of node.childNodes || []) { const hit = findIn(c, pred); if (hit) return hit; }
  return null;
}
const head = El("head");
const body = El("body");
const html = El("html");
doc.appendChild(html);
html.appendChild(head);
html.appendChild(body);
doc.body = body; doc.head = head; doc.documentElement = html;
doc.getElementById = (id) => findIn(doc, (n) => n.id === id);
doc.querySelector = (sel) => findIn(doc, selPred(sel));
doc.querySelectorAll = (sel) => { const h = doc.querySelector(sel); return h ? [h] : []; };
doc.createElement = (tag) => El(tag);
doc.createElementNS = (_ns, tag) => El(tag);
doc.createComment = (data) => { const c = El("#comment", 8); c.textContent = data; return c; };
doc.createText = (data) => { const t = El("#text", 3); t.textContent = data; return t; };
doc.createTextNode = doc.createText;
doc.createDocumentFragment = () => El("#fragment", 11);
doc.addEventListener = () => {};
doc.removeEventListener = () => {};
doc.currentScript = null;
doc.baseURI = pathToFileURL(BASE + "/").href;
doc.importNode = (n) => n;
doc.elementFromPoint = () => null;
doc.getSelection = () => ({ removeAllRanges() {}, addRange() {}, getRangeAt: () => ({}) });

function makeEventTarget() {
  const listeners = new Map();
  return {
    addEventListener: (t, fn) => { if (!listeners.has(t)) listeners.set(t, new Set()); listeners.get(t).add(fn); },
    removeEventListener: (t, fn) => { listeners.get(t)?.delete(fn); },
    dispatchEvent: (ev) => { for (const fn of listeners.get(ev?.type) || []) fn(ev); return true; },
  };
}

const fileFetch = async (input, init) => {
  const url = String(typeof input === "string" ? input : (input && (input.url || input.href)) || input);
  const u = url.split("?")[0];
  let file = null;
  if (u.startsWith("file://")) file = fileURLToPath(u);
  else for (const p of SERVE_PREFIXES) if (u.startsWith(p)) file = u.slice(p.length);
  if (file) {
    try {
      const data = fs.readFileSync(file);
      const type = file.endsWith(".wasm") ? "application/wasm"
        : file.endsWith(".js") ? "text/javascript"
        : file.endsWith(".json") ? "application/json"
        : file.endsWith(".zip") ? "application/zip"
        : "application/octet-stream";
      return new Response(data, { status: 200, headers: { "content-type": type, "content-length": String(data.length) } });
    } catch {
      return new Response("not found", { status: 404 });
    }
  }
  return new Response("blocked", { status: 0 });
};

function urlToFile(u0) {
  const u = String(u0).split("?")[0];
  if (u.startsWith("file://")) return fileURLToPath(u);
  for (const p of SERVE_PREFIXES) if (u.startsWith(p)) return u.slice(p.length);
  return null;
}
class XHR {
  constructor() { this.readyState = 0; this.status = 0; this.response = null; this.responseText = ""; this.responseType = ""; this.withCredentials = false; this.timeout = 0; this.upload = { addEventListener() {} }; this._headers = {}; }
  open(method, url) { this._method = method; this._url = String(url); this.readyState = 1; }
  setRequestHeader(k, v) { this._headers[k] = v; }
  getAllResponseHeaders() { return "content-type: application/octet-stream\r\n"; }
  getResponseHeader(k) { return k.toLowerCase() === "content-type" ? "application/octet-stream" : null; }
  addEventListener(type, fn) { this["on" + type] = fn; }
  removeEventListener() {}
  abort() {}
  send() {
    setImmediate(async () => {
      try {
        const file = urlToFile(this._url);
        const data = fs.readFileSync(file);
        this.status = 200; this.readyState = 4;
        if (this.responseType === "arraybuffer") this.response = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
        else { this.response = data.toString("utf8"); this.responseText = this.response; }
        this.onload && this.onload({ target: this }); this.onreadystatechange && this.onreadystatechange();
      } catch (e) {
        this.status = 0; this.readyState = 4; this.onerror && this.onerror(e); this.onreadystatechange && this.onreadystatechange();
      }
    });
  }
}

const target = globalThis;
const et = makeEventTarget();
function defineGlobal(key, value) {
  try {
    Object.defineProperty(target, key, { configurable: true, writable: true, enumerable: true, value });
  } catch {
    /* leave the host's binding in place if it cannot be replaced */
  }
}
const globals = {
  window: target,
  document: doc,
  location: { href: doc.baseURI, origin: "file://", pathname: "/", search: "", hash: "", protocol: "file:", assign() {}, replace() {}, reload() {} },
  history: { state: null, length: 1, pushState() {}, replaceState() {}, back() {}, forward() {}, go() {}, scrollRestoration: "auto" },
  navigator: { userAgent: "EngineVerse", language: "en-US", languages: ["en-US"], platform: "linux", maxTouchPoints: 0, hardwareConcurrency: 2 },
  Node: Object.assign(class Node {}, {
    ELEMENT_NODE: 1, ATTRIBUTE_NODE: 2, TEXT_NODE: 3, CDATA_SECTION_NODE: 4,
    COMMENT_NODE: 8, DOCUMENT_NODE: 9, DOCUMENT_TYPE_NODE: 10, DOCUMENT_FRAGMENT_NODE: 11,
  }),
  Element: El,
  HTMLElement: El,
  HTMLInputElement: class extends El {},
  HTMLDivElement: class extends El {},
  SVGElement: class extends El {},
  Comment: class extends El { constructor(data) { super("#comment", 8); this.textContent = data == null ? "" : String(data); } },
  Text: class extends El { constructor(data) { super("#text", 3); this.textContent = data == null ? "" : String(data); } },
  DocumentFragment: class extends El { constructor() { super("#fragment", 11); } },
  Event: class { constructor(type, init) { this.type = type; Object.assign(this, init || {}); } },
  CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init || {}); } },
  DOMParser: class { parseFromString() { return doc; } },
  MutationObserver: class { observe() {} disconnect() {} takeRecords() { return []; } },
  ResizeObserver: class { observe() {} disconnect() {} },
  XMLHttpRequest: XHR,
  getComputedStyle: () => new Proxy({}, { get: () => "" }),
  requestAnimationFrame: (cb) => setTimeout(() => cb(Date.now()), 1),
  cancelAnimationFrame: clearTimeout,
  requestIdleCallback: (cb) => setTimeout(() => cb({ didTimeout: false, timeRemaining: () => 5 }), 1),
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  fetch: fileFetch,
  addEventListener: et.addEventListener, removeEventListener: et.removeEventListener, dispatchEvent: et.dispatchEvent,
};
for (const [key, value] of Object.entries(globals)) defineGlobal(key, value);

// ---- load the Blazor loader ------------------------------------------------
let savedScript = null;
const origAppend = head.appendChild.bind(head);
head.appendChild = (child) => {
  origAppend(child);
  if (child && child.tagName === "SCRIPT" && child.src) {
    const file = urlToFile(child.src) || child.src;
    setImmediate(async () => {
      try {
        savedScript = doc.currentScript;
        doc.currentScript = child;
        await import(pathToFileURL(file).href);
        doc.currentScript = savedScript;
        child.onload && child.onload({});
      } catch (e) {
        doc.currentScript = savedScript;
        child.onerror && child.onerror(e);
      }
    });
  }
  return child;
};

const run = async () => {
  await import(pathToFileURL(path.join(BASE, "blazor-wasm.js")).href);
  const runner = globalThis.BlazorRunner.create({ baseUrl: pathToFileURL(BASE + "/").href });
  const result = await runner.run(source, stdinText);
  if (result && result.success) {
    process.stdout.write(result.output || "");
    process.exit(0);
  }
  const errs = (result && result.errors) || [];
  for (const e of errs) {
    process.stderr.write(`${e.severity || "error"} ${e.id || ""}${e.line ? ` (${e.line}:${e.column})` : ""}: ${e.message}\n`);
  }
  if (!result) process.stderr.write("runner returned no result\n");
  else if (!errs.length) process.stderr.write(`compilation failed: ${result.output || "no diagnostics"}\n`);
  process.exit(1);
};

run().catch((e) => fail(e && e.stack ? e.stack : e));
