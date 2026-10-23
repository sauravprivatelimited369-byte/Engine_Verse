"use strict";
/* Meridian in-browser language runtimes (static GitHub Pages & Android TWA).
 *
 * One isolated worker driving six genuine language engines, all vendored
 * same-origin by scripts/fetch_browser_runtimes.py and cached offline:
 *
 *   c / cpp     Clang 22 compiled to WebAssembly (@live-codes/clang-wasm).
 *               Compiles real C17 / C++20 (<stdio.h>, <math.h>, <bits/stdc++.h>,
 *               full libc++ STL) to wasm32-wasi and executes with stdin/stdout/stderr.
 *   typescript  The official TypeScript 5.9 compiler (typescript.js) with full
 *               syntactic + semantic type-checking, cached AST libs, ES2023+ &
 *               Node-compatible + browser-convention runtime environment.
 *   javascript  Direct Node-compatible + browser-convention execution inside
 *               this isolated worker (supports require('fs').readFileSync(0),
 *               readline, path, util, assert, crypto, Buffer, process, input, print).
 *   sql         SQLite 3 compiled to WebAssembly (sql.js) with multi-statement
 *               CTEs, window functions, triggers, views, and setup scripts.
 *   go          The GopherJS Go 1.24 compiler (@live-codes/go2js) with a full
 *               virtual POSIX descriptor layer supporting os.Stdin (fmt.Scan,
 *               bufio.Scanner, io.ReadAll), os.Stdout (including fmt.Print
 *               without trailing newline), os.Stderr, /tmp files, and timers.
 *   bash        Real POSIX sh / Bash interpreter (just-bash) with stdin, pipes,
 *               functions, arrays, arithmetic, virtual filesystem, and coreutils
 *               (grep, sed, awk, sort, uniq, wc, cut, tr, head, tail, find, jq).
 *
 * Protocol (client: backend/static/js/pages-live.js):
 *   in : { type: "assets", assets: { clang, typescript, sql, go, bash, tsLibs } }
 *        { type: "init", id, lang }
 *        { type: "run", id, lang, code, stdin }
 *   out: { type: "progress", lang, message }
 *        { type: "ready", id, lang }
 *        { type: "init-error", id, lang, error }
 *        { type: "result", id, status, stdout, stderr, compileOutput,
 *          exitCode, runtimeMs }
 */

const EV_MAX_OUTPUT = 65536;
let EV_ASSETS = null;

function evCap(text) {
  const s = String(text == null ? "" : text);
  return s.length > EV_MAX_OUTPUT ? s.slice(0, EV_MAX_OUTPUT) : s;
}

function evFail(status, message) {
  const err = new Error(message);
  err.evStatus = status;
  return err;
}

function evProgress(lang, message) {
  try {
    self.postMessage({ type: "progress", lang, message });
  } catch (_) {}
}

/* ------------------------------------------------------------------ C/C++ */
const evClangCompilers = {};
const evClangBooting = {};

async function evEnsureClang(lang) {
  const id = lang === "cpp" ? "cpp" : "c";
  if (evClangCompilers[id]) return evClangCompilers[id];
  if (!evClangBooting[id]) {
    evClangBooting[id] = (async () => {
      if (!EV_ASSETS || !EV_ASSETS.clang) {
        throw new Error("Clang WebAssembly assets are not configured.");
      }
      evProgress(
        id,
        id === "cpp"
          ? "Loading Clang++ 22 WebAssembly compiler & libc++ standard library…"
          : "Loading Clang 22 WebAssembly C compiler & sysroot…"
      );
      if (!self.clangWasm) {
        importScripts(EV_ASSETS.clang + "clang-wasm.global.js");
      }
      const compiler = await self.clangWasm.createCompiler(id, {
        baseUrl: EV_ASSETS.clang + "assets/",
        std: id === "cpp" ? "gnu++20" : "gnu17",
      });
      evClangCompilers[id] = compiler;
      return compiler;
    })().catch((err) => {
      delete evClangBooting[id];
      throw err;
    });
  }
  return evClangBooting[id];
}

async function evRunClang(lang, code, stdin) {
  const compiler = await evEnsureClang(lang);
  evProgress(lang, lang === "cpp" ? "Compiling & running C++…" : "Compiling & running C…");
  const result = await compiler.run(String(code || ""), String(stdin || ""));
  const errors = result.errors || [];
  if (errors.length) {
    const diag = evCap(errors.join("\n"));
    return {
      status: "compile_error",
      stdout: evCap(result.stdout),
      stderr: diag,
      compileOutput: diag,
      exitCode: null,
    };
  }
  return {
    status: result.exitCode === 0 ? "accepted" : "runtime_error",
    stdout: evCap(result.stdout),
    stderr: evCap(result.stderr),
    compileOutput: "",
    exitCode: result.exitCode,
  };
}

/* ----------------------------------------- Node + Browser JS Runtime Shim */
function evFormatJsValue(val, depth) {
  if (val === null) return "null";
  if (val === undefined) return "undefined";
  if (typeof val === "string") return depth > 0 ? JSON.stringify(val) : val;
  if (typeof val === "number" || typeof val === "boolean" || typeof val === "symbol") return String(val);
  if (typeof val === "bigint") return String(val) + "n";
  if (typeof val === "function") return `[Function: ${val.name || "anonymous"}]`;
  if (val instanceof Error) return val.stack || `${val.name}: ${val.message}`;
  if (val instanceof Map) {
    if (depth > 3) return "Map(...)";
    const entries = [];
    for (const [k, v] of val.entries()) entries.push(`${evFormatJsValue(k, depth + 1)} => ${evFormatJsValue(v, depth + 1)}`);
    return `Map(${val.size}) { ${entries.join(", ")} }`;
  }
  if (val instanceof Set) {
    if (depth > 3) return "Set(...)";
    const items = [];
    for (const v of val.values()) items.push(evFormatJsValue(v, depth + 1));
    return `Set(${val.size}) { ${items.join(", ")} }`;
  }
  if (ArrayBuffer.isView(val)) {
    if (val instanceof Uint8Array && val._isEvBuffer) {
      return `<Buffer ${Array.from(val.subarray(0, 50)).map((b) => b.toString(16).padStart(2, "0")).join(" ")}${val.length > 50 ? " ... " : ""}>`;
    }
    return `${val.constructor.name}(${val.length}) [ ${Array.from(val.slice(0, 100)).join(", ")} ]`;
  }
  if (Array.isArray(val)) {
    if (depth > 4) return "[Array]";
    return `[ ${val.map((x) => evFormatJsValue(x, depth + 1)).join(", ")} ]`;
  }
  try {
    return JSON.stringify(val);
  } catch (_) {
    return Object.prototype.toString.call(val);
  }
}

