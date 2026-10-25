"""Reference data, part 1: Python, Java, JavaScript, TypeScript and C.

Each language is a lookup table for a working programmer rather than a
tutorial: a short model of how the language runs, the syntax that carries
meaning, the type system, the standard library by job, the errors you will
actually meet with their causes and fixes, idioms, version history and
upstream sources.

Rows are deliberately short. The depth is in the *coverage* - a reference that
names the cause of an error and the fix is more useful than one that lists the
error - and in the cross-language table assembled by
``seed_data.language_reference``.
"""

from __future__ import annotations

REFERENCE: dict[str, dict] = {
    "python": {
        "version": "3.12 / 3.13",
        "tagline": "Dynamic, garbage-collected and battery-included, with readability as a design goal.",
        "model": [
            "CPython compiles source to bytecode and interprets it. Every value is an object with an "
            "identity, a type and a reference count; cyclic garbage is collected separately. Names are "
            "bindings to objects, so assignment rebinds and passing copies the reference, not the value.",
            "The global interpreter lock lets only one thread run Python bytecode at a time, so threads "
            "overlap I/O but not CPU work; processes and native extensions supply parallelism. Python 3.13 "
            "offers an experimental free-threaded build that removes the GIL, but it is a separate build "
            "and C extensions must opt in.",
        ],
        "facts": [
            {"label": "Execution", "value": "Bytecode on CPython; 3.13 adds an experimental JIT."},
            {"label": "Typing", "value": "Dynamic and strong; annotations are not enforced at runtime."},
            {"label": "Memory", "value": "Reference counting plus a cycle collector."},
            {"label": "Concurrency", "value": "Threads for I/O, processes for CPU, asyncio for many sockets."},
            {"label": "Null", "value": "One `None`; `None` is a singleton and falsy."},
            {"label": "Packaging", "value": "`venv` + `pip`, `pyproject.toml`, wheels on PyPI."},
        ],
        "syntax": [
            {"feature": "Function with defaults", "code": "def greet(name, greeting='Hello'):\n    return f'{greeting}, {name}'", "note": "Defaults are evaluated once at definition; use `None` for mutable defaults."},
            {"feature": "Class and dataclass", "code": "@dataclass(frozen=True)\nclass User:\n    id: int\n    name: str", "note": "Dataclasses generate init, repr and equality; `frozen` adds immutability."},
            {"feature": "Comprehension", "code": "squares = [n * n for n in range(10) if n % 2 == 0]", "note": "Scoped like a function; a generator expression avoids the list."},
            {"feature": "Context manager", "code": "with open(path, encoding='utf-8') as handle:\n    text = handle.read()", "note": "Calls `__enter__`/`__exit__`; the file closes on exceptions too."},
            {"feature": "Exception chain", "code": "try:\n    value = int(text)\nexcept ValueError as err:\n    raise ConfigError('bad value') from err", "note": "`from err` preserves the cause in the traceback."},
            {"feature": "Unpacking", "code": "first, *rest = values\nkey, value = pair", "note": "Starred targets collect the remainder into a list."},
            {"feature": "Pattern matching", "code": "match command:\n    case ['go', direction]:\n        move(direction)\n    case _:\n        raise ValueError(command)", "note": "Structural, not a switch on values; guards use `if`."},
            {"feature": "Type hint", "code": "def total(values: list[int]) -> int:\n    return sum(values)", "note": "Checked by mypy/pyright, not at runtime; `list[int]` needs 3.9+."},
        ],
        "types": [
            {"name": "int", "detail": "Arbitrary precision; no overflow, division `/` returns float, `//` floors."},
            {"name": "float", "detail": "IEEE-754 double; `0.1 + 0.2 != 0.3`; use `Decimal` for money."},
            {"name": "str", "detail": "Immutable Unicode code points; `len` counts code points, not bytes."},
            {"name": "bytes / bytearray", "detail": "Immutable/mutable byte sequences for binary I/O and encodings."},
            {"name": "list / tuple", "detail": "Mutable sequence vs immutable, hashable record; both support slicing."},
            {"name": "dict / set", "detail": "Hash-based O(1) lookup; keys must be hashable; insertion-ordered dict."},
            {"name": "None", "detail": "The single null value; test with `is None`, never `== None`."},
        ],
        "stdlib": [
            {"job": "Group and count", "api": "`collections.Counter`, `defaultdict`", "note": "`Counter.most_common`; `defaultdict(list)` for grouping."},
            {"job": "Paths and files", "api": "`pathlib.Path`", "note": "`read_text(encoding=...)`, `glob`, `mkdir(parents=True, exist_ok=True)`."},
            {"job": "Dates and zones", "api": "`datetime`, `zoneinfo`", "note": "Store aware UTC; convert for display; avoid naive `utcnow()`."},
            {"job": "JSON and CSV", "api": "`json`, `csv`", "note": "`json.dumps(ensure_ascii=False)`; open CSV with `newline=''`."},
            {"job": "Functional tools", "api": "`itertools`, `functools`", "note": "`chain`, `islice`, `groupby`, `cache`, `partial`."},
            {"job": "Regular expressions", "api": "`re`", "note": "Raw strings; `fullmatch` when the whole string must match."},
            {"job": "Concurrency", "api": "`threading`, `concurrent.futures`, `asyncio`, `multiprocessing`", "note": "Pick by bottleneck, not by fashion."},
            {"job": "Logging and CLI", "api": "`logging`, `argparse`", "note": "`getLogger(__name__)`; configure handlers once at entry."},
            {"job": "Local database", "api": "`sqlite3`", "note": "Parameterised SQL, explicit transactions, `row_factory`."},
        ],
        "errors": [
            {"error": "TypeError: 'NoneType' object is not callable", "cause": "A function returned `None`, or a name was shadowed by a value.", "fix": "Find the missing return; rename the shadowing binding."},
            {"error": "TypeError: 'NoneType' object is not subscriptable", "cause": "Indexed a value that a function returned as `None`.", "fix": "Check the producer's return path; fail at the source."},
            {"error": "UnboundLocalError", "cause": "A local name is read before the assignment that makes it local.", "fix": "Move the assignment earlier or declare `nonlocal`/`global` deliberately."},
            {"error": "KeyError", "cause": "Dictionary key absent.", "fix": "`dict.get`, `defaultdict` or check membership."},
            {"error": "IndexError", "cause": "Sequence index outside the length.", "fix": "Check `len`; iterate instead of indexing."},
            {"error": "AttributeError", "cause": "Object lacks the attribute, frequently because it is `None`.", "fix": "Test for `None`; use `hasattr` only when the API is genuinely dynamic."},
            {"error": "ModuleNotFoundError", "cause": "Package not installed in the active environment.", "fix": "Activate the venv; install with pip; check `sys.path`."},
            {"error": "RuntimeError: dictionary changed size during iteration", "cause": "Mutated a dict inside its own loop.", "fix": "Iterate `list(d)`, or build a new dict."},
            {"error": "UnicodeDecodeError", "cause": "Decoded bytes with the wrong encoding.", "fix": "Pass `encoding='utf-8'` or handle bytes explicitly."},
        ],
        "idioms": [
            {"task": "Enumerate with index", "code": "for index, item in enumerate(items, start=1):\n    print(index, item)", "note": "Avoids manual counters and off-by-one starts."},
            {"task": "Pair sequences", "code": "for name, score in zip(names, scores):", "note": "Stops at the shorter sequence; `strict=True` (3.10+) rejects length mismatch."},
            {"task": "Default a mapping", "code": "count = counts.get(word, 0) + 1", "note": "`Counter` or `defaultdict` when the pattern repeats."},
            {"task": "Swap and compare", "code": "a, b = b, a\nif 0 <= score <= 100:", "note": "Tuple assignment; chained comparisons evaluate the middle once."},
            {"task": "Fresh mutable default", "code": "def collect(item, bucket=None):\n    bucket = [] if bucket is None else bucket", "note": "Never use `[]` as a default argument."},
            {"task": "Join text", "code": "','.join(parts)", "note": "Linear; `+` in a loop is quadratic."},
        ],
        "versions": [
            {"release": "3.8", "change": "Walrus operator, positional-only parameters, `functools.cached_property`."},
            {"release": "3.10", "change": "Structural pattern matching, parenthesised context managers, union `X | Y` types."},
            {"release": "3.11", "change": "Exception groups and `except*`, `tomllib`, much faster interpreter."},
            {"release": "3.12", "change": "Type parameter syntax, per-interpreter GIL, f-string grammar improvements."},
            {"release": "3.13", "change": "Experimental free-threaded build and JIT; improved REPL and error messages."},
        ],
        "sources": [
            {"title": "Python documentation", "url": "https://docs.python.org/3/"},
            {"title": "The Python Tutorial", "url": "https://docs.python.org/3/tutorial/"},
            {"title": "Standard library index", "url": "https://docs.python.org/3/library/"},
            {"title": "Python Enhancement Proposals", "url": "https://peps.python.org/"},
            {"title": "Python Package Index", "url": "https://pypi.org/"},
        ],
    },
    "java": {
        "version": "21 LTS / 25 LTS",
        "tagline": "Statically typed on the JVM, with a mature library and a long compatibility promise.",
        "model": [
            "Java compiles to bytecode that the JVM verifies, loads and JIT-compiles. Objects live on a "
            "managed heap with a generational garbage collector; primitives hold values directly. Types are "
            "nominal and generics are erased, so runtime type information is limited compared with C#.",
            "Execution starts at a static `main` in a class. The JVM provides threads, class loading, "
            "reflection and a security model; virtual threads (21) make blocking-style concurrency scale "
            "to many tasks without a thread per request. Checked exceptions are part of a method's signature.",
        ],
        "facts": [
            {"label": "Execution", "value": "Bytecode on the JVM, JIT-compiled; AOT via GraalVM is optional."},
            {"label": "Typing", "value": "Static, nominal; generics are erased at runtime."},
            {"label": "Memory", "value": "Generational GC; no manual free; finalizers are unreliable."},
            {"label": "Concurrency", "value": "Platform threads, virtual threads, executors, `CompletableFuture`."},
            {"label": "Null", "value": "Any reference can be `null`; no language-level non-null type."},
            {"label": "Packaging", "value": "Maven or Gradle, JARs, JPMS modules; Maven Central."},
        ],
        "syntax": [
            {"feature": "Class and main", "code": "public class Main {\n    public static void main(String[] args) {\n        System.out.println(\"hello\");\n    }\n}", "note": "One public class per file; the file name matches the class."},
            {"feature": "Record", "code": "public record User(long id, String name) { }", "note": "Immutable data carrier with generated accessors, equality and `toString`."},
            {"feature": "Variable", "code": "var total = 0L;\nfinal String name = \"Asha\";", "note": "`var` is local inference, not dynamic typing; `final` prevents reassignment."},
            {"feature": "Switch expression", "code": "String label = switch (status) {\n    case ACTIVE -> \"live\";\n    case PAUSED -> \"paused\";\n    default -> \"closed\";\n};", "note": "Arrow form has no fall-through; the expression must be exhaustive."},
            {"feature": "Try-with-resources", "code": "try (var reader = Files.newBufferedReader(path)) {\n    return reader.readLine();\n}", "note": "Closes in reverse order; close failures become suppressed exceptions."},
            {"feature": "Stream pipeline", "code": "var names = users.stream()\n    .filter(u -> u.active())\n    .map(User::name)\n    .toList();", "note": "Lazy until a terminal operation; `toList()` is unmodifiable."},
            {"feature": "Optional", "code": "Optional<User> found = repo.find(id);\nreturn found.orElseThrow(() -> new NotFound(id));", "note": "A return type for absence, not a field type."},
            {"feature": "Sealed hierarchy", "code": "sealed interface Shape permits Circle, Square { }\nrecord Circle(double r) implements Shape { }", "note": "Exhaustive pattern matching without a default arm."},
        ],
        "types": [
            {"name": "byte / short / int / long", "detail": "Fixed widths 8/16/32/64; overflow wraps silently; use `Math.*Exact`."},
            {"name": "float / double", "detail": "IEEE-754; `0.1 + 0.2 != 0.3`; `BigDecimal` for money."},
            {"name": "boolean / char", "detail": "`char` is a UTF-16 code unit, not a code point; use `codePoints()`."},
            {"name": "String", "detail": "Immutable UTF-16; literals interned; compare with `equals`, not `==`."},
            {"name": "arrays", "detail": "Covariant, fixed length; `ArrayStoreException` on a wrong store."},
            {"name": "collections", "detail": "`List`, `Set`, `Map` interfaces; choose implementation by complexity."},
            {"name": "boxed types", "detail": "`Integer` etc. cache -128..127; `==` compares references."},
        ],
        "stdlib": [
            {"job": "Collections", "api": "`ArrayList`, `HashMap`, `ArrayDeque`, `TreeMap`, `PriorityQueue`", "note": "`ArrayDeque` for queues; `HashMap` keys need `equals`/`hashCode`."},
            {"job": "Streams", "api": "`java.util.stream`, `Collectors`", "note": "`groupingBy`, `toMap` with a merge function, `joining`."},
            {"job": "Dates and times", "api": "`java.time`", "note": "`Instant`, `Duration`, `ZonedDateTime`; formatters are thread-safe."},
            {"job": "Files", "api": "`java.nio.file.Files`, `Path`", "note": "`readString`, `walk`, try-with-resources, explicit UTF-8."},
            {"job": "HTTP", "api": "`java.net.http.HttpClient`", "note": "Set timeouts; check the status, 4xx does not throw."},
            {"job": "JSON", "api": "Jackson or Gson (not in the JDK)", "note": "Configure unknown properties and date handling."},
            {"job": "Databases", "api": "JDBC, `PreparedStatement`", "note": "Parameters prevent injection; close connections and statements."},
            {"job": "Numbers", "api": "`BigDecimal`, `BigInteger`, `Math.*Exact`", "note": "Set scale and `RoundingMode` for money."},
            {"job": "Concurrency", "api": "`ExecutorService`, `CompletableFuture`, `ConcurrentHashMap`", "note": "Virtual threads for blocking work."},
        ],
        "errors": [
            {"error": "NullPointerException", "cause": "A reference was null at the throw site.", "fix": "Read the helpful message (14+); validate at the boundary."},
            {"error": "ClassCastException", "cause": "Cast to a type the object is not.", "fix": "Use `instanceof` patterns instead of blind casts."},
            {"error": "IllegalArgumentException", "cause": "The caller passed an invalid parameter.", "fix": "Validate and name the parameter in the message."},
            {"error": "IllegalStateException", "cause": "The object is not in a state that allows the call.", "fix": "Check the lifecycle; do not reuse closed resources."},
            {"error": "UnsupportedOperationException", "cause": "Mutated an immutable collection such as `List.of`.", "fix": "Copy into `new ArrayList<>(...)`."},
            {"error": "ConcurrentModificationException", "cause": "A collection changed during iteration.", "fix": "`removeIf`, an iterator's `remove`, or a new collection."},
            {"error": "ArrayIndexOutOfBoundsException", "cause": "Index outside `0..length-1`.", "fix": "Check the bound; iterate with an enhanced for."},
            {"error": "NumberFormatException", "cause": "Text is not a number.", "fix": "Validate before parsing; report the field."},
            {"error": "OutOfMemoryError / StackOverflowError", "cause": "Retention or unbounded recursion.", "fix": "Heap dump / thread dump; fix the cause, do not catch `Error`."},
        ],
        "idioms": [
            {"task": "Resource cleanup", "code": "try (var stream = Files.newInputStream(path)) {\n    return stream.readAllBytes();\n}", "note": "Deterministic close even on exception."},
            {"task": "Map upsert", "code": "counts.merge(key, 1, Integer::sum);", "note": "Atomic on `ConcurrentHashMap`; no read-modify-write race."},
            {"task": "Group records", "code": "Map<String, List<Sale>> byRegion =\n    sales.stream().collect(Collectors.groupingBy(Sale::region));", "note": "Downstream collectors aggregate in one pass."},
            {"task": "Sort with tie-break", "code": "users.sort(Comparator.comparingInt(User::score)\n    .reversed().thenComparing(User::name));", "note": "Stable and explicit; avoid subtraction-based comparators."},
            {"task": "Build text", "code": "var text = new StringBuilder();\ntext.append(a).append(b);", "note": "Avoid `+=` in a loop."},
            {"task": "Optional value", "code": "return repo.find(id).map(User::name).orElse(\"unknown\");", "note": "`orElseGet` for expensive defaults."},
        ],
        "versions": [
            {"release": "8", "change": "Lambdas, streams, `Optional`, `java.time`, default methods."},
            {"release": "11", "change": "`var` in locals, `HttpClient`, `String.isBlank`, single-file source launch."},
            {"release": "17", "change": "Records, sealed classes, pattern matching for `instanceof`, text blocks."},
            {"release": "21", "change": "Virtual threads, pattern matching for `switch`, sequenced collections, record patterns."},
            {"release": "25", "change": "Further pattern matching, compact source files, ahead-of-time options; long-term support."},
        ],
        "sources": [
            {"title": "Java documentation", "url": "https://docs.oracle.com/en/java/"},
            {"title": "Java Language Specification", "url": "https://docs.oracle.com/javase/specs/"},
            {"title": "JVM specification", "url": "https://docs.oracle.com/javase/specs/jvms/se21/html/index.html"},
            {"title": "dev.java tutorials", "url": "https://dev.java/learn/"},
            {"title": "Maven Central", "url": "https://central.sonatype.com/"},
        ],
    },
    "javascript": {
        "version": "ECMAScript 2024 (ES15)",
        "tagline": "The language of the web and, through Node, of a large share of backend services.",
        "model": [
            "JavaScript is dynamically typed, garbage-collected and event-driven. Engines such as V8 compile "
            "source to bytecode and then to optimised machine code, deoptimising when assumptions change. "
            "Objects are property bags with a prototype link; functions are first-class objects.",
            "The event loop runs one JavaScript task at a time. Synchronous code runs to completion; promises "
            "and timers queue microtasks and macrotasks, so blocking work starves timers, rendering and "
            "requests. Modules are strict by default and have their own scope.",
        ],
        "facts": [
            {"label": "Execution", "value": "JIT-compiled by the engine; single-threaded execution per realm."},
            {"label": "Typing", "value": "Dynamic and weakly coerced; `===` avoids conversion."},
            {"label": "Memory", "value": "Tracing garbage collector; leaks are retained references."},
            {"label": "Concurrency", "value": "Event loop, promises, workers; no shared-memory threads by default."},
            {"label": "Null", "value": "Two empty values: `null` and `undefined`."},
            {"label": "Packaging", "value": "npm, ES modules, bundlers; lockfiles pin transitive versions."},
        ],
        "syntax": [
            {"feature": "Binding", "code": "const limit = 10;\nlet count = 0;", "note": "`const` prevents rebinding, not mutation; `let` is block-scoped."},
            {"feature": "Arrow function", "code": "const double = (n) => n * 2;", "note": "Inherits `this`; not usable as a constructor."},
            {"feature": "Destructuring", "code": "const { name, age = 18 } = user;\nconst [first, ...rest] = rows;", "note": "Defaults apply to `undefined`, not `null`."},
            {"feature": "Template literal", "code": "console.log(`${name}: ${score.toFixed(1)}`);", "note": "Interpolation and multi-line strings; no auto-escaping for HTML."},
            {"feature": "Optional chaining", "code": "const city = user?.address?.city ?? 'unknown';", "note": "`?.` short-circuits; `??` replaces only null/undefined."},
            {"feature": "Async function", "code": "async function load(url) {\n  const res = await fetch(url);\n  if (!res.ok) throw new Error(`HTTP ${res.status}`);\n  return res.json();\n}", "note": "Always returns a promise; `fetch` does not reject on 4xx/5xx."},
            {"feature": "Module", "code": "export function total(values) { return values.reduce((a, b) => a + b, 0); }\nimport { total } from './math.js';", "note": "ES modules are strict and statically analysable."},
            {"feature": "Class", "code": "class Counter {\n  #value = 0;\n  add() { this.#value += 1; }\n  get value() { return this.#value; }\n}", "note": "`#` fields are truly private, not convention."},
        ],
        "types": [
            {"name": "number", "detail": "IEEE-754 double; safe integers up to 2^53-1; `NaN !== NaN`."},
            {"name": "bigint", "detail": "Arbitrary precision integers; cannot mix with `number` implicitly."},
            {"name": "string", "detail": "Immutable UTF-16; `length` counts code units."},
            {"name": "boolean / null / undefined", "detail": "`undefined` means absent or unassigned; `null` is explicit absence."},
            {"name": "object / array", "detail": "References; spreading copies one level; arrays are objects with `length`."},
            {"name": "Map / Set", "detail": "Insertion-ordered collections with O(1) lookup by `SameValueZero`."},
            {"name": "function", "detail": "Callable object with a prototype; closures capture bindings."},
        ],
        "stdlib": [
            {"job": "Array transforms", "api": "`map`, `filter`, `reduce`, `flatMap`, `toSorted`", "note": "`sort` mutates and compares strings by default."},
            {"job": "Objects", "api": "`Object.keys/values/entries`, `hasOwn`, `assign`, `freeze`", "note": "`freeze` is shallow."},
            {"job": "Text and numbers", "api": "`Intl.NumberFormat`, `Intl.DateTimeFormat`, `Intl.Collator`", "note": "Locale-aware formatting instead of hand-built strings."},
            {"job": "JSON", "api": "`JSON.parse`, `JSON.stringify`", "note": "No validation; `BigInt` throws; `undefined` keys vanish."},
            {"job": "Dates", "api": "`Date`, `Intl.DateTimeFormat`", "note": "ISO strings at boundaries; `Temporal` is the successor."},
            {"job": "Regex", "api": "`RegExp`, `matchAll`, `replaceAll`", "note": "Named groups; avoid catastrophic backtracking."},
            {"job": "Async", "api": "`Promise.all/allSettled/race/any`, `AbortSignal`", "note": "`fetch` needs an explicit timeout and status check."},
            {"job": "Platform", "api": "`URL`, `URLSearchParams`, `TextEncoder`, `crypto`", "note": "Encode query strings; use `crypto.randomUUID()` for ids."},
            {"job": "Files and processes (Node)", "api": "`node:fs/promises`, `node:path`, `node:child_process`", "note": "Prefer `spawn` over `exec` for untrusted input."},
        ],
        "errors": [
            {"error": "TypeError: Cannot read properties of undefined", "cause": "A property was read from a missing value.", "fix": "Find where `undefined` entered; use `?.` only when absence is expected."},
            {"error": "ReferenceError: x is not defined", "cause": "The name does not exist or is in the temporal dead zone.", "fix": "Declare before use; check imports and spelling."},
            {"error": "SyntaxError: Unexpected token", "cause": "Invalid source, often malformed JSON.", "fix": "Validate the text; log the first bytes."},
            {"error": "TypeError: x is not a function", "cause": "Wrong import shape or lost `this`.", "fix": "Check the export and the call site."},
            {"error": "RangeError: Maximum call stack size exceeded", "cause": "Unbounded recursion or a cyclic structure.", "fix": "Add a base case or an explicit stack."},
            {"error": "Unhandled promise rejection", "cause": "A promise rejected with no handler or await.", "fix": "Await it, catch it, or attach a handler at the boundary."},
            {"error": "TypeError: Assignment to constant variable", "cause": "Rebound a `const`.", "fix": "Use `let`, or replace the value instead of mutating it."},
            {"error": "Illegal invocation", "cause": "A native method called with the wrong receiver.", "fix": "Bind or wrap the method; do not detach it."},
        ],
        "idioms": [
            {"task": "Default a value", "code": "const name = user.name ?? 'anonymous';", "note": "`??` keeps `0` and `''`; `||` does not."},
            {"task": "Clone data", "code": "const copy = structuredClone(state);", "note": "Deep for data; functions and prototypes are not preserved."},
            {"task": "Group records", "code": "const byTeam = new Map();\nfor (const row of rows) byTeam.set(row.team, [...(byTeam.get(row.team) ?? []), row]);", "note": "`Object.groupBy` is newer; `Map` allows any key."},
            {"task": "Run in parallel", "code": "const [user, orders] = await Promise.all([loadUser(id), loadOrders(id)]);", "note": "Rejects fast; use `allSettled` for every outcome."},
            {"task": "Cancel work", "code": "const signal = AbortSignal.timeout(2000);\nawait fetch(url, { signal });", "note": "Pass the signal through every layer."},
            {"task": "Deduplicate", "code": "const unique = [...new Set(values)];", "note": "Objects deduplicate by identity."},
        ],
        "versions": [
            {"release": "ES2015", "change": "`let`/`const`, classes, modules, promises, arrow functions, template literals."},
            {"release": "ES2020", "change": "Optional chaining, nullish coalescing, `BigInt`, `Promise.allSettled`, `globalThis`."},
            {"release": "ES2022", "change": "Top-level await, class fields, `Error.cause`, `.at()`, `Object.hasOwn`."},
            {"release": "ES2023", "change": "`toSorted`, `toReversed`, `with`, `findLast`, hashbang syntax."},
            {"release": "ES2024", "change": "`Promise.withResolvers`, `Object.groupBy`, `Map.groupBy`, regexp `v` flag."},
        ],
        "sources": [
            {"title": "MDN Web Docs", "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript"},
            {"title": "ECMAScript language specification", "url": "https://tc39.es/ecma262/"},
            {"title": "TC39 proposals", "url": "https://github.com/tc39/proposals"},
            {"title": "Node.js documentation", "url": "https://nodejs.org/docs/latest/api/"},
            {"title": "web.dev — platform guides", "url": "https://web.dev/"},
        ],
    },
    "typescript": {
        "version": "5.x",
        "tagline": "JavaScript with a structural type system that is checked and then erased.",
        "model": [
            "TypeScript is a superset of JavaScript: every valid JavaScript program is valid TypeScript. The "
            "compiler checks types, then emits JavaScript with all type syntax removed. Interfaces, type "
            "aliases, generics and casts do not exist at runtime, so they cannot validate data.",
            "Typing is structural: a value is assignable if its shape matches. Inference is local and "
            "flow-sensitive, and narrowing follows `typeof`, `instanceof`, `in` and literal comparisons. "
            "`strict` adds null checking, implicit-any errors and stricter function variance.",
        ],
        "facts": [
            {"label": "Execution", "value": "Compiled to JavaScript by `tsc`, a bundler, or a runtime stripper."},
            {"label": "Typing", "value": "Static, structural, erased; no runtime type information."},
            {"label": "Memory", "value": "Inherited from the JavaScript runtime."},
            {"label": "Concurrency", "value": "Inherited; promises and workers."},
            {"label": "Null", "value": "`strictNullChecks` makes `null`/`undefined` explicit."},
            {"label": "Packaging", "value": "npm, `tsconfig.json`, declaration files, project references."},
        ],
        "syntax": [
            {"feature": "Type alias", "code": "type User = { id: string; name: string; email?: string };", "note": "`?` means the property may be absent; under `exactOptionalPropertyTypes` it is not `undefined`."},
            {"feature": "Interface", "code": "interface Repo {\n  find(id: string): User | undefined;\n}", "note": "Open to declaration merging; usually interchangeable with a type alias."},
            {"feature": "Generic function", "code": "function first<T>(items: readonly T[]): T | undefined {\n  return items[0];\n}", "note": "Constraints (`T extends X`) restrict the operations allowed."},
            {"feature": "Discriminated union", "code": "type Result<T> =\n  | { ok: true; value: T }\n  | { ok: false; error: string };", "note": "Narrowing on `ok` gives exhaustive handling."},
            {"feature": "Type guard", "code": "function isUser(value: unknown): value is User {\n  return typeof value === 'object' && value !== null && 'id' in value;\n}", "note": "A predicate is only as correct as its body; test it with malformed input."},
            {"feature": "satisfies", "code": "const limits = { retries: 3, timeoutMs: 500 } satisfies Limits;", "note": "Checks the shape without widening the literal types."},
            {"feature": "Utility types", "code": "type Patch = Partial<Omit<User, 'id'>>;\ntype ById = Record<string, User>;", "note": "Built-ins save hand-written mapped types."},
            {"feature": "Enum alternative", "code": "const Status = { Active: 'active', Paused: 'paused' } as const;\ntype Status = typeof Status[keyof typeof Status];", "note": "Prefer union literals to `enum` for erasable output."},
        ],
        "types": [
            {"name": "any / unknown", "detail": "`any` disables checking; `unknown` must be narrowed before use."},
            {"name": "never", "detail": "The empty type; return type of a function that never returns; exhaustiveness checks."},
            {"name": "literal types", "detail": "`'on' | 'off'`, numeric and template literals; `as const` keeps them narrow."},
            {"name": "tuple", "detail": "Fixed length with per-position types; labels improve readability."},
            {"name": "interface / type", "detail": "Structural shapes; interfaces merge, types compose with unions and conditionals."},
            {"name": "generics", "detail": "Reusable relations between input and output; erased at runtime."},
            {"name": "utility types", "detail": "`Partial`, `Required`, `Readonly`, `Pick`, `Omit`, `Record`, `Exclude`, `Extract`."},
        ],
        "stdlib": [
            {"job": "Array and tuple types", "api": "`Array<T>`, `readonly T[]`, `[A, B]`", "note": "`noUncheckedIndexedAccess` makes `arr[i]` possibly undefined."},
            {"job": "Promises", "api": "`Promise<T>`, `Awaited<T>`, `Promise.all` tuples", "note": "`async` functions always return a promise."},
            {"job": "JSON boundary", "api": "`JSON.parse` + a validator", "note": "The parser returns `any`; validate into `unknown` and narrow."},
            {"job": "DOM types", "api": "`lib.dom.d.ts`", "note": "`querySelector` returns `Element | null`; check it."},
            {"job": "Node types", "api": "`@types/node`", "note": "`process.env` is `string | undefined`; validate at startup."},
            {"job": "Iteration", "api": "`Iterable<T>`, `Iterator<T>`, `Generator<T>`", "note": "`Map`/`Set` are iterable; objects are not."},
            {"job": "Formatting", "api": "`Intl` types", "note": "Typed options catch misspelled currency or date fields."},
            {"job": "Module types", "api": "`moduleResolution`, `.d.ts`, `@types/*`", "note": "Match the runtime's resolution or the build will lie."},
        ],
        "errors": [
            {"error": "TS2322: Type X is not assignable to type Y", "cause": "A value does not match the expected shape.", "fix": "Compare properties; narrow, convert or fix the type."},
            {"error": "TS2345: Argument of type X is not assignable", "cause": "The call site passes the wrong type.", "fix": "Check the parameter type, not the argument expression."},
            {"error": "TS2339: Property does not exist on type", "cause": "Typo, optional property or un-narrowed union.", "fix": "Narrow with a guard or add the property."},
            {"error": "TS2532: Object is possibly undefined", "cause": "`strictNullChecks` found a missing null check.", "fix": "Guard, default with `??`, or return early."},
            {"error": "TS7006: Parameter implicitly has an 'any' type", "cause": "Inference had no source for the callback parameter.", "fix": "Annotate it or type the array."},
            {"error": "TS2307: Cannot find module", "cause": "Wrong path, alias or module resolution.", "fix": "Fix `tsconfig` paths or install the package."},
            {"error": "TS2742: Inferred type cannot be named", "cause": "A public signature leaks a private type.", "fix": "Annotate the exported return type."},
        ],
        "idioms": [
            {"task": "Narrow unknown input", "code": "function parse(value: unknown): User {\n  if (!isUser(value)) throw new Error('invalid user');\n  return value;\n}", "note": "Validate once at the boundary; trust the type inside."},
            {"task": "Exhaustive switch", "code": "default:\n  return assertNever(value);", "note": "A `never` parameter fails to compile when a case is added."},
            {"task": "Read-only data", "code": "function total(items: readonly number[]): number { ... }", "note": "Prevents mutation through the reference."},
            {"task": "Type-only import", "code": "import type { User } from './types.js';", "note": "Erased at compile time; required by `verbatimModuleSyntax`."},
            {"task": "Literal config", "code": "const config = { mode: 'dark' } as const;", "note": "Preserves the literal for a union type."},
            {"task": "Result instead of throw", "code": "type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };", "note": "Forces callers to handle failure."},
        ],
        "versions": [
            {"release": "4.9", "change": "`satisfies` operator; performance improvements."},
            {"release": "5.0", "change": "Standard decorators, `const` type parameters, `--moduleResolution bundler`."},
            {"release": "5.2", "change": "`using` declarations for disposal, tuple named elements."},
            {"release": "5.4", "change": "Preserved narrowing in closures, `NoInfer`."},
            {"release": "5.6", "change": "Strict builtin iterator checks, region-prioritised diagnostics."},
        ],
        "sources": [
            {"title": "TypeScript Handbook", "url": "https://www.typescriptlang.org/docs/handbook/"},
            {"title": "tsconfig reference", "url": "https://www.typescriptlang.org/tsconfig/"},
            {"title": "TypeScript release notes", "url": "https://devblogs.microsoft.com/typescript/"},
            {"title": "DefinitelyTyped", "url": "https://github.com/DefinitelyTyped/DefinitelyTyped"},
            {"title": "TypeScript Playground", "url": "https://www.typescriptlang.org/play"},
        ],
    },
    "c": {
        "version": "C17 / C23",
        "tagline": "Portable systems C: close to the machine, with a small standard library and no safety net.",
        "model": [
            "C compiles each translation unit to an object file and links them into a program. Types are "
            "checked per translation unit, not across the program; the linker resolves names. There is no "
            "garbage collector and no runtime: automatic objects live on the stack and allocated objects "
            "live until `free`.",
            "The standard defines the language and part of the library, but behaviour outside the rules is "
            "undefined, and the optimiser may assume it never happens. Pointers, alignment, aliasing and "
            "integer conversions are therefore part of correctness, not micro-optimisation.",
        ],
        "facts": [
            {"label": "Execution", "value": "Compiled to native code; no runtime or GC."},
            {"label": "Typing", "value": "Static and nominally weak; implicit conversions are common."},
            {"label": "Memory", "value": "Manual: stack, static, heap; `malloc`/`free`."},
            {"label": "Concurrency", "value": "C11 threads/atomics (optional); POSIX threads in practice."},
            {"label": "Null", "value": "`NULL` pointer constant; dereferencing it is undefined."},
            {"label": "Packaging", "value": "Make, CMake, Meson; headers plus static/shared libraries."},
        ],
        "syntax": [
            {"feature": "Program entry", "code": "int main(void) {\n    printf(\"hello\\n\");\n    return 0;\n}", "note": "`main` returns `int`; `void` states that no arguments are read."},
            {"feature": "Struct", "code": "struct point { int x; int y; };", "note": "The tag is separate from the type name; `typedef` creates an alias."},
            {"feature": "Pointer", "code": "int value = 42;\nint *ptr = &value;\nprintf(\"%d\\n\", *ptr);", "note": "`&` takes an address, `*` dereferences; a pointer may be null."},
            {"feature": "Array and length", "code": "size_t n = sizeof values / sizeof values[0];", "note": "An array decays to a pointer in a call; pass the count explicitly."},
            {"feature": "Preprocessor", "code": "#define MAX(a, b) ((a) > (b) ? (a) : (b))\n#include <stdint.h>", "note": "Macros are textual; parenthesise arguments and prefer `static inline`."},
            {"feature": "Bounded format", "code": "char buf[16];\nsnprintf(buf, sizeof buf, \"%s\", text);", "note": "Check the return value for truncation."},
            {"feature": "Enum", "code": "enum color { RED, GREEN = 5, BLUE };", "note": "Values are `int`; later members continue from the last explicit value."},
            {"feature": "Function prototype", "code": "int parse_port(const char *text, unsigned short *out);", "note": "A prototype enables argument checking across translation units."},
        ],
        "types": [
            {"name": "char / signed char / unsigned char", "detail": "`char` signedness is implementation-defined; use `unsigned char` for bytes."},
            {"name": "short / int / long / long long", "detail": "Minimum widths only; `<stdint.h>` gives exact widths."},
            {"name": "float / double / long double", "detail": "Usually IEEE-754; compare with a tolerance, check `isnan`."},
            {"name": "arrays", "detail": "Contiguous, fixed length; decay to a pointer in expressions."},
            {"name": "pointers", "detail": "Address plus type; arithmetic valid only within an array (one past the end)."},
            {"name": "struct / union", "detail": "Aggregate with padding; union members share storage; layout is implementation-defined."},
            {"name": "size_t / ptrdiff_t", "detail": "Unsigned size and signed difference; use `%zu` and `%td`."},
        ],
        "stdlib": [
            {"job": "Formatted I/O", "api": "`printf`, `fprintf`, `snprintf`, `fgets`", "note": "Check return values; never use `gets`."},
            {"job": "Strings", "api": "`strlen`, `strcmp`, `strchr`, `strstr`, `memcpy`, `memmove`", "note": "`memmove` for overlap; bounded formatting instead of `strcpy`."},
            {"job": "Allocation", "api": "`malloc`, `calloc`, `realloc`, `free`", "note": "Check `NULL`; assign `realloc` to a temporary."},
            {"job": "Parsing", "api": "`strtol`, `strtod`, `strtoul`", "note": "Check `errno`, `endptr` and range."},
            {"job": "Sorting", "api": "`qsort`, `bsearch`", "note": "Comparator must be a strict total order."},
            {"job": "Characters", "api": "`<ctype.h>`", "note": "Cast to `unsigned char`; locale-sensitive."},
            {"job": "Math", "api": "`<math.h>`", "note": "Some errors via `errno`, some via `NaN`/infinity; link `-lm`."},
            {"job": "Time", "api": "`time`, `clock`, `strftime`", "note": "`localtime`/`gmtime` share static storage."},
            {"job": "Integers", "api": "`<stdint.h>`, `<inttypes.h>`", "note": "Use `PRIu64`-style macros for printing."},
        ],
        "errors": [
            {"error": "Segmentation fault", "cause": "Null, freed or out-of-bounds pointer access.", "fix": "ASan and a debugger; fix the lifetime or the bound."},
            {"error": "stack smashing detected", "cause": "A write past a stack buffer.", "fix": "Bound the copy (`snprintf`), audit sizes, enable ASan."},
            {"error": "free(): invalid pointer / double free", "cause": "Ownership violation.", "fix": "One owner, one free; set pointers to `NULL` after free."},
            {"error": "undefined reference to function", "cause": "Declaration without a definition or a missing library.", "fix": "Add the source/library; check link order."},
            {"error": "implicit declaration of function", "cause": "Missing prototype; pre-C99 assumptions.", "fix": "Include the header; compile with `-Werror=implicit-function-declaration`."},
            {"error": "format specifies type int but argument has type long", "cause": "Wrong `printf` specifier.", "fix": "Use the matching macro from `<inttypes.h>`."},
            {"error": "signed integer overflow", "cause": "Undefined behaviour at the limit.", "fix": "Use a wider type or a checked operation."},
            {"error": "use of uninitialised value", "cause": "Read before assignment.", "fix": "Initialise at declaration; run MemorySanitizer/valgrind."},
        ],
        "idioms": [
            {"task": "Single-exit cleanup", "code": "int rc = -1;\nchar *buf = malloc(n);\nif (!buf) goto done;\n/* ... */\nrc = 0;\ndone:\nfree(buf);\nreturn rc;", "note": "C has no destructors; `goto` cleanup keeps one exit path."},
            {"task": "Bounded copy", "code": "if (snprintf(dst, size, \"%s\", src) >= (int)size) return -1;", "note": "Detects truncation instead of ignoring it."},
            {"task": "Parse safely", "code": "errno = 0;\nlong n = strtol(text, &end, 10);\nif (errno || end == text || *end) return -1;", "note": "Rejects overflow, empty input and trailing text."},
            {"task": "Iterate a size", "code": "for (size_t i = values_len; i-- > 0; ) { /* ... */ }", "note": "Unsigned reverse loop that terminates correctly."},
            {"task": "Opaque type", "code": "struct handle;\nstruct handle *handle_open(const char *path);\nvoid handle_close(struct handle *h);", "note": "Hides layout from callers; ABI stability."},
            {"task": "Array length macro", "code": "#define LEN(a) (sizeof(a) / sizeof((a)[0]))", "note": "Only for real arrays, never for pointers."},
        ],
        "versions": [
            {"release": "C89/C90", "change": "The original standard: declarations at block start, no `//` comments."},
            {"release": "C99", "change": "`//` comments, `long long`, variable-length arrays, `<stdint.h>`, designated initialisers."},
            {"release": "C11", "change": "`_Generic`, `_Static_assert`, threads and atomics (optional), anonymous structs/unions."},
            {"release": "C17", "change": "Bug fixes and clarifications; no new language features."},
            {"release": "C23", "change": "`nullptr`, `constexpr`, `typeof`, bit-precise integers, attributes, `#embed`."},
        ],
        "sources": [
            {"title": "cppreference — C", "url": "https://en.cppreference.com/w/c"},
            {"title": "ISO C working group (WG14)", "url": "https://www.open-std.org/jtc1/sc22/wg14/"},
            {"title": "POSIX specification", "url": "https://pubs.opengroup.org/onlinepubs/9699919799/"},
            {"title": "GCC documentation", "url": "https://gcc.gnu.org/onlinedocs/"},
            {"title": "Clang documentation", "url": "https://clang.llvm.org/docs/"},
        ],
    },
}
