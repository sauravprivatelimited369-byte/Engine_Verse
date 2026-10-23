"""stdin/stdout harnesses ("wrappers") appended to a submission before it runs.

A coding problem's stub only *declares* an entry point - ``def two_sum(nums, target)``
or ``class LRUCache``.  Nothing calls it, so running the submission verbatim would
always print nothing and fail every test.

Each problem therefore names a *wrapper* (``coding_problems.wrapper``).  The judge
appends the matching driver, which:

    1. reads stdin using the convention documented on the problem page,
    2. parses it into the entry point's arguments,
    3. calls the entry point,
    4. prints the result in the exact form the expected output uses.

Adding a new problem shape means adding one wrapper here - the judge, the editor
and the test cases are untouched.  The wrapper name is stored in the database, so
new problems are data, not code.

Python and JavaScript have full driver sets below (``python_driver`` /
``javascript_driver``), so a function-style stub in either language is judged
against the same stdin/stdout contract and the same expected outputs. Other
languages run the submission verbatim: the learner writes a complete program
that reads stdin and prints the answer (the compiler page's starters show that
shape). ``java_driver`` is the partial Java equivalent used by the Java sandbox
service.
"""

from __future__ import annotations

import re

# Every wrapper the platform knows about.  Kept explicit so the editor can show
# the I/O convention and the seeder can validate a problem's wrapper.
WRAPPERS = (
    "raw",
    "list-target",
    "int-list-int",
    "int-list",
    "string-bool",
    "string-int",
    "two-lists",
    "lines",
    "linked-list",
    "cycle",
    "tree",
    "graph",
    "lru",
    "int-n",
    "int-int",
    "string-list",
    "matrix",
    "intervals",
    "grid",
    "list-pair",
    "two-lines",
    "word-ladder",
)

# How each wrapper feeds the entry point, shown on the problem page.
WRAPPER_DOCS = {
    "raw": "Read stdin yourself and print the answer.",
    "list-target": "Line 1: a list, e.g. `[2, 7, 11, 15]`. Line 2: an integer.",
    "int-list-int": "Line 1: space-separated integers. Line 2: an integer.",
    "int-list": "One line of space-separated integers.",
    "string-bool": "One line of text.",
    "string-int": "One line of text.",
    "two-lists": "Line 1: space-separated integers. Line 2: space-separated integers.",
    "lines": "One line: an integer count.",
    "linked-list": "One line of space-separated integers, built into a linked list.",
    "cycle": "Values followed by the value of the node the tail links back to. "
             "If no node has that value, the list is acyclic.",
    "tree": "Level-order values separated by spaces, using `None` for a missing node.",
    "graph": "One `Node:Neighbour1w1,Neighbour2w2` line per node, then the start "
             "node, then the end node.",
    "lru": "Line 1: capacity. Then one `put k v` or `get k` command per line; "
           "every `get` result is printed, space-separated.",
    "int-n": "One integer.",
    "int-int": "Two integers on one line.",
    "string-list": "One line of space-separated words.",
    "matrix": "Line 1: rows and columns. Then one line of space-separated integers per row.",
    "intervals": "Line 1: how many pairs. Then one `start end` pair per line. "
                 "When the answer is a list of pairs it is printed one pair per line.",
    "grid": "Line 1: rows and columns. Then one line of characters per row.",
    "list-pair": "Two lines of space-separated integers.",
    "two-lines": "Two lines of text.",
    "word-ladder": "Line 1: the begin word. Line 2: the end word. Remaining lines: the word list.",
}

# Python ``def``/``class`` and JavaScript ``function``/``class`` signatures.
_ENTRY_RE = re.compile(r"^\s*(?:def|class|function)\s+([A-Za-z_][A-Za-z0-9_]*)")

# Node/tree types the harness carries itself, so a submission still runs even if
# the learner deleted the helper classes that ship in the stub.  Private names
# keep them out of the way of the learner's own code.
_EV_NODE = """class _EvNode:
    __slots__ = ("value", "next")
    def __init__(self, value=0, nxt=None):
        self.value = value
        self.next = nxt"""


def entrypoint(signature: str | None, fallback: str = "solution") -> str:
    """Pulls the callable name out of a stored stub signature."""
    if signature:
        match = _ENTRY_RE.match(signature)
        if match:
            return match.group(1)
    return fallback