function evMakeBufferClass() {
  const enc = new TextEncoder();
  const dec = new TextDecoder("utf-8");
  function wrap(u8) {
    Object.setPrototypeOf(u8, EvBuffer.prototype);
    u8._isEvBuffer = true;
    return u8;
  }
  function fromBase64(str) {
    const bin = atob(String(str).replace(/\s+/g, ""));
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
    return out;
  }
  function toBase64(u8) {
    let bin = "";
    for (let i = 0; i < u8.length; i += 1) bin += String.fromCharCode(u8[i]);
    return btoa(bin);
  }
  function EvBuffer(arg, encodingOrOffset, length) {
    return EvBuffer.from(arg, encodingOrOffset, length);
  }
  Object.setPrototypeOf(EvBuffer.prototype, Uint8Array.prototype);
  Object.setPrototypeOf(EvBuffer, Uint8Array);
  EvBuffer.from = (value, encodingOrOffset, length) => {
    if (typeof value === "string") {
      const mode = String(encodingOrOffset || "utf8").toLowerCase();
      if (mode === "hex") {
        const clean = value.replace(/[^0-9a-fA-F]/g, "");
        const out = new Uint8Array(Math.floor(clean.length / 2));
        for (let i = 0; i < out.length; i += 1) out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
        return wrap(out);
      }
      if (mode === "base64" || mode === "base64url") {
        const norm = mode === "base64url" ? value.replace(/-/g, "+").replace(/_/g, "/") : value;
        return wrap(fromBase64(norm));
      }
      return wrap(enc.encode(value));
    }
    if (value instanceof ArrayBuffer) {
      return wrap(new Uint8Array(value, encodingOrOffset || 0, length == null ? value.byteLength - (encodingOrOffset || 0) : length));
    }
    if (ArrayBuffer.isView(value)) {
      return wrap(new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength)));
    }
    return wrap(new Uint8Array(value || 0));
  };
  EvBuffer.alloc = (size, fill) => {
    const out = wrap(new Uint8Array(Number(size) || 0));
    if (fill !== undefined) out.fill(typeof fill === "string" ? fill.charCodeAt(0) : Number(fill) || 0);
    return out;
  };
  EvBuffer.allocUnsafe = (size) => wrap(new Uint8Array(Number(size) || 0));
  EvBuffer.isBuffer = (v) => Boolean(v && v._isEvBuffer);
  EvBuffer.byteLength = (v, encoding) => (typeof v === "string" ? EvBuffer.from(v, encoding).length : (v ? v.byteLength || v.length || 0 : 0));
  EvBuffer.concat = (list, totalLength) => {
    const total = totalLength == null ? list.reduce((s, b) => s + b.length, 0) : totalLength;
    const out = wrap(new Uint8Array(total));
    let off = 0;
    for (const item of list) {
      const slice = off + item.length > total ? item.subarray(0, total - off) : item;
      out.set(slice, off);
      off += slice.length;
      if (off >= total) break;
    }
    return out;
  };
  EvBuffer.prototype.toString = function toString(encoding, start, end) {
    const sub = this.subarray(start || 0, end == null ? this.length : end);
    const mode = String(encoding || "utf8").toLowerCase();
    if (mode === "hex") return Array.from(sub).map((b) => b.toString(16).padStart(2, "0")).join("");
    if (mode === "base64") return toBase64(sub);
    if (mode === "base64url") return toBase64(sub).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    if (mode === "latin1" || mode === "binary" || mode === "ascii") {
      let s = "";
      for (let i = 0; i < sub.length; i += 1) s += String.fromCharCode(sub[i]);
      return s;
    }
    return dec.decode(sub);
  };
  EvBuffer.prototype.write = function write(str, offset) {
    const bytes = enc.encode(String(str));
    const at = Number(offset) || 0;
    const n = Math.min(bytes.length, this.length - at);
    this.set(bytes.subarray(0, n), at);
    return n;
  };
  EvBuffer.prototype.equals = function equals(other) {
    if (!other || this.length !== other.length) return false;
    for (let i = 0; i < this.length; i += 1) if (this[i] !== other[i]) return false;
    return true;
  };
  return EvBuffer;
}

class EvProcessExit extends Error {
  constructor(code) {
    super(`process.exit(${code})`);
    this.evExitCode = Number.isFinite(Number(code)) ? Number(code) : 0;
  }
}

