"""Depth wave 3, part two: JavaScript and TypeScript semantics modules.

Same contract as the other wave-3 files: book-depth lessons in the legacy
body/example/exercise shape, each ending in an existing judged problem.
"""

BOOK_MODULES: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "javascript": [
        (
            "js-semantics-deep",
            "Coercion, references and the corners of JavaScript",
            "Types and typeof, number precision, the == table, reference semantics, this binding, "
            "hoisting and closures, and the JSON and cloning rules that lose data.",
            r"""**Why this matters.** JavaScript's reputation for weirdness comes from a small number of
rules applied consistently. `[] == false`, `typeof null === "object"` and a missing `this` are not
random; they are what happens when a loosely typed language with reference semantics and a
prototype chain follows its own rules. Learn the rules and the surprises become predictable, which
is the difference between debugging by permutation and debugging by model.

**Seven primitive types and one object type.** `string`, `number`, `boolean`, `bigint`, `symbol`,
`undefined`, `null` are primitives; everything else is an object (including arrays, functions,
dates and maps). `typeof` returns `"undefined"`, `"boolean"`, `"number"`, `"bigint"`, `"string"`,
`"symbol"`, `"function"` and `"object"` - and `typeof null` is `"object"` for historical reasons,
so test null with `value === null`. `Array.isArray` is the array test; `typeof []` is `"object"`.

**Numbers are 64-bit floats.** There is no separate integer type in ordinary code, so `0.1 + 0.2`
is not `0.3`, and integers above `Number.MAX_SAFE_INTEGER` (2^53 - 1) silently lose precision.
`9007199254740993` prints as `9007199254740992`. Use `BigInt` (`10n`) for exact large integers;
it cannot be mixed with `number` in arithmetic without an explicit conversion, and `JSON.stringify`
throws on it. `NaN` is the only value not equal to itself; use `Number.isNaN` (not the global
`isNaN`, which coerces) and `Object.is` when you need to distinguish `-0` from `0`. `Number.isInteger`
and `Number.isSafeInteger` answer the questions people try to answer with `typeof` and `%`.

**Equality.** `===` compares type and value for primitives and identity for objects; there is no
deep equality in the language. `==` coerces according to a short table, and the table is worth
knowing because it explains the folklore: `null == undefined` is true; `null == 0` is false;
`"" == 0` and `"0" == 0` are true; `[] == false` is true (both become `""` and `0`); `[1] == 1`
is true. Objects convert with `ToPrimitive`, which calls `valueOf` then `toString`. The practical
rule is to use `===` everywhere except the deliberate `x == null` idiom that tests null or
undefined in one comparison. Even that idiom is a style choice; being explicit costs four
characters.

**Truthiness.** The falsy values are `false`, `0`, `-0`, `0n`, `""`, `null`, `undefined` and
`NaN`. Everything else is truthy, including `[]` and `{}` and `"0"`. That is why `if (value)` is a
bug when `0` or `""` are valid, and why `value || fallback` silently replaces them. Use
`value ?? fallback` when the test is nullish, and an explicit comparison when the test is "has a
value" for a number or string.

**Assignment copies primitives and shares objects.** `const b = a` on an object makes two names
for one object; `{...a}` and `Object.assign({}, a)` copy one level. Spread copies own enumerable
properties and their values, so nested objects remain shared, and class instances lose their
prototype. `Object.freeze` is shallow: `Object.freeze(obj)` prevents reassigning `obj.x` but not
`obj.nested.x`. `structuredClone` is the built-in deep clone; it handles dates, maps, sets,
typed arrays and cycles, but throws `DataCloneError` on functions, DOM nodes and symbols.

**Property order is defined.** Integer-like keys come first in ascending numeric order, then string
keys in insertion order, then symbol keys. That is why a parsed JSON object with numeric-looking
keys comes back sorted, and why relying on `Object.keys` order for mixed keys is a mistake.

**`this` is decided by the call, not the definition.** For a normal function, `this` is the
receiver at the call site: `obj.method()` binds `obj`, a bare `fn()` binds `undefined` in strict
mode (modules are strict), `fn.call(x)` and `fn.apply(x, args)` bind explicitly, and
`fn.bind(x)` returns a bound copy. Arrow functions have no `this` of their own; they capture the
enclosing one, which is why they are the right tool for callbacks and the wrong tool for methods.
The classic bug is `setTimeout(obj.method, 100)`: the method is detached from its receiver, so
`this` is lost. Bind it, wrap it in an arrow, or use a class field arrow.

**Scope and hoisting.** `var` is function-scoped and hoisted as `undefined`; `let` and `const` are
block-scoped and hoisted but in the temporal dead zone until initialised, which is why reading
before the declaration throws `ReferenceError` rather than returning `undefined`. Function
declarations hoist completely; function expressions assigned to `const` do not. A closure captures
the binding, not the value: with `var` in a loop, every callback sees the final value; with `let`,
each iteration gets a fresh binding. That single difference is the whole explanation for the
classic `setTimeout` loop bug.

**The prototype chain.** Property lookup walks the object, then its prototype, then that
prototype's prototype, until `null`. `Object.create(proto)` makes the link explicit;
`Object.getPrototypeOf` reads it. `class` syntax is a thin layer over the same chain: methods live
on the prototype, instance fields on the object, and `super` walks the parent prototype. `for...
in` enumerates inherited enumerable string keys, which is why it is wrong for arrays; `for...
of` iterates values of an iterable, and `Object.entries` gives keys and values without surprise.

**Arrays are objects with a `length`.** They can be sparse: `const a = [1, , 3]` has a hole, and
`map`, `forEach` and `filter` skip holes while `Array.from` does not. `sort` mutates the array and,
without a comparator, sorts by UTF-16 code units, so `[10, 9, 1].sort()` is `[1, 10, 9]`.
`toSorted`, `toReversed`, `toSpliced` and `with` (ES2023) are the non-mutating versions. `forEach`
cannot be stopped; use `some`/`every` or a `for...of` loop with `break`.

**JSON is lossy by design.** `JSON.stringify` omits properties whose value is `undefined`, a
function or a symbol; converts `NaN` and `Infinity` to `null`; serialises dates with
`toISOString`; turns maps and sets into `{}`; and throws on `BigInt` and cycles. `JSON.parse`
returns plain objects, loses prototypes, and will happily parse `{"__proto__": ...}` into an own
property - prototype pollution is a real attack when merging parsed input into objects. Parse at a
trust boundary and validate the shape before use.

| Check | Truthy when | Use for |
| --- | --- | --- |
| `if (value)` | Not `false`, `0`, `-0`, `0n`, `""`, `null`, `undefined`, `NaN` | Booleans and objects only |
| `value ?? fallback` | `null` or `undefined` only | Defaults that must keep `0` and `""` |
| `value \|\| fallback` | Any falsy value | A default when `0`/`""` are invalid anyway |
| `value === undefined` | Undefined only | Distinguishing "missing" from `null` |
| `Number.isFinite(value)` | A real number | Numeric input validation |

**The judgment call.** Use `===` and `??`, `Object.is` for edge numeric comparisons, spread for
one-level copies and `structuredClone` for deep ones. Treat objects as shared unless you copied
them, and treat `this` as a property of the call site. Most "JavaScript weirdness" is one of
those four sentences being violated.""",
            r"""console.log(typeof null, typeof [], typeof (() => {}));

console.log(0.1 + 0.2);
console.log(9007199254740993);
console.log(Number.MAX_SAFE_INTEGER);

console.log([] == false, "" == 0, null == undefined, null == 0);
console.log(Object.is(NaN, NaN), NaN === NaN);
console.log(Object.is(0, -0));

const original = { name: "ana", tags: ["a"] };
const shared = original;
const shallow = { ...original };
shallow.name = "bo";
shallow.tags.push("b");
console.log(original, shared);

const deep = structuredClone(original);
deep.tags.push("c");
console.log(original.tags, deep.tags);

const counter = {
  count: 0,
  increment() { this.count += 1; return this.count; },
};
const detached = counter.increment;
console.log(counter.increment());
try { console.log(detached()); } catch (error) { console.log(error.name); }

const callbacks = [];
for (var i = 0; i < 3; i++) callbacks.push(() => i);
console.log(callbacks.map((fn) => fn()));

const stable = [];
for (let j = 0; j < 3; j++) stable.push(() => j);
console.log(stable.map((fn) => fn()));

console.log([10, 9, 1].sort());
console.log([10, 9, 1].sort((a, b) => a - b));

console.log(JSON.stringify({ a: undefined, b: NaN, c: new Date(0) }));
""",
            "Predict every output before running the example, then explain each line in one sentence. Next, "
            "write a deep clone that keeps `Date` and `Map` values, and compare it with `structuredClone`. "
            "Finally, find a loop in your own code that captures a variable and fix it without changing the "
            "iteration order. Practise with /practice/problems/group-anagrams.",
        ),
        (
            "js-stdlib-deep",
            "The platform library: arrays, Intl, fetch and the Node core",
            "Array and object utility, Map and Set identity rules, date and Intl formatting, regular "
            "expressions, promise combinators, fetch with cancellation, and the Node modules that replace packages.",
            r"""**Why this matters.** The JavaScript platform is much larger than the language: arrays and
objects, `Intl`, `Date`, `RegExp`, promises, `fetch`, `URL`, `TextEncoder`, `structuredClone`, and
- in Node - `fs`, `path`, `process`, `stream` and the test runner. Most utility packages exist
because the author did not know one of these, or knew an older version of it. This module is the
map, with the identity and mutation rules that decide whether a shortcut is safe.

**Arrays.** `map`, `filter`, `reduce`, `find`, `findIndex`, `some`, `every`, `flat`, `flatMap`,
`includes`, `indexOf`, `slice`, `splice`, `concat`, `join`, `at` (negative indexing) and the
ES2023 non-mutating `toSorted`/`toReversed`/`toSpliced`/`with`. Know which ones mutate: `sort`,
`reverse`, `splice`, `push`, `pop`, `shift`, `unshift`, `fill`, `copyWithin`. `includes` uses
SameValueZero, so it finds `NaN`; `indexOf` uses strict equality, so it does not. `reduce` without
an initial value throws on an empty array. `Object.groupBy` and `Map.groupBy` (ES2024) replace the
hand-written grouping loop.

**Objects.** `Object.keys`, `values`, `entries`, `fromEntries`, `assign`, `freeze`, `seal`,
`hasOwn` (replaces `hasOwnProperty.call`), `getPrototypeOf`, `defineProperty`. `Object.fromEntries`
plus `Object.entries` is the clean way to transform a record. `Object.freeze` is shallow, and
`Object.seal` prevents adding or removing keys but allows changing values. Property descriptors
(`writable`, `enumerable`, `configurable`) are how libraries create non-enumerable methods.

**Map, Set and WeakMap.** `Map` keys keep insertion order, allow any type and use SameValueZero, so
`NaN` is a valid key and `+0`/`-0` are the same key. Objects as keys are compared by identity, not
by content, which is the difference from a plain object. `Set` deduplicates by the same rule.
`WeakMap` and `WeakSet` hold keys weakly, so entries disappear when the key is collected; that is
the right place to attach metadata to DOM nodes or objects you do not own. Weak collections are not
iterable and have no `size`, by design.

**Text and Unicode.** Strings are UTF-16 code units. `"😀".length` is 2; `[...str]` iterates code
points; `Intl.Segmenter` segments grapheme clusters, words and sentences. `normalize("NFC")` makes
canonically equivalent strings compare equal - important for usernames and search. `localeCompare`
sorts by language rules; `Intl.Collator` caches the comparison for repeated sorts.

**Intl replaces date libraries.** `Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle:
"short", timeZone: "Asia/Kolkata" })` formats without a dependency; `Intl.NumberFormat` handles
currency, percent, compact notation and units; `Intl.RelativeTimeFormat` produces "3 days ago";
`Intl.PluralRules` and `Intl.ListFormat` handle grammar. All of them take a locale explicitly when
output must be stable across environments.

**Dates.** `Date` is a timestamp plus a UTC/local presentation, and its API is famously easy to
misuse: months are zero-based, `getMonth()` and `getUTCMonth()` differ, `new Date("2026-01-01")`
is parsed as UTC while `new Date("2026-01-01T00:00")` is parsed as local, and the local rules
follow the host time zone, including DST. Store and transmit ISO-8601 UTC strings; convert at the
edge with `Intl`; never add 24 hours to represent "tomorrow" in a zone with DST. `Temporal` is
the intended replacement, but support is still uneven, so check the target before adopting it.

**Regular expressions.** Literals are compiled once; `new RegExp` in a loop is not. The `g` flag
makes `test` and `exec` stateful through `lastIndex`, which is why a global regex reused across
calls alternates true/false; `matchAll` requires `g` and returns an iterator. Named groups
(`(?<year>\d{4})`), lookbehind, Unicode property escapes (`\p{Letter}` with `u`) and the `d` flag
for match indices are all standard now. Beware catastrophic backtracking: `(a+)+$` against a long
non-matching string can freeze the process. There is no timeout in the language; validate input
length and prefer simpler patterns. Never parse HTML with a regex.

**Promises and async.** `Promise.all` fails fast, `allSettled` waits for every outcome, `race`
takes the first to settle and `any` takes the first to fulfil (rejecting with `AggregateError` if
all fail). `withResolvers` (ES2024) exposes the resolve/reject pair without the executor dance.
An `async` function always returns a promise, and a `throw` inside it becomes a rejection. An
unhandled rejection does not stop Node or the browser by default; it should be logged and treated
as a bug. `await` in a loop is sequential - use `Promise.all` for independent work, but bound the
concurrency when the downstream service has limits.

**Fetch and cancellation.** `fetch` rejects only on network failure; an HTTP 404 or 500 resolves
with `response.ok === false`, so check it. Pass `AbortSignal.timeout(5000)` or an
`AbortController` for cancellation; an aborted request rejects with `AbortError`. Responses are
streams: `response.json()`, `.text()`, `.arrayBuffer()` consume the body once. Set the `content-type`
header yourself for JSON bodies, and remember that CORS is a browser rule, not a server one.

**URL and bytes.** `new URL(input, base)` parses and resolves; `URLSearchParams` encodes query
values (and turns spaces into `+`, which matters when a server expects `%20`). `TextEncoder` and
`TextDecoder` convert between strings and UTF-8 bytes; `atob`/`btoa` are Latin-1 only, so encode
first. `structuredClone` deep-clones; `crypto.randomUUID()` generates an identifier in secure
contexts; `crypto.getRandomValues` is the correct source for tokens.

**Node core.** `node:fs/promises` for file IO (`readFile`, `writeFile`, `readdir`, `mkdir` with
`recursive: true`, `stat`), `node:path` for `join`/`resolve`/`dirname`, `node:os` for platform and
CPU information, `process.argv` for arguments (or `node:util` `parseArgs` for flags), `node:test`
and `node:assert` for tests, `node:readline` for line input, `node:stream` for pipelines,
`node:worker_threads` for CPU work off the main thread, and `node:child_process` with `spawn`
(argument arrays, never a shell string built from input). `node:events` provides `EventEmitter`;
`node:crypto` provides hashing and HMAC.

| Method | Mutates? | Returns | Use when |
| --- | --- | --- | --- |
| `push` / `pop` / `shift` / `unshift` | Yes | New length or element | Building a list in place |
| `sort` / `reverse` | Yes | The same array | You own the array |
| `toSorted` / `toReversed` / `with` | No | A new array | The input is shared (state, props) |
| `splice` | Yes | Removed elements | Editing in place |
| `slice` | No | A shallow copy range | Taking a view of a list |
| `map` / `filter` | No | A new array | Transforming values |

**The judgment call.** Reach for `Intl` before a date or number package, `structuredClone` before a
clone package, `fetch` before an HTTP client (except where you need agent-level control), and the
`node:` core before a utility. Check the mutation column before calling an array method, and pass an
explicit time zone and locale anywhere output must be reproducible.""",
            r"""const rows = [
  { team: "red", points: 10 },
  { team: "blue", points: 7 },
  { team: "red", points: 4 },
];

const totals = Object.groupBy(rows, (row) => row.team);
console.log(totals);

const votes = new Map();
votes.set("ana", 2);
votes.set("bo", 3);
votes.set("ana", votes.get("ana") + 1);
console.log([...votes.entries()]);

const when = new Date("2026-03-08T06:30:00Z");
console.log(new Intl.DateTimeFormat("en-GB", {
  dateStyle: "full", timeStyle: "short", timeZone: "Asia/Kolkata",
}).format(when));

console.log(new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
}).format(1250000));

const text = "The year 2026 and the year 1999";
for (const match of text.matchAll(/(?<year>\d{4})/g)) {
  console.log(match.groups.year, match.index);
}

async function load(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

Promise.allSettled([load("/a"), load("/b")]).then((results) => {
  for (const result of results) {
    console.log(result.status, result.status === "fulfilled" ? result.value : result.reason.message);
  }
});

const params = new URLSearchParams({ q: "binary search", page: "2" });
console.log(params.toString());
console.log(new TextEncoder().encode("héllo").length);
""",
            "Rewrite a date-formatting helper so it uses `Intl` and an explicit time zone, then prove it is stable "
            "in two environments. Replace a promise chain with `allSettled` plus per-result error handling, and "
            "add a timeout to every network call. Finally, reproduce the stateful global-regex bug with `test` "
            "and fix it with `matchAll` or a fresh regex. Practise with /practice/problems/top-k-frequent.",
        ),
        (
            "js-diagnostics-deep",
            "Debugging JavaScript: errors, async stacks, memory and the network",
            "The error taxonomy, lost async stack traces, unhandled rejections, event-loop starvation, "
            "the leak patterns DevTools finds, and the Node diagnostics that survive production.",
            r"""**Why this matters.** JavaScript rarely crashes loudly. It rejects a promise nobody awaits,
leaks a listener per render, or blocks the event loop for 400 ms and calls it "slow". The skill is
not memorising error names; it is knowing which layer owns the failure - language, runtime, event
loop, memory or network - and reaching for the tool that measures that layer.

**The error taxonomy.** `TypeError` means a value was not the kind the operation required, and the
overwhelmingly common case is reading a property of `undefined` (`Cannot read properties of
undefined (reading 'name')`). The message names the property, not the object that was supposed to
own it; trace the producer. `ReferenceError` is an undeclared name or a temporal-dead-zone read.
`SyntaxError` is a parse failure, including `JSON.parse` on malformed input. `RangeError` is
`Invalid array length`, a call stack overflow or an invalid `toFixed` digit count. `AggregateError`
groups failures from `Promise.any`. `DOMException` covers browser APIs (`AbortError`,
`QuotaExceededError`, `NotAllowedError`).

**Try/catch does not catch everything.** It catches synchronous throws and awaits inside `try`. It
does not catch a rejected promise that was never awaited, an error thrown in a `setTimeout`
callback, or an error in another microtask. For those, register `window.onunhandledrejection` /
`window.onerror` in the browser, or `process.on("unhandledRejection")` and
`process.on("uncaughtException")` in Node - and treat both as last-resort logging, because the
process state is no longer trustworthy.

**Async stack traces.** An error thrown after an `await` appears at the `await` line, not at the
call that started the chain. Modern V8 stitches async frames when it can, but the chain is often
incomplete across timers and event handlers. Carry context explicitly: wrap the failure with the
operation and identifiers (`throw new Error("loadOrders failed", { cause: error })`), use
`Error.captureStackTrace` only when you know why, and log the request id alongside the trace.

**Event-loop starvation.** The loop runs one macrotask at a time and drains the microtask queue
between them. A long synchronous computation blocks timers, rendering and I/O; a chain of
`Promise.resolve().then(...)` can starve timers indefinitely because microtasks keep refilling. A
`while` loop that polls a flag never yields. Move CPU work to a worker, chunk it with
`scheduler.yield()` or `setTimeout`, and measure long tasks with `PerformanceObserver` rather than
guessing.

**Memory leaks in a garbage-collected language.** The collector frees what is unreachable; a leak is
a reference you kept. The four patterns that matter:
* a listener added on every render and never removed (`addEventListener` without
  `removeEventListener`, or an `AbortSignal` you never abort);
* a global or module-level array that accumulates;
* a closure held by a long-lived timer or subscription that captures a large object;
* a detached DOM node still referenced from a map or array, so the whole subtree stays alive.

DevTools' Memory panel takes a heap snapshot; compare two snapshots after repeating an action and
look for retained objects that grow. The Performance monitor shows the JS heap trend. In Node,
`--inspect` plus Chrome DevTools, or `node --heap-prof` for an allocation profile.

**The browser toolbox.** The Console is for state, not for logging everything; `console.table`,
`console.group`, `console.time`/`timeEnd`, `console.trace` and `console.assert` exist for a reason.
The Sources panel sets breakpoints, conditional breakpoints and logpoints, and evaluates in the
paused scope. The Network panel answers "was it slow or was it 500?" - check status, timing,
request payload and response headers before touching code. Lighthouse measures, it does not
diagnose.

**Source maps and production.** Minified code without source maps gives you line 1, column 48213.
Ship source maps to your error tracker, not necessarily to the public; configure the bundler to
emit them and upload them in CI. Log the release version with every error so a stack can be mapped
to the build that produced it.

**Node diagnostics.** `node --inspect-brk script.js` waits for a debugger. `node --cpu-prof`
writes a CPU profile; `--heap-prof` writes allocations; `--trace-gc` shows GC pauses. `process.
memoryUsage()` and `process.hrtime.bigint()` measure. `--trace-warnings` turns warnings into
visible output at startup. The `diagnostics_channel` module and `async_hooks` are for libraries and
APM agents, not application code; `AsyncLocalStorage` is the right tool for request-scoped context
across async boundaries.

**The error-handling shape that holds.** Validate at the boundary (HTTP input, JSON.parse, storage,
third-party responses), convert to a domain error with a message that names the operation, log once
at the layer that can act, and return a result the caller can handle. A library should throw typed
errors and not log; an application should catch at its edges and log with context. Never swallow an
error to keep a promise chain tidy - a `.catch(() => {})` is a bug with a delay fuse.

| Symptom | First question | Tool |
| --- | --- | --- |
| `TypeError` reading a property | Which producer returned undefined? | Breakpoint on the producer |
| Tab freezes, timers late | Which task runs too long? | Performance panel, long-task markers |
| Heap grows per interaction | What is retained and by whom? | Memory panel, heap snapshot diff |
| Slow request | Slow or failing? | Network panel: status, timing, payload |
| Rejection nobody handled | Which promise lost its `await`? | `unhandledrejection`, async stack |

**The judgment call.** Identify the layer first: a `TypeError` is usually a missing guard at a
boundary, an unhandled rejection is a missing `await`, a frozen tab is a blocking task, a rising
heap is a retained reference. Measure with the platform tools before adding a library that
"handles errors" for you.""",
            r"""const pending = new Map();

function withTimeout(promise, ms, label) {
  const timer = new Promise((_, reject) => {
    const id = setTimeout(() => reject(new Error(`${label} timed out after ${ms} ms`)), ms);
    promise.finally(() => clearTimeout(id));
  });
  return Promise.race([promise, timer]);
}

async function loadUser(id) {
  const response = await fetch(`/api/users/${id}`);
  if (!response.ok) {
    throw new Error(`loadUser(${id}) failed with ${response.status}`);
  }
  return response.json();
}

process.on("unhandledRejection", (reason) => {
  console.error("unhandled rejection:", reason.message);
});

withTimeout(loadUser(7), 2000, "loadUser")
  .catch((error) => {
    console.error(error.message);
    return { id: "unknown", name: "offline" };
  })
  .then((user) => console.log("resolved to", user));

function chunkedWork(items, handle) {
  let index = 0;
  function step() {
    const started = performance.now();
    while (index < items.length && performance.now() - started < 8) {
      handle(items[index]);
      index += 1;
    }
    if (index < items.length) setTimeout(step, 0);
  }
  step();
}

chunkedWork([1, 2, 3, 4, 5], (value) => console.log(value * value));

const controller = new AbortController();
controller.signal.addEventListener("abort", () => {
  console.log("cancelled:", controller.signal.reason);
});
controller.abort(new Error("user navigated away"));

pending.set("job-1", controller);
pending.delete("job-1");
console.log("pending jobs:", pending.size);
""",
            "Reproduce three failures deliberately: a property read on `undefined`, an unhandled rejection, and a "
            "timer that is never cleared. For each, write the diagnostic question you would ask first and the "
            "tool that answers it. Then take a page or script you own, record a heap snapshot before and after "
            "repeating an action ten times, and explain what grew. Practise with "
            "/practice/problems/course-schedule.",
        ),
    ],
    "typescript": [
        (
            "ts-semantics-deep",
            "The type system as a proof system, and where the proof stops",
            "Structural typing, widening and narrowing, discriminated unions, variance, generics, "
            "conditional and mapped types, and the erasure rule that makes runtime validation necessary.",
            r"""**Why this matters.** TypeScript is not "JavaScript with types" in the sense of annotations
that document what you already know. It is a checker with its own logic: assignability is
structural, literals widen unless you stop them, unions narrow through control flow, and generics
are solved by unification. Knowing the logic turns type errors from obstacles into proofs, and
knowing the erasure rule stops you trusting the types at runtime.

**Structural typing.** A value is assignable to a type when it has the required shape; the name of
the type is irrelevant. `{ name: string; age: number }` is assignable to `{ name: string }`, and a
class instance is assignable to an interface it never declares. Two consequences: a typo in a
property name is an excess-property error only on a fresh object literal (which is why
`satisfies` helps), and a structurally identical but semantically different type is assignable
(`Meters` and `Feet` are both `number`). Branding fixes the second: intersect with a phantom
property, `type Meters = number & { readonly __brand: "Meters" }`.

**Widening and literal types.** `let x = "on"` has type `string`; `const x = "on"` has type `"on"`.
Object properties widen, which is why `const config = { mode: "dark" }` passes `string` to a
function that wants `"dark" | "light"`. `as const` freezes the literals and makes properties
readonly; `satisfies` checks a value against a type while keeping the narrow inferred type, which
is the right tool for configuration objects and lookup tables.

**Narrowing is control-flow analysis.** `typeof x === "string"`, `Array.isArray(x)`,
`x instanceof Date`, `"kind" in x`, `x === null` and a user-defined predicate
(`function isUser(x: unknown): x is User`) all narrow the type inside the branch. A discriminated
union - every member with a literal `kind` - plus a `switch` gives exhaustiveness: the `default`
branch assigns to `never`, so adding a member without handling it is a compile error.

**`any`, `unknown` and `never`.** `any` disables checking and spreads silently through every
expression; it is an escape hatch, not a type. `unknown` accepts anything but requires narrowing
before use, which is the correct type for `JSON.parse`, caught errors (`catch (error: unknown)`)
and third-party boundaries. `never` is the empty type: a function that always throws, an
impossible branch, and the exhaustiveness check.

**Variance.** Arrays are covariant (`Dog[]` is assignable to `Animal[]`) even though that is unsound
for writes; TypeScript accepts it for ergonomics, which is why `push` on a widened array can put a
`Cat` into a `Dog[]`. Function parameter positions are checked bivariantly for method syntax and
contravariantly for function-property syntax under `strictFunctionTypes`. Readonly arrays
(`readonly T[]`) remove the write methods, which is the honest type for a parameter you do not
mutate.

**Generics.** A type parameter is a constraint, not a wildcard. `<T extends { id: string }>` lets
you read `id`; `<T = string>` supplies a default; `keyof T` gives the keys; `T[K]` indexes.
Inference works left to right, so a generic that appears only in the return type cannot be inferred
from the arguments and must be supplied explicitly. Prefer a generic when the relationship between
inputs and outputs matters; use a union when the set is closed.

**Conditional, mapped and template-literal types.** `T extends U ? X : Y` computes a type; with
`infer` it extracts (`type Element<T> = T extends (infer U)[] ? U : never`). Mapped types transform
every key (`{ [K in keyof T]?: T[K] }`), and key remapping (`as`) renames or filters them.
Template-literal types compose strings (`type Event = `on${Capitalize<"click" | "focus">}``), which
is how typed event maps and route parameters are built. These are compile-time computations: they
cost checker time and produce error messages that name the expanded type, so wrap a complicated one
in a named alias.

**Erasure.** Types are removed at compile time. There is no runtime check behind `as User`; it is an
assertion, not a conversion. `enum` is the exception that emits an object (unless `const enum` or
`erasableSyntaxOnly`), and class parameter properties and decorators emit code too. The practical
rule: every value that enters the program from outside - JSON, `localStorage`, URL parameters,
messages, form data - is `unknown` until a validator proves otherwise. A schema library (Zod,
Valibot, ArkType) or a hand-written guard is the boundary; the type is the interior.

**Declaration merging and modules.** Interfaces with the same name merge, which is how libraries
extend `Window` or `Express.Request`; module augmentation does the same for a module. Type-only
imports (`import type`) disappear at runtime; `verbatimModuleSyntax` enforces the distinction.
Namespace declarations are for declaration files and legacy code, not for new application code.

| Keyword | Accepts | Requires narrowing |
| --- | --- | --- |
| `any` | Everything | No - checking is off from here |
| `unknown` | Everything | Yes, before any use |
| `never` | Nothing | It is the empty type (a `throw`, an impossible branch) |
| `object` | Any non-primitive | Yes, before property access |
| `Record<string, T>` | Any object | No, and every key looks present |

**The judgment call.** Use `unknown` at boundaries, discriminated unions for closed variants,
generics for relationships, `satisfies` for configuration, and a runtime validator wherever the
data came from outside. Trust a type only as far as the code that constructed it.""",
            r"""type Result<T> =
  | { kind: "ok"; value: T }
  | { kind: "error"; message: string };

function unwrap<T>(result: Result<T>): T {
  switch (result.kind) {
    case "ok":
      return result.value;
    case "error":
      throw new Error(result.message);
    default: {
      const never: never = result;
      return never;
    }
  }
}

type User = { id: string; name: string; role: "admin" | "member" };

function isUser(value: unknown): value is User {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.id === "string"
    && typeof candidate.name === "string"
    && (candidate.role === "admin" || candidate.role === "member");
}

const parsed: unknown = JSON.parse('{"id":"u1","name":"Ana","role":"admin"}');
if (isUser(parsed)) {
  console.log(parsed.name.toUpperCase());
}

const routes = {
  home: "/",
  user: "/users/:id",
} as const;

type RouteName = keyof typeof routes;
type RoutePath = (typeof routes)[RouteName];

function navigate(name: RouteName): RoutePath {
  return routes[name];
}

console.log(navigate("home"));
console.log(unwrap<number>({ kind: "ok", value: 42 }));

type ElementOf<T> = T extends readonly (infer U)[] ? U : never;
const first: ElementOf<readonly string[]> = "a";
console.log(first);
""",
            "Write a `Result` type with three variants and prove exhaustiveness with a `never` branch. Then take a "
            "`JSON.parse` call and replace the `any` with an `unknown` plus a guard, and show the error the "
            "compiler gives when the guard is removed. Finally, convert a config object to `satisfies` and "
            "explain what type it has now that it did not have before. Practise with "
            "/practice/problems/valid-parentheses.",
        ),
        (
            "ts-stdlib-deep",
            "Types for the platform: lib.d.ts, DOM, Node and the JSON boundary",
            "Which library definitions apply, typing the DOM and Node APIs, utility types that earn "
            "their keep, iterators and promises, module resolution and declaration files.",
            r"""**Why this matters.** Most TypeScript frustration is not the language; it is the environment.
`document` is not defined in Node, `process` is not defined in the browser, `fetch` exists in both
but its types come from different libraries, and `JSON.parse` returns `any` no matter how careful
the rest of the code is. Knowing which `lib` is loaded, and where the boundary types come from,
removes the noise and restores the checker.

**The `lib` setting and the DOM.** `target` decides which syntax is downlevelled; `lib` decides
which global declarations exist. `"lib": ["ES2023", "DOM", "DOM.Iterable"]` in a browser project;
`"lib": ["ES2023"]` plus `@types/node` on the server. Without `DOM`, `document`, `window`,
`localStorage` and `fetch` are missing; with it on the server, the compiler accepts browser APIs
that will fail at runtime. A shared package should avoid both and take the environment as an
explicit dependency.

**DOM types are accurate, not convenient.** `document.querySelector` returns `Element | null`;
`Element` has no `.value`, so you need `HTMLInputElement` and a cast or a generic
(`querySelector<HTMLInputElement>("#email")`). The null is real: the element may not exist. Event
handlers receive `Event`, which must be narrowed to `MouseEvent`, `KeyboardEvent` or
`SubmitEvent` before reading `key` or `preventDefault`. `Element.closest` also returns null.
`structuredClone`, `AbortSignal.timeout` and `crypto.randomUUID` are in modern DOM libs; older
`lib` settings will not have them.

**Node types.** `@types/node` declares `process`, `Buffer`, `__dirname`, `require` and the
`node:` modules. In ESM, `__dirname` is not defined; use `import.meta.url` and
`fileURLToPath`. `process.env.X` is `string | undefined`, and treating it as a string is the most
common Node type lie; parse and validate configuration once at startup. `Buffer` is a `Uint8Array`
subtype with its own encodings; `fs.readFile` with no encoding returns a `Buffer`, with `"utf8"`
returns a `string`, which is why the overload you pick changes the return type.

**`JSON.parse` is the boundary.** It returns `any`, so every downstream access is unchecked and the
`any` propagates through inference. The fix is one function: parse to `unknown`, validate the
shape, return a typed value, and throw a domain error with the path that failed. The same rule
applies to `response.json()`, `localStorage.getItem` plus `JSON.parse`, and `postMessage`.

**Utility types that earn their keep.** `Partial<T>`, `Required<T>`, `Readonly<T>`, `Record<K, V>`,
`Pick<T, K>`, `Omit<T, K>`, `Exclude<T, U>`, `Extract<T, U>`, `NonNullable<T>`, `ReturnType<F>`,
`Parameters<F>`, `Awaited<T>`, `InstanceType<C>`. Use them to derive types from the source of
truth rather than restating shapes. `Omit` on a union distributes badly (`Omit<A | B, "kind">`
collapses the distinction); `Exclude` on a union is the right tool. `Record<string, T>` makes every
key look present, so `noUncheckedIndexedAccess` is what makes indexing honest.

**Functions and overloads.** Optional parameters (`x?: T`) and default parameters
(`x: T = value`) are different: an optional parameter's type includes `undefined` inside the
function. Overload signatures are for public APIs with genuinely different call shapes; a union of
parameter types plus narrowing is usually clearer. Generic constraints express "has this method",
not "is this class".

**Iterators, generators and promises.** `Iterable<T>` and `Iterator<T>` describe `for...of`;
`AsyncIterable<T>` describes `for await...of`. A generator's return type is
`Generator<Yield, Return, Next>`. `Promise<T>` composes with `Awaited<T>`; an `async` function's
return type is always a promise, so annotating it as `Promise<T>` is correct and annotating it as
`T` is an error. `Promise.all` preserves tuple types when the argument is a tuple, which is a small
feature that removes a lot of casts.

**Modules and declarations.** `moduleResolution: "bundler"` for a bundler, `"node16"`/`"nodenext"`
for Node's ESM rules, `"classic"` only for legacy. A `.d.ts` file describes a JavaScript module that
has no types; keep it next to the source or publish it with the package. `declare module "x"` is a
last resort for untyped dependencies, and it should describe the real API, not `any`. Project
references split a monorepo into buildable units and make incremental builds fast.

**Strict flags that pay for themselves.** `strict` enables the family, including
`strictNullChecks`, `strictFunctionTypes`, `strictPropertyInitialization` and
`useUnknownInCatchVariables`. `noUncheckedIndexedAccess` makes `arr[i]` include `undefined`, which
is true. `exactOptionalPropertyTypes` distinguishes "missing" from "present and undefined".
`noImplicitOverride` and `noFallthroughCasesInSwitch` catch real bugs. `verbatimModuleSyntax`
keeps `import type` honest. Turn them on in a new project; in an old one, turn them on one at a
time with a baseline.

| Source of data | Type it arrives as | What to do |
| --- | --- | --- |
| `JSON.parse` | `any` | Return `unknown`, validate, then narrow |
| `response.json()` | `any` | Same as JSON.parse, plus a status check |
| `localStorage.getItem` | `string \| null` | Parse, validate, handle null |
| `process.env.X` | `string \| undefined` | Parse and validate config at startup |
| `document.querySelector` | `Element \| null` | Null-check and narrow to the element type |
| `postMessage` payload | `any` | Treat as `unknown` and validate |

**The judgment call.** Know which lib you compiled against, treat every external value as
`unknown`, derive types from the source of truth with utility types, and make indexing honest with
`noUncheckedIndexedAccess`. The DOM's nulls are real; the environment's globals are not
interchangeable.""",
            r"""type Config = {
  port: number;
  host: string;
  debug?: boolean;
};

function parseConfig(raw: unknown): Config {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("config must be an object");
  }
  const value = raw as Record<string, unknown>;
  if (typeof value.port !== "number" || typeof value.host !== "string") {
    throw new Error("config needs a numeric port and a string host");
  }
  if (value.debug !== undefined && typeof value.debug !== "boolean") {
    throw new Error("debug must be a boolean");
  }
  return { port: value.port, host: value.host, debug: value.debug };
}

const env = parseConfig(JSON.parse('{"port":8080,"host":"localhost"}'));

type User = { id: string; name: string; email: string; createdAt: Date };
type UserRow = Omit<User, "createdAt"> & { createdAt: string };
type PublicUser = Pick<User, "id" | "name">;

const row: UserRow = { id: "u1", name: "Ana", email: "a@example.com", createdAt: "2026-01-02T00:00:00Z" };
const publicUser: PublicUser = { id: row.id, name: row.name };

async function firstLine(path: string): Promise<string> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const text = await response.text();
  return text.split("\n")[0] ?? "";
}

const entries: [string, number][] = [["a", 1], ["b", 2]];
const record: Record<string, number> = Object.fromEntries(entries);

function isDefined<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

console.log(env, publicUser, record, firstLine("/x").catch(() => "offline"));
""",
            "Type a small browser module and a small Node module with separate `lib` settings and show the errors "
            "each environment produces in the other. Replace three `any` values from `JSON.parse`, `fetch` and "
            "`localStorage` with guarded `unknown` values. Then add `noUncheckedIndexedAccess` to a project and "
            "fix the errors it reveals without using `!`. Practise with /practice/problems/validate-ipv4.",
        ),
        (
            "ts-diagnostics-deep",
            "Reading TypeScript errors and shipping types that hold",
            "The error codes that account for most failures, narrowing patterns, generic inference "
            "troubles, strict flags, declaration emit and the runtime validation boundary.",
            r"""**Why this matters.** TypeScript errors are precise and often read as cryptic because the
compiler prints the expanded type. Once you can recognise the twenty codes that cover most
failures, the checker becomes a fast reviewer rather than an obstacle. The second half of the
lesson is the harder half: making types survive a build, a package boundary and a runtime full of
untrusted data.

**The codes you will meet most.**
| Code | Message | Usual cause |
| --- | --- | --- |
| 2322 | Type X is not assignable to type Y | Shape mismatch, widened literal, null |
| 2345 | Argument of type X is not assignable to parameter of type Y | Wrong argument order or a widened value |
| 2339 | Property does not exist on type | Typo, missing union member, wrong narrowing |
| 2532 | Object is possibly undefined | Honest nullability from an index or optional field |
| 18046 | `x` is of type unknown | Missing guard before use |
| 7006 | Parameter implicitly has an `any` type | No annotation and no inference context |
| 7053 | No index signature with parameter of type string | Accessing a record with a dynamic key |
| 2769 | No overload matches this call | Argument types do not fit any overload |
| 2352 | Conversion may be a mistake | `as` across unrelated types |
| 2741 | Property is missing in type | Incomplete object literal |
| 2554 | Expected N arguments, but got M | Wrong call arity, often an optional parameter |

**Read the type, not the line.** The message prints two types; compare them structurally. A
`never` in the message means the compiler concluded there is no value of that type at that point -
often a `default` branch after exhaustive handling, or an impossible generic constraint. A union
printed across many lines is a single type; the last line of the message names the offender.

**Narrowing patterns that keep working.** Prefer early returns (`if (!user) return;`) over nested
conditions, so the type narrows for the rest of the function. Use `in` for discriminated unions
without a tag, `instanceof` for classes, `Array.isArray` for arrays and a user-defined predicate when
the check is non-trivial. Avoid `as` for narrowing; an assertion tells the compiler to stop
checking, and the runtime error moves to production. When you must assert, assert to `unknown`
first so the cast cannot be accidental.

**Generic inference troubleshooting.** The compiler infers type parameters from arguments, then
checks the body. If inference produces `unknown` or a union you did not expect, annotate the call
site explicitly (`select<User>(rows)`), add a default (`<T = never>`), or split the generic so each
parameter appears in exactly one position. Constraints that reference other parameters
(`<K extends keyof T>`) are usually fine; constraints across mutually recursive types produce error
messages that are hard to read, so name intermediate aliases.

**Function variance and method syntax.** `strictFunctionTypes` checks function-property parameters
contravariantly; methods are bivariant for compatibility with the DOM and older libraries. When a
callback type is rejected, check whether the parameter is declared as a method or a property.
`readonly` on parameters is documentation and a hint; it does not stop mutation of a nested object.

**Strict flags as a migration plan.** Start with `strict: true` if the codebase is small. Otherwise
turn on `noImplicitAny`, then `strictNullChecks`, then `strictFunctionTypes`, then
`useUnknownInCatchVariables`, then `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`.
Each step produces a burst of errors and then a permanently smaller class of bug. Do not silence a
new flag with `// @ts-ignore`; use `@ts-expect-error` only where a test is deliberately checking
that a call fails, because it errors when the error disappears.

**Declaration emit.** `declaration: true` writes `.d.ts` files; the public types are now an API
contract. Keep exported types explicit and stable, avoid leaking private class members, and run
`tsc --noEmit` in CI plus an API extractor if the package is consumed by others. `isolatedModules`
forces each file to be independently transpilable, which is what bundlers and Node's type stripping
require; `verbatimModuleSyntax` makes `import type` the only way to import a type-only binding.

**Type tests.** A type test asserts that a type is what you think: `expectTypeOf(value).toEqualTypeOf<User>()`,
or a compile-only fixture with `// @ts-expect-error` for the negative cases. Run them in CI with
`tsc --noEmit`; they cost seconds and catch the regression a unit test cannot see.

**The runtime boundary.** Types vanish, so the only real guarantee is the validator at the edge. Put
one function per external shape - HTTP request, response, message, storage - and return a typed
domain object or throw a domain error. Keep the schema next to the type (`z.infer<typeof UserSchema>`)
so they cannot drift. Inside the program, trust the types; at the edge, trust nothing.

**Debugging the compiler itself.** `tsc --noEmit --extendedDiagnostics` reports time spent by phase;
`--generateTrace` writes a trace for `@typescript/perf-trace` when the project is slow.
`--explainFiles` shows why a file is in the program. A sudden slowdown is usually a new dependency
with a huge `.d.ts` or a recursive conditional type; isolate it rather than disabling the checker.

**The judgment call.** Fix the type, not the message: narrow instead of asserting, derive instead of
restating, validate at the boundary instead of trusting `any`. Turn on strict flags one at a time,
and treat the emitted declarations as part of the product.""",
            r"""type ApiResponse =
  | { status: "ok"; data: { id: string; name: string } }
  | { status: "error"; code: number; message: string };

function handle(response: ApiResponse): string {
  if (response.status === "error") {
    return `error ${response.code}: ${response.message}`;
  }
  return response.data.name;
}

function assertNever(value: never): never {
  throw new Error(`unhandled variant: ${JSON.stringify(value)}`);
}

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

function parseJson(text: string): Json {
  const value: unknown = JSON.parse(text);
  return toJson(value);
}

function toJson(value: unknown): Json {
  if (value === null || typeof value === "string" || typeof value === "number"
      || typeof value === "boolean") {
    return value;
  }
  if (Array.isArray(value)) return value.map(toJson);
  if (typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, toJson(item)]));
  }
  throw new Error(`not JSON: ${typeof value}`);
}

const rows = [{ id: "a" }, { id: "b" }];
const byId: Record<string, { id: string }> = Object.fromEntries(
  rows.map((row) => [row.id, row]),
);

console.log(handle({ status: "ok", data: { id: "1", name: "Ana" } }));
console.log(handle({ status: "error", code: 404, message: "missing" }));
console.log(parseJson('{"ok":true,"items":[1,2,null]}'), byId["a"]);
console.log(assertNever as unknown as string);
""",
            "Take a project without `strict` and turn the flags on in the order this lesson gives, recording the "
            "errors each one exposes. Fix them without `any`, `!` or `as`. Then add a compile-only type test that "
            "proves a bad call fails, using `@ts-expect-error`, and run it in CI. Finally, move one `JSON.parse` "
            "behind a validator and remove every downstream cast. Practise with "
            "/practice/problems/version-compare.",
        ),
    ],
}

MODULE_PRACTICE: dict[str, str] = {
    "js-semantics-deep": "group-anagrams",
    "js-stdlib-deep": "top-k-frequent",
    "js-diagnostics-deep": "course-schedule",
    "ts-semantics-deep": "valid-parentheses",
    "ts-stdlib-deep": "validate-ipv4",
    "ts-diagnostics-deep": "version-compare",
}
