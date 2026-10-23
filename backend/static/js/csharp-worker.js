/* Meridian C# browser worker (static GitHub Pages copy).
 *
 * Runs the real Roslyn compiler on the .NET WebAssembly runtime, from the
 * same @live-codes/blazor-wasm bundle the hosted judge executes under
 * Node (backend/engineverse/judge/csharp_wasm_runner.mjs +
 * scripts/setup_toolchains.py). The bundle expects a DOM; a worker has
 * none, so - exactly like the Node runner - this file installs the minimal
 * fake DOM the bundle's boot actually touches, loads blazor-wasm.js, and
 * drives BlazorRunner.create({ baseUrl }).run(source, stdin). Compiler
 * diagnostics, program stdout and stdin (Console.ReadLine) are all the
 * runtime's own. Any boot failure is reported as sandbox_unavailable so
 * the page says NOT RUN rather than inventing a result.
 *
 * This is a module worker only so the bundle's ES-module runtime files
 * (dotnet.js) can be loaded with a real dynamic import; everything else
 * here is plain worker code. `self.__EV_IMPORT__` is a test seam used by
 * scripts/check_browser_runtimes.js to load modules from disk under
 * Node; browsers always take the native dynamic-import path.
 */

const EV_MAX_OUTPUT = 65536;
const EV_NOISE = /Not a valid logical element|Unhandled exception rendering component|MONO_WASM:|ExperimentalWarning|trace-warnings|MODULE_TYPELESS/;

const evRealError = console.error ? console.error.bind(console) : () => {};
for (const level of ["log", "info", "warn", "debug", "trace"]) {
  if (typeof console[level] === "function") console[level] = () => {};
}
console.error = (...args) => {
  const text = args.map((a) => String((a && a.message) || a)).join(" ");
  if (!EV_NOISE.test(text)) evRealError(...args);
};

const evCap = (text) => {
  const s = String(text == null ? "" : text);
  return s.length > EV_MAX_OUTPUT ? s.slice(0, EV_MAX_OUTPUT) : s;
};
const evImport = (url) =>
  typeof self.__EV_IMPORT__ === "function" ? self.__EV_IMPORT__(url) : import(url);

/* ------------------------------------------------------------ fake DOM -- */
function evMakeDom(baseUrl) {
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
  doc.createTextNode = (data) => { const t = El("#text", 3); t.textContent = data; return t; };
  doc.createDocumentFragment = () => El("#fragment", 11);
  doc.addEventListener = () => {};
  doc.removeEventListener = () => {};
  doc.currentScript = null;
  doc.baseURI = baseUrl;
  doc.importNode = (n) => n;
  doc.elementFromPoint = () => null;
  doc.getSelection = () => ({ removeAllRanges() {}, addRange() {}, getRangeAt: () => ({}) });
  return { doc, head, El };
}

let evGlobalsInstalled = false;