function evRunJavaScriptEnvironment(code, stdin) {
  const rawInput = String(stdin == null ? "" : stdin);
  const BufferClass = evMakeBufferClass();
  const stdinBuf = BufferClass.from(rawInput, "utf8");
  const lines = rawInput === "" ? [] : rawInput.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");
  let lineIdx = 0;

  let outBuf = "";
  let errBuf = "";
  let exitCode = 0;
  const timers = new Map();

  const writeOut = (chunk) => {
    outBuf += chunk instanceof Uint8Array ? BufferClass.from(chunk).toString("utf8") : String(chunk);
    return true;
  };
  const writeErr = (chunk) => {
    errBuf += chunk instanceof Uint8Array ? BufferClass.from(chunk).toString("utf8") : String(chunk);
    return true;
  };
  const fmtArgs = (args) => Array.from(args).map((a) => evFormatJsValue(a, 0)).join(" ");

  const cons = {
    log: (...a) => writeOut(fmtArgs(a) + "\n"),
    info: (...a) => writeOut(fmtArgs(a) + "\n"),
    debug: (...a) => writeOut(fmtArgs(a) + "\n"),
    dir: (obj) => writeOut(evFormatJsValue(obj, 0) + "\n"),
    table: (data) => writeOut(evFormatJsValue(data, 0) + "\n"),
    warn: (...a) => writeErr(fmtArgs(a) + "\n"),
    error: (...a) => writeErr(fmtArgs(a) + "\n"),
    assert: (cond, ...a) => {
      if (!cond) writeErr("Assertion failed: " + (a.length ? fmtArgs(a) : "console.assert") + "\n");
    },
    time: (label = "default") => timers.set(String(label), performance.now()),
    timeEnd: (label = "default") => {
      const t0 = timers.get(String(label));
      timers.delete(String(label));
      writeOut(`${label}: ${(performance.now() - (t0 || performance.now())).toFixed(2)}ms\n`);
    },
    clear: () => {},
  };

  class EventEmitter {
    constructor() { this._ev = new Map(); }
    on(e, fn) { if (!this._ev.has(e)) this._ev.set(e, []); this._ev.get(e).push(fn); return this; }
    addListener(e, fn) { return this.on(e, fn); }
    once(e, fn) {
      const w = (...a) => { this.off(e, w); return fn(...a); };
      return this.on(e, w);
    }
    off(e, fn) {
      const list = this._ev.get(e);
      if (list) this._ev.set(e, list.filter((f) => f !== fn));
      return this;
    }
    removeListener(e, fn) { return this.off(e, fn); }
    removeAllListeners(e) { if (e) this._ev.delete(e); else this._ev.clear(); return this; }
    emit(e, ...a) {
      const list = (this._ev.get(e) || []).slice();
      for (const fn of list) fn(...a);
      return list.length > 0;
    }
  }

  // Virtual in-memory filesystem with fd 0 / "/dev/stdin" wired to stdin
  const vfs = new Map();
  vfs.set("/dev/stdin", stdinBuf);
  const normPath = (p) => {
    const s = String(p).replace(/\\/g, "/");
    const parts = [];
    for (const seg of s.split("/")) {
      if (!seg || seg === ".") continue;
      if (seg === "..") parts.pop();
      else parts.push(seg);
    }
    return "/" + parts.join("/");
  };

  const fsMod = {
    readFileSync(target, options) {
      let data;
      if (target === 0 || target === "/dev/stdin" || target === "/dev/fd/0") {
        data = stdinBuf;
      } else {
        const key = normPath(target);
        if (!vfs.has(key)) {
          const err = new Error(`ENOENT: no such file or directory, open '${target}'`);
          err.code = "ENOENT";
          throw err;
        }
        data = vfs.get(key);
      }
      const enc = typeof options === "string" ? options : options && options.encoding;
      return enc ? data.toString(enc) : BufferClass.from(data);
    },
    writeFileSync(target, content, options) {
      const enc = (typeof options === "string" ? options : options && options.encoding) || "utf8";
      const buf = content instanceof Uint8Array ? BufferClass.from(content) : BufferClass.from(String(content), enc);
      if (target === 1 || target === "/dev/stdout") { writeOut(buf); return; }
      if (target === 2 || target === "/dev/stderr") { writeErr(buf); return; }
      vfs.set(normPath(target), buf);
    },
    appendFileSync(target, content, options) {
      const enc = (typeof options === "string" ? options : options && options.encoding) || "utf8";
      const add = content instanceof Uint8Array ? BufferClass.from(content) : BufferClass.from(String(content), enc);
      const key = normPath(target);
      const prev = vfs.get(key);
      vfs.set(key, prev ? BufferClass.concat([prev, add]) : add);
    },
    existsSync(target) {
      if (target === 0 || target === "/dev/stdin") return true;
      const key = normPath(target);
      if (vfs.has(key)) return true;
      const prefix = key === "/" ? "/" : key + "/";
      for (const k of vfs.keys()) if (k.startsWith(prefix)) return true;
      return false;
    },
    unlinkSync(target) { vfs.delete(normPath(target)); },
    mkdirSync() { return undefined; },
    readdirSync(dir) {
      const prefix = normPath(dir) === "/" ? "/" : normPath(dir) + "/";
      const out = new Set();
      for (const k of vfs.keys()) {
        if (k.startsWith(prefix)) out.add(k.slice(prefix.length).split("/")[0]);
      }
      return Array.from(out);
    },
    statSync(target) {
      const buf = fsMod.readFileSync(target);
      return { size: buf.length, isFile: () => true, isDirectory: () => false };
    },
  };
  fsMod.promises = {
    readFile: async (t, o) => fsMod.readFileSync(t, o),
    writeFile: async (t, c, o) => fsMod.writeFileSync(t, c, o),
    appendFile: async (t, c, o) => fsMod.appendFileSync(t, c, o),
    stat: async (t) => fsMod.statSync(t),
    readdir: async (d) => fsMod.readdirSync(d),
    mkdir: async () => undefined,
    unlink: async (t) => fsMod.unlinkSync(t),
  };

  const pathMod = {
    sep: "/",
    delimiter: ":",
    normalize: normPath,
    join: (...parts) => (parts.length ? normPath(parts.join("/")).replace(/^\/+/, parts[0].startsWith("/") ? "/" : "") || "." : "."),
    resolve: (...parts) => normPath("/tmp/" + parts.join("/")),
    dirname: (p) => { const n = normPath(p); const i = n.lastIndexOf("/"); return i <= 0 ? "/" : n.slice(0, i); },
    basename: (p, ext) => { const b = String(p).replace(/\/+$/, "").split("/").pop() || ""; return ext && b.endsWith(ext) ? b.slice(0, -ext.length) : b; },
    extname: (p) => { const b = pathMod.basename(p); const i = b.lastIndexOf("."); return i <= 0 ? "" : b.slice(i); },
    isAbsolute: (p) => String(p).startsWith("/"),
  };
  pathMod.posix = pathMod;

  const assertFn = (val, msg) => {
    if (!val) throw new Error(msg || "AssertionError [ERR_ASSERTION]: The expression evaluated to a falsy value");
  };
  assertFn.ok = assertFn;
  assertFn.equal = (a, b, m) => assertFn(a == b, m || `Expected ${evFormatJsValue(a, 0)} == ${evFormatJsValue(b, 0)}`);
  assertFn.strictEqual = (a, b, m) => assertFn(Object.is(a, b), m || `Expected ${evFormatJsValue(a, 0)} === ${evFormatJsValue(b, 0)}`);
  assertFn.notStrictEqual = (a, b, m) => assertFn(!Object.is(a, b), m || `Expected values to not be strictly equal`);
  assertFn.deepEqual = (a, b, m) => assertFn(JSON.stringify(a) === JSON.stringify(b), m || `Expected deep equality between ${evFormatJsValue(a, 0)} and ${evFormatJsValue(b, 0)}`);
  assertFn.deepStrictEqual = assertFn.deepEqual;
  assertFn.throws = (fn, m) => {
    let threw = false;
    try { fn(); } catch (_) { threw = true; }
    assertFn(threw, m || "Expected function to throw");
  };

  const stdinStream = Object.assign(new EventEmitter(), {
    isTTY: false,
    setEncoding() { return this; },
    resume() {
      queueMicrotask(() => {
        if (rawInput.length) stdinStream.emit("data", rawInput);
        stdinStream.emit("end");
      });
      return this;
    },
    pause() { return this; },
    read() { return rawInput || null; },
    async *[Symbol.asyncIterator]() {
      if (rawInput.length) yield rawInput;
    },
  });
  const origStdinOn = stdinStream.on.bind(stdinStream);
  let stdinScheduled = false;
  stdinStream.on = (ev, fn) => {
    origStdinOn(ev, fn);
    if (!stdinScheduled && (ev === "data" || ev === "end")) {
      stdinScheduled = true;
      queueMicrotask(() => {
        if (rawInput.length) stdinStream.emit("data", rawInput);
        stdinStream.emit("end");
      });
    }
    return stdinStream;
  };

  const readlineMod = {
    createInterface() {
      const rl = new EventEmitter();
      let emitted = false;
      const pump = () => {
        if (emitted) return;
        emitted = true;
        queueMicrotask(() => {
          for (const l of lines) rl.emit("line", l);
          rl.emit("close");
        });
      };
      const origOn = rl.on.bind(rl);
      rl.on = (ev, fn) => {
        origOn(ev, fn);
        if (ev === "line" || ev === "close") pump();
        return rl;
      };
      rl.close = () => { rl.emit("close"); };
      rl.question = (promptText, cb) => {
        if (promptText) writeOut(String(promptText));
        const next = lineIdx < lines.length ? lines[lineIdx++] : "";
        queueMicrotask(() => cb(next));
      };
      rl[Symbol.asyncIterator] = async function* rlIter() {
        for (const l of lines) yield l;
      };
      return rl;
    },
  };

  const utilMod = {
    format: (...a) => fmtArgs(a),
    inspect: (v) => evFormatJsValue(v, 0),
    promisify: (fn) => (...args) => new Promise((res, rej) => fn(...args, (err, val) => (err ? rej(err) : res(val)))),
    types: {
      isPromise: (v) => Boolean(v && typeof v.then === "function"),
      isRegExp: (v) => v instanceof RegExp,
      isDate: (v) => v instanceof Date,
      isMap: (v) => v instanceof Map,
      isSet: (v) => v instanceof Set,
    },
    TextEncoder,
    TextDecoder,
  };

  const osMod = {
    EOL: "\n",
    platform: () => "linux",
    arch: () => "wasm32",
    tmpdir: () => "/tmp",
    homedir: () => "/tmp",
    cpus: () => [{ model: "WebAssembly", speed: 2400 }],
  };

  const cryptoMod = {
    randomUUID: () => (self.crypto && self.crypto.randomUUID ? self.crypto.randomUUID() : "00000000-0000-4000-8000-000000000000"),
    randomBytes: (n) => {
      const u8 = new Uint8Array(Number(n) || 0);
      if (self.crypto && self.crypto.getRandomValues) self.crypto.getRandomValues(u8);
      return BufferClass.from(u8);
    },
    randomInt: (min, max) => {
      const lo = max === undefined ? 0 : Number(min);
      const hi = max === undefined ? Number(min) : Number(max);
      return lo + Math.floor(Math.random() * (hi - lo));
    },
  };

  const proc = {
    argv: ["node", "/workspace/main.js"],
    env: { NODE_ENV: "production", HOME: "/tmp", TMPDIR: "/tmp" },
    platform: "linux",
    arch: "wasm32",
    version: "v22.0.0",
    versions: { node: "22.0.0" },
    cwd: () => "/tmp",
    stdin: stdinStream,
    stdout: { write: writeOut, isTTY: false },
    stderr: { write: writeErr, isTTY: false },
    nextTick: (fn, ...a) => queueMicrotask(() => fn(...a)),
    exit: (code = 0) => { throw new EvProcessExit(code); },
    hrtime: Object.assign(
      (prev) => {
        const nowNs = BigInt(Math.round(performance.now() * 1e6));
        const baseNs = prev ? BigInt(prev[0]) * 1000000000n + BigInt(prev[1]) : 0n;
        const diff = nowNs - baseNs;
        return [Number(diff / 1000000000n), Number(diff % 1000000000n)];
      },
      { bigint: () => BigInt(Math.round(performance.now() * 1e6)) }
    ),
  };

  const builtins = {
    fs: fsMod,
    "fs/promises": fsMod.promises,
    path: pathMod,
    "path/posix": pathMod,
    assert: assertFn,
    "assert/strict": assertFn,
    events: EventEmitter,
    readline: readlineMod,
    util: utilMod,
    os: osMod,
    crypto: cryptoMod,
    buffer: { Buffer: BufferClass },
    perf_hooks: { performance },
    url: { URL, URLSearchParams },
  };

  const req = (specifier) => {
    const clean = String(specifier || "").replace(/^node:/, "");
    if (Object.prototype.hasOwnProperty.call(builtins, clean)) return builtins[clean];
    throw new Error(`Cannot find module '${specifier}'`);
  };

  const readLineHelper = () => (lineIdx < lines.length ? lines[lineIdx++] : null);
  const moduleObj = { exports: {} };
  const prevStdinGlobal = self.__STDIN__;
  const prevBufferGlobal = self.Buffer;
  const prevProcessGlobal = self.process;
  self.__STDIN__ = rawInput;
  self.Buffer = BufferClass;
  self.process = proc;

  const restore = () => {
    self.__STDIN__ = prevStdinGlobal;
    self.Buffer = prevBufferGlobal;
    self.process = prevProcessGlobal;
  };

  const finish = (threw) => {
    restore();
    const failed = threw || exitCode !== 0;
    return {
      status: failed ? "runtime_error" : "accepted",
      stdout: evCap(outBuf),
      stderr: evCap(errBuf),
      compileOutput: "",
      exitCode: threw ? (exitCode || 1) : exitCode,
    };
  };

  let ret;
  try {
    const run = new Function(
      "require", "module", "exports", "__filename", "__dirname",
      "process", "Buffer", "console", "stdin", "input", "readline", "print",
      "{ " + String(code || "") + "\n}"
    );
    ret = run(
      req, moduleObj, moduleObj.exports, "/tmp/main.js", "/tmp",
      proc, BufferClass, cons, rawInput, rawInput, readLineHelper, cons.log
    );
  } catch (err) {
    if (err instanceof EvProcessExit) {
      exitCode = err.evExitCode;
      return finish(false);
    }
    errBuf += (err && err.stack ? err.stack : String((err && err.message) || err)) + "\n";
    return finish(true);
  }

  return (async () => {
    try {
      if (ret && typeof ret.then === "function") await ret;
      // Allow queued microtasks / readline / stdin listeners to flush cleanly.
      await new Promise((r) => setTimeout(r, 0));
      return finish(false);
    } catch (err) {
      if (err instanceof EvProcessExit) {
        exitCode = err.evExitCode;
        return finish(false);
      }
      errBuf += (err && err.stack ? err.stack : String((err && err.message) || err)) + "\n";
      return finish(true);
    }
  })();
}