def _python_body(wrapper: str, entry: str) -> str | None:
    """Returns the driver body for a wrapper, or None for 'raw'."""
    if wrapper == "raw":
        return None

    if wrapper == "list-target":
        return f"""
import sys as _sys, ast as _ast
_d = _sys.stdin.read().split("\\n")
_a = _ast.literal_eval(_d[0].strip()) if _d and _d[0].strip() else []
_b = int(_d[1].strip()) if len(_d) > 1 and _d[1].strip() else 0
print({entry}(_a, _b))
"""

    if wrapper == "int-list-int":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_a = [int(x) for x in _d[0].split()] if _d and _d[0].strip() else []
_b = int(_d[1].strip()) if len(_d) > 1 and _d[1].strip() else 0
print({entry}(_a, _b))
"""

    if wrapper == "int-list":
        return f"""
import sys as _sys
_a = [int(x) for x in _sys.stdin.read().split()]
print({entry}(_a))
"""

    if wrapper == "string-bool":
        return f"""
import sys as _sys
print(bool({entry}(_sys.stdin.read().split("\\n")[0])))
"""

    if wrapper == "string-int":
        return f"""
import sys as _sys
print({entry}(_sys.stdin.read().split("\\n")[0]))
"""

    if wrapper == "two-lists":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_a = [int(x) for x in _d[0].split()] if len(_d) > 0 and _d[0].strip() else []
_b = [int(x) for x in _d[1].split()] if len(_d) > 1 and _d[1].strip() else []
print(" ".join(str(v) for v in {entry}(_a, _b)))
"""

    if wrapper == "lines":
        return f"""
import sys as _sys
_n = int((_sys.stdin.read().strip() or "0"))
print(" ".join(str(v) for v in {entry}(_n)))
"""

    if wrapper == "linked-list":
        return f"""
import sys as _sys


{_EV_NODE}


def _ev_build(values):
    dummy = _EvNode()
    tail = dummy
    for value in values:
        tail.next = _EvNode(value)
        tail = tail.next
    return dummy.next


def _ev_dump(head):
    out = []
    while head:
        out.append(head.value)
        head = head.next
    return out


_h = _ev_build([int(x) for x in _sys.stdin.read().split()])
_r = {entry}(_h)
print(" ".join(str(v) for v in (_ev_dump(_r) if _r is not None else [])))
"""

    if wrapper == "cycle":
        # Convention: the values of the list, then the value of the node the tail
        # links back to.  No node carrying that value means the list is acyclic.
        return f"""
import sys as _sys


{_EV_NODE}


_t = _sys.stdin.read().split()
_vals = [int(x) for x in _t[:-1]] if len(_t) > 1 else []
_target = int(_t[-1]) if _t else None
_nodes = [_EvNode(v) for v in _vals]
for _i in range(len(_nodes) - 1):
    _nodes[_i].next = _nodes[_i + 1]
if _nodes and _target is not None:
    for _n in _nodes:
        if _n.value == _target:
            _nodes[-1].next = _n
            break
_h = _nodes[0] if _nodes else None
print(bool({entry}(_h)))
"""

    if wrapper == "tree":
        return f"""
import sys as _sys
from collections import deque as _ev_deque


class _EvTree:
    __slots__ = ("value", "left", "right")
    def __init__(self, value=0, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def _ev_build(values):
    if not values:
        return None
    root = _EvTree(values[0])
    queue = _ev_deque([root])
    index = 1
    while queue and index < len(values):
        node = queue.popleft()
        if index < len(values):
            if values[index] is not None:
                node.left = _EvTree(values[index])
                queue.append(node.left)
            index += 1
        if index < len(values):
            if values[index] is not None:
                node.right = _EvTree(values[index])
                queue.append(node.right)
            index += 1
    return root


_t = _sys.stdin.read().split()
_v = [None if x == "None" else int(x) for x in _t]
print({entry}(_ev_build(_v)))
"""

    if wrapper == "graph":
        return f"""
import sys as _sys, re as _re
_g, _rest = {{}}, []
for _line in _sys.stdin.read().split("\\n"):
    if ":" in _line:
        _node, _, _edges = _line.partition(":")
        _adj = []
        for _e in _edges.split(","):
            _m = _re.match(r"^([A-Za-z0-9_]+?)(-?\\d+)$", _e.strip())
            if _m:
                _adj.append((_m.group(1), int(_m.group(2))))
        _g[_node.strip()] = _adj
    elif _line.strip():
        _rest.append(_line.strip())
_s = _rest[0] if _rest else ""
_e = _rest[1] if len(_rest) > 1 else ""
print({entry}(_g, _s, _e))
"""

    if wrapper == "int-n":
        return f"""
import sys as _sys
print({entry}(int(_sys.stdin.read().strip() or "0")))
"""

    if wrapper == "int-int":
        return f"""
import sys as _sys
_t = [int(x) for x in _sys.stdin.read().split()]
print({entry}(_t[0] if _t else 0, _t[1] if len(_t) > 1 else 0))
"""

    if wrapper == "string-list":
        return f"""
import sys as _sys
_t = _sys.stdin.readline().split()
print({entry}(_t))
"""

    if wrapper == "matrix":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_h = _d[0].split() if _d and _d[0].strip() else []