function evInstallGlobals(baseUrl) {
  if (evGlobalsInstalled) return;
  evGlobalsInstalled = true;
  const { doc, head, El } = evMakeDom(baseUrl);
  const base = new URL(baseUrl);
  const listeners = new Map();
  const eventTarget = {
    addEventListener: (t, fn) => { if (!listeners.has(t)) listeners.set(t, new Set()); listeners.get(t).add(fn); },
    removeEventListener: (t, fn) => { listeners.get(t)?.delete(fn); },
    dispatchEvent: (ev) => { for (const fn of listeners.get(ev?.type) || []) fn(ev); return true; },
  };
  const define = (key, value) => {
    try {
      Object.defineProperty(self, key, { configurable: true, writable: true, enumerable: true, value });
    } catch (_) {
      /* leave the host binding in place if it cannot be replaced */
    }
  };
  define("window", self);
  define("document", doc);
  define("location", {
    href: baseUrl, origin: base.origin, pathname: base.pathname, search: "", hash: "",
    protocol: base.protocol, assign() {}, replace() {}, reload() {},
  });
  define("history", { state: null, length: 1, pushState() {}, replaceState() {}, back() {}, forward() {}, go() {}, scrollRestoration: "auto" });
  define("Node", Object.assign(class Node {}, {
    ELEMENT_NODE: 1, ATTRIBUTE_NODE: 2, TEXT_NODE: 3, CDATA_SECTION_NODE: 4,
    COMMENT_NODE: 8, DOCUMENT_NODE: 9, DOCUMENT_TYPE_NODE: 10, DOCUMENT_FRAGMENT_NODE: 11,
  }));
  define("Element", El);
  define("HTMLElement", El);
  define("HTMLInputElement", class extends El {});
  define("HTMLDivElement", class extends El {});
  define("SVGElement", class extends El {});
  define("Comment", class extends El { constructor(data) { super("#comment", 8); this.textContent = data == null ? "" : String(data); } });
  define("Text", class extends El { constructor(data) { super("#text", 3); tFix(this, data); } });
  define("DocumentFragment", class extends El { constructor() { super("#fragment", 11); } });
  define("DOMParser", class { parseFromString() { return doc; } });
  define("MutationObserver", class { observe() {} disconnect() {} takeRecords() { return []; } });
  define("ResizeObserver", class { observe() {} disconnect() {} });
  define("getComputedStyle", () => new Proxy({}, { get: () => "" }));
  define("requestAnimationFrame", (cb) => setTimeout(() => cb(Date.now()), 1));
  define("cancelAnimationFrame", clearTimeout);
  define("requestIdleCallback", (cb) => setTimeout(() => cb({ didTimeout: false, timeRemaining: () => 5 }), 1));
  define("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  define("addEventListener", eventTarget.addEventListener);
  define("removeEventListener", eventTarget.removeEventListener);
  define("dispatchEvent", eventTarget.dispatchEvent);

  function tFix(node, data) {
    node.textContent = data == null ? "" : String(data);
  }

  const originalAppend = head.appendChild.bind(head);
  head.appendChild = (child) => {
    originalAppend(child);
    if (child && child.tagName === "SCRIPT" && child.src) {
      const url = new URL(child.src, baseUrl).href;
      setTimeout(async () => {
        const saved = doc.currentScript;
        doc.currentScript = child;
        try {
          try {
            await evImport(url);
          } catch (_) {
            const text = await (await fetch(url)).text();
            (0, eval)(text);
          }
          doc.currentScript = saved;
          if (child.onload) child.onload({});
        } catch (err) {
          doc.currentScript = saved;
          if (child.onerror) child.onerror(err);
        }
      }, 0);
    }
    return child;
  };
  return { doc, head };
}

/* ----------------------------------------------------------------- boot -- */
let evRunnerPromise = null;

async function evBoot(baseUrl) {
  if (!evRunnerPromise) {
    evRunnerPromise = (async () => {
      self.postMessage({ type: "progress", lang: "csharp", message: "Loading Roslyn & .NET WebAssembly runtime…" });
      evInstallGlobals(baseUrl);
      const bundleUrl = new URL("blazor-wasm.js", baseUrl).href;
      const res = await fetch(bundleUrl);
      if (!res.ok) throw new Error(`blazor-wasm.js: HTTP ${res.status}`);
      const text = await res.text();
      const moduleShim = { exports: {} };
      const load = new Function(
        "module", "exports", "self", "window",
        `${text}\n;if (typeof BlazorRunner !== "undefined") module.exports = module.exports || {}; if (typeof BlazorRunner !== "undefined" && !module.exports.BlazorRunner) module.exports.BlazorRunner = BlazorRunner;`
      );
      load.call(moduleShim.exports, moduleShim, moduleShim.exports, self, self);
      const factory = self.BlazorRunner || moduleShim.exports.BlazorRunner;
      if (!factory || typeof factory.create !== "function") {
        throw new Error("the C# bundle did not expose BlazorRunner");
      }
      const runner = factory.create({ baseUrl });
      if (runner && typeof runner.ready === "function") await runner.ready();
      return runner;
    })().catch((err) => {
      evRunnerPromise = null;
      throw err;
    });
  }
  return evRunnerPromise;
}

/* ----------------------------------------------------------------- main -- */
self.onmessage = async (ev) => {
  const msg = ev.data || {};
  if (msg.type === "init") {
    try {
      await evBoot(msg.baseUrl);
      self.postMessage({ type: "ready" });
    } catch (err) {
      self.postMessage({ type: "init-error", error: String((err && err.message) || err) });
    }
    return;
  }
  if (msg.type !== "run") return;
  const started = Date.now();
  const done = (result) =>
    self.postMessage({ type: "result", id: msg.id, runtimeMs: Math.max(1, Date.now() - started), ...result });
  try {
    const runner = await evBoot(msg.baseUrl);
    const result = await runner.run(String(msg.code || ""), String(msg.stdin || ""));
    if (result && result.success) {
      done({ status: "accepted", stdout: evCap(result.output), stderr: "", compileOutput: "", exitCode: 0 });
      return;
    }
    const errors = (result && result.errors) || [];
    if (errors.length) {
      const text = errors
        .map((e) => `${e.severity || "error"} ${e.id || ""}${e.line ? ` (${e.line}:${e.column})` : ""}: ${e.message}`)
        .join("\n");
      done({ status: "compile_error", stdout: "", stderr: evCap(text), compileOutput: evCap(text), exitCode: null });
      return;
    }
    done({
      status: "runtime_error",
      stdout: "",
      stderr: evCap((result && result.output) || "The C# runtime reported a failure without diagnostics."),
      compileOutput: "",
      exitCode: 1,
    });
  } catch (err) {
    done({
      status: "sandbox_unavailable",
      stdout: "",
      stderr: evCap(`The C# browser runtime could not run: ${String((err && err.message) || err)}`),
      compileOutput: "",
      exitCode: null,
    });
  }
};