async function evRunJavaScript(_lang, code, stdin) {
  return evRunJavaScriptEnvironment(code, stdin);
}

/* -------------------------------------------------------------- TypeScript */
let evTsBootPromise = null;
let evTsLibs = null; // Map<basename, ts.SourceFile>

async function evBootTypeScript() {
  if (evTsLibs) return;
  if (!evTsBootPromise) {
    evTsBootPromise = (async () => {
      evProgress("typescript", "Loading TypeScript 5.9 compiler…");
      if (!self.ts) {
        importScripts(EV_ASSETS.typescript + "typescript.js");
      }
      const parsed = new Map();
      await Promise.all(
        (EV_ASSETS.tsLibs || []).map(async (name) => {
          const res = await fetch(EV_ASSETS.typescript + name);
          if (!res.ok) throw new Error(`lib ${name}: HTTP ${res.status}`);
          const text = await res.text();
          parsed.set(
            name,
            self.ts.createSourceFile(name, text, self.ts.ScriptTarget.ES2020, true)
          );
        })
      );
      evTsLibs = parsed;
    })().catch((err) => {
      evTsBootPromise = null;
      throw err;
    });
  }
  return evTsBootPromise;
}

const EV_TS_GLOBALS = `
declare var input: string;
declare var stdin: string;
declare function readline(): string | null;
declare function print(...args: any[]): void;
declare var require: (id: string) => any;
declare var module: { exports: any };
declare var exports: any;
declare var __filename: string;
declare var __dirname: string;
declare class Buffer extends Uint8Array {
  static from(value: any, encodingOrOffset?: any, length?: number): Buffer;
  static alloc(size: number, fill?: any): Buffer;
  static allocUnsafe(size: number): Buffer;
  static isBuffer(obj: any): obj is Buffer;
  static byteLength(string: string | ArrayBufferView, encoding?: string): number;
  static concat(list: readonly Uint8Array[], totalLength?: number): Buffer;
  toString(encoding?: string, start?: number, end?: number): string;
  write(string: string, offset?: number): number;
  equals(otherBuffer: Uint8Array): boolean;
}
declare const process: {
  argv: string[];
  env: Record<string, string | undefined>;
  platform: string;
  arch: string;
  version: string;
  cwd(): string;
  stdin: any;
  stdout: { write(chunk: string | Uint8Array): boolean; isTTY?: boolean };
  stderr: { write(chunk: string | Uint8Array): boolean; isTTY?: boolean };
  nextTick(cb: (...args: any[]) => void, ...args: any[]): void;
  exit(code?: number): never;
  hrtime: { (time?: [number, number]): [number, number]; bigint(): bigint };
};
declare const console: {
  log(...args: any[]): void;
  info(...args: any[]): void;
  warn(...args: any[]): void;
  error(...args: any[]): void;
  debug(...args: any[]): void;
  dir(item?: any, options?: any): void;
  table(tabularData?: any, properties?: string[]): void;
  assert(condition?: any, ...data: any[]): void;
  time(label?: string): void;
  timeEnd(label?: string): void;
  clear(): void;
};
declare function setTimeout(handler: (...args: any[]) => void, timeout?: number, ...args: any[]): any;
declare function clearTimeout(id?: any): void;
declare function setInterval(handler: (...args: any[]) => void, timeout?: number, ...args: any[]): any;
declare function clearInterval(id?: any): void;
declare function queueMicrotask(callback: () => void): void;
declare function structuredClone<T>(value: T): T;
declare function atob(data: string): string;
declare function btoa(data: string): string;
declare const performance: { now(): number };
declare const crypto: { randomUUID(): string; getRandomValues<T extends ArrayBufferView>(array: T): T };
declare class TextEncoder { encode(input?: string): Uint8Array }
declare class TextDecoder { constructor(label?: string, options?: any); decode(input?: BufferSource, options?: any): string }
declare class URL { constructor(url: string | URL, base?: string | URL); href: string; origin: string; pathname: string; search: string; searchParams: URLSearchParams; hash: string; host: string; hostname: string; port: string; protocol: string; toString(): string }
declare class URLSearchParams { constructor(init?: any); get(name: string): string | null; set(name: string, value: string): void; append(name: string, value: string): void; has(name: string): boolean; delete(name: string): void; entries(): IterableIterator<[string, string]>; toString(): string }

interface String {
  replaceAll(searchValue: string | RegExp, replaceValue: string | ((substring: string, ...args: any[]) => string)): string;
  at(index: number): string | undefined;
}
interface Array<T> {
  at(index: number): T | undefined;
  findLast<S extends T>(predicate: (value: T, index: number, array: T[]) => value is S, thisArg?: any): S | undefined;
  findLast(predicate: (value: T, index: number, array: T[]) => unknown, thisArg?: any): T | undefined;
  findLastIndex(predicate: (value: T, index: number, array: T[]) => unknown, thisArg?: any): number;
  toReversed(): T[];
  toSorted(compareFn?: (a: T, b: T) => number): T[];
  toSpliced(start: number, deleteCount?: number, ...items: T[]): T[];
  with(index: number, value: T): T[];
}
interface ReadonlyArray<T> {
  at(index: number): T | undefined;
  findLast(predicate: (value: T, index: number, array: readonly T[]) => unknown, thisArg?: any): T | undefined;
  findLastIndex(predicate: (value: T, index: number, array: readonly T[]) => unknown, thisArg?: any): number;
  toReversed(): T[];
  toSorted(compareFn?: (a: T, b: T) => number): T[];
}
interface ObjectConstructor {
  hasOwn(o: object, v: PropertyKey): boolean;
  groupBy<K extends PropertyKey, T>(items: Iterable<T>, keySelector: (item: T, index: number) => K): Partial<Record<K, T[]>>;
}
interface MapConstructor {
  groupBy<K, T>(items: Iterable<T>, keySelector: (item: T, index: number) => K): Map<K, T[]>;
}

declare module "fs" {
  export function readFileSync(path: number | string, options: "utf8" | "utf-8" | { encoding: "utf8" | "utf-8" }): string;
  export function readFileSync(path: number | string, options?: string | { encoding?: string | null }): any;
  export function writeFileSync(path: number | string, data: string | Uint8Array, options?: any): void;
  export function appendFileSync(path: string, data: string | Uint8Array, options?: any): void;
  export function existsSync(path: number | string): boolean;
  export function statSync(path: number | string): { size: number; isFile(): boolean; isDirectory(): boolean };
  export function readdirSync(path?: string): string[];
  export function mkdirSync(path: string, options?: any): void;
  export function unlinkSync(path: string): void;
  export const promises: {
    readFile(path: number | string, options?: any): Promise<any>;
    writeFile(path: number | string, data: string | Uint8Array, options?: any): Promise<void>;
    appendFile(path: string, data: string | Uint8Array): Promise<void>;
  };
}
declare module "node:fs" { export * from "fs"; }
declare module "fs/promises" {
  export function readFile(path: number | string, options?: any): Promise<any>;
  export function writeFile(path: number | string, data: string | Uint8Array, options?: any): Promise<void>;
  export function appendFile(path: string, data: string | Uint8Array): Promise<void>;
}
declare module "node:fs/promises" { export * from "fs/promises"; }
declare module "path" {
  export const sep: string;
  export const delimiter: string;
  export function normalize(p: string): string;
  export function join(...paths: string[]): string;
  export function resolve(...paths: string[]): string;
  export function dirname(p: string): string;
  export function basename(p: string, ext?: string): string;
  export function extname(p: string): string;
  export function isAbsolute(p: string): boolean;
  export function parse(p: string): { root: string; dir: string; base: string; ext: string; name: string };
}
declare module "node:path" { export * from "path"; }
declare module "readline" {
  export interface Interface {
    on(event: string, listener: (...args: any[]) => void): this;
    question(query: string, callback: (answer: string) => void): void;
    close(): void;
    [Symbol.asyncIterator](): AsyncIterableIterator<string>;
  }
  export function createInterface(input?: any, output?: any): Interface;
}
declare module "node:readline" { export * from "readline"; }
declare module "events" {
  export class EventEmitter {
    on(eventName: string | symbol, listener: (...args: any[]) => void): this;
    once(eventName: string | symbol, listener: (...args: any[]) => void): this;
    off(eventName: string | symbol, listener: (...args: any[]) => void): this;
    emit(eventName: string | symbol, ...args: any[]): boolean;
    removeAllListeners(event?: string | symbol): this;
  }
}
declare module "node:events" { export * from "events"; }
declare module "assert" {
  function assert(value: unknown, message?: string | Error): asserts value;
  namespace assert {
    function ok(value: unknown, message?: string | Error): asserts value;
    function equal(actual: unknown, expected: unknown, message?: string | Error): void;
    function strictEqual<T>(actual: unknown, expected: T, message?: string | Error): asserts actual is T;
    function deepEqual(actual: unknown, expected: unknown, message?: string | Error): void;
    function deepStrictEqual<T>(actual: unknown, expected: T, message?: string | Error): asserts actual is T;
    function throws(block: () => unknown, message?: any): void;
  }
  export = assert;
}
declare module "node:assert" { import assert = require("assert"); export = assert; }
declare module "assert/strict" { import assert = require("assert"); export = assert; }
declare module "util" {
  export function format(format?: any, ...param: any[]): string;
  export function inspect(object: any, options?: any): string;
  export function promisify(fn: (...args: any[]) => void): (...args: any[]) => Promise<any>;
  export { TextEncoder, TextDecoder };
}
declare module "node:util" { export * from "util"; }
declare module "os" {
  export const EOL: string;
  export function platform(): string;
  export function arch(): string;
  export function tmpdir(): string;
  export function homedir(): string;
  export function cpus(): Array<{ model: string; speed: number }>;
}
declare module "node:os" { export * from "os"; }
declare module "crypto" {
  export function randomUUID(): string;
  export function randomBytes(size: number): Buffer;
  export function randomInt(min: number, max?: number): number;
}
declare module "node:crypto" { export * from "crypto"; }
declare module "buffer" { export { Buffer }; }
declare module "node:buffer" { export { Buffer }; }
declare module "url" { export { URL, URLSearchParams }; }
declare module "node:url" { export { URL, URLSearchParams }; }
declare module "perf_hooks" { export { performance }; }
declare module "node:perf_hooks" { export { performance }; }
`;

