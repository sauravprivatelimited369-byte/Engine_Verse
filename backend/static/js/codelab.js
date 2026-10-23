/* ===========================================================================
   EngineVerse CodeLab — Online Compiler
   Modular client architecture:
     1. LanguageRegistry   — single source of truth for executable languages
     2. ExecutionService   — real backend /api/execute client (+ static worker fallback)
     3. LanguageSelector   — active language pills, dropdown, examples & runtime badge
     4. CodeEditor         — gutter line numbers, syntax highlighter, smart indent,
                             bracket matching, formatter, autocomplete & Android keys
     5. InputPanel         — pre-execution stdin panel with sample inputs
     6. OutputConsole      — separated Output / Errors / Compilation tabs & status
     7. ExecutionControls  — Run, Stop (AbortController), Copy, Download, Clear,
                             Reset Starter & Local + Cloud Snippet persistence
     8. CodeLabPage        — orchestrator & mobile viewport switch controller
   =========================================================================== */
(function () {
  "use strict";

  const STORAGE_DRAFT_PREFIX = "ev_codelab_draft_v1:";
  const STORAGE_STDIN_PREFIX = "ev_codelab_stdin_v1:";
  const STORAGE_SNIPPETS_KEY = "ev_codelab_snippets_v1";
  const STORAGE_RECENT_KEY = "ev_codelab_recent_v1";
  const STORAGE_LANG_KEY = "ev_codelab_active_lang_v1";
  const STORAGE_FONT_KEY = "ev_codelab_fontsize_v1";

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function safeStorageGet(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : raw;
    } catch (_err) {
      return fallback;
    }
  }

  function safeStorageSet(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_err) {
      /* storage quota / private mode */
    }
  }

  function toastMessage(msg) {
    const el = document.getElementById("ev-toast");
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
    el.classList.add("show");
    clearTimeout(toastMessage._t);
    toastMessage._t = setTimeout(() => {
      el.classList.remove("show");
    }, 2400);
  }

  /* -------------------------------------------------------------------------
     1. LanguageRegistry
     ------------------------------------------------------------------------- */
  class LanguageRegistry {
    constructor(bootstrap) {
      this._languages = new Map();
      this._provider = { name: "disabled", available: false, runnableCount: 0 };
      this._limits = { maxSourceChars: 65536, maxStdinChars: 20000 };
      this.mode = "server";
      if (bootstrap) {
        this.hydrate(bootstrap);
      }
    }

    hydrate(payload) {
      if (!payload || !Array.isArray(payload.languages)) return;
      this._languages.clear();
      this._provider = payload.provider || this._provider;
      this._limits = payload.limits || this._limits;
      for (const entry of payload.languages) {
        this._languages.set(entry.id, { ...entry });
      }
    }

    markStaticBrowserFallback(pyodideAvailable, runtimeLanguages = []) {
      this.mode = "static";
      // Real compilers/interpreters vendored for the browser (see
      // scripts/fetch_browser_runtimes.py); the manifest decides which of
      // these this copy carries. CodeLab ids match the runtime slugs.
      const BROWSER_ENGINES = {
        c: "Clang 22 (GNU17 WebAssembly) in browser",
        cpp: "Clang 22 (GNU++20 WebAssembly) in browser",
        java: "OpenJDK + TeaVM (WebAssembly) in browser",
        typescript: "TypeScript 5.9 compiler in browser",
        go: "Go 1.24 (GopherJS) in browser",
        rust: "rustc/Miri (WebAssembly) in browser",
        csharp: "Roslyn (.NET WebAssembly) in browser",
        sql: "SQLite (WebAssembly) in browser",
        bash: "Bash (POSIX shell) in browser",
      };
      for (const [id, spec] of this._languages.entries()) {
        if (id === "javascript") {
          spec.available = true;
          spec.runtimeLabel = "Node-compatible Browser Web Worker";
        } else if (id === "python" && pyodideAvailable) {
          spec.available = true;
          spec.runtimeLabel = "CPython 3.12 WebAssembly (Pyodide Worker)";
        } else if (BROWSER_ENGINES[id] && runtimeLanguages.includes(id)) {
          spec.available = true;
          spec.runtimeLabel = BROWSER_ENGINES[id];
        } else {
          spec.available = false;
          spec.runtimeLabel = `${spec.name} requires a live EngineVerse server runtime`;
        }
      }
      const runnableCount = this.executableLanguages().length;
      this._provider = {
        name: "browser-worker",
        available: runnableCount > 0,
        runnableCount,
      };
    }

    allLanguages() {
      return Array.from(this._languages.values());
    }

    executableLanguages() {
      return this.allLanguages().filter((lang) => Boolean(lang.available));
    }

    unavailableLanguages() {
      return this.allLanguages().filter((lang) => !lang.available);
    }

    get(id) {
      return this._languages.get(String(id || "").toLowerCase()) || null;
    }

    provider() {
      return this._provider;
    }

    limits() {
      return this._limits;
    }
  }

  /* -------------------------------------------------------------------------
     2. ExecutionService
     ------------------------------------------------------------------------- */
  class ExecutionService {
    constructor(registry) {
      this.registry = registry;
      this._controller = null;
      this._worker = null;
    }

    get isRunning() {
      return Boolean(this._controller || this._worker);
    }

    abort() {
      if (this._controller) {
        this._controller.abort();
        this._controller = null;
      }
      if (this._worker) {
        this._worker.terminate();
        this._worker = null;
      }
    }

    async refreshCapabilities() {
      try {
        const res = await fetch("api/codelab/languages".startsWith("/") ? "/api/codelab/languages" : "/api/codelab/languages", {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        const ct = res.headers.get("content-type") || "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          if (data && Array.isArray(data.languages)) {
            this.registry.mode = "server";
            this.registry.hydrate(data);
            return;
          }
        }
        if (res.status === 404 || res.status === 405 || !ct.includes("application/json")) {
          await this._probeStaticFallback();
        }
      } catch (_err) {
        await this._probeStaticFallback();
      }
    }

    async _probeStaticFallback() {
      // The exported pages carry an #ev-live boot config (base + runtime
      // URLs); use it when present so subpath deployments resolve too.
      let cfg = {};
      try {
        cfg = JSON.parse(document.getElementById("ev-live")?.textContent || "{}");
      } catch (_e) {
        cfg = {};
      }
      const base = cfg.base || "./";
      let pyReady = false;
      try {
        const check = await fetch(`${cfg.pyodide || `${base}pyodide/`}pyodide.js`, { method: "HEAD" });
        pyReady = check.ok;
      } catch (_e) {
        pyReady = false;
      }
      let runtimeLanguages = [];
      try {
        const res = await fetch(`${cfg.runtimes || `${base}runtimes/`}manifest.json`);
        if (res.ok) {
          const manifest = await res.json();
          runtimeLanguages = [
            ...new Set(
              Object.values(manifest.runtimes || {}).flatMap((rt) => rt.languages || []),
            ),
          ];
        }
      } catch (_e) {
        /* no vendored runtimes in this copy - languages stay server-only */
      }
      this.registry.markStaticBrowserFallback(pyReady, runtimeLanguages);
    }

    async execute({ language, sourceCode, stdin }) {
      const spec = this.registry.get(language);
      if (!spec) {
        return {
          ok: false,
          executed: false,
          language,
          stdout: "",
          stderr: `Unsupported language "${language}".`,
          compileOutput: "",
          exitCode: null,
          executionTime: 0,
          status: "service_unavailable",
        };
      }
      if (!spec.available) {
        return {
          ok: false,
          executed: false,
          language: spec.id,
          languageName: spec.name,
          runtime: spec.runtimeLabel,
          stdout: "",
          stderr: `${spec.name} runtime is not configured on this host. Only genuinely installed compilers are executed.`,
          compileOutput: "",
          exitCode: null,
          executionTime: 0,
          status: "service_unavailable",
        };
      }
      if (!sourceCode || !sourceCode.trim()) {
        return {
          ok: false,
          executed: false,
          language: spec.id,
          languageName: spec.name,
          runtime: spec.runtimeLabel,
          stdout: "",
          stderr: "Editor is empty — write code or choose an Example program first.",
          compileOutput: "",
          exitCode: 1,
          executionTime: 0,
          status: "runtime_error",
          emptyCode: true,
        };
      }

      if (this.registry.mode === "static") {
        return this._executeInIsolatedWorker(spec, sourceCode, stdin || "");
      }

      this.abort();
      const controller = new AbortController();
      this._controller = controller;
      try {
        const response = await fetch("/api/execute", {
          method: "POST",
          credentials: "same-origin",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRF-Token": csrfToken(),
          },
          body: JSON.stringify({
            language: spec.id,
            sourceCode,
            stdin: stdin || "",
          }),
        });
        if (response.status === 429) {
          return {
            ok: false,
            executed: false,
            language: spec.id,
            languageName: spec.name,
            runtime: spec.runtimeLabel,
            stdout: "",
            stderr: "Rate limit reached — please wait a few seconds before running again.",
            compileOutput: "",
            exitCode: null,
            executionTime: 0,
            status: "service_unavailable",
          };
        }
        const payload = await response.json();
        return payload;
      } catch (err) {
        if (err && err.name === "AbortError") {
          return {
            ok: false,
            aborted: true,
            executed: false,
            language: spec.id,
            languageName: spec.name,
            runtime: spec.runtimeLabel,
            stdout: "",
            stderr: "Execution stopped by user.",
            compileOutput: "",
            exitCode: null,
            executionTime: 0,
            status: "idle",
          };
        }
        return {
          ok: false,
          executed: false,
          language: spec.id,
          languageName: spec.name,
          runtime: spec.runtimeLabel,
          stdout: "",
          stderr: "Could not reach the execution server. Check your connection and try again.",
          compileOutput: "",
          exitCode: null,
          executionTime: 0,
          status: "service_unavailable",
        };
      } finally {
        if (this._controller === controller) {
          this._controller = null;
        }
      }
    }

    async _executeInIsolatedWorker(spec, sourceCode, stdin) {
      if (typeof window.EV_BROWSER_TERMINAL === "function") {
        const r = await window.EV_BROWSER_TERMINAL(spec.id, sourceCode, stdin || "");
        const rawStatus = r.status || "runtime_error";
        const mappedStatus =
          rawStatus === "accepted"
            ? "success"
            : rawStatus === "compile_error"
            ? "compilation_error"
            : rawStatus === "sandbox_unavailable" || rawStatus === "unsupported_language"
            ? "service_unavailable"
            : rawStatus;
        return {
          ok: rawStatus === "accepted",
          executed: r.executed !== false,
          language: spec.id,
          languageName: spec.name,
          runtime: r.via || spec.runtimeLabel,
          stdout: r.stdout || "",
          stderr: mappedStatus === "compilation_error" ? "" : r.stderr || "",
          compileOutput:
            r.compileOutput || (mappedStatus === "compilation_error" ? r.stderr || "" : ""),
          exitCode: r.exitCode != null ? r.exitCode : rawStatus === "accepted" ? 0 : 1,
          executionTime: r.runtimeMs || 0,
          status: mappedStatus,
        };
      }
      if (spec.id === "python") {
        return this._executePythonWasmWorker(spec, sourceCode, stdin);
      }
      if (spec.id !== "javascript") {
        return {
          ok: false,
          executed: false,
          language: spec.id,
          languageName: spec.name,
          runtime: spec.runtimeLabel,
          stdout: "",
          stderr: `${spec.name} requires a live server compiler and cannot be simulated in a static browser page.`,
          compileOutput: "",
          exitCode: null,
          executionTime: 0,
          status: "service_unavailable",
        };
      }
      return new Promise((resolve) => {
        const started = performance.now();
        const workerSrc = `
          self.onmessage = async (ev) => {
            const { code, stdin } = ev.data;
            let stdout = "";
            let stderr = "";
            const fmt = (args) => args.map((v) => typeof v === "string" ? v : JSON.stringify(v)).join(" ");
            self.console = {
              log: (...a) => { stdout += fmt(a) + "\\n"; },
              info: (...a) => { stdout += fmt(a) + "\\n"; },
              warn: (...a) => { stderr += fmt(a) + "\\n"; },
              error: (...a) => { stderr += fmt(a) + "\\n"; }
            };
            self.__STDIN__ = stdin;
            let fn;
            try {
              fn = new Function(code);
            } catch (syntaxErr) {
              self.postMessage({ status: "compilation_error", stdout: "", stderr: "", compileOutput: String(syntaxErr.stack || syntaxErr), exitCode: 1 });
              return;
            }
            try {
              await fn();
              self.postMessage({ status: "success", stdout, stderr, compileOutput: "", exitCode: 0 });
            } catch (runErr) {
              self.postMessage({ status: "runtime_error", stdout, stderr: (stderr ? stderr + "\\n" : "") + String(runErr.stack || runErr), compileOutput: "", exitCode: 1 });
            }
          };
        `;
        const blob = new Blob([workerSrc], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        const worker = new Worker(url);
        this._worker = worker;
        const timer = setTimeout(() => {
          worker.terminate();
          URL.revokeObjectURL(url);
          this._worker = null;
          resolve({
            ok: true,
            executed: true,
            language: "javascript",
            languageName: "JavaScript",
            runtime: spec.runtimeLabel,
            stdout: "",
            stderr: "Time limit exceeded (5000 ms) — isolated Web Worker terminated.",
            compileOutput: "",
            exitCode: 124,
            executionTime: Math.round(performance.now() - started),
            status: "timeout",
          });
        }, 5000);
        worker.onmessage = (event) => {
          clearTimeout(timer);
          worker.terminate();
          URL.revokeObjectURL(url);
          this._worker = null;
          resolve({
            ok: true,
            executed: true,
            language: "javascript",
            languageName: "JavaScript",
            runtime: spec.runtimeLabel,
            ...event.data,
            executionTime: Math.round(performance.now() - started),
          });
        };
        worker.onerror = (err) => {
          clearTimeout(timer);
          worker.terminate();
          URL.revokeObjectURL(url);
          this._worker = null;
          resolve({
            ok: true,
            executed: true,
            language: "javascript",
            languageName: "JavaScript",
            runtime: spec.runtimeLabel,
            stdout: "",
            stderr: err.message || "Worker execution error.",
            compileOutput: "",
            exitCode: 1,
            executionTime: Math.round(performance.now() - started),
            status: "runtime_error",
          });
        };
        worker.postMessage({ code: sourceCode, stdin });
      });
    }

    _executePythonWasmWorker(spec, sourceCode, stdin) {
      return new Promise((resolve) => {
        const started = performance.now();
        const baseUrl = new URL("./pyodide/", window.location.href).href;
        const workerSrc = `
          self.onmessage = async (ev) => {
            const { code, stdin, baseUrl } = ev.data;
            let stdout = "";
            let stderr = "";
            try {
              importScripts(baseUrl + "pyodide.js");
              const pyodide = await loadPyodide({ indexURL: baseUrl });
              const lines = String(stdin || "").split("\\n");
              let idx = 0;
              pyodide.setStdin({ stdin: () => (idx < lines.length ? lines[idx++] + "\\n" : null) });
              pyodide.setStdout({ batched: (msg) => { stdout += msg + "\\n"; } });
              pyodide.setStderr({ batched: (msg) => { stderr += msg + "\\n"; } });
              pyodide.globals.set("__ev_src", code);
              try {
                await pyodide.runPythonAsync("compile(__ev_src, 'main.py', 'exec')");
              } catch (syntaxErr) {
                self.postMessage({ status: "compilation_error", stdout: "", stderr: "", compileOutput: String(syntaxErr), exitCode: 1 });
                return;
              }
              try {
                await pyodide.runPythonAsync("exec(compile(__ev_src, 'main.py', 'exec'), {'__name__': '__main__'})");
                self.postMessage({ status: "success", stdout, stderr, compileOutput: "", exitCode: 0 });
              } catch (runErr) {
                self.postMessage({ status: "runtime_error", stdout, stderr: (stderr ? stderr + "\\n" : "") + String(runErr), compileOutput: "", exitCode: 1 });
              }
            } catch (loadErr) {
              self.postMessage({ status: "service_unavailable", stdout: "", stderr: "CPython WASM runtime unavailable: " + String(loadErr), compileOutput: "", exitCode: null });
            }
          };
        `;
        const blob = new Blob([workerSrc], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        const worker = new Worker(url);
        this._worker = worker;
        const timer = setTimeout(() => {
          worker.terminate();
          URL.revokeObjectURL(url);
          this._worker = null;
          resolve({
            ok: true,
            executed: true,
            language: "python",
            languageName: "Python 3",
            runtime: spec.runtimeLabel,
            stdout: "",
            stderr: "Time limit exceeded — CPython WebAssembly worker terminated.",
            compileOutput: "",
            exitCode: 124,
            executionTime: Math.round(performance.now() - started),
            status: "timeout",
          });
        }, 180000);
        worker.onmessage = (event) => {
          clearTimeout(timer);
          worker.terminate();
          URL.revokeObjectURL(url);
          this._worker = null;
          resolve({
            ok: event.data.status !== "service_unavailable",
            executed: event.data.status !== "service_unavailable",
            language: "python",
            languageName: "Python 3",
            runtime: spec.runtimeLabel,
            ...event.data,
            executionTime: Math.round(performance.now() - started),
          });
        };
        worker.postMessage({ code: sourceCode, stdin, baseUrl });
      });
    }
  }

  /* -------------------------------------------------------------------------
     Syntax Highlighter + Formatter Utilities (used by CodeEditor)
     ------------------------------------------------------------------------- */
  const PAIRS = { "(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`" };
  const CLOSERS = new Set([")", "]", "}", '"', "'", "`"]);
  const BRACKET_MATCH = { "(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{" };

  function highlightSource(source, spec) {
    if (!source) return "\n";
    const family = (spec && spec.syntaxFamily) || "clike";
    const keywords = new Set((spec && spec.keywords) || []);
    const tokenPattern =
      family === "python"
        ? /('''[\s\S]*?'''|"""[\s\S]*?"""|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|#[^\n]*|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b)/g
        : family === "sql"
        ? /('(?:''|[^'])*'|"(?:\\.|[^"\\])*"|--[^\n]*|\/\*[\s\S]*?\*\/|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b)/g
        : family === "shell"
        ? /('[^']*'|"(?:\\.|[^"\\])*"|#[^\n]*|\$[A-Za-z_][A-Za-z0-9_]*|\b\d+\b|\b[A-Za-z_][A-Za-z0-9_]*\b)/g
        : /(\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|#[A-Za-z_]+|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*!?(?=\s*\()|\b[A-Za-z_][A-Za-z0-9_]*\b)/g;

    let last = 0;
    let html = "";
    let match;
    while ((match = tokenPattern.exec(source)) !== null) {
      if (match.index > last) {
        html += escapeHtml(source.slice(last, match.index));
      }
      const tok = match[0];
      let cls = "";
      if (
        tok.startsWith("//") ||
        tok.startsWith("/*") ||
        (family === "sql" && tok.startsWith("--")) ||
        ((family === "python" || family === "shell") && tok.startsWith("#"))
      ) {
        cls = "tok-com";
      } else if (
        tok.startsWith('"') ||
        tok.startsWith("'") ||
        tok.startsWith("`")
      ) {
        cls = "tok-str";
      } else if (/^\d/.test(tok)) {
        cls = "tok-num";
      } else if (tok.startsWith("#") || tok.startsWith("$")) {
        cls = "tok-meta";
      } else if (
        keywords.has(tok) ||
        (family === "sql" && keywords.has(tok.toUpperCase()))
      ) {
        cls = /^[A-Z][A-Za-z0-9_]*$/.test(tok) && family !== "sql" ? "tok-type" : "tok-kw";
      } else if (/^[A-Z][A-Za-z0-9_]*$/.test(tok)) {
        cls = "tok-type";
      } else {
        const after = source.slice(match.index + tok.length, match.index + tok.length + 2);
        if (after.startsWith("(")) {
          cls = "tok-fn";
        }
      }
      html += cls ? `<span class="${cls}">${escapeHtml(tok)}</span>` : escapeHtml(tok);
      last = match.index + tok.length;
    }
    if (last < source.length) {
      html += escapeHtml(source.slice(last));
    }
    if (source.endsWith("\n")) {
      html += " ";
    }
    return html;
  }

  function formatSourceCode(source, spec) {
    if (!source || !source.trim()) return source;
    const indentUnit = spec && spec.id === "go" ? "\t" : " ".repeat((spec && spec.indentSize) || 4);
    const family = (spec && spec.syntaxFamily) || "clike";

    if (family === "python" || family === "shell") {
      return (
        source
          .replace(/\r\n/g, "\n")
          .split("\n")
          .map((line) => line.replace(/\t/g, indentUnit).replace(/[ \t]+$/g, ""))
          .join("\n")
          .replace(/\n{3,}/g, "\n\n")
          .trimEnd() + "\n"
      );
    }

    if (family === "sql") {
      const clauses = [
        "SELECT", "FROM", "WHERE", "LEFT JOIN", "INNER JOIN", "JOIN",
        "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "INSERT INTO", "VALUES",
        "UPDATE", "SET", "DELETE FROM", "CREATE TABLE",
      ];
      let formatted = source.replace(/\r\n/g, "\n");
      for (const kw of clauses) {
        const re = new RegExp(`\\b${kw.replace(/ /g, "\\s+")}\\b`, "gi");
        formatted = formatted.replace(re, kw);
      }
      return (
        formatted
          .split("\n")
          .map((l) => l.replace(/[ \t]+$/g, ""))
          .join("\n")
          .trimEnd() + "\n"
      );
    }

    // Brace-delimited formatter (C, C++, Java, JS, TS, Go, Rust, C#)
    const lines = source.replace(/\r\n/g, "\n").split("\n");
    let depth = 0;
    const out = [];
    for (const rawLine of lines) {
      const trimmed = rawLine.trim();
      if (!trimmed) {
        out.push("");
        continue;
      }
      const leadingClose = (trimmed.match(/^[}\])]+/) || [""])[0].length;
      const effectiveDepth = Math.max(0, depth - leadingClose);
      const prefix = trimmed.startsWith("#") ? "" : indentUnit.repeat(effectiveDepth);
      out.push(prefix + trimmed);

      const stripped = trimmed
        .replace(/\/\/.*$/, "")
        .replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`/g, "");
      for (const ch of stripped) {
        if (ch === "{" || ch === "(" || ch === "[") depth++;
        else if (ch === "}" || ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
      }
    }
    return out.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + "\n";
  }

  /* -------------------------------------------------------------------------
     3. CodeEditor
     ------------------------------------------------------------------------- */
  class CodeEditor {
    constructor(elements, onRunShortcut, onChange) {
      this.textarea = elements.textarea;
      this.highlightCode = elements.highlightCode;
      this.highlightPre = elements.highlightPre;
      this.gutter = elements.gutter;
      this.cursorInfo = elements.cursorInfo;
      this.bracketInfo = elements.bracketInfo;
      this.acBox = elements.acBox;
      this.symbolBar = elements.symbolBar;
      this.onRunShortcut = onRunShortcut;
      this.onChange = onChange;
      this.spec = null;
      this._acItems = [];
      this._acIndex = 0;
      this._acPrefixStart = 0;
      this._fontSize = Number(safeStorageGet(STORAGE_FONT_KEY, 0)) || 0;
      if (this._fontSize >= 12 && this._fontSize <= 22) {
        document.documentElement.style.setProperty("--cl-font-size", `${this._fontSize}px`);
      }
      this._bind();
    }

    setLanguageSpec(spec) {
      this.spec = spec;
      if (spec) {
        this.textarea.style.tabSize = String(spec.indentSize || 4);
        this.highlightPre.style.tabSize = String(spec.indentSize || 4);
      }
      this.hideAutocomplete();
      this.render();
    }

    getValue() {
      return this.textarea.value;
    }

    setValue(code) {
      this.textarea.value = typeof code === "string" ? code : "";
      this.textarea.scrollTop = 0;
      this.textarea.scrollLeft = 0;
      this.hideAutocomplete();
      this.render();
      this._syncScroll();
    }

    adjustFontSize(delta) {
      const current =
        parseFloat(getComputedStyle(this.textarea).fontSize) || 14.5;
      const next = Math.min(22, Math.max(12, Math.round((current + delta) * 2) / 2));
      this._fontSize = next;
      document.documentElement.style.setProperty("--cl-font-size", `${next}px`);
      safeStorageSet(STORAGE_FONT_KEY, String(next));
      this._syncScroll();
    }

    format() {
      const formatted = formatSourceCode(this.getValue(), this.spec);
      if (formatted !== this.getValue()) {
        const pos = this.textarea.selectionStart;
        this.setValue(formatted);
        const clamped = Math.min(pos, formatted.length);
        this.textarea.setSelectionRange(clamped, clamped);
        this._updateCursorStatus();
        if (this.onChange) this.onChange(formatted);
      }
    }

    insertSymbol(token) {
      const ta = this.textarea;
      ta.focus();
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const val = ta.value;

      if (token === "TAB") {
        const unit = " ".repeat((this.spec && this.spec.indentSize) || 4);
        this._replaceRange(start, end, unit, start + unit.length);
        return;
      }
      if (token === "LEFT") {
        const p = Math.max(0, start - 1);
        ta.setSelectionRange(p, p);
        this._updateCursorStatus();
        return;
      }
      if (token === "RIGHT") {
        const p = Math.min(val.length, end + 1);
        ta.setSelectionRange(p, p);
        this._updateCursorStatus();
        return;
      }
      if (PAIRS[token] && start === end) {
        const pair = token + PAIRS[token];
        this._replaceRange(start, end, pair, start + 1);
        return;
      }
      this._replaceRange(start, end, token, start + token.length);
    }

    _replaceRange(start, end, insertion, caretAfter) {
      const ta = this.textarea;
      const val = ta.value;
      ta.value = val.slice(0, start) + insertion + val.slice(end);
      ta.setSelectionRange(caretAfter, caretAfter);
      this.render();
      this._updateCursorStatus();
      if (this.onChange) this.onChange(ta.value);
    }

    render() {
      const val = this.textarea.value;
      const lineCount = Math.max(1, val.split("\n").length);
      let nums = "";
      for (let i = 1; i <= lineCount; i++) {
        nums += i + "\n";
      }
      this.gutter.textContent = nums;
      this.highlightCode.innerHTML = highlightSource(val, this.spec);
      this._updateCursorStatus();
    }

    _syncScroll() {
      this.highlightPre.scrollTop = this.textarea.scrollTop;
      this.highlightPre.scrollLeft = this.textarea.scrollLeft;
      this.gutter.scrollTop = this.textarea.scrollTop;
    }

    _updateCursorStatus() {
      const val = this.textarea.value;
      const pos = this.textarea.selectionStart || 0;
      const before = val.slice(0, pos);
      const lines = before.split("\n");
      const ln = lines.length;
      const col = lines[lines.length - 1].length + 1;
      if (this.cursorInfo) {
        this.cursorInfo.textContent = `Ln ${ln}, Col ${col} · ${val.length.toLocaleString()} chars`;
      }
      if (this.bracketInfo) {
        const matchInfo = this._findMatchingBracket(val, pos);
        this.bracketInfo.textContent = matchInfo || "";
      }
    }

    _findMatchingBracket(val, pos) {
      const idx = BRACKET_MATCH[val[pos]] ? pos : BRACKET_MATCH[val[pos - 1]] ? pos - 1 : -1;
      if (idx < 0) return "";
      const ch = val[idx];
      const target = BRACKET_MATCH[ch];
      const forward = ch === "(" || ch === "[" || ch === "{";
      let depth = 0;
      for (let i = idx; forward ? i < val.length : i >= 0; i += forward ? 1 : -1) {
        if (val[i] === ch) depth++;
        else if (val[i] === target) {
          depth--;
          if (depth === 0) {
            const matchLine = val.slice(0, i).split("\n").length;
            return `Matched ${ch}${target} (Ln ${matchLine})`;
          }
        }
      }
      return `Unclosed ${ch}`;
    }

    _updateAutocomplete() {
      const val = this.textarea.value;
      const pos = this.textarea.selectionStart;
      if (pos !== this.textarea.selectionEnd) {
        this.hideAutocomplete();
        return;
      }
      const prefixMatch = val.slice(0, pos).match(/([#A-Za-z_][A-Za-z0-9_!]*)$/);
      if (!prefixMatch || prefixMatch[1].length < 2) {
        this.hideAutocomplete();
        return;
      }
      const prefix = prefixMatch[1];
      this._acPrefixStart = pos - prefix.length;
      const pool = new Set((this.spec && this.spec.keywords) || []);
      const fileWords = val.match(/\b[A-Za-z_][A-Za-z0-9_]{2,}\b/g) || [];
      for (const w of fileWords) pool.add(w);

      const lower = prefix.toLowerCase();
      const matches = Array.from(pool)
        .filter((w) => w !== prefix && w.toLowerCase().startsWith(lower))
        .slice(0, 6);

      if (!matches.length) {
        this.hideAutocomplete();
        return;
      }
      this._acItems = matches;
      this._acIndex = 0;
      this._renderAutocomplete();
    }

    _renderAutocomplete() {
      if (!this.acBox || !this._acItems.length) return;
      this.acBox.innerHTML = "";
      const label = document.createElement("span");
      label.className = "cl-ac-label";
      label.textContent = "Suggest:";
      this.acBox.appendChild(label);
      this._acItems.forEach((word, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cl-ac-item" + (idx === this._acIndex ? " selected" : "");
        btn.textContent = word;
        btn.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          this._acceptAutocomplete(word);
        });
        btn.addEventListener("click", (ev) => {
          ev.preventDefault();
          this._acceptAutocomplete(word);
        });
        this.acBox.appendChild(btn);
      });
      this.acBox.hidden = false;
    }

    _acceptAutocomplete(word) {
      const chosen = word || this._acItems[this._acIndex];
      if (!chosen) return;
      const pos = this.textarea.selectionEnd;
      this.hideAutocomplete();
      this._replaceRange(this._acPrefixStart, pos, chosen, this._acPrefixStart + chosen.length);
      this.textarea.focus();
    }

    hideAutocomplete() {
      this._acItems = [];
      this._acIndex = 0;
      if (this.acBox) {
        this.acBox.hidden = true;
      }
    }

    _bind() {
      const ta = this.textarea;
      ta.addEventListener("scroll", () => this._syncScroll());
      ta.addEventListener("click", () => this._updateCursorStatus());
      ta.addEventListener("keyup", (ev) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(ev.key)) {
          this._updateCursorStatus();
        }
      });

      ta.addEventListener("input", () => {
        this.render();
        this._syncScroll();
        this._updateAutocomplete();
        if (this.onChange) this.onChange(ta.value);
      });

      ta.addEventListener("keydown", (ev) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
          ev.preventDefault();
          this.hideAutocomplete();
          if (this.onRunShortcut) this.onRunShortcut();
          return;
        }
        if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && ev.key.toLowerCase() === "f") {
          ev.preventDefault();
          this.format();
          return;
        }
        if (ev.ctrlKey && ev.key === " ") {
          ev.preventDefault();
          this._updateAutocomplete();
          return;
        }

        if (!this.acBox.hidden && this._acItems.length) {
          if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this._acIndex = (this._acIndex + 1) % this._acItems.length;
            this._renderAutocomplete();
            return;
          }
          if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this._acIndex = (this._acIndex - 1 + this._acItems.length) % this._acItems.length;
            this._renderAutocomplete();
            return;
          }
          if (ev.key === "Escape") {
            ev.preventDefault();
            this.hideAutocomplete();
            return;
          }
          if (ev.key === "Tab" && !ev.shiftKey) {
            ev.preventDefault();
            this._acceptAutocomplete();
            return;
          }
        }

        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        const val = ta.value;
        const indent = " ".repeat((this.spec && this.spec.indentSize) || 4);

        if (ev.key === "Tab") {
          ev.preventDefault();
          if (start === end && !ev.shiftKey) {
            this._replaceRange(start, end, indent, start + indent.length);
            return;
          }
          const lineStart = val.lastIndexOf("\n", start - 1) + 1;
          const lineEndIdx = val.indexOf("\n", end);
          const blockEnd = lineEndIdx === -1 ? val.length : lineEndIdx;
          const lines = val.slice(lineStart, blockEnd).split("\n");
          const updated = lines.map((line) => {
            if (ev.shiftKey) {
              if (line.startsWith(indent)) return line.slice(indent.length);
              if (line.startsWith("\t")) return line.slice(1);
              return line.replace(/^ {1,4}/, "");
            }
            return indent + line;
          });
          const joined = updated.join("\n");
          ta.value = val.slice(0, lineStart) + joined + val.slice(blockEnd);
          ta.setSelectionRange(lineStart, lineStart + joined.length);
          this.render();
          if (this.onChange) this.onChange(ta.value);
          return;
        }

        if (ev.key === "Enter" && !ev.isComposing) {
          ev.preventDefault();
          this.hideAutocomplete();
          const lineStart = val.lastIndexOf("\n", start - 1) + 1;
          const currentLine = val.slice(lineStart, start);
          const baseIndent = (currentLine.match(/^[ \t]*/) || [""])[0];
          const trimmed = currentLine.trimEnd();
          const lastChar = trimmed[trimmed.length - 1] || "";
          const nextChar = val[end] || "";
          const opensBlock =
            lastChar === "{" ||
            lastChar === "[" ||
            lastChar === "(" ||
            (this.spec && this.spec.syntaxFamily === "python" && lastChar === ":");

          if (opensBlock && BRACKET_MATCH[lastChar] && nextChar === BRACKET_MATCH[lastChar]) {
            const inner = `\n${baseIndent}${indent}\n${baseIndent}`;
            const caret = start + 1 + baseIndent.length + indent.length;
            this._replaceRange(start, end, inner, caret);
            return;
          }
          const extra = opensBlock ? indent : "";
          const insert = `\n${baseIndent}${extra}`;
          this._replaceRange(start, end, insert, start + insert.length);
          return;
        }

        if (CLOSERS.has(ev.key) && start === end && val[start] === ev.key) {
          ev.preventDefault();
          ta.setSelectionRange(start + 1, start + 1);
          this._updateCursorStatus();
          return;
        }

        if (PAIRS[ev.key] && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
          if (start !== end) {
            ev.preventDefault();
            const wrapped = ev.key + val.slice(start, end) + PAIRS[ev.key];
            ta.value = val.slice(0, start) + wrapped + val.slice(end);
            ta.setSelectionRange(start + 1, end + 1);
            this.render();
            if (this.onChange) this.onChange(ta.value);
            return;
          }
          const nextCh = val[start] || "";
          if (!nextCh || /[\s)\]};,>]/.test(nextCh)) {
            ev.preventDefault();
            this._replaceRange(start, end, ev.key + PAIRS[ev.key], start + 1);
          }
        }
      });

      if (this.symbolBar) {
        this.symbolBar.addEventListener("click", (ev) => {
          const btn = ev.target.closest("[data-sym]");
          if (!btn) return;
          ev.preventDefault();
          this.insertSymbol(btn.dataset.sym);
        });
      }
    }
  }

  /* -------------------------------------------------------------------------
     4. InputPanel
     ------------------------------------------------------------------------- */
  class InputPanel {
    constructor(elements, onChange) {
      this.box = elements.stdinBox;
      this.meta = elements.stdinMeta;
      this.clearBtn = elements.clearStdinBtn;
      this.sampleBtn = elements.sampleStdinBtn;
      this.onChange = onChange;
      this._sampleStdin = "";
      this._bind();
    }

    setSampleStdin(sample) {
      this._sampleStdin = typeof sample === "string" ? sample : "";
    }

    getValue() {
      return this.box ? this.box.value : "";
    }

    setValue(val) {
      if (!this.box) return;
      this.box.value = typeof val === "string" ? val : "";
      this._updateMeta();
    }

    _updateMeta() {
      if (!this.meta || !this.box) return;
      const val = this.box.value;
      const lines = val ? val.split("\n").length : 0;
      this.meta.textContent = val ? `${lines} line${lines === 1 ? "" : "s"} · ${val.length} B` : "Optional";
    }

    _bind() {
      if (this.box) {
        this.box.addEventListener("input", () => {
          this._updateMeta();
          if (this.onChange) this.onChange(this.box.value);
        });
      }
      if (this.clearBtn) {
        this.clearBtn.addEventListener("click", () => {
          this.setValue("");
          if (this.onChange) this.onChange("");
        });
      }
      if (this.sampleBtn) {
        this.sampleBtn.addEventListener("click", () => {
          this.setValue(this._sampleStdin);
          if (this.onChange) this.onChange(this._sampleStdin);
          toastMessage("Loaded sample stdin input.");
        });
      }
    }
  }

  /* -------------------------------------------------------------------------
     5. OutputConsole
     ------------------------------------------------------------------------- */
  const STATUS_LABELS = {
    idle: "Idle",
    running: "Running…",
    success: "Success",
    compilation_error: "Compilation Error",
    runtime_error: "Runtime Error",
    timeout: "Timeout",
    service_unavailable: "Service Unavailable",
  };

  class OutputConsole {
    constructor(elements) {
      this.statusPill = elements.statusPill;
      this.metaRuntime = elements.metaRuntime;
      this.metaMetrics = elements.metaMetrics;
      this.emptyState = elements.emptyState;
      this.stdoutPre = elements.stdoutPre;
      this.stderrPre = elements.stderrPre;
      this.compilePre = elements.compilePre;
      this.tabs = elements.tabs;
      this.counts = elements.counts;
      this.activeTab = "output";
      this._elapsedTimer = null;
      this._lastResult = null;
      this._bind();
    }

    setRunning(runtimeName) {
      this._stopTimer();
      const started = performance.now();
      this._setStatus("running", "Running (0.0s)");
      this.metaRuntime.textContent = runtimeName || "Executing in isolated sandbox…";
      this.metaMetrics.textContent = "Running…";
      this.emptyState.hidden = false;
      this.emptyState.innerHTML =
        "<p><strong>Compiling &amp; executing real code…</strong></p>" +
        "<p class=\"tiny\">Isolated process with CPU, memory, and timeout limits active.</p>";
      this.stdoutPre.hidden = true;
      this.stderrPre.hidden = true;
      this.compilePre.hidden = true;
      this._elapsedTimer = setInterval(() => {
        const secs = ((performance.now() - started) / 1000).toFixed(1);
        this._setStatus("running", `Running (${secs}s)`);
      }, 100);
    }

    renderResult(res) {
      this._stopTimer();
      this._lastResult = res;
      const status = res.status || "idle";
      this._setStatus(status, STATUS_LABELS[status] || status);

      const stdout = res.stdout || "";
      const stderr = res.stderr || "";
      const compileOut = res.compileOutput || "";

      this.metaRuntime.textContent = res.runtime || "";
      const parts = [];
      if (typeof res.executionTime === "number") {
        parts.push(`Time: ${res.executionTime} ms`);
      }
      if (res.exitCode !== null && res.exitCode !== undefined) {
        parts.push(`Exit code: ${res.exitCode}`);
      }
      this.metaMetrics.textContent = parts.join(" · ") || "—";

      this._updateTabCount("output", stdout ? stdout.split("\n").filter(Boolean).length : 0, false);
      this._updateTabCount("errors", stderr ? 1 : 0, Boolean(stderr));
      this._updateTabCount("compilation", compileOut ? 1 : 0, status === "compilation_error");

      if (status === "compilation_error") {
        this.selectTab("compilation");
      } else if ((status === "runtime_error" || status === "timeout" || status === "service_unavailable") && !stdout) {
        this.selectTab("errors");
      } else {
        this.selectTab("output");
      }
    }

    clear() {
      this._stopTimer();
      this._lastResult = null;
      this._setStatus("idle", STATUS_LABELS.idle);
      this.metaMetrics.textContent = "Exit code: — · Time: —";
      this._updateTabCount("output", 0, false);
      this._updateTabCount("errors", 0, false);
      this._updateTabCount("compilation", 0, false);
      this.stdoutPre.textContent = "";
      this.stderrPre.textContent = "";
      this.compilePre.textContent = "";
      this.stdoutPre.hidden = true;
      this.stderrPre.hidden = true;
      this.compilePre.hidden = true;
      this.emptyState.hidden = false;
      this.emptyState.innerHTML =
        "<p><strong>Ready to run</strong></p>" +
        "<p class=\"tiny\">Press <code>Ctrl/Cmd + Enter</code> or tap <strong>Run Code</strong> to compile and execute with the active language runtime.</p>";
    }

    selectTab(tabName) {
      this.activeTab = tabName;
      for (const [key, btn] of Object.entries(this.tabs)) {
        const on = key === tabName;
        btn.classList.toggle("active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      }
      if (!this._lastResult) {
        this.stdoutPre.hidden = true;
        this.stderrPre.hidden = true;
        this.compilePre.hidden = true;
        this.emptyState.hidden = false;
        return;
      }
      const res = this._lastResult;
      this.emptyState.hidden = true;
      this.stdoutPre.hidden = tabName !== "output";
      this.stderrPre.hidden = tabName !== "errors";
      this.compilePre.hidden = tabName !== "compilation";

      if (tabName === "output") {
        this.stdoutPre.textContent =
          res.stdout !== ""
            ? res.stdout
            : res.status === "success"
            ? "(Program finished with exit code 0 and produced no stdout output.)"
            : "(No standard output produced — inspect the Errors or Compilation tab for details.)";
      } else if (tabName === "errors") {
        this.stderrPre.textContent =
          res.stderr !== "" ? res.stderr : "(No runtime errors on stderr.)";
      } else if (tabName === "compilation") {
        this.compilePre.textContent =
          res.compileOutput !== ""
            ? res.compileOutput
            : res.status === "compilation_error"
            ? "(Compilation failed.)"
            : "(Clean build — compiler emitted 0 errors and 0 warnings.)";
      }
    }

    getActiveText() {
      if (!this._lastResult) return "";
      if (this.activeTab === "errors") return this._lastResult.stderr || "";
      if (this.activeTab === "compilation") return this._lastResult.compileOutput || "";
      return this._lastResult.stdout || "";
    }

    _setStatus(statusKey, label) {
      this.statusPill.dataset.status = statusKey;
      this.statusPill.textContent = label;
    }

    _updateTabCount(tab, n, isAlert) {
      const badge = this.counts[tab];
      if (!badge) return;
      badge.textContent = n > 0 ? (tab === "output" ? String(n) : "!") : "0";
      badge.classList.toggle("has-alert", Boolean(isAlert && n > 0));
    }

    _stopTimer() {
      if (this._elapsedTimer) {
        clearInterval(this._elapsedTimer);
        this._elapsedTimer = null;
      }
    }

    _bind() {
      for (const [key, btn] of Object.entries(this.tabs)) {
        btn.addEventListener("click", () => this.selectTab(key));
      }
    }
  }

  /* -------------------------------------------------------------------------
     6. LanguageSelector
     ------------------------------------------------------------------------- */
  class LanguageSelector {
    constructor(elements, registry, onSelectLanguage, onSelectExample) {
      this.pillsWrap = elements.pillsWrap;
      this.selectEl = elements.selectEl;
      this.examplesSelect = elements.examplesSelect;
      this.runtimeBannerDot = elements.runtimeBannerDot;
      this.runtimeBannerText = elements.runtimeBannerText;
      this.fileTag = elements.fileTag;
      this.unavailableNote = elements.unavailableNote;
      this.registry = registry;
      this.onSelectLanguage = onSelectLanguage;
      this.onSelectExample = onSelectExample;
      this.activeId = null;
      this._bind();
    }

    render(preferredId) {
      const executable = this.registry.executableLanguages();
      const unavailable = this.registry.unavailableLanguages();

      this.pillsWrap.innerHTML = "";
      this.selectEl.innerHTML = "";

      if (!executable.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No executable runtimes available";
        this.selectEl.appendChild(opt);
        this.selectEl.disabled = true;
        this.activeId = null;
        this.runtimeBannerDot.classList.add("off");
        this.runtimeBannerText.textContent = "Execution service unavailable on this host";
        if (this.unavailableNote) {
          this.unavailableNote.textContent =
            "No compiler runtimes are active on this host. Configure local sandbox namespaces/toolchains or ENGINEVERSE_JUDGE0_URL.";
        }
        return null;
      }

      this.selectEl.disabled = false;
      for (const lang of executable) {
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "cl-lang-pill";
        pill.dataset.langId = lang.id;
        pill.textContent = lang.shortLabel || lang.name;
        pill.addEventListener("click", () => this.select(lang.id, true));
        this.pillsWrap.appendChild(pill);

        const opt = document.createElement("option");
        opt.value = lang.id;
        opt.textContent = `${lang.name} (${lang.extension})`;
        this.selectEl.appendChild(opt);
      }

      if (this.unavailableNote) {
        this.unavailableNote.textContent = unavailable.length
          ? `Active verified compilers (${executable.length}): ${executable.map((l) => l.shortLabel).join(", ")}. Not installed on this host (disabled): ${unavailable.map((l) => l.name).join(", ")}.`
          : `All ${executable.length} registered toolchains verified active on this host.`;
      }

      const target =
        executable.find((l) => l.id === preferredId) || executable[0];
      return this.select(target.id, false);
    }

    select(langId, notify) {
      const spec = this.registry.get(langId);
      if (!spec || !spec.available) return null;
      this.activeId = spec.id;
      this.selectEl.value = spec.id;
      for (const pill of this.pillsWrap.querySelectorAll(".cl-lang-pill")) {
        pill.classList.toggle("active", pill.dataset.langId === spec.id);
      }
      this.fileTag.textContent = spec.fileName;
      this.runtimeBannerDot.classList.remove("off");
      this.runtimeBannerText.textContent = spec.runtimeLabel || spec.executionEnv;

      // Populate starter + example options
      this.examplesSelect.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Load example…";
      this.examplesSelect.appendChild(placeholder);

      const starterOpt = document.createElement("option");
      starterOpt.value = "__starter__";
      starterOpt.textContent = `Starter (${spec.fileName})`;
      this.examplesSelect.appendChild(starterOpt);

      for (const ex of spec.examples || []) {
        const opt = document.createElement("option");
        opt.value = ex.id;
        opt.textContent = ex.title;
        this.examplesSelect.appendChild(opt);
      }

      safeStorageSet(STORAGE_LANG_KEY, spec.id);
      if (notify && this.onSelectLanguage) {
        this.onSelectLanguage(spec);
      }
      return spec;
    }

    _bind() {
      this.selectEl.addEventListener("change", () => {
        if (this.selectEl.value) {
          this.select(this.selectEl.value, true);
        }
      });
      this.examplesSelect.addEventListener("change", () => {
        const val = this.examplesSelect.value;
        this.examplesSelect.value = "";
        if (!val || !this.activeId) return;
        const spec = this.registry.get(this.activeId);
        if (!spec) return;
        if (val === "__starter__") {
          this.onSelectExample({
            title: `${spec.name} Starter`,
            code: spec.starterCode,
            stdin: spec.defaultStdin || "",
          });
          return;
        }
        const found = (spec.examples || []).find((e) => e.id === val);
        if (found) {
          this.onSelectExample(found);
        }
      });
    }
  }

  /* -------------------------------------------------------------------------
     7. ExecutionControls + Snippets Manager & 8. CodeLabPage Orchestrator
     ------------------------------------------------------------------------- */
  class CodeLabPage {
    constructor(bootstrap) {
      this.signedIn = Boolean(bootstrap && bootstrap.signedIn);
      this.serverSnippets = Array.isArray(bootstrap && bootstrap.savedSnippets)
        ? bootstrap.savedSnippets
        : [];
      this.registry = new LanguageRegistry(bootstrap && bootstrap.registry);
      this.execService = new ExecutionService(this.registry);

      this.workspaceEl = document.getElementById("cl-workspace");
      this.runBtn = document.getElementById("cl-run-btn");
      this.mobileRunBtn = document.getElementById("cl-mobile-run-btn");
      this.stopBtn = document.getElementById("cl-stop-btn");
      this.formatBtn = document.getElementById("cl-format-btn");
      this.copyBtn = document.getElementById("cl-copy-btn");
      this.downloadBtn = document.getElementById("cl-download-btn");
      this.clearCodeBtn = document.getElementById("cl-clear-code-btn");
      this.resetBtn = document.getElementById("cl-reset-btn");
      this.saveSnippetBtn = document.getElementById("cl-save-snippet-btn");
      this.toggleSnippetsBtn = document.getElementById("cl-toggle-snippets-btn");
      this.snippetsDrawer = document.getElementById("cl-snippets-drawer");
      this.snippetsListEl = document.getElementById("cl-snippets-list");
      this.recentListEl = document.getElementById("cl-recent-list");
      this.copyOutputBtn = document.getElementById("cl-copy-output-btn");
      this.clearOutputBtn = document.getElementById("cl-clear-output-btn");
      this.backToCodeBtn = document.getElementById("cl-back-to-code-btn");

      this.editor = new CodeEditor(
        {
          textarea: document.getElementById("cl-code-input"),
          highlightCode: document.getElementById("cl-highlight-code"),
          highlightPre: document.getElementById("cl-highlight-pre"),
          gutter: document.getElementById("cl-gutter"),
          cursorInfo: document.getElementById("cl-cursor-info"),
          bracketInfo: document.getElementById("cl-bracket-info"),
          acBox: document.getElementById("cl-autocomplete"),
          symbolBar: document.getElementById("cl-symbol-bar"),
        },
        () => this.runCode(),
        (val) => {
          if (this.selector && this.selector.activeId) {
            safeStorageSet(STORAGE_DRAFT_PREFIX + this.selector.activeId, val);
          }
        }
      );

      this.inputPanel = new InputPanel(
        {
          stdinBox: document.getElementById("cl-stdin-input"),
          stdinMeta: document.getElementById("cl-stdin-meta"),
          clearStdinBtn: document.getElementById("cl-clear-stdin-btn"),
          sampleStdinBtn: document.getElementById("cl-sample-stdin-btn"),
        },
        (stdinVal) => {
          if (this.selector && this.selector.activeId) {
            safeStorageSet(STORAGE_STDIN_PREFIX + this.selector.activeId, stdinVal);
          }
        }
      );

      this.console = new OutputConsole({
        statusPill: document.getElementById("cl-status-pill"),
        metaRuntime: document.getElementById("cl-console-runtime"),
        metaMetrics: document.getElementById("cl-console-metrics"),
        emptyState: document.getElementById("cl-empty-state"),
        stdoutPre: document.getElementById("cl-stdout-pre"),
        stderrPre: document.getElementById("cl-stderr-pre"),
        compilePre: document.getElementById("cl-compile-pre"),
        tabs: {
          output: document.getElementById("cl-tab-output"),
          errors: document.getElementById("cl-tab-errors"),
          compilation: document.getElementById("cl-tab-compilation"),
        },
        counts: {
          output: document.getElementById("cl-count-output"),
          errors: document.getElementById("cl-count-errors"),
          compilation: document.getElementById("cl-count-compilation"),
        },
      });

      this.selector = new LanguageSelector(
        {
          pillsWrap: document.getElementById("cl-lang-pills"),
          selectEl: document.getElementById("cl-lang-select"),
          examplesSelect: document.getElementById("cl-example-select"),
          runtimeBannerDot: document.getElementById("cl-runtime-dot"),
          runtimeBannerText: document.getElementById("cl-runtime-label"),
          fileTag: document.getElementById("cl-file-tag"),
          unavailableNote: document.getElementById("cl-unavailable-note"),
        },
        this.registry,
        (spec) => this._applyLanguage(spec),
        (example) => {
          this.editor.setValue(example.code);
          this.inputPanel.setValue(example.stdin || "");
          if (this.selector.activeId) {
            safeStorageSet(STORAGE_DRAFT_PREFIX + this.selector.activeId, example.code);
            safeStorageSet(STORAGE_STDIN_PREFIX + this.selector.activeId, example.stdin || "");
          }
          this.setMobileView("code");
          toastMessage(`Loaded "${example.title}".`);
        }
      );

      this._bindControls();
      if (typeof window.EV_ON_RUNTIME_STATUS === "function") {
        window.EV_ON_RUNTIME_STATUS(({ lang, message }) => {
          if (this.execService.isRunning && this.selector.activeId === lang && this.console.metaRuntime) {
            this.console.metaRuntime.textContent = message;
          }
        });
      }
      this._init(bootstrap && bootstrap.defaultLanguage);
    }

    async _init(serverDefaultLang) {
      const urlParams = new URLSearchParams(window.location.search);
      const queryLang = urlParams.get("lang");
      const savedLang = safeStorageGet(STORAGE_LANG_KEY, "");
      const initialChoice = queryLang || savedLang || serverDefaultLang || "python";

      const chosen = this.selector.render(initialChoice);
      if (chosen) {
        this._applyLanguage(chosen);
      } else {
        this._syncExecutableState();
      }
      this.console.clear();
      this.renderSnippets();

      await this.execService.refreshCapabilities();
      const refreshed = this.selector.render(this.selector.activeId || initialChoice);
      if (refreshed) {
        this._applyLanguage(refreshed, true);
        if (this.registry.mode === "static" && typeof window.EV_BROWSER_PREWARM === "function") {
          setTimeout(() => window.EV_BROWSER_PREWARM(refreshed.id), 120);
        }
      }
      this._syncExecutableState();
    }

    _syncExecutableState() {
      const canRun = Boolean(this.selector.activeId && this.registry.get(this.selector.activeId)?.available);
      this.runBtn.disabled = !canRun;
      if (this.mobileRunBtn) this.mobileRunBtn.disabled = !canRun;
      if (!canRun) {
        this.console.renderResult({
          status: "service_unavailable",
          runtime: "No runtime configured",
          stdout: "",
          stderr: "Code execution is not available on this host until a compiler sandbox is enabled.",
          compileOutput: "",
          exitCode: null,
          executionTime: 0,
        });
      }
    }

    _applyLanguage(spec, preserveCurrentEditorIfSame) {
      if (!spec) return;
      this.editor.setLanguageSpec(spec);
      this.inputPanel.setSampleStdin(spec.defaultStdin || "");
      if (!preserveCurrentEditorIfSame) {
        let savedDraft = safeStorageGet(STORAGE_DRAFT_PREFIX + spec.id, null);
        let savedStdin = safeStorageGet(STORAGE_STDIN_PREFIX + spec.id, null);
        if (spec.id === "go" && savedDraft && savedDraft.includes("GopherJS cannot read stdin")) {
          savedDraft = null;
          savedStdin = null;
          safeStorageSet(STORAGE_DRAFT_PREFIX + spec.id, spec.starterCode);
          safeStorageSet(STORAGE_STDIN_PREFIX + spec.id, spec.defaultStdin || "");
        }
        this.editor.setValue(savedDraft !== null ? savedDraft : spec.starterCode);
        this.inputPanel.setValue(savedStdin !== null ? savedStdin : spec.defaultStdin || "");
      }
      this.console.metaRuntime.textContent = spec.runtimeLabel || spec.executionEnv;
      if (this.registry.mode === "static" && spec.available && typeof window.EV_BROWSER_PREWARM === "function") {
        window.EV_BROWSER_PREWARM(spec.id);
      }
    }

    setMobileView(view) {
      if (!this.workspaceEl) return;
      this.workspaceEl.dataset.mobileView = view;
      document.querySelectorAll("[data-cl-mobile-tab]").forEach((btn) => {
        const active = btn.dataset.clMobileTab === view;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
    }

    async runCode() {
      const langId = this.selector.activeId;
      if (!langId || this.execService.isRunning) return;
      const spec = this.registry.get(langId);
      const sourceCode = this.editor.getValue();
      const stdin = this.inputPanel.getValue();

      this.runBtn.disabled = true;
      if (this.mobileRunBtn) this.mobileRunBtn.disabled = true;
      this.stopBtn.disabled = false;
      this.setMobileView("output");
      this.console.setRunning(spec ? spec.runtimeLabel : langId);

      const result = await this.execService.execute({
        language: langId,
        sourceCode,
        stdin,
      });

      this.runBtn.disabled = false;
      if (this.mobileRunBtn) this.mobileRunBtn.disabled = false;
      this.stopBtn.disabled = true;

      if (result && result.aborted) {
        this.console.clear();
        toastMessage("Execution stopped.");
        return;
      }

      this.console.renderResult(result);
      if (sourceCode.trim()) {
        this._recordRecentRun(spec, sourceCode, stdin, result.status);
      }
    }

    stopExecution() {
      this.execService.abort();
      this.stopBtn.disabled = true;
      this.runBtn.disabled = false;
      if (this.mobileRunBtn) this.mobileRunBtn.disabled = false;
    }

    async copySource() {
      const code = this.editor.getValue();
      try {
        await navigator.clipboard.writeText(code);
        toastMessage("Source code copied to clipboard.");
      } catch (_err) {
        this.editor.textarea.select();
        document.execCommand("copy");
        toastMessage("Source code copied.");
      }
    }

    downloadSource() {
      const spec = this.registry.get(this.selector.activeId);
      const filename = (spec && spec.fileName) || "program.txt";
      const code = this.editor.getValue();

      if (
        window.EngineVerseAndroid &&
        typeof window.EngineVerseAndroid.shareSourceFile === "function"
      ) {
        window.EngineVerseAndroid.shareSourceFile(filename, code);
        toastMessage(`Sharing ${filename}…`);
        return;
      }

      const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toastMessage(`Downloaded ${filename}`);
    }

    async saveSnippet() {
      const spec = this.registry.get(this.selector.activeId);
      if (!spec) return;
      const sourceCode = this.editor.getValue();
      const stdin = this.inputPanel.getValue();
      if (!sourceCode.trim()) {
        toastMessage("Write some code before saving a snippet.");
        return;
      }
      const defaultTitle = `${spec.name} — ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
      const titleInput = window.prompt("Snippet title:", defaultTitle);
      if (titleInput === null) return;
      const title = titleInput.trim() || defaultTitle;

      if (this.signedIn && this.registry.mode === "server") {
        try {
          const res = await fetch("/api/codelab/snippets", {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrfToken(),
            },
            body: JSON.stringify({ title, language: spec.id, sourceCode, stdin }),
          });
          const data = await res.json();
          if (res.ok && data.ok && data.snippet) {
            this.serverSnippets.unshift(data.snippet);
            this.snippetsDrawer.hidden = false;
            this.renderSnippets();
            toastMessage(`Saved "${title}" to your account.`);
            return;
          }
        } catch (_err) {
          /* fall back to local storage */
        }
      }

      const local = this._readLocalSnippets();
      local.unshift({
        id: "local-" + Date.now(),
        title,
        language: spec.id,
        sourceCode,
        stdin,
        updatedAt: Date.now(),
        localOnly: true,
      });
      safeStorageSet(STORAGE_SNIPPETS_KEY, JSON.stringify(local.slice(0, 30)));
      this.snippetsDrawer.hidden = false;
      this.renderSnippets();
      toastMessage(`Saved "${title}" on this device.`);
    }

    async deleteSnippet(snippet) {
      if (snippet && !snippet.localOnly && this.signedIn) {
        try {
          await fetch(`/api/codelab/snippets/${encodeURIComponent(snippet.id)}`, {
            method: "DELETE",
            credentials: "same-origin",
            headers: { "X-CSRF-Token": csrfToken() },
          });
        } catch (_err) {
          /* ignore */
        }
        this.serverSnippets = this.serverSnippets.filter((s) => s.id !== snippet.id);
      } else {
        const next = this._readLocalSnippets().filter((s) => s.id !== snippet.id);
        safeStorageSet(STORAGE_SNIPPETS_KEY, JSON.stringify(next));
      }
      this.renderSnippets();
    }

    _readLocalSnippets() {
      try {
        const parsed = JSON.parse(safeStorageGet(STORAGE_SNIPPETS_KEY, "[]"));
        return Array.isArray(parsed) ? parsed : [];
      } catch (_err) {
        return [];
      }
    }

    _recordRecentRun(spec, sourceCode, stdin, status) {
      if (!spec) return;
      try {
        const prev = JSON.parse(safeStorageGet(STORAGE_RECENT_KEY, "[]"));
        const list = Array.isArray(prev) ? prev : [];
        const filtered = list.filter(
          (item) => !(item.language === spec.id && item.sourceCode === sourceCode)
        );
        filtered.unshift({
          id: "recent-" + Date.now(),
          title: `${spec.shortLabel} (${STATUS_LABELS[status] || status})`,
          language: spec.id,
          sourceCode,
          stdin,
          updatedAt: Date.now(),
          localOnly: true,
        });
        safeStorageSet(STORAGE_RECENT_KEY, JSON.stringify(filtered.slice(0, 8)));
        this.renderSnippets();
      } catch (_err) {
        /* ignore */
      }
    }

    renderSnippets() {
      if (!this.snippetsListEl) return;
      const merged = [...this.serverSnippets, ...this._readLocalSnippets()];
      this.snippetsListEl.innerHTML = "";
      if (!merged.length) {
        const empty = document.createElement("p");
        empty.className = "muted small";
        empty.textContent = "No saved snippets yet. Click Save Snippet to keep reusable programs here.";
        this.snippetsListEl.appendChild(empty);
      } else {
        for (const item of merged) {
          this.snippetsListEl.appendChild(this._buildSnippetCard(item, true));
        }
      }

      if (this.recentListEl) {
        this.recentListEl.innerHTML = "";
        let recents = [];
        try {
          recents = JSON.parse(safeStorageGet(STORAGE_RECENT_KEY, "[]")) || [];
        } catch (_e) {
          recents = [];
        }
        if (!recents.length) {
          const emptyR = document.createElement("p");
          emptyR.className = "muted small";
          emptyR.textContent = "Recent runs on this device will appear here automatically.";
          this.recentListEl.appendChild(emptyR);
        } else {
          for (const rec of recents) {
            this.recentListEl.appendChild(this._buildSnippetCard(rec, false));
          }
        }
      }
    }

    _buildSnippetCard(item, allowDelete) {
      const card = document.createElement("div");
      card.className = "cl-snippet-card";

      const head = document.createElement("div");
      const title = document.createElement("div");
      title.className = "cl-snippet-title";
      title.textContent = item.title;
      const sub = document.createElement("div");
      sub.className = "tiny muted";
      sub.textContent = `${String(item.language || "").toUpperCase()} · ${(item.sourceCode || "").split("\n").length} lines`;
      head.appendChild(title);
      head.appendChild(sub);

      const actions = document.createElement("div");
      actions.className = "cl-snippet-actions";
      const loadBtn = document.createElement("button");
      loadBtn.type = "button";
      loadBtn.className = "cl-mini-btn";
      loadBtn.textContent = "Open in Editor";
      loadBtn.addEventListener("click", () => {
        if (this.registry.get(item.language)?.available) {
          this.selector.select(item.language, false);
          this.editor.setLanguageSpec(this.registry.get(item.language));
        }
        this.editor.setValue(item.sourceCode || "");
        this.inputPanel.setValue(item.stdin || "");
        this.setMobileView("code");
        toastMessage(`Opened "${item.title}".`);
      });
      actions.appendChild(loadBtn);

      if (allowDelete) {
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "cl-mini-btn";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => this.deleteSnippet(item));
        actions.appendChild(delBtn);
      }

      card.appendChild(head);
      card.appendChild(actions);
      return card;
    }

    _bindControls() {
      this.runBtn.addEventListener("click", () => this.runCode());
      if (this.mobileRunBtn) {
        this.mobileRunBtn.addEventListener("click", () => this.runCode());
      }
      this.stopBtn.addEventListener("click", () => this.stopExecution());
      this.formatBtn.addEventListener("click", () => {
        this.editor.format();
        toastMessage("Formatted code.");
      });
      this.copyBtn.addEventListener("click", () => this.copySource());
      this.downloadBtn.addEventListener("click", () => this.downloadSource());

      this.clearCodeBtn.addEventListener("click", () => {
        this.editor.setValue("");
        if (this.selector.activeId) {
          safeStorageSet(STORAGE_DRAFT_PREFIX + this.selector.activeId, "");
        }
        this.editor.textarea.focus();
      });

      this.resetBtn.addEventListener("click", () => {
        const spec = this.registry.get(this.selector.activeId);
        if (!spec) return;
        this.editor.setValue(spec.starterCode);
        this.inputPanel.setValue(spec.defaultStdin || "");
        safeStorageSet(STORAGE_DRAFT_PREFIX + spec.id, spec.starterCode);
        safeStorageSet(STORAGE_STDIN_PREFIX + spec.id, spec.defaultStdin || "");
        toastMessage(`Reset to ${spec.name} starter template.`);
      });

      this.saveSnippetBtn.addEventListener("click", () => this.saveSnippet());
      this.toggleSnippetsBtn.addEventListener("click", () => {
        const nextHidden = !this.snippetsDrawer.hidden;
        this.snippetsDrawer.hidden = nextHidden;
        this.toggleSnippetsBtn.setAttribute("aria-expanded", nextHidden ? "false" : "true");
        if (!nextHidden) {
          this.renderSnippets();
          this.snippetsDrawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      });

      this.copyOutputBtn.addEventListener("click", async () => {
        const text = this.console.getActiveText();
        if (!text) {
          toastMessage("Nothing in console to copy yet.");
          return;
        }
        try {
          await navigator.clipboard.writeText(text);
          toastMessage("Console output copied.");
        } catch (_err) {
          toastMessage("Could not access clipboard.");
        }
      });

      this.clearOutputBtn.addEventListener("click", () => this.console.clear());

      const fontDec = document.getElementById("cl-font-dec");
      const fontInc = document.getElementById("cl-font-inc");
      if (fontDec) fontDec.addEventListener("click", () => this.editor.adjustFontSize(-1));
      if (fontInc) fontInc.addEventListener("click", () => this.editor.adjustFontSize(1));

      document.querySelectorAll("[data-cl-mobile-tab]").forEach((btn) => {
        btn.addEventListener("click", () => this.setMobileView(btn.dataset.clMobileTab));
      });
      if (this.backToCodeBtn) {
        this.backToCodeBtn.addEventListener("click", () => this.setMobileView("code"));
      }

      document.addEventListener("keydown", (ev) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") {
          ev.preventDefault();
          this.saveSnippet();
        }
      });
    }
  }

  window.EngineVerseCodeLab = {
    LanguageRegistry,
    ExecutionService,
    LanguageSelector,
    CodeEditor,
    InputPanel,
    OutputConsole,
    CodeLabPage,
    formatSourceCode,
    highlightSource,
  };

  document.addEventListener("DOMContentLoaded", () => {
    const bootNode = document.getElementById("codelab-bootstrap");
    if (!bootNode) return;
    let bootstrap = {};
    try {
      bootstrap = JSON.parse(bootNode.textContent || "{}");
    } catch (_err) {
      bootstrap = {};
    }
    window.__codelab = new CodeLabPage(bootstrap);
  });
})();