_rows = int(_h[0]) if _h else 0
_grid = []
for _line in _d[1:_rows + 1]:
    _grid.append([int(x) for x in _line.split()] if _line.strip() else [])
_r = {entry}(_grid)
# A matrix problem can return a matrix, or a single number such as a
# determinant the caller asked for.
if isinstance(_r, (list, tuple)) and _r and isinstance(_r[0], (list, tuple)):
    for _row in _r:
        print(" ".join(str(v) for v in _row))
else:
    print(_r)
"""

    if wrapper == "intervals":
        return f"""
import sys as _sys
_d = [line for line in _sys.stdin.read().split("\\n") if line.strip()]
_n = int(_d[0].strip()) if _d else 0
_pairs = []
for _line in _d[1:_n + 1]:
    _p = [int(x) for x in _line.split()]
    if len(_p) >= 2:
        _pairs.append(_p[:2])
_r = {entry}(_pairs)
# A sheet problem can return a list of pairs, or a single answer such as a
# boolean or a count. Both are printed, and the shape decides how: iterating a
# bool to print it "one pair per line" is a crash, not a verdict.
if isinstance(_r, (list, tuple)) and _r and isinstance(_r[0], (list, tuple)):
    for _pair in _r:
        print(" ".join(str(v) for v in _pair))
else:
    print(_r)
"""

    if wrapper == "grid":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_h = _d[0].split() if _d and _d[0].strip() else []
_rows = int(_h[0]) if _h else 0
_grid = [list(_line.strip()) for _line in _d[1:_rows + 1] if _line.strip()]
_r = {entry}(_grid)
print(" ".join(str(v) for v in _r) if isinstance(_r, (list, tuple)) else _r)
"""

    if wrapper == "list-pair":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_a = [int(x) for x in _d[0].split()] if _d and _d[0].strip() else []
_b = [int(x) for x in _d[1].split()] if len(_d) > 1 and _d[1].strip() else []
print({entry}(_a, _b))
"""

    if wrapper == "two-lines":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_a = _d[0].strip() if _d else ""
_b = _d[1].strip() if len(_d) > 1 else ""
print({entry}(_a, _b))
"""

    if wrapper == "word-ladder":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_begin = _d[0].strip() if _d else ""
_end = _d[1].strip() if len(_d) > 1 else ""
_words = " ".join(_d[2:]).split()
print({entry}(_begin, _end, _words))
"""

    if wrapper == "lru":
        return f"""
import sys as _sys
_d = _sys.stdin.read().split("\\n")
_c = {entry}(int(_d[0].strip()) if _d and _d[0].strip() else 0)
_out = []
for _line in _d[1:]:
    _p = _line.split()
    if not _p:
        continue
    if _p[0] == "put" and len(_p) >= 3:
        _c.put(int(_p[1]), int(_p[2]))
    elif _p[0] == "get" and len(_p) >= 2:
        _out.append(str(_c.get(int(_p[1]))))