let evTsGlobalsSource = null;

function evFormatTsDiagnostic(diag) {
  const text = self.ts.flattenDiagnosticMessageText(diag.messageText, "\n");
  if (diag.file && typeof diag.start === "number") {
    const pos = diag.file.getLineAndCharacterOfPosition(diag.start);
    const name = diag.file.fileName.split("/").pop();
    return `${name}:${pos.line + 1}:${pos.character + 1}: ${text}`;
  }
  return text;
}

async function evRunTypeScript(_lang, code, stdin) {
  await evBootTypeScript();
  const ts = self.ts;
  const codeText = String(code || "");
  if (!evTsGlobalsSource) {
    evTsGlobalsSource = ts.createSourceFile("globals.d.ts", EV_TS_GLOBALS, ts.ScriptTarget.ES2020, true);
  }
  const hasUserAmbient = /\bdeclare\s+(?:const|let|var|function|class)\s+(input|stdin|readline|print|require|module|exports|__filename|__dirname|Buffer|process|console)\b/.test(codeText);
  const globalsSf = hasUserAmbient
    ? ts.createSourceFile(
        "globals.d.ts",
        EV_TS_GLOBALS.replace(
          /^declare\s+(?:var|const|function)\s+(input|stdin|readline|print|require|module|exports|__filename|__dirname)\b.*$/gm,
          (line, ident) => (new RegExp(`\\bdeclare\\s+(?:const|let|var|function|class)\\s+${ident}\\b`).test(codeText) ? "" : line)
        ),
        ts.ScriptTarget.ES2020,
        true
      )
    : evTsGlobalsSource;
  const userSource = ts.createSourceFile("main.ts", codeText, ts.ScriptTarget.ES2020, true);
  const baseName = (name) => String(name).split("/").pop();
  const getSf = (fileName) => {
    const base = baseName(fileName);
    if (base === "main.ts") return userSource;
    if (base === "globals.d.ts") return globalsSf;
    return evTsLibs.get(base);
  };
  const host = {
    getSourceFile: (fileName) => getSf(fileName),
    getDefaultLibFileName: () => "lib.es2020.d.ts",
    writeFile: (fileName, text) => {
      if (fileName.endsWith("main.js")) host._emit = text;
    },
    getCurrentDirectory: () => "",
    getDirectories: () => [],
    getCanonicalFileName: (fileName) => fileName.toLowerCase(),
    getNewLine: () => "\n",
    useCaseSensitiveFileNames: () => false,
    fileExists: (fileName) => Boolean(getSf(fileName)),
    readFile: (fileName) => {
      const sf = getSf(fileName);
      return sf ? sf.text : undefined;
    },
    directoryExists: () => true,
    getEnvironmentVariable: () => "",
  };
  const program = ts.createProgram(["main.ts", "globals.d.ts"], {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    moduleResolution: ts.ModuleResolutionKind.Node10,
    esModuleInterop: true,
    allowSyntheticDefaultImports: true,
    lib: ["lib.es2020.d.ts"],
    downlevelIteration: true,
    strict: false,
    skipLibCheck: true,
    noEmitOnError: true,
    types: [],
  }, host);
  const diagnostics = [
    ...program.getSyntacticDiagnostics(),
    ...program.getSemanticDiagnostics(),
  ].filter((d) => d.category === ts.DiagnosticCategory.Error);
  if (diagnostics.length) {
    const diag = evCap(diagnostics.map(evFormatTsDiagnostic).join("\n"));
    return {
      status: "compile_error",
      stdout: "",
      stderr: diag,
      compileOutput: diag,
      exitCode: null,
    };
  }
  const emit = program.emit();
  if (emit.emitSkipped || !host._emit) {
    return {
      status: "compile_error",
      stdout: "",
      stderr: "",
      compileOutput: "TypeScript emit was skipped.",
      exitCode: null,
    };
  }
  return evRunJavaScriptEnvironment(host._emit, stdin);
}

