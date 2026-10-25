"""Depth wave 3, part one: the Python and Java semantics modules.

These are book-depth lessons, not A-O structured units. Each one covers the
material a reference site lists but does not explain: what the language's
execution model makes true, which failures follow from it, and the standard
library map that removes the need for a dependency. Every module ends in a
judged problem that already exists in the bank.
"""

BOOK_MODULES: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "python": [
        (
            "python-semantics-deep",
            "Names, objects and mutation: the Python execution model",
            "Binding versus copying, identity versus equality, argument passing, closure scope, "
            "and the numeric and string rules that explain the surprising results.",
            r"""**Why this matters.** Python looks simple because the syntax hides the object model. The
bugs that survive code review are almost always reference bugs: two names pointing at one list,
a default argument shared between calls, a closure that captured the variable rather than its
value. None of those are quirks. They are the direct consequences of three rules, and once you can
state the rules you can predict the behaviour instead of testing for it.

**A name is a binding, not a box.** `a = [1, 2]` creates a list object and binds the name `a` to
it. `b = a` binds a second name to the *same* object; it does not copy. `b.append(3)` is visible
through `a` because there was only ever one list. This is not "pass by reference" in the C++
sense - there are no references as values - it is assignment of a reference. The same rule explains
function calls: arguments are evaluated and the parameter names are bound to those objects. A
function that mutates a parameter mutates the caller's object; a function that rebinds the
parameter does not affect the caller.

```python
def add_item(items, value):
    items.append(value)      # mutates the caller's list

def reassign(items):
    items = [value]          # rebinds a local name only

data = []
add_item(data, 1)
reassign(data)
print(data)                  # [1]
```

**Default arguments are evaluated once.** The default expression is evaluated when the `def`
statement runs, not when the call happens, so a mutable default is one object shared by every
call that omits the argument.

```python
def collect(value, bucket=[]):   # one list for the lifetime of the function
    bucket.append(value)
    return bucket

print(collect(1))   # [1]
print(collect(2))   # [1, 2] - not [2]
```

Write `bucket=None` and create the list inside. The same trap appears in class bodies, decorators
and closures: anything that looks like a per-call default is actually per-definition.

**Identity and equality are different questions.** `==` asks whether two objects consider
themselves equal, which is `__eq__`. `is` asks whether they are the same object. Use `is` only for
singletons whose identity is part of the contract: `None`, `True`, `False`, and sentinels you
create yourself (`_MISSING = object()`). Small-integer caching and string interning are
implementation details; code that relies on `a is b` for two computed strings works on one
interpreter and fails on another. Note also that `float('nan') == float('nan')` is false while
`x is x` is true, and that `1 == 1.0 == True` is a chain that Python evaluates pairwise.

**Mutable and immutable is a property of the object, not the name.** `int`, `float`, `str`,
`bytes`, `tuple` and `frozenset` are immutable; `list`, `dict`, `set`, `bytearray` and most
user-defined instances are mutable. A tuple containing a list is still "immutable" in the only
sense that matters: you cannot replace its elements, but you can mutate the list inside it. That
distinction decides whether an object is safe to share between threads, whether it can be a
dictionary key, and whether a copy is needed at an interface boundary.

**Copying is shallow by default.** `list(seq)`, `seq[:]`, `dict.copy()` and `copy.copy()` create a
new outer container whose elements are the same objects. For nested data you need
`copy.deepcopy()`, which is slower and can fail on objects that do not support it. At API
boundaries the cheapest correct rule is: do not expose a mutable internal list; return a copy or a
tuple, and accept a copy on the way in.

**Scopes are lexical, and closures capture variables.** Python resolves a name using the local
scope, then enclosing function scopes, then the module globals, then builtins. A nested function
that reads `x` sees the `x` from the enclosing scope at call time, not at definition time. That is
why a loop of lambdas all print the final value; bind the loop variable with a default argument
(`lambda x=x: ...`) or a factory function. Assignment inside the inner function makes the name
local unless you declare `nonlocal` (or `global`). Comprehensions have their own scope in Python
3, so the loop variable does not leak into the enclosing function, which is one more reason a
comprehension is not just a shorter `for`.

**Evaluation order is left to right, and short-circuiting is part of the language.** Function
arguments are evaluated left to right before the call. `and`/`or` return an operand, not a
boolean, so `value or default` is not a safe test for "missing" when `0`, `""` or `[]` are valid
values. Chained comparisons (`a < b < c`) evaluate `b` once. Augmented assignment calls
`__iadd__` on mutable objects (in place) but rebinds on immutable ones - `x += [1]` mutates a
list, while `s += "a"` creates a new string each time, which is why building a large string with
`+=` in a loop is quadratic.

**Numbers.**
* `int` is arbitrary precision. It does not overflow; it grows, and a loop that would overflow a
  C `int` will simply get slower as the value gets larger.
* `float` is a 64-bit binary value. `0.1 + 0.2` is not `0.3` because none of the three is
  representable exactly. Compare with `math.isclose`, never with `==`, and use `decimal.Decimal`
  for money or any value whose decimal digits are part of the contract.
* `//` floors toward negative infinity (`-7 // 2 == -4`), and `%` takes the sign of the divisor
  (`-7 % 3 == 2`). Both differ from C. `divmod` returns the pair consistently.
* `round` uses banker's rounding: `round(2.5) == 2`, `round(3.5) == 4`. `Decimal` has explicit
  rounding modes.
* `bool` is a subclass of `int`, so `True + True == 2`; this is occasionally useful and usually a
  sign that two concepts were conflated.

**Strings are sequences of Unicode code points.** Indexing returns a one-character `str`, not a
byte, and `len` counts code points rather than user-perceived characters: an emoji with a
variation selector can be several code points, and a grapheme cluster can be several of those.
Encoding to UTF-8 changes the length. Slicing a `str` copies; `in` is a substring test. For byte
work, keep `bytes` and decode once at the boundary with an explicit encoding.

| Operation | What it does | Copy? |
| --- | --- | --- |
| `b = a` | Binds a second name to the same object | No |
| `b = a[:]` / `list(a)` | New outer container, same elements | Shallow |
| `copy.copy(a)` | Shallow copy of any object | Shallow |
| `copy.deepcopy(a)` | Recursively copies nested objects | Deep |
| `a is b` | Same object? | - |
| `a == b` | `__eq__` says equal? | - |

**The judgment call.** Reach for a copy when ownership crosses a boundary, a `None` default when
the value is created per call, and `Decimal` when the digits are money. Reach for `is` only for
singletons. Everything else in this lesson is a consequence of one sentence: assignment binds a
name to an object, and objects are either shared or copied explicitly.""",
            r"""def collect(value, bucket=[]):
    bucket.append(value)
    return bucket

print(collect(1))          # [1]
print(collect(2))          # [1, 2] - the default is shared

def collect_fixed(value, bucket=None):
    bucket = [] if bucket is None else bucket
    bucket.append(value)
    return bucket

print(collect_fixed(1))    # [1]
print(collect_fixed(2))    # [2]

a = [1, 2]
b = a
b.append(3)
print(a, a is b)           # [1, 2, 3] True

c = a[:]
c.append(4)
print(a, c)                # [1, 2, 3] [1, 2, 3, 4]

print(0.1 + 0.2)           # 0.30000000000000004
from decimal import Decimal
print(Decimal("0.1") + Decimal("0.2"))   # 0.3

fns = [lambda: i for i in range(3)]
print([fn() for fn in fns])              # [2, 2, 2]
fns = [lambda i=i: i for i in range(3)]
print([fn() for fn in fns])              # [0, 1, 2]

print(-7 // 2, -7 % 3)     # -4 2
print(round(2.5), round(3.5))            # 2 4
""",
            "Run the example and explain every line before reading the comments. Then write two functions: "
            "one that appends to a list passed by the caller, and one that returns a new list, and show the "
            "difference at the call site. Finally, fix the closure that captures a loop variable, and explain "
            "why the default-argument version works. Practise with /practice/problems/group-anagrams.",
        ),
        (
            "python-stdlib-deep",
            "The standard library map: the module to use instead of writing one",
            "Collections, itertools and functools, dataclasses and typing, pathlib and subprocess, datetime "
            "and zoneinfo, logging and argparse - with the costs and the traps.",
            r"""**Why this matters.** A Python installation ships with a large standard library, and most
projects add a dependency for something that is already there: a counter, a deep merge, a date
parser, a CSV reader, a CLI parser, a retry loop. Knowing the map makes programs smaller, removes
supply-chain risk, and often makes them faster, because the standard implementation is the one
other people have already debugged. This module is the map, organised by the job you are doing.

**Collections that match the shape of the data.**
| Job | Use | Why not the obvious alternative |
| --- | --- | --- |
| Count occurrences | `collections.Counter` | A dict plus `if key in d` is the same idea, written three times |
| Group rows by key | `collections.defaultdict(list)` | Plain `dict.setdefault` works but calls the factory every time |
| Queue or stack | `collections.deque` | `list.pop(0)` is O(n); deque is O(1) at both ends |
| Fixed record | `collections.namedtuple` or `dataclasses.dataclass` | Tuples by index are unreadable at the call site |
| Merge configuration layers | `collections.ChainMap` | Copying dictionaries loses the precedence rule |
| Most common k items | `Counter.most_common(k)` | `sorted(d.items(), key=...)` is a full sort |

`Counter` is a dict subclass, so missing keys return zero; `Counter("hello")` counts characters.
`defaultdict` inserts the default on read, which is convenient and also why a typo silently
creates a key. `deque(maxlen=n)` is a ring buffer, which is the correct sliding-window structure.

**Iteration tools.** `itertools` is where loops go to become expressions: `groupby` (requires
sorted input), `islice` (lazy slicing), `chain`/`chain.from_iterable`, `combinations`,
`permutations`, `product`, `cycle`, `repeat`, `pairwise` (3.10+), `batched` (3.12+). `functools`
holds the decorators worth knowing: `cache`/`lru_cache` (memoise; keys must be hashable; do not
cache functions with side effects or unbounded arguments), `partial`, `reduce` (prefer an explicit
loop when it reads better), `singledispatch` (type-directed dispatch without an if-chain), and
`wraps` (preserve the wrapped function's metadata).

**Data classes and types.** `@dataclass` generates `__init__`, `__repr__` and `__eq__` from the
annotations; `frozen=True` adds immutability and hashability; `slots=True` (3.10+) removes the
per-instance `__dict__`; `field(default_factory=list)` is the correct mutable default. `Enum` gives
a closed set of named values, and `StrEnum` (3.11+) lets the values compare as strings for JSON
and database boundaries. Type hints are not enforced at runtime; they are checked by `mypy` or
`pyright`, and `from __future__ import annotations` postpones evaluation so forward references
work without quotes.

**Files and paths.** `pathlib.Path` replaces most `os.path` string manipulation: `/` to join,
`.read_text(encoding="utf-8")`, `.write_text`, `.iterdir()`, `.glob("**/*.py")`, `.stem`,
`.suffix`, `.with_suffix`. Always pass an explicit encoding; the platform default differs between
Windows and Linux and is a classic "works on my machine" bug. Use `shutil` for tree copies and
`tempfile.TemporaryDirectory()` for scratch space; use `Path.resolve()` before comparing paths.

**Text formats.** `json` handles the common boundary: `json.dumps(obj, ensure_ascii=False,
indent=2)`, `json.loads`. It cannot serialise `datetime`, `Decimal`, `bytes` or sets without a
custom `default=` function, and it silently turns non-string dictionary keys into strings.
`csv.writer` needs `newline=""` when opening the file, otherwise Windows produces blank lines;
`csv.DictReader` is usually what you want. `tomllib` (3.11+) reads TOML but does not write it.
`configparser` is for INI files, not for JSON. For a local database, `sqlite3` is in the standard
library: always use `?` parameters, never string formatting; set `row_factory = sqlite3.Row` to
get mapping access.

**Time.** `datetime` has two kinds of value and they are not interchangeable: naive values have no
timezone, aware values carry a `tzinfo`. Store UTC, convert at the edge, and never subtract a
naive value from an aware one. `zoneinfo.ZoneInfo` (3.9+) gives real IANA zones including DST
transitions, which is why `pytz` is rarely needed now. `datetime.now(timezone.utc)` is aware;
`datetime.utcnow()` is naive and deprecated in 3.12. Use `time.perf_counter()` for durations and
`time.monotonic()` for timeouts; never use wall-clock time to measure an interval.

**Numbers, randomness, statistics.** `decimal.Decimal` for exact decimal arithmetic, `fractions`
for exact rationals, `statistics` for mean/median/stdev (watch the difference between
`pstdev` and `stdev`), and `random` for simulations. For anything security-sensitive use
`secrets`, not `random`: the latter is a deterministic PRNG seeded from the clock.

**Regular expressions.** `re` is powerful and easy to misuse. Compile a pattern once if it is used
in a loop, use raw strings (`r"\d+"`), prefer `fullmatch` when you mean the whole string, use
`finditer` rather than repeated `search`, and never parse HTML or JSON with a regex - use the
parsers. Catastrophic backtracking is real: nested quantifiers over long inputs can hang a
process. `re` is not a sandbox, and a user-supplied pattern is a denial-of-service risk.

**Processes, shells and exit codes.** `subprocess.run([...], check=True, capture_output=True,
text=True)` is the default shape. Never let the call run through a shell with a string built from
untrusted input; pass the program and its arguments as a list. `shlex.split` parses a command line the way a shell would. `sys.exit(1)` reports
failure; `atexit` runs cleanup; `signal` handles termination, but a `KeyboardInterrupt` should
usually propagate.

**Logging and command lines.** `logging` is the standard diagnostic channel: create a logger per
module (`logging.getLogger(__name__)`), configure handlers once in the entry point, and use
`logger.exception` inside an `except` block so the traceback is attached. `print` is for program
output, not diagnostics. `argparse` gives you `--help`, types, defaults and errors for free;
define subcommands with `add_subparsers`, and keep the parser construction in a function so tests
can call `parse_args([...])`.

**Concurrency in the standard library.** `concurrent.futures.ThreadPoolExecutor` for I/O-bound
work, `ProcessPoolExecutor` for CPU-bound work, `asyncio` for high-fan-out I/O, `threading` for
locks and events, `queue` for producer/consumer handoff. The choice is dictated by where the time
goes, not by which API is fashionable; a thread pool around CPU-bound Python does not run in
parallel because of the GIL, while a process pool pays serialisation costs for every result.

**The judgment call.** Before adding a package, check the standard library by job, not by module
name. Use `collections` for shape, `itertools` for laziness, `pathlib` for paths, `zoneinfo` for
zones, `logging` for diagnostics and `argparse` for interfaces. Add a dependency when it is
better maintained than the twenty lines you would write - not because you did not know the twenty
lines already exist.""",
            r"""import argparse
import logging
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

@dataclass(frozen=True)
class Reading:
    station: str
    celsius: float
    tags: tuple[str, ...] = field(default=())

def summarise(rows: list[Reading]) -> dict[str, float]:
    by_station: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_station[row.station].append(row.celsius)
    return {station: round(sum(values) / len(values), 1)
            for station, values in by_station.items()}

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarise station readings")
    parser.add_argument("path", type=Path, nargs="?", help="CSV file of station,celsius")
    parser.add_argument("--top", type=int, default=3)
    return parser.parse_args(argv)

SAMPLE = "station,celsius\nnorth,12.4\nsouth,19.2\nnorth,14.1\neast,9.8\n"

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    if args.path is None:
        sample = Path(tempfile.gettempdir()) / "station-readings.csv"
        sample.write_text(SAMPLE, encoding="utf-8")
        args.path = sample
    rows = []
    for line in args.path.read_text(encoding="utf-8").splitlines()[1:]:
        station, celsius = line.split(",")
        rows.append(Reading(station, float(celsius)))
    totals = summarise(rows)
    for station, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:args.top]:
        log.info("%s %.1f C", station, value)

if __name__ == "__main__":
    main()
""",
            "Rewrite a script you already have so it uses at least six standard-library modules from this "
            "lesson instead of hand-written code: `Path` for files, `Counter` or `defaultdict` for grouping, "
            "`argparse` for options, `logging` for output, `dataclass` for records and `zoneinfo` for any "
            "timestamps. Then list every third-party package you removed and what it was doing. Practise "
            "with /practice/problems/top-k-frequent.",
        ),
        (
            "python-diagnostics-deep",
            "Reading Python failures: tracebacks, logging and the debugger",
            "How to read a traceback, chain and catch exceptions correctly, when assert disappears, a "
            "catalogue of runtime errors, and the tools that find the cause instead of the symptom.",
            r"""**Why this matters.** A traceback is not an error message; it is a stack recording. Most
people read the last line, change it until the symptom disappears, and leave the cause in place.
This module teaches the opposite habit: read the structure, find the frame you own, and fix the
state that made the line fail.

**Anatomy of a traceback.** Python prints the oldest call first and the failing call last. Each
block names the file, the line and the source text. The final line is the exception type and
message. Two headers matter:
* `During handling of the above exception, another exception occurred` means a second exception was
  raised inside an `except` block; the first is context, not the cause.
* `The above exception was the direct cause` appears when code uses `raise new from old`; the
  original is the cause and the new one is the surface error. Use `from` when you translate a
  low-level failure into a domain error, so the traceback preserves both.

A bare `raise` inside `except` re-raises the same exception with its original traceback. `raise
RuntimeError(...) from exc` adds context; `raise RuntimeError(...) from None` suppresses the
context, which is only appropriate when the original is noise.

**Catch narrowly, and only what you can handle.** `except Exception` is a boundary tool: a worker
loop, a request handler, a CLI entry point. It is not a substitute for knowing which error you
expect. Never write `except:` - it catches `KeyboardInterrupt`, `SystemExit` and `GeneratorExit`,
which are control flow, not failures. Catch the specific classes, keep the handler short, and
re-raise anything you cannot fix. Do not silently `pass`: a swallowed exception is a bug that will
resurface later with less context.

**Exception groups.** Since 3.11, `ExceptionGroup` and `except*` let one failure carry several
independent errors, which is what concurrent work needs. A `TaskGroup` cancels its siblings when
one task fails and then reports the failures together. If you catch a group as a single exception,
you lose the per-task distinction.

**The runtime errors you will actually meet.**
| Error | Usual cause | What to check |
| --- | --- | --- |
| `NameError` | Misspelled or unimported name | The import and the spelling, not the line alone |
| `UnboundLocalError` | Assignment later in the function makes the name local | Add `nonlocal`/`global`, or rename the local |
| `AttributeError: 'NoneType'` | A function returned `None` on a path you assumed succeeded | The producer, not the consumer |
| `TypeError: 'NoneType' object is not callable` | A callback or optional dependency is `None` | The wiring and the default |
| `TypeError: 'NoneType' object is not subscriptable` | Parsing or lookup returned `None` | Add an explicit check and a domain error |
| `KeyError` | Missing dictionary key | `get` with a sentinel, or validate the input |
| `IndexError` | Off-by-one or empty sequence | The boundary and the empty case |
| `ValueError` | Right type, wrong content | Parse at the boundary and report the value |
| `ModuleNotFoundError` | Package not installed or wrong interpreter | `sys.executable`, `pip show`, virtualenv |
| `RecursionError` | Missing base case or genuinely deep recursion | Base case; convert to an explicit stack if deep |
| `PermissionError` / `FileNotFoundError` | Path and process identity | The absolute path and the user the process runs as |
| `RuntimeError: dictionary changed size during iteration` | Mutating a dict while iterating | Iterate over `list(d)` or build a new dict |

**`assert` is not validation.** Assertions are removed when Python runs with `-O` or
`PYTHONOPTIMIZE`, so an `assert` must never enforce an input contract or a security check. Use it
for internal invariants that should be impossible, and raise `ValueError`/`TypeError` for anything
that comes from outside the function.

**Warnings are a separate channel.** `DeprecationWarning` is hidden by default outside `__main__`,
which is why upgrades surprise people. Run the tests with `-W error::DeprecationWarning` to turn
them into failures. `warnings.warn(..., stacklevel=2)` points at the caller rather than the
library.

**Logging instead of print.** Create a module logger, configure the root once at the entry point,
and log the event plus the identifiers needed to find it again. `logger.exception("...")` inside an
`except` block attaches the traceback; `logger.error("...", exc_info=True)` does the same
explicitly. Log at the level that matches the decision: `DEBUG` for state you would only inspect
while diagnosing, `INFO` for lifecycle events, `WARNING` for something recovered from, `ERROR` for
a failed operation, `CRITICAL` for the process cannot continue. Never log passwords, tokens or
full request bodies; redact at the logging boundary, not at the call site.

**The debugger.** `breakpoint()` drops into `pdb` (or `pdb++` if installed). The commands worth
memorising: `n` next line, `s` step into, `c` continue, `r` return from the current function, `l`
list source, `p expr` print, `pp expr` pretty print, `w` where (the stack), `u`/`d` move up and
down the stack, `b file:line` set a breakpoint, `q` quit. `python -m pdb script.py` starts under
the debugger; `pdb.pm()` after an uncaught exception enters post-mortem mode. `breakpoint()` is
removed by `-O`, like `assert`.

**When the process dies or hangs.** `faulthandler.enable()` prints a Python stack on a fatal
signal; `PYTHONFAULTHANDLER=1` does the same without a code change. `faulthandler.dump_traceback_later(30, exit=True)` turns a hang into a diagnostic. For a segfault in a C extension,
faulthandler tells you which Python frame was running, which is usually enough to identify the
extension.

**Measure before changing.** `time.perf_counter()` for a coarse measurement, `timeit` for a
micro-benchmark, `cProfile -s cumtime` for a call profile, `tracemalloc` for allocations. The
common causes are boring and repeatable: a quadratic string or list operation, an `in` test
against a list inside a loop, an N+1 database query, blocking I/O inside an async function, and a
regular expression that backtracks catastrophically. Fix the algorithm before tuning the
interpreter.

**The judgment call.** Read the traceback from the bottom up and the frames from the top down.
Catch the narrowest type you can handle, chain the rest with `from`, and log once at the boundary.
Reach for `breakpoint()` when you need state, `cProfile` when you need cost, and `faulthandler`
when the process gives you nothing else.""",
            r"""import logging
import traceback

log = logging.getLogger("orders")

class OrderError(Exception):
    # A failure the caller can act on.
    pass

def price_of(order: dict) -> float:
    try:
        return float(order["total"])
    except KeyError as exc:
        raise OrderError(f"order {order.get('id')} has no total") from exc
    except (TypeError, ValueError) as exc:
        raise OrderError(f"order {order.get('id')} has an invalid total") from exc

def handle(order: dict) -> None:
    try:
        print(f"total: {price_of(order):.2f}")
    except OrderError:
        log.exception("could not price order %s", order.get("id"))
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for candidate in ({"id": 1, "total": "10.50"}, {"id": 2}, {"id": 3, "total": "ten"}):
        try:
            handle(candidate)
        except OrderError:
            print(f"order {candidate['id']} rejected")
""",
            "Run the example and read the full traceback for each rejected order. Then explain why the "
            "`KeyError` appears as the cause rather than the surface error, and why `log.exception` is "
            "inside the `except` block. Rewrite one function from your own code so it raises a domain "
            "error with `from`, and add a `faulthandler` timeout around a suspected hang. Practise with "
            "/practice/problems/course-schedule.",
        ),
    ],
    "java": [
        (
            "java-semantics-deep",
            "Primitives, references and the JVM's equality rules",
            "Boxing caches, string interning, floating-point money bugs, records, arrays and the "
            "pass-by-value rule that explains why a method cannot swap your variables.",
            r"""**Why this matters.** Java's type system is small enough to hold in your head and subtle
enough to produce bugs that pass review. `==` compares primitives by value and object references
by identity, boxing inserts a cache you did not ask for, and `BigDecimal` has a constructor that
produces a value nobody expects. Each of those is a rule, not a quirk; this module states the rules
and shows the failure each one prevents.

**Eight primitives, no objects.** `byte` (8-bit signed), `short` (16), `int` (32), `long` (64),
`float` (32-bit IEEE 754), `double` (64-bit IEEE 754), `char` (16-bit UTF-16 code unit), `boolean`.
They are values stored on the stack or inline in an object; they have no methods and no null.
Arithmetic on `byte` and `short` promotes to `int`, so `byte b = 100; b += 100;` compiles to a
narrowing assignment and wraps. Integer arithmetic wraps on overflow rather than throwing; use
`Math.addExact`, `multiplyExact` or `BigInteger` when overflow is a correctness concern. There is
no unsigned `int` in the language; `Integer.toUnsignedString`, `compareUnsigned` and
`Long.toUnsignedString` handle the boundary cases.

**`char` is a UTF-16 code unit, not a character.** Most text fits in one `char`, but anything
outside the Basic Multilingual Plane (many emoji, some CJK extensions) needs a surrogate pair and
therefore two `char` values. `String.length()` counts code units, and `codePointCount` counts code
points. Iterating a string with `for (char c : s.toCharArray())` splits surrogate pairs. Use
`codePoints()` when the distinction matters.

**Boxing and the cache.** Each primitive has a wrapper (`Integer`, `Long`, `Double`, ...). Autoboxing
converts automatically; `Integer.valueOf(100)` returns a cached instance for values in -128..127,
because the JLS requires that range to be cached. `Integer.valueOf(1000)` may return a new object
each time. Therefore `==` on two boxed values is an identity test that happens to work for small
numbers and fails for large ones. Always compare boxed values with `equals` or, better, unbox them
with `Objects.equals(a, b)` which handles null. A `null` wrapper unboxed into an `int` throws
`NullPointerException`, which is why a `Map<String, Integer>` get followed by `+ 1` fails on a
missing key.

**Floating point is binary.** `0.1 + 0.2 != 0.3`, and `double` cannot represent most decimal
fractions exactly. For money use `BigDecimal` with a scale and a rounding mode, and construct it
from a `String` or `BigDecimal.valueOf` - `new BigDecimal(0.1)` expands the binary value and gives
you `0.1000000000000000055511151231257827...`. `BigDecimal.equals` compares scale as well as value,
so `1.0` and `1.00` are not equal; `compareTo` compares value only. NaN is not equal to itself, and
`Double.compare` orders it above every number; `-0.0 == 0.0` is true but `Double.compare(-0.0, 0.0)`
is not zero.

**Strings are immutable and pooled.** A string literal is interned in the class file's constant
pool, so two identical literals are the same object. `new String("x")` is a different object with
the same content. `==` on strings is identity; `equals` is content. Concatenation in a loop creates
a new string each iteration (`StringBuilder` is the linear-time alternative; the compiler only
optimises a single expression). `String` methods that seem to mutate (`trim`, `replace`,
`toUpperCase`) return a new string. `switch` on strings compares by `equals`, but `case` labels
must be constants.

**The equals/hashCode contract.** `equals` must be reflexive, symmetric, transitive, consistent and
false for null. `hashCode` must be consistent with `equals`: equal objects must have equal hash
codes. Violate it and `HashMap`/`HashSet` silently lose entries. `record` generates both from the
components; a plain class needs both by hand or via `Objects.equals`/`Objects.hash`. Never use a
mutable field in `hashCode` and then mutate it while the object is a key.

**Java passes values.** Every argument is passed by value. For an object, the value is the
reference, so the method can mutate the object the caller points at, but it cannot rebind the
caller's variable. That is why a `swap(a, b)` method cannot work.

**Arrays are objects with covariance.** `String[]` is a subtype of `Object[]`, so assigning a
`String[]` to an `Object[]` variable compiles, and storing an `Integer` through that variable
throws `ArrayStoreException` at runtime. Arrays are fixed-length and zero-initialised. `clone()`
is shallow; `Arrays.copyOf` and `System.arraycopy` copy references, not the objects they point
at. Multidimensional arrays are arrays of arrays, with a separate length per row.

**`final`, `static` and compile-time constants.** `final` on a field means it cannot be reassigned;
for a reference, the object behind it can still mutate. `static final` with a compile-time constant
initialiser is inlined into every class that reads it, so changing the constant requires
recompiling the readers - a classic stale-build bug. `final` on a local variable captured by a
lambda (or effectively final) is required because the lambda captures the value.

**Varargs.** `f(String... args)` receives an array. Calling `f(null)` is ambiguous and can produce
a `NullPointerException` when the compiler treats the null as the array itself. `@SafeVarargs`
suppresses the generic-array warning on a `final`/`static` method and is only safe when the method
does not expose the array.

| Question | Correct operator | Falls into |
| --- | --- | --- |
| Same object? | `a == b` | Boxed numbers below 128, interned strings |
| Same value (objects)? | `a.equals(b)` | A class that did not override `equals` |
| Same value (null-safe)? | `Objects.equals(a, b)` | - |
| Same money amount? | `a.compareTo(b) == 0` | `equals` also compares `BigDecimal` scale |
| Exact binary value? | `Double.compare(a, b) == 0` | `==` is fine for primitives but not `NaN` |

**The judgment call.** Use primitives for local computation, `equals` for every object comparison,
`BigDecimal` for money, `record` when the value is defined by its components, and `StringBuilder`
when building text in a loop. When you see `==` on two object types, ask what identity would even
mean there - the answer is usually that the author meant `equals`.""",
            r"""import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class Equality {
    record Money(BigDecimal amount, String currency) {}

    public static void main(String[] args) {
        Integer a = 1000;
        Integer b = 1000;
        System.out.println(a == b);            // false - different objects
        System.out.println(a.equals(b));       // true
        System.out.println(Objects.equals(a, b));

        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println(smallA == smallB);   // true - cached

        String x = "java";
        String y = new String("java");
        System.out.println(x == y);            // false
        System.out.println(x.equals(y));       // true

        System.out.println(0.1 + 0.2);         // 0.30000000000000004
        BigDecimal tenth = new BigDecimal("0.1");
        BigDecimal fifth = new BigDecimal("0.2");
        System.out.println(tenth.add(fifth));  // 0.3
        System.out.println(new BigDecimal(0.1)); // 0.1000000000000000055511151231257827...

        Money price = new Money(new BigDecimal("19.99"), "EUR");
        Money same = new Money(new BigDecimal("19.99"), "EUR");
        System.out.println(price.equals(same)); // true - records compare components

        int[] numbers = {3, 1, 2};
        int[] copy = numbers.clone();
        copy[0] = 99;
        System.out.println(numbers[0]);        // 3 - shallow copy of values

        System.out.println(BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP));
    }
}
""",
            "Compile and run the example, then explain the two `==` results that differ only by magnitude. Add a "
            "`Map<Integer, String>` and show what happens when a lookup returns `null` and the result is "
            "auto-unboxed. Finally, replace a monetary `double` calculation in a small program with `BigDecimal` "
            "and state the scale and rounding mode you chose and why. Practise with "
            "/practice/problems/count-provinces.",
        ),
        (
            "java-stdlib-deep",
            "Collections, streams, time and IO: choosing the right JDK type",
            "Complexity and memory of the standard collections, the stream rules that bite, Optional as "
            "a return type, java.time without the timezone bugs, and NIO file handling.",
            r"""**Why this matters.** The JDK is a large library, and the difference between two choices is
often asymptotic rather than stylistic. `ArrayList` and `LinkedList` are both `List`, but one has
O(1) indexed access and the other does not; `HashMap` and `TreeMap` are both `Map`, but only one
keeps order and only one has O(log n) lookups. This module is the decision table, plus the
standard-library material that replaces a utility dependency.

**Collections by cost.**
| Type | Access | Insert/remove | Order | Use when |
| --- | --- | --- | --- | --- |
| `ArrayList` | O(1) index | O(n) in the middle, amortised O(1) at the end | insertion order | The default list |
| `LinkedList` | O(n) | O(1) at the ends with a reference | insertion order | Almost never; `ArrayDeque` is faster |
| `ArrayDeque` | O(1) ends | O(1) ends | FIFO/LIFO | Queues and stacks |
| `HashMap` | O(1) average | O(1) average | none | Keyed lookup, unordered |
| `LinkedHashMap` | O(1) average | O(1) average | insertion or access order | Predictable iteration, LRU |
| `TreeMap` | O(log n) | O(log n) | sorted by key | Range queries, ordering |
| `HashSet` / `TreeSet` | O(1) / O(log n) | same | none / sorted | Membership, deduplication |
| `PriorityQueue` | O(1) peek | O(log n) | heap order | Scheduling, top-k |
| `EnumMap` / `EnumSet` | array / bitset | very fast | enum order | A key or member is an enum |

`HashMap` starts with a table of 16, grows at a load factor of 0.75, and turns a bucket into a
red-black tree once it holds eight entries and the table is large enough. That is why a bad
`hashCode` degrades lookups to O(log n) rather than O(n) on modern JDKs - and why a *mutable* key
still loses entries entirely. `ConcurrentHashMap` is the concurrent map; it does not permit null
keys or values. `CopyOnWriteArrayList` is for read-mostly listener lists.

**Iteration and modification.** An iterator is fail-fast: modifying the collection structurally
while iterating throws `ConcurrentModificationException`. Use `iterator.remove()`, `removeIf`, or
build a new collection. The fail-fast check is best-effort, not a concurrency guarantee; two
threads can still corrupt a plain collection. Use the concurrent collections for sharing.

**Streams are lazy, single-use pipelines.** A stream is created from a source, transformed by
intermediate operations (`map`, `filter`, `sorted`, `distinct`, `limit`) and consumed by one
terminal operation (`collect`, `forEach`, `reduce`, `count`, `anyMatch`). Nothing runs until the
terminal operation. A stream cannot be reused. `Collectors.toMap` throws on a duplicate key unless
you pass a merge function; `Collectors.groupingBy` returns a `Map<K, List<V>>` by default and needs
a downstream collector for counts. Parallel streams only help when the work is CPU-bound, the
source splits cheaply (arrays, ranges) and the operation has no shared mutable state; otherwise
they add overhead and can reorder side effects. Measure before adding `.parallel()`.

**Optional is a return type.** It means "may be absent" and forces the caller to decide. Do not use
it for fields (use null or a default), parameters (overload instead), or collections (return an
empty collection). `orElse` evaluates its argument eagerly; `orElseGet` takes a supplier and only
runs when empty; `orElseThrow` is the explicit failure. `Optional.ofNullable(x).map(...).orElse(...)`
is the idiomatic chain.

**Text.** `String.format` is convenient and slow in a hot loop; `StringBuilder` is the loop
primitive. `strip` understands Unicode whitespace while `trim` only trims characters <= U+0020.
`isBlank`, `lines`, `repeat`, `chars`, `indent` and `transform` cover most of what used to be a
utility library. `String.join(",", list)` and `Collectors.joining` avoid the trailing-comma bug.
Always specify a charset when converting bytes: `getBytes(StandardCharsets.UTF_8)`, and the same on
the reading side.

**Time.** `java.time` has four types and they answer different questions:
* `Instant` - a point on the timeline, always UTC.
* `LocalDate` / `LocalTime` / `LocalDateTime` - a calendar value with no zone. It is not a moment.
* `OffsetDateTime` - a local value plus a fixed offset.
* `ZonedDateTime` - a local value plus a region, so it knows about DST.

Store `Instant` (or an ISO-8601 string in UTC), convert with `ZoneId` for display, and never use
`LocalDateTime` for an instant such as "when the order was placed". `Duration` measures elapsed
time, `Period` measures calendar time; `ChronoUnit` converts. `DateTimeFormatter` is immutable and
thread-safe; `SimpleDateFormat` is not. DST gaps and overlaps are real: a local time can be
missing or repeated, and `ZonedDateTime` resolves that with rules you should test.

**IO and NIO.** Use `java.nio.file.Path` and `Files` rather than `File`: `Files.readString(path,
UTF_8)`, `Files.writeString`, `Files.walk`, `Files.createDirectories`, `Files.move` with
`StandardCopyOption.ATOMIC_MOVE`. Close resources with try-with-resources, because the compiler
generates the `finally` that suppresses the secondary exception. Buffer streams for many small
reads and writes; an unbuffered `FileInputStream` reading one byte at a time is a syscall per byte.
`Files.lines` is lazy and must be closed.

**Concurrency utilities.** `ExecutorService` owns threads; `submit` returns a `Future`, `invokeAll`
runs a batch. `CompletableFuture` composes asynchronous work: `thenApply` maps, `thenCompose`
flat-maps, `exceptionally`/`handle` recover. Always pass a timeout to `future.get`. Java 21's
virtual threads make blocking code scale in thread count, but a `synchronized` block or a native
call can pin the carrier thread, and `ThreadLocal` becomes expensive per task. Measure; do not
assume.

**JSON and networking.** The JDK has no JSON parser in the standard library; Jackson or Gson is the
normal choice, with records as the data shape. `java.net.http.HttpClient` is built in: set
`connectTimeout`, pass a `HttpRequest.BodyPublishers` and read `HttpResponse.BodyHandlers.ofString`.
HTTP status codes are not exceptions; check them.

**The judgment call.** Start with `ArrayList` and `HashMap`, move to `ArrayDeque` for queues,
`LinkedHashMap` for predictable order, `TreeMap` for ranges, `EnumMap` for enum keys. Use streams
when they make the transformation clearer, not to avoid a loop with a mutable accumulator. Store
instants, not local dates. Buffer IO and specify charsets.""",
            r"""import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class Catalogue {
    record Item(String sku, String category, BigDecimal price, Instant added) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
            new Item("A-1", "books", new BigDecimal("12.50"), Instant.parse("2026-01-02T09:00:00Z")),
            new Item("B-2", "books", new BigDecimal("30.00"), Instant.parse("2026-02-03T10:00:00Z")),
            new Item("C-3", "tools", new BigDecimal("8.75"), Instant.parse("2026-02-04T11:00:00Z"))
        );

        Map<String, List<String>> byCategory = items.stream()
            .collect(Collectors.groupingBy(Item::category,
                Collectors.mapping(Item::sku, Collectors.toList())));
        System.out.println(byCategory);

        Optional<Item> cheapest = items.stream().min(Comparator.comparing(Item::price));
        System.out.println(cheapest.map(Item::sku).orElse("none"));

        ArrayDeque<String> queue = new ArrayDeque<>(List.of("first", "second"));
        queue.addLast("third");
        while (!queue.isEmpty()) {
            System.out.println(queue.removeFirst());
        }

        Instant now = Instant.now();
        Duration age = Duration.between(items.get(0).added(), now);
        System.out.println(age.toDays() + " days");
        String shown = DateTimeFormatter.ISO_LOCAL_DATE
            .withZone(ZoneId.of("Asia/Kolkata"))
            .format(items.get(0).added());
        System.out.println(shown);

        List<String> skus = new ArrayList<>();
        for (Item item : items) {
            skus.add(item.sku());
        }
        System.out.println(String.join(", ", skus));
    }
}
""",
            "Fix the example: replace one `BigDecimal` built from a `double` with the `String` constructor, which is "
            "the bug the module describes. Then add a `LinkedHashMap` that keeps insertion order, a "
            "`TreeMap` that returns a range of keys, and a method that returns `Optional<Item>` for a lookup that "
            "may miss. Measure `ArrayList` against `ArrayDeque` for ten million queue operations. Practise with "
            "/practice/problems/moving-average.",
        ),
        (
            "java-diagnostics-deep",
            "Stack traces, the JVM and failures you can actually fix",
            "Reading cause chains and suppressed exceptions, the common runtime errors, dependency conflicts, "
            "logging that survives production, and the JVM tools that explain memory and threads.",
            r"""**Why this matters.** A Java stack trace is one of the most information-dense error reports in
mainstream languages, and most of it is ignored. The JVM also fails in ways that look mysterious
until you know which resource ran out: heap, metaspace, direct memory, native threads or file
descriptors. This module teaches the reading, the catalogue and the tools.

**The shape of a stack trace.** Read the top line for the type and message, then the frames for the
first line that belongs to your code, then the cause chain. `Caused by:` blocks are the real
failures in order from outermost to innermost. `Suppressed:` blocks come from try-with-resources
when the close also failed; the primary failure is the one that matters, and the suppressed one is
usually the reason cleanup failed. `... 23 more` means the frames are identical to the enclosing
trace and were elided. Lambda frames (`lambda$method$0`) tell you which lambda, not which line in
the source.

**Errors, causes and fixes.**
| Failure | Cause | Fix |
| --- | --- | --- |
| `NullPointerException` | Dereferencing null; helpful messages (JEP 358) name the expression | Fix the producer, not the dereference |
| `ClassNotFoundException` | A class named at runtime is absent from the classpath | Fix the dependency or the launch script |
| `NoClassDefFoundError` | The class existed at compile time but failed to initialise or is absent | Read the cause; check versions |
| `NoSuchMethodError` | Two versions of a library at runtime | `mvn dependency:tree` / `gradle dependencies` |
| `StackOverflowError` | Unbounded recursion | Base case, or an explicit stack |
| `OutOfMemoryError: Java heap space` | Live set exceeds `-Xmx` | Find the retention with a heap dump |
| `OutOfMemoryError: Metaspace` | Too many generated classes | Check class loading, frameworks, dynamic proxies |
| `OutOfMemoryError: unable to create native thread` | Thread limit or memory | Bound thread creation; use a pool |
| `ConcurrentModificationException` | Structurally modified during iteration | `removeIf`, iterator, or a concurrent collection |
| `DateTimeParseException` | Wrong pattern, locale or offset | Use ISO formats and explicit `DateTimeFormatter` |
| `NumberFormatException` | Text is not a number | Validate at the boundary and report the input |
| `InterruptedException` | The thread was cancelled during a blocking call | Restore the flag and stop cleanly |

**Checked versus unchecked is a design decision.** Checked exceptions are for conditions the caller
can reasonably recover from; unchecked ones are programming errors or unrecoverable conditions.
Wrapping a checked exception in `RuntimeException` to avoid `throws` is not a fix - it hides the
contract. When you translate, keep the cause: `throw new OrderException("...", exc)`.

**Build failures.** `cannot find symbol` is a missing import, a typo, or a dependency that is on
the test classpath only. `incompatible types` usually means a generic invariant (`List<Dog>` is not
a `List<Animal>`). `method does not override` means the signature drifted. `class file has wrong
version 61.0, should be 55.0` means the library was compiled for a newer JDK than the compiler
target. `UnsupportedClassVersionError` at runtime is the same mismatch on the run JDK.

**Logging.** Use SLF4J with a backend (Logback or Log4j2), never `System.out`, and log a
parameterised message: `log.info("order {} failed for {}", id, user)` avoids building strings when
the level is disabled. Pass the exception as the last argument with no `{}` placeholder; otherwise
you log its `toString` and lose the trace. Log each failure once, at the boundary that can act on
it. MDC carries a request id across threads, but remember a thread pool reuses threads - clear it.
Never log secrets or full payment data.

**JVM diagnostics.** `jps` lists JVMs. `jstack <pid>` dumps threads and reports deadlocks directly.
`jcmd <pid> Thread.print` does the same, and `jcmd <pid> GC.heap_info`, `VM.flags`,
`VM.system_properties` expose runtime state. `jmap -histo:live <pid>` shows class
histograms; a heap dump plus Eclipse MAT's dominator tree finds what is retaining memory.
`-Xlog:gc*` (JDK 9+) prints GC events; a full GC every few seconds is a capacity problem, not a
tuning problem. Java Flight Recorder (`-XX:StartFlightRecording`) records allocation, locks and
latency with low overhead, and JFR is the first tool to reach for when the question is "where did
the time go".

**Thread pool and latency failures.** A pool with a bounded queue and a caller-runs rejection
policy degrades instead of collapsing; an unbounded queue hides overload until memory runs out.
Blocking a request thread on a downstream call consumes a thread per wait - that is exactly what
virtual threads change, provided no `synchronized` block pins the carrier. Connection pools have
their own limit; a request that waits for a database connection while holding a thread is a
capacity bug, not a timeout bug.

**Assertions and invariants.** `assert` is disabled unless `-ea` is passed, so it is a development
tool, not validation. Use it for internal invariants and explicit checks for input.

**The judgment call.** Start from the innermost cause, find your frame, and fix the state that
made the line possible. When the JVM dies without a useful trace, take a heap dump or a thread
dump and read it before restarting. Log once, with the identifiers, at the layer that decides.""",
            r"""import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

public class Retry {
    private static final Logger log = Logger.getLogger(Retry.class.getName());

    static final class TransientFailure extends Exception {
        TransientFailure(String message, Throwable cause) { super(message, cause); }
    }

    static String fetch(int attempt) throws TransientFailure {
        try {
            if (attempt < 3) {
                throw new IllegalStateException("upstream unavailable");
            }
            return "payload";
        } catch (IllegalStateException exc) {
            throw new TransientFailure("attempt " + attempt + " failed", exc);
        }
    }

    public static void main(String[] args) {
        List<Throwable> failures = new ArrayList<>();
        for (int attempt = 1; attempt <= 4; attempt++) {
            try {
                System.out.println(fetch(attempt));
                break;
            } catch (TransientFailure exc) {
                failures.add(exc);
                log.log(Level.WARNING, "retrying after " + exc.getMessage(), exc);
            }
        }
        System.out.println("attempts recorded: " + failures.size());
        for (Throwable failure : failures) {
            System.out.println(failure.getCause().getMessage());
        }
    }
}
""",
            "Run the example under `-ea` and without it, and explain why the assertion policy is part of the run "
            "configuration. Then reproduce a `ConcurrentModificationException` and fix it three ways: iterator "
            "removal, `removeIf`, and a concurrent collection. Finally, start a small program with "
            "`-Xmx64m`, fill a list until it fails, and identify which `OutOfMemoryError` variant you got. "
            "Practise with /practice/problems/validate-ipv4.",
        ),
    ],
}

MODULE_PRACTICE: dict[str, str] = {
    "python-semantics-deep": "group-anagrams",
    "python-stdlib-deep": "top-k-frequent",
    "python-diagnostics-deep": "course-schedule",
    "java-semantics-deep": "count-provinces",
    "java-stdlib-deep": "moving-average",
    "java-diagnostics-deep": "validate-ipv4",
}