print(" ".join(_out))
"""

    return None


def python_driver(wrapper: str, entry: str) -> str:
    body = _python_body(wrapper, entry)
    if not body:
        return ""
    return "\n\n# ---- EngineVerse harness (appended by the judge) ----\n" + body.strip() + "\n"


#: JavaScript equivalent of the Python drivers: ONE harness with a wrapper
#: switch, mirroring ``_python_body`` case by case (same stdin conventions,
#: same output shapes - Python-style ``print`` formatting included, so the
#: same expected outputs grade both languages). ``__EV_WRAPPER__`` is always
#: one of :data:`WRAPPERS` and ``__EV_ENTRY__`` is validated as an identifier
#: before substitution, so neither placeholder can inject code.
_JS_PRELUDE = """let _evUserWrote = false;
{
  const _evOrigWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = function (chunk, ...rest) {
    _evUserWrote = true;
    return _evOrigWrite(chunk, ...rest);
  };
}
"""

_JS_HARNESS = r'''
// ---- EngineVerse harness (appended by the judge) ----
(() => {
  const _evWrapper = "__EV_WRAPPER__";
  const _evEntry = typeof __EV_ENTRY__ !== "undefined" ? __EV_ENTRY__ : null;
  if (_evEntry === null) {
    if (typeof _evUserWrote !== "undefined" && _evUserWrote) return;
    console.error("EngineVerse harness: entry point '__EV_ENTRY__' is not defined. Define the function named in the stub.");
    process.exit(1);
  }
  const _evText = require("fs").readFileSync(0, "utf8");
  const _evLines = _evText.split("\n");
  const _evInts = (s) => (String(s || "").trim() ? String(s).trim().split(/\s+/).map(Number) : []);
  function _evBuildList(vals) {
    let head = null, tail = null;
    for (const v of vals) { const n = { value: v, val: v, next: null }; if (tail) tail.next = n; else head = n; tail = n; }
    return head;
  }
  function _evDumpList(head) {
    const out = []; let cur = head, guard = 0;
    while (cur && guard++ < 100000) { out.push(cur.value !== undefined ? cur.value : cur.val); cur = cur.next; }
    return out;
  }
  function _evBuildTree(tokens) {
    if (!tokens.length || tokens[0] === null) return null;
    const root = { value: tokens[0], val: tokens[0], left: null, right: null };
    const q = [root]; let i = 1;
    while (q.length && i < tokens.length) {
      const node = q.shift();
      if (i < tokens.length) { if (tokens[i] !== null) { node.left = { value: tokens[i], val: tokens[i], left: null, right: null }; q.push(node.left); } i++; }
      if (i < tokens.length) { if (tokens[i] !== null) { node.right = { value: tokens[i], val: tokens[i], left: null, right: null }; q.push(node.right); } i++; }
    }
    return root;
  }
  function _evArgs() {
    const L = _evLines, l0 = L[0] || "", l1 = L.length > 1 ? L[1] : "";
    switch (_evWrapper) {
      case "list-target": {
        let a = []; const s = l0.trim();
        if (s) { try { a = JSON.parse(s); } catch (_) { a = _evInts(s.replace(/[\[\],]/g, " ")); } }
        return [a, l1.trim() ? Number(l1.trim()) : 0];
      }
      case "int-list-int": return [_evInts(l0), l1.trim() ? Number(l1.trim()) : 0];
      case "int-list": return [_evInts(_evText)];
      case "string-bool": case "string-int": return [l0];
      case "two-lists": case "list-pair": return [_evInts(l0), _evInts(l1)];
      case "lines": case "int-n": return [Number(_evText.trim() || 0)];
      case "int-int": { const t = _evInts(_evText); return [t[0] || 0, t.length > 1 ? t[1] : 0]; }
      case "string-list": return [l0.trim() ? l0.trim().split(/\s+/) : []];
      case "two-lines": return [l0.trim(), l1.trim()];
      case "linked-list": return [_evBuildList(_evInts(_evText))];
      case "cycle": {
        const t = _evInts(_evText);
        const vals = t.length > 1 ? t.slice(0, -1) : [];
        const target = t.length ? t[t.length - 1] : null;
        const nodes = vals.map((v) => ({ value: v, val: v, next: null }));
        for (let i = 0; i + 1 < nodes.length; i++) nodes[i].next = nodes[i + 1];
        if (nodes.length && target !== null) { const hit = nodes.find((n) => n.value === target); if (hit) nodes[nodes.length - 1].next = hit; }
        return [nodes[0] || null];
      }
      case "tree": {
        const toks = _evText.trim() ? _evText.trim().split(/\s+/).map((x) => (x === "None" ? null : Number(x))) : [];
        return [_evBuildTree(toks)];
      }
      case "graph": {
        const g = {}; const rest = [];
        for (const line of L) {
          if (line.includes(":")) {
            const idx = line.indexOf(":");
            const adj = [];
            for (const e of line.slice(idx + 1).split(",")) {
              const m = /^([A-Za-z0-9_]+?)(-?\d+)$/.exec(e.trim());
              if (m) adj.push([m[1], Number(m[2])]);
            }
            g[line.slice(0, idx).trim()] = adj;
          } else if (line.trim()) rest.push(line.trim());
        }
        return [g, rest[0] || "", rest.length > 1 ? rest[1] : ""];
      }
      case "matrix": {
        const h = _evInts(l0); const rows = h.length ? h[0] : 0;
        const grid = [];
        for (const line of L.slice(1, rows + 1)) grid.push(_evInts(line));
        return [grid];
      }
      case "intervals": {
        const d = L.filter((x) => x.trim());
        const n = d.length ? Number(d[0].trim()) : 0;
        const pairs = [];
        for (const line of d.slice(1, n + 1)) { const p = _evInts(line); if (p.length >= 2) pairs.push(p.slice(0, 2)); }
        return [pairs];
      }
      case "grid": {
        const h = _evInts(l0); const rows = h.length ? h[0] : 0;
        return [L.slice(1, rows + 1).filter((x) => x.trim()).map((x) => x.trim().split(""))];
      }
      case "word-ladder": return [l0.trim(), l1.trim(), L.slice(2).join(" ").split(/\s+/).filter(Boolean)];
      default: return [_evText];
    }
  }
  function _evRepr(v) {
    if (v === null || v === undefined) return "None";
    if (typeof v === "boolean") return v ? "True" : "False";
    if (Array.isArray(v)) return "[" + v.map(_evRepr).join(", ") + "]";
    if (typeof v === "string") return "'" + v + "'";
    return String(v);
  }
  function _evShow(v) { return typeof v === "string" ? v : _evRepr(v); }
  let _evOut;
  if (_evWrapper === "lru") {
    const cap = _evLines.length && _evLines[0].trim() ? Number(_evLines[0].trim()) : 0;
    const cache = new _evEntry(cap);
    const gets = [];
    for (const line of _evLines.slice(1)) {
      const p = line.trim().split(/\s+/).filter(Boolean);
      if (p[0] === "put" && p.length >= 3) cache.put(Number(p[1]), Number(p[2]));
      else if (p[0] === "get" && p.length >= 2) gets.push(String(cache.get(Number(p[1]))));
    }
    _evOut = gets.join(" ");
  } else {
    const res = _evEntry(..._evArgs());
    if (_evWrapper === "string-bool" || _evWrapper === "cycle") _evOut = res ? "True" : "False";
    else if (_evWrapper === "two-lists" || _evWrapper === "lines") _evOut = Array.from(res).map(String).join(" ");
    else if (_evWrapper === "linked-list") _evOut = res == null ? "" : _evDumpList(res).map(String).join(" ");
    else if (_evWrapper === "matrix" || _evWrapper === "intervals") {
      _evOut = Array.isArray(res) && res.length && Array.isArray(res[0])
        ? res.map((row) => Array.from(row).map(String).join(" ")).join("\n") : _evShow(res);
    } else if (_evWrapper === "grid") _evOut = Array.isArray(res) ? res.map(String).join(" ") : _evShow(res);
    else _evOut = _evShow(res);
  }
  console.log(_evOut);
})();
'''

_JS_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def javascript_driver(wrapper: str, entry: str) -> str:
    """The stdin/stdout harness appended to a JavaScript submission.

    Mirrors :func:`python_driver`: returns "" for ``raw`` (and for an unknown
    wrapper, where inventing a convention would silently misgrade). Without
    this, a function-style JavaScript stub (``function twoSum(...)``) ran
    verbatim, printed nothing and could never be accepted - the language was
    listed as supported while its judged path was decorative.
    """
    if wrapper == "raw" or wrapper not in WRAPPERS:
        return ""
    safe_entry = entry if _JS_IDENTIFIER.match(entry or "") else "solution"
    return _JS_HARNESS.replace("__EV_WRAPPER__", wrapper).replace("__EV_ENTRY__", safe_entry)


def compose(language: str, code: str, wrapper: str, signature: str | None) -> str:
    """Returns the program the judge should actually execute."""
    wrapper = (wrapper or "raw").strip() or "raw"
    if language == "python":
        return code.rstrip("\n") + python_driver(wrapper, entrypoint(signature))
    if language == "javascript":
        driver = javascript_driver(wrapper, entrypoint(signature))
        if not driver:
            return code
        return _JS_PRELUDE + code.rstrip("\n") + "\n" + driver
    # Other languages run the submission verbatim as a complete program that
    # reads stdin itself (see the module docstring). Claiming a harness here
    # without one existing is how JavaScript silently never printed anything.
    return code


def java_driver(wrapper: str, entry: str) -> str:
    """Java equivalent of :func:`python_driver`.

    Used by the Java sandbox runner (``sandbox-java``) where the submission is a
    class body rather than a script.  Returns an empty string for ``raw``.
    """
    if wrapper in ("raw", ""):
        return ""
    if wrapper == "int-list-int":
        return f"""
    // ---- EngineVerse harness ----
    public static void main(String[] args) throws Exception {{
        java.io.BufferedReader br = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
        String l1 = br.readLine(); String l2 = br.readLine();
        java.util.List<Integer> a = new java.util.ArrayList<>();
        if (l1 != null && !l1.isBlank()) for (String t : l1.trim().split("\\\\s+")) a.add(Integer.parseInt(t));
        int b = (l2 == null || l2.isBlank()) ? 0 : Integer.parseInt(l2.trim());
        System.out.println(new Solution().{entry}(a, b));
    }}
"""
    return ""