/* --------------------------------------------------------------------- SQL */
let evSqlJsPromise = null;

async function evBootSql() {
  if (!evSqlJsPromise) {
    evSqlJsPromise = (async () => {
      evProgress("sql", "Loading SQLite 3 WebAssembly engine…");
      importScripts(EV_ASSETS.sql + "sql-wasm.js");
      const wasm = await fetch(EV_ASSETS.sql + "sql-wasm.wasm");
      if (!wasm.ok) throw new Error(`sql-wasm.wasm: HTTP ${wasm.status}`);
      return self.initSqlJs({ wasmBinary: await wasm.arrayBuffer() });
    })().catch((err) => {
      evSqlJsPromise = null;
      throw err;
    });
  }
  return evSqlJsPromise;
}

function evSplitSql(sql) {
  const statements = [];
  let buf = "";
  let i = 0;
  const text = String(sql || "");
  let quote = null;
  let lineComment = false;
  let blockComment = false;
  while (i < text.length) {
    const ch = text[i];
    const next = text[i + 1] || "";
    if (lineComment) {
      buf += ch;
      if (ch === "\n") lineComment = false;
      i += 1;
      continue;
    }
    if (blockComment) {
      buf += ch;
      if (ch === "*" && next === "/") {
        buf += next;
        i += 2;
        blockComment = false;
        continue;
      }
      i += 1;
      continue;
    }
    if (quote) {
      buf += ch;
      if (ch === quote) {
        if (quote === "'" && next === "'") {
          buf += next;
          i += 2;
          continue;
        }
        quote = null;
      }
      i += 1;
      continue;
    }
    if (ch === "-" && next === "-") lineComment = true;
    else if (ch === "/" && next === "*") blockComment = true;
    else if (ch === "'" || ch === '"' || ch === "`") quote = ch;
    else if (ch === ";") {
      buf += ch;
      statements.push(buf);
      buf = "";
      i += 1;
      continue;
    }
    buf += ch;
    i += 1;
  }
  if (buf.trim()) statements.push(buf);
  return statements;
}

async function evRunSql(_lang, code, stdin) {
  const SQL = await evBootSql();
  const db = new SQL.Database();
  let stdout = "";
  const execScript = (script) => {
    for (const statement of evSplitSql(script)) {
      if (!statement.trim()) continue;
      const tables = db.exec(statement);
      for (const table of tables || []) {
        for (const row of table.values) {
          stdout += row.map((v) => (v === null ? "NULL" : String(v))).join(" | ") + "\n";
        }
      }
    }
  };
  try {
    execScript(stdin || "");
    execScript(code || "");
  } catch (err) {
    db.close();
    return {
      status: "runtime_error",
      stdout: evCap(stdout),
      stderr: evCap(`SQL error: ${(err && err.message) || err}`),
      compileOutput: "",
      exitCode: 1,
    };
  }
  db.close();
  return { status: "accepted", stdout: evCap(stdout), stderr: "", compileOutput: "", exitCode: 0 };
}

/* ---------------------------------------------------------------------- Go */
class EvGoExit extends Error {
  constructor(code) {
    super(`os.Exit(${code})`);
    this.evExitCode = Number.isFinite(Number(code)) ? Number(code) : 0;
  }
}

async function evBootGo() {
  if (typeof self.go2jsCompile !== "function") {
    evProgress("go", "Loading Go 1.24 compiler & standard library…");
    importScripts(EV_ASSETS.go + "go2js-compile.js");
  }
}

async function evRunGo(_lang, code, stdin) {
  await evBootGo();
  let compiled;
  try {
    compiled = await new Promise((resolve, reject) => {
      try {
        self.go2jsCompile(String(code || ""), EV_ASSETS.go, (err, out) =>
          err ? reject(new Error(String(err))) : resolve(out)
        );
      } catch (err) {
        reject(err);
      }
    });
  } catch (err) {
    throw evFail("compile_error", String((err && err.message) || err).trim());
  }

  // Install a per-run POSIX descriptor & virtual /tmp filesystem layer so
  // Go's standard library (os.Stdin, fmt.Scan, bufio.NewScanner, io.ReadAll,
  // fmt.Print without trailing newline, os.Stderr, os.WriteFile/ReadFile,
  // os.Exit, goroutines & timers) works identically to native `go run`.
  const enc = new TextEncoder();
  const outDec = new TextDecoder("utf-8", { fatal: false });
  const errDec = new TextDecoder("utf-8", { fatal: false });
  const stdinBytes = enc.encode(String(stdin == null ? "" : stdin));
  let stdinPos = 0;
  let stdout = "";
  let stderr = "";
  let exitCode = 0;

  const files = new Map(); // path -> Uint8Array
  const openFds = new Map(); // fd >= 3 -> { path, pos, flags }
  let nextFd = 3;
  const norm = (p) => {
    const s = String(p || "/tmp").replace(/\\/g, "/");
    const parts = [];
    for (const seg of s.split("/")) {
      if (!seg || seg === ".") continue;
      if (seg === "..") parts.pop();
      else parts.push(seg);
    }
    return "/" + parts.join("/");
  };
  const makeStat = (size, isDir, isChar) => ({
    dev: 0, ino: 1, mode: isDir ? 0o40755 : isChar ? 0o20666 : 0o100644,
    nlink: 1, uid: 1000, gid: 1000, rdev: 0, size,
    blksize: 4096, blocks: Math.ceil(size / 512),
    atimeMs: Date.now(), mtimeMs: Date.now(), ctimeMs: Date.now(), birthtimeMs: Date.now(),
    isDirectory: () => Boolean(isDir),
    isFile: () => Boolean(!isDir && !isChar),
    isBlockDevice: () => false,
    isCharacterDevice: () => Boolean(isChar),
    isSymbolicLink: () => false,
    isFIFO: () => false,
    isSocket: () => false,
  });
  const ebadf = (cb) => { const e = new Error("EBADF"); e.code = "EBADF"; cb(e); };
  const enoent = (cb) => { const e = new Error("ENOENT"); e.code = "ENOENT"; cb(e); };

  const prevFs = self.fs;
  const prevProcess = self.process;
  const originalConsole = { log: console.log, info: console.info, warn: console.warn, error: console.error };
  const fmt = (args) => Array.prototype.map.call(args, (a) => (typeof a === "object" ? JSON.stringify(a) : String(a))).join(" ");
  console.log = (...a) => { stdout += fmt(a) + "\n"; };
  console.info = console.log;
  console.warn = (...a) => { stderr += fmt(a) + "\n"; };
  console.error = (...a) => { stderr += fmt(a) + "\n"; };

  self.fs = {
    constants: {
      O_WRONLY: 1, O_RDWR: 2, O_CREAT: 64, O_EXCL: 128, O_NOCTTY: 256, O_TRUNC: 512, O_APPEND: 1024, O_SYNC: 4096,
    },
    writeSync(fd, buf) {
      const bytes = typeof buf === "string" ? enc.encode(buf) : buf;
      if (fd === 1) {
        stdout += outDec.decode(bytes, { stream: true });
        return bytes.byteLength;
      }
      if (fd === 2) {
        stderr += errDec.decode(bytes, { stream: true });
        return bytes.byteLength;
      }
      const entry = openFds.get(fd);
      if (!entry) return 0;
      const cur = files.get(entry.path) || new Uint8Array(0);
      const pos = (entry.flags & 1024) ? cur.byteLength : entry.pos;
      const end = pos + bytes.byteLength;
      const next = end > cur.byteLength ? new Uint8Array(end) : cur;
      if (next !== cur) next.set(cur, 0);
      next.set(bytes, pos);
      files.set(entry.path, next);
      entry.pos = end;
      return bytes.byteLength;
    },
    write(fd, buf, offset, length, position, callback) {
      const bytes = typeof buf === "string"
        ? enc.encode(buf)
        : buf.subarray(offset || 0, (offset || 0) + (length == null ? buf.byteLength : length));
      if (fd >= 3 && position !== null && position !== undefined && openFds.has(fd)) {
        openFds.get(fd).pos = position;
      }
      callback(null, this.writeSync(fd, bytes));
    },
    read(fd, buffer, offset, length, position, callback) {
      if (fd === 0) {
        if (position !== null && position !== undefined) stdinPos = position;
        const avail = Math.max(0, stdinBytes.byteLength - stdinPos);
        const n = Math.min(length, avail);
        if (n > 0) {
          buffer.set(stdinBytes.subarray(stdinPos, stdinPos + n), offset || 0);
          stdinPos += n;
        }
        callback(null, n);
        return;
      }
      const entry = openFds.get(fd);
      if (!entry) { ebadf(callback); return; }
      const data = files.get(entry.path) || new Uint8Array(0);
      const pos = position !== null && position !== undefined ? position : entry.pos;
      const avail = Math.max(0, data.byteLength - pos);
      const n = Math.min(length, avail);
      if (n > 0) {
        buffer.set(data.subarray(pos, pos + n), offset || 0);
        if (position === null || position === undefined) entry.pos = pos + n;
      }
      callback(null, n);
    },
    open(path, flags, _mode, callback) {
      const p = norm(path);
      if (p === "/dev/stdin") { callback(null, 0); return; }
      if (p === "/dev/stdout") { callback(null, 1); return; }
      if (p === "/dev/stderr") { callback(null, 2); return; }
      const exists = files.has(p);
      if (!exists && !(flags & 64)) { enoent(callback); return; }
      if (exists && (flags & 64) && (flags & 128)) { const e = new Error("EEXIST"); e.code = "EEXIST"; callback(e); return; }
      if (!exists || (flags & 512)) files.set(p, new Uint8Array(0));
      const fd = nextFd++;
      openFds.set(fd, { path: p, pos: 0, flags: flags || 0 });
      callback(null, fd);
    },
    close(fd, callback) { openFds.delete(fd); callback(null); },
    fsync(_fd, callback) { callback(null); },
    fstat(fd, callback) {
      if (fd === 0) { callback(null, makeStat(stdinBytes.byteLength, false, false)); return; }
      if (fd === 1 || fd === 2) { callback(null, makeStat(0, false, true)); return; }
      const entry = openFds.get(fd);
      if (!entry) { ebadf(callback); return; }
      const data = files.get(entry.path) || new Uint8Array(0);
      callback(null, makeStat(data.byteLength, false, false));
    },
    stat(path, callback) {
      const p = norm(path);
      if (p === "/" || p === "/tmp" || p === "/dev") { callback(null, makeStat(0, true, false)); return; }
      if (files.has(p)) { callback(null, makeStat(files.get(p).byteLength, false, false)); return; }
      enoent(callback);
    },
    lstat(path, callback) { this.stat(path, callback); },
    mkdir(_path, _perm, callback) { callback(null); },
    unlink(path, callback) { files.delete(norm(path)); callback(null); },
    rmdir(_path, callback) { callback(null); },
    rename(from, to, callback) {
      const a = norm(from), b = norm(to);
      if (!files.has(a)) { enoent(callback); return; }
      files.set(b, files.get(a));
      files.delete(a);
      callback(null);
    },
    chmod(_path, _mode, callback) { callback(null); },
    fchmod(_fd, _mode, callback) { callback(null); },
    truncate(path, len, callback) {
      const p = norm(path);
      const cur = files.get(p) || new Uint8Array(0);
      const next = new Uint8Array(Number(len) || 0);
      next.set(cur.subarray(0, next.byteLength), 0);
      files.set(p, next);
      callback(null);
    },
    ftruncate(fd, len, callback) {
      const entry = openFds.get(fd);
      if (!entry) { ebadf(callback); return; }
      this.truncate(entry.path, len, callback);
    },
    readdir(path, callback) {
      const prefix = norm(path) === "/" ? "/" : norm(path) + "/";
      const names = new Set();
      for (const k of files.keys()) if (k.startsWith(prefix)) names.add(k.slice(prefix.length).split("/")[0]);
      callback(null, Array.from(names));
    },
  };
  self.process = {
    pid: 42,
    ppid: 1,
    argv: ["go"],
    env: { HOME: "/tmp", TMPDIR: "/tmp", PATH: "/usr/bin:/bin" },
    cwd: () => "/tmp",
    chdir: () => {},
    getuid: () => 1000,
    getgid: () => 1000,
    geteuid: () => 1000,
    getegid: () => 1000,
    getgroups: () => [1000],
    umask: () => 0o022,
    exit: (c) => { throw new EvGoExit(c); },
  };

  // Track timers created while Go executes so goroutines using time.Sleep /
  // time.After finish before we harvest output.
  let pendingTimers = 0;
  const origSetTimeout = self.setTimeout.bind(self);
  const origClearTimeout = self.clearTimeout.bind(self);
  const activeIds = new Set();
  self.setTimeout = (fn, delay, ...args) => {
    pendingTimers += 1;
    const id = origSetTimeout((...cbArgs) => {
      if (activeIds.delete(id)) pendingTimers = Math.max(0, pendingTimers - 1);
      return fn(...cbArgs);
    }, delay, ...args);
    activeIds.add(id);
    return id;
  };
  self.clearTimeout = (id) => {
    if (activeIds.delete(id)) pendingTimers = Math.max(0, pendingTimers - 1);
    return origClearTimeout(id);
  };

  let threw = null;
  try {
    (0, eval)(String(compiled));
    const waitDeadline = Date.now() + 10000;
    while (pendingTimers > 0 && Date.now() < waitDeadline) {
      await new Promise((r) => origSetTimeout(r, 8));
    }
    // Give microtasks / immediate goroutine continuations one final turn.
    await new Promise((r) => origSetTimeout(r, 0));
  } catch (err) {
    if (err instanceof EvGoExit) exitCode = err.evExitCode;
    else threw = err;
  } finally {
    stdout += outDec.decode();
    stderr += errDec.decode();
    self.setTimeout = origSetTimeout;
    self.clearTimeout = origClearTimeout;
    self.fs = prevFs;
    self.process = prevProcess;
    console.log = originalConsole.log;
    console.info = originalConsole.info;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
  }

  if (threw) stderr += (stderr ? "\n" : "") + String((threw && threw.message) || threw);
  const died = Boolean(threw) || exitCode !== 0 || /(^|\n)\s*(panic:|fatal error:)/.test(stderr);
  return {
    status: died ? "runtime_error" : "accepted",
    stdout: evCap(stdout),
    stderr: evCap(stderr),
    compileOutput: "",
    exitCode: died ? (exitCode || 1) : 0,
  };
}

/* -------------------------------------------------------------------- Bash */
async function evBootBash() {
  if (!self.JustBash || typeof self.JustBash.Bash !== "function") {
    if (!EV_ASSETS || !EV_ASSETS.bash) {
      throw new Error("Shell runtime assets are not configured.");
    }
    evProgress("bash", "Loading POSIX Shell / Bash runtime…");
    importScripts(EV_ASSETS.bash + "bash.iife.js");
  }
}

async function evRunBash(_lang, code, stdin) {
  await evBootBash();
  const sh = new self.JustBash.Bash();
  const result = await sh.exec(String(code || ""), { stdin: String(stdin == null ? "" : stdin) });
  const exitCode = Number(result && result.exitCode != null ? result.exitCode : 0);
  return {
    status: exitCode === 0 ? "accepted" : "runtime_error",
    stdout: evCap(result && result.stdout),
    stderr: evCap(result && result.stderr),
    compileOutput: "",
    exitCode,
  };
}

/* -------------------------------------------------------------------- main */
const EV_INIT = {
  c: () => evEnsureClang("c"),
  cpp: () => evEnsureClang("cpp"),
  typescript: evBootTypeScript,
  javascript: async () => {},
  sql: evBootSql,
  go: evBootGo,
  bash: evBootBash,
};

const EV_RUNNERS = {
  c: evRunClang,
  cpp: evRunClang,
  typescript: evRunTypeScript,
  javascript: evRunJavaScript,
  sql: evRunSql,
  go: evRunGo,
  bash: evRunBash,
};

self.onmessage = async (ev) => {
  const msg = ev.data || {};
  if (msg.type === "assets") {
    EV_ASSETS = msg.assets || null;
    return;
  }
  if (msg.type === "init") {
    try {
      if (!EV_ASSETS) throw new Error("Browser runtime assets were not configured.");
      const initFn = EV_INIT[msg.lang];
      if (!initFn) throw new Error(`No browser runtime initializer for "${msg.lang}".`);
      await initFn();
      self.postMessage({ type: "ready", id: msg.id, lang: msg.lang });
    } catch (err) {
      self.postMessage({
        type: "init-error",
        id: msg.id,
        lang: msg.lang,
        error: String((err && err.message) || err),
      });
    }
    return;
  }
  if (msg.type !== "run") return;
  const started = Date.now();
  const done = (result) =>
    self.postMessage({
      type: "result",
      id: msg.id,
      runtimeMs: Math.max(1, Date.now() - started),
      ...result,
    });
  if (!EV_ASSETS) {
    done({ status: "sandbox_unavailable", stdout: "", stderr: "Browser runtime assets were not configured.", compileOutput: "", exitCode: null });
    return;
  }
  const runner = EV_RUNNERS[msg.lang];
  if (!runner) {
    done({ status: "unsupported_language", stdout: "", stderr: `No browser runtime for "${msg.lang}".`, compileOutput: "", exitCode: null });
    return;
  }
  try {
    done(await runner(msg.lang, msg.code, msg.stdin));
  } catch (err) {
    const status = (err && err.evStatus) || "sandbox_unavailable";
    done({
      status,
      stdout: "",
      stderr: evCap(
        status === "compile_error"
          ? String((err && err.message) || err)
          : `The ${msg.lang} browser runtime could not start: ${String((err && err.message) || err)}`
      ),
      compileOutput: status === "compile_error" ? evCap(String((err && err.message) || err)) : "",
      exitCode: null,
    });
  }
};
