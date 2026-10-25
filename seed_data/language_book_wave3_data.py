"""Depth wave 3, part 5: Rust and SQL semantics, libraries and diagnostics.

Rust turns ownership into a compile-time proof; SQL turns queries into a
planner's decision. Both reward knowing the model before writing the code. The
Rust modules cover ownership, the library and compiler errors; the SQL modules
cover relational semantics, the function catalogue and plan reading.
"""

from __future__ import annotations

BOOK_MODULES: dict[str, list[tuple]] = {
    "rust": [
        (
            "rust-semantics-deep",
            "Ownership as semantics: moves, borrows and lifetimes",
            "What the compiler proves, how values move, and where interior mutability fits.",
            r"""**Why this matters.** Rust's borrow checker is usually presented as a
gatekeeper. It is better understood as a proof obligation: every reference has
a lifetime derived from the value it points at, and the compiler rejects the
program when the proof cannot be constructed. Learning the rules turns errors
from arbitrary rejections into statements about ownership that you can fix by
changing the design - not by adding `clone()` until it compiles.

**Every value has one owner.** Binding a value to a name makes that name the
owner. Assigning to another name moves ownership; the original binding becomes
invalid and cannot be used. Passing by value moves. Returning by value moves
out. When the owner goes out of scope, `Drop::drop` runs and the value is
freed deterministically - no collector, no finalizer, no pause. Types that are
cheap to copy implement `Copy` (integers, floats, `bool`, `char`, references,
tuples of `Copy` types), and assignment copies them instead of moving. `Clone`
is an explicit deep copy; `clone()` in a hot loop is a design signal.

**Borrows are temporary permissions.** `&T` is a shared borrow; `&mut T` is an
exclusive borrow. At any moment you may have any number of `&T` or exactly one
`&mut T`, never both. A borrow ends at its last use (non-lexical lifetimes), so
a `&mut` can be taken after the last read of a `&`. A reference cannot outlive
the value it points to; the compiler infers a lifetime for every reference and
checks that it is used only while the referent is alive.

**Lifetimes are constraints, not durations you specify.** `fn first<'a>(items:
&'a [String]) -> &'a str` says the returned reference is valid for as long as
the input borrow. Elision rules cover the common cases; you annotate only when
the compiler cannot infer which input a return borrow comes from. A `'static`
bound means the reference lives for the whole program - string literals are
`&'static str`, and a leaked allocation can be too. Lifetimes do not change
runtime behaviour; they describe it.

**Structs own their fields by default.** `struct User { name: String }` owns
the string. If the struct borrows, it needs a lifetime parameter and cannot
outlive the borrowed data. `&str` fields are fine for a short-lived view,
`String` fields for an owning domain object. Returning a reference to a local
is impossible - return the owned value instead.

**Interior mutability is the escape hatch for shared mutation.** `Cell<T>` and
`RefCell<T>` move the borrow check to runtime: `RefCell` panics if two mutable
borrows overlap. `Rc<T>` is shared ownership for a single thread; `Arc<T>` is
atomic and `Send`/`Sync`; `Rc<RefCell<T>>` is the classic shared mutable graph
and the classic way to create a reference cycle (`Weak<T>` breaks it).
`Mutex<T>` and `RwLock<T>` provide shared mutation across threads with
blocking. `OnceLock`/`LazyLock` initialise globals safely.

**Deref coercion is convenience, not inheritance.** `&String` coerces to
`&str`, `&Vec<T>` to `&[T]`, `Box<T>` to `&T` through `Deref`. Write functions
against the borrowed form (`&str`, `&[T]`, `impl AsRef<Path>`) so callers do not
have to allocate. Do not implement `Deref` to fake inheritance; it confuses
method resolution.

**Enums and patterns make illegal states unrepresentable.** `Option<T>`
replaces null; `Result<T, E>` replaces exceptions for expected failures;
`match` must be exhaustive. Patterns destructure structs, enums, tuples,
references and slices; `_` discards, `..` ignores the rest, guards (`if`)
add conditions. `if let` and `while let` are single-arm matches. `let else`
(1.65+) makes the failure path explicit and early.

**`?` propagates with conversion.** In a function returning `Result<T, E>`,
`expr?` returns `Err(From::from(err))` on failure. `From` conversions let a
function return one error type while calling functions that return others -
this is the basis of `thiserror` and `anyhow`. `?` also works on `Option` in a
function returning `Option`.

**Panics are bugs, not control flow.** `panic!` unwinds (or aborts with
`panic = "abort"`), runs destructors and poisons mutexes held across the panic.
`unwrap`/`expect` are appropriate for invariants and tests, not for user input.
`catch_unwind` does not make panics safe to recover from; it exists for FFI
and test harnesses. A panic in one thread does not kill others.

**Numeric and textual details.** Integer overflow panics in debug builds and
wraps in release unless `overflow-checks` is enabled; use
`checked_add`/`wrapping_add`/`saturating_add` when the behaviour matters.
`usize` is pointer-sized; `as` casting truncates silently. `str` is UTF-8 and
cannot be indexed by byte; iterate `chars()`, `bytes()` or `char_indices()`.
`String` owns, `&str` borrows, `OsString`/`Path` handle platform encodings.

**Closures capture by reference, mutable reference or value.** `move` forces
ownership into the closure, which is required for `'static` threads. `Fn`
borrows immutably, `FnMut` mutably, `FnOnce` consumes. A closure that returns a
reference to a captured local cannot compile - the closure does not own the
local.

**`Send` and `Sync` are auto traits.** A type is `Send` if it can move to
another thread; `Sync` if it can be referenced from several threads.
`Rc<T>`/`RefCell<T>` are neither; `Arc<T>`/`Mutex<T>` are `Send` when their
contents are. The compiler checks these at the boundary, which is why a
threaded program that compiles in Rust usually has its shared state designed
correctly.

| Symptom | Real rule | Fix |
|---|---|---|
| use of moved value | Assignment moves | Borrow, clone or restructure |
| cannot borrow as mutable | A shared borrow is alive | End the borrow earlier |
| two mutable borrows | Exclusive borrow overlap | Split the struct or index once |
| does not live long enough | Reference outlives owner | Own the value or extend scope |
| missing lifetime specifier | Return borrow ambiguous | Annotate or return owned data |
| RefCell already borrowed | Runtime borrow overlap | Shorten the borrow |
| cannot be sent between threads | `Rc`/`RefCell` is not `Send` | Use `Arc`/`Mutex` |

**The judgment call.** Design ownership first: who owns the data, who borrows
it, and how long the borrow lasts. Most borrow-checker fights are a data-model
problem, and the fix - an owned value, an index instead of a reference, or a
smaller scope - usually makes the program clearer as well.""",
            r"""use std::cell::RefCell;
use std::rc::Rc;

#[derive(Debug)]
struct Node {
    name: String,
    children: Vec<Rc<RefCell<Node>>>,
}

fn main() {
    let parent = Rc::new(RefCell::new(Node {
        name: "root".into(),
        children: vec![],
    }));
    let child = Rc::new(RefCell::new(Node {
        name: "leaf".into(),
        children: vec![],
    }));
    parent.borrow_mut().children.push(Rc::clone(&child));
    println!("{}", parent.borrow().children[0].borrow().name);

    let name = String::from("engine");
    let shout = move || name.to_uppercase();   // owns name
    println!("{}", shout());
    // println!("{}", name);                   // would not compile: moved

    let mut values = vec![1, 2, 3];
    let first = &values[0];
    println!("{first}");
    values.push(4);                            // first is no longer used
    println!("{values:?}");

    let maybe: Option<i32> = Some(5);
    match maybe {
        Some(n) if n > 3 => println!("big {n}"),
        Some(n) => println!("small {n}"),
        None => println!("missing"),
    }

    let mut data = RefCell::new(vec![1]);
    let a = data.borrow();
    println!("{:?}", a);
    drop(a);
    data.borrow_mut().push(2);
    println!("{:?}", data.borrow());
}""",
            """Explain why the closure in the example must be `move` and what would happen if
`name` were borrowed instead. Write a function `longest` that returns a `&str` from two
inputs, then explain the explicit lifetime it needs. Build a shared tree with
`Rc<RefCell<Node>>`, introduce a cycle, and show that it leaks; break it with `Weak`.
Finally solve `reverse-linked-list` with `Option<Box<ListNode>>`, taking ownership of
the head and explaining every move.
Practice: /practice/problems/reverse-linked-list""",
        ),
        (
            "rust-stdlib-deep",
            "The Rust standard library and the crates that matter",
            "Collections, iterators, errors, I/O, threads and the ecosystem boundary.",
            r"""**Why this matters.** Rust's standard library is deliberately small:
it owns the core abstractions (collections, iterators, I/O traits, threads,
sync) and leaves async runtimes, serialisation and CLI parsing to crates. A
Rust engineer therefore needs two maps: what `std` provides, and which crate
owns the rest. This module is both, with the costs and the conventions.

**Collections.** `Vec<T>` is a contiguous growable array: O(1) indexing,
amortised O(1) push, O(n) middle insert; `reserve` avoids reallocation.
`VecDeque<T>` is O(1) at both ends and is the queue/deque. `HashMap<K, V>` is
O(1) average with SipHash by default (choose `FxHashMap`/`ahash` for hot
non-adversarial paths); `BTreeMap`/`BTreeSet` are sorted O(log n) and support
range queries. `BinaryHeap<T>` is a max-heap; wrap a value in `Reverse` for a
min-heap. `String` is a UTF-8 growable buffer; `&str` is a borrowed view.

**Iterators are lazy and zero-cost.** `iter()` borrows, `iter_mut()` borrows
mutably, `into_iter()` consumes. Adapters (`map`, `filter`, `flat_map`, `zip`,
`chain`, `take`, `skip`, `take_while`, `scan`, `enumerate`, `peekable`) return
new iterators; consumers (`collect`, `sum`, `fold`, `count`, `any`, `all`,
`find`, `position`, `max_by_key`) drive them. A `for` loop over an iterator is
the same machine code as the chain in most cases. `collect()` into a `Vec`
allocates; `collect::<Result<Vec<_>, _>>()` stops at the first error;
`collect::<String>()` is a common fast path. `Iterator::size_hint` matters for
allocation, and `Vec::with_capacity` is the explicit version.

**Errors have two layers.** Libraries define precise error enums with
`thiserror` (derive `Error`, `Display`, `From`); applications use `anyhow::Result`
for context and backtraces. `Box<dyn Error>` is fine for a small tool.
`Error::source()` preserves the chain; `context()` from `anyhow` adds a
message without losing the cause. Do not stringify errors at the boundary;
map them to a stable API error type there.

**Option and Result combinators replace branching.** `map`, `and_then`,
`ok_or`, `unwrap_or`, `unwrap_or_else`, `filter`, `or_else`, `transpose`
(`Option<Result<T, E>>`), `?` on both. `Option::take` moves out of `&mut
Option<T>`; `Result::unwrap_or_default` is often the right default. `expect`
messages should state the invariant, not "failed".

**Strings, OS strings and paths.** `String` is UTF-8 and owns; `&str` is a
slice of UTF-8; `OsString`/`&OsStr` preserve platform encoding; `Path`/`PathBuf`
handle separators and conversions (`Path::new`, `join`, `with_extension`,
`file_name`, `parent`, `components`). `format!`, `format_args!` and
`std::fmt` avoid allocation when the result is written directly. `to_string`
and `String::from` allocate; `Cow<str>` avoids it when the input is usually
borrowed.

**I/O is traits.** `Read`, `Write`, `BufRead`, `Seek`; `File`, `Stdin`,
`Stdout`, `Cursor`, `BufReader`, `BufWriter`. `read_to_string` for text,
`read_to_end` for bytes, `lines()` for a buffered line iterator. `BufWriter`
must be flushed explicitly or dropped (and dropping ignores errors). `?`
converts `io::Error` into a crate error through `From`.

**Time.** `Instant::now()` is monotonic and the right choice for elapsed time;
`Duration` is the difference. `SystemTime` is wall-clock and can move
backwards; `UNIX_EPOCH` arithmetic is the portable conversion. There is no
calendar or time-zone type in `std` - use `chrono` or `time` and be explicit
about UTC versus local.

**Threads and sync.** `thread::spawn` requires `'static + Send`; `thread::scope`
(1.63+) allows borrowing stack data. `mpsc::channel` is multi-producer,
single-consumer; `crossbeam`/`flume` extend it. `Mutex<T>` owns the data it
protects, so the lock cannot be forgotten; `RwLock` for read-mostly;
`OnceLock`/`LazyLock` for globals; `AtomicUsize` and friends for counters and
flags. Beware lock-order inversions; the deadlock still exists, only the data
race is gone.

**The ecosystem boundaries.** `serde` + `serde_json` for serialisation (derive
`Serialize`/`Deserialize`; `#[serde(rename_all = "camelCase")]`);
`rand` for randomness (`thread_rng` for simulations, `OsRng` for seeds);
`regex` for regular expressions (linear-time, no backreferences); `clap` for
CLI; `tokio`/`async-std` for async; `reqwest` for HTTP; `tracing` for
structured logs; `proptest` for property tests; `criterion` for benchmarks.
Every dependency is a supply-chain decision: check maintenance, features and
the tree.

**Cargo is part of the library.** `Cargo.toml` declares dependencies and
features; `Cargo.lock` pins versions for binaries and applications.
`cargo build --release`, `cargo test`, `cargo clippy -- -D warnings`,
`cargo fmt --check`, `cargo doc --open`, `cargo tree`, `cargo audit` and
`cargo deny` are the standard checks. Feature flags should be additive and
documented; `default-features = false` is how you keep a dependency small.

| Job | Tool | Caveat |
|---|---|---|
| Growable list | `Vec<T>` | Reserve when known |
| FIFO | `VecDeque<T>` | Not index-heavy |
| Key lookup | `HashMap` | SipHash; choose hasher for hot paths |
| Sorted keys | `BTreeMap` | O(log n) |
| Priority | `BinaryHeap` | Max-heap; `Reverse` for min |
| Transform a sequence | iterator chain | Lazy until consumed |
| Fallible parsing | `Result` + `?` | `From` conversions |
| Shared ownership | `Arc<T>` | Atomic cost |
| Shared mutation | `Mutex<T>` | Lock poisoning |
| JSON | `serde_json` | Validate after parse |
| Random secret | `OsRng` | Never `thread_rng` |
| Regex | `regex` | No backtracking |

**The judgment call.** Use borrowed types in signatures (`&str`, `&[T]`,
`impl AsRef<Path>`), own at boundaries, return `Result` rather than panicking,
and treat each dependency as code you now maintain.""",
            r"""use std::collections::{BinaryHeap, HashMap};
use std::cmp::Reverse;

fn counts(words: &[&str]) -> HashMap<&str, usize> {
    let mut map = HashMap::new();
    for word in words {
        *map.entry(*word).or_insert(0) += 1;
    }
    map
}

fn top_words(words: &[&str], k: usize) -> Vec<(&str, usize)> {
    let map = counts(words);
    let mut heap: BinaryHeap<Reverse<(&str, usize)>> = BinaryHeap::new();
    for (word, count) in map {
        heap.push(Reverse((word, count)));
        if heap.len() > k {
            heap.pop();
        }
    }
    heap.into_iter().map(|Reverse(item)| item).collect()
}

fn main() {
    let words = ["a", "b", "a", "c", "a", "b"];
    println!("{:?}", counts(&words));
    println!("{:?}", top_words(&words, 2));

    let total: usize = words.iter().filter(|w| **w != "c").count();
    println!("{total}");

    let parsed: Result<Vec<i32>, _> = ["1", "2", "x"]
        .iter()
        .map(|s| s.parse::<i32>())
        .collect();
    println!("{parsed:?}");                    // Err(ParseIntError { .. })

    let name = "engineverse";
    let upper = name.to_uppercase();
    let borrowed = name.strip_prefix("engine").unwrap_or(name);
    println!("{upper} {borrowed}");

    let mut values = vec![3, 1, 2];
    values.sort_unstable();
    println!("{values:?}");
}""",
            """Rewrite a `Vec` loop as an iterator chain and confirm with `cargo bench` or a
simple timing loop that it is not slower. Build a frequency map with `entry`, then take
the top k with `BinaryHeap<Reverse<_>>` and explain the time complexity. Create a custom
error enum with `thiserror`, propagate it with `?`, and add context at the boundary. Use
`serde_json` to parse an untrusted payload into a struct and reject missing fields.
Finally solve `top-k-frequent` and compare the heap approach with sorting the counts.
Practice: /practice/problems/top-k-frequent""",
        ),
        (
            "rust-diagnostics-deep",
            "Reading rustc and clippy: borrows, bounds and backtraces",
            "Turn compiler errors into design fixes, and runtime panics into reproductions.",
            r"""**Why this matters.** Rust's compiler is unusually good at explaining what
it rejected, but the explanation is written in terms of a proof you did not
know you were making. Once you can read the error code, the "cannot borrow"
family and the trait-bound family, the compiler becomes a design reviewer
rather than an obstacle. The runtime tools - backtraces, Miri, sanitizers,
fuzzers - cover the smaller class of bugs the type system cannot see.

**Read the diagnostic in three parts.** The primary span is where the error is
reported; the notes and "help" lines name the rule; the secondary spans show
the conflicting borrow or the expected type. `rustc --explain E0382` prints the
full explanation for an error code. `cargo clippy` gives a second opinion with
lints grouped by category; `clippy -- -D warnings` in CI keeps the codebase
from drifting.

**The borrow-checker family.** E0382 "use of moved value": the value was moved
and the old binding is dead - borrow, clone deliberately, or restructure.
E0502 "cannot borrow as mutable because it is also borrowed as immutable":
shorten the shared borrow, split the struct into fields, or use
`split_at_mut`. E0499 "two mutable borrows": same fix. E0597 "borrowed value
does not live long enough": the reference outlives its owner - own the value or
extend the owner's scope. E0515 "returning reference to temporary": return an
owned value. E0106 "missing lifetime specifier": annotate which input the
output borrows from.

**Lifetime errors are usually ownership errors.** If a function returns a
reference derived from a local, no annotation can fix it. If a struct borrows
from two inputs, the annotation states which one it is tied to. If a closure
captures a reference and is stored beyond the call, use `move`. `'static` is
not a magic fix: it means the value lives forever, which usually means leaking
or owning.

**Trait-bound errors name the missing capability.** E0277 "trait bound not
satisfied": the type does not implement something the generic requires -
`Debug`, `Display`, `Clone`, `Send`, `Sync`, `From`. Read the "required by"
chain to find which call imposed the bound. E0308 "mismatched types": compare
the expected and found types; integer width and reference level are the usual
differences - convert with `as`, `try_into` or `&`/`*`. E0433 "failed to
resolve": a missing `use` or a feature flag, not a logic bug.

**Cargo and feature failures.** `error: could not compile ... (features ...)`
is a feature unification problem; `cargo tree -e features -i crate` shows who
enabled what. A dependency compiled for a different target or with a different
Rust edition shows up as a type mismatch between two versions of the same
crate; `cargo tree -d` finds duplicates. `cargo update -p crate --precise
x.y.z` pins a transitive version while the root cause is fixed.

**Panics: read the message and the backtrace.** `RUST_BACKTRACE=1` (or `full`
for inlined frames) prints the stack. A panic message should state the
invariant (`expect("config must define PORT")`), not "unreachable". Panics in
tests report the exact assertion; `#[should_panic(expected = "...")]` checks
the message. A panic in a thread does not stop the process, so a server can
lose a worker silently - log it at the join point.

**Unsafe code needs proof, not optimism.** `unsafe` permits dereferencing raw
pointers, calling unsafe functions, accessing mutable statics, implementing
unsafe traits and reading unions. Each block needs a safety comment explaining
the invariant. Miri (`cargo +nightly miri test`) detects undefined behaviour
in unsafe code - out-of-bounds, use-after-free, invalid aliasing, uninitialised
reads. AddressSanitizer via `-Z sanitizer=address` covers FFI and C
dependencies. A safe API that can be misused is not yet finished.

**Concurrency failures.** A data race cannot occur in safe Rust, but a
deadlock, a livelock, a poisoned mutex, or a `Send` violation through `unsafe`
can. `loom` explores concurrent interleavings for lock-free structures;
`cargo test -- --test-threads=1` distinguishes order dependence from a race.
`Mutex` poisoning happens when a panic occurs while the lock is held - decide
whether to recover (`into_inner`) or fail.

**Performance and codegen.** `cargo build --release` uses optimisation;
`opt-level`, LTO and `codegen-units` are tunables. `cargo bench` with
`criterion` reports distributions, not one number. `perf` and `cargo flamegraph`
show hotspots. Bounds checks are usually cheap; `get_unchecked` is not a
default optimisation. `#[inline]` is a hint, and `Box<dyn Trait>` versus
generics is a dispatch decision, not a style one.

**Supply chain and correctness checks.** `cargo audit` reports advisories,
`cargo deny` enforces licences and bans, `cargo tree` shows the dependency
graph, `cargo outdated` shows drift. `cargo test` runs unit, integration and
doc tests; doc tests compile the examples in your documentation, which keeps
them honest. `cargo doc` with `#![deny(missing_docs)]` is a quality gate for
libraries.

| Error | Meaning | First fix |
|---|---|---|
| E0382 | Use after move | Borrow or clone deliberately |
| E0502 | Shared + mutable borrow | Shorten one borrow |
| E0499 | Two mutable borrows | Split fields or scopes |
| E0597 | Reference outlives owner | Own the data |
| E0515 | Return reference to local | Return owned value |
| E0106 | Ambiguous lifetime | Annotate inputs |
| E0277 | Trait not implemented | Implement or add bound |
| E0308 | Type mismatch | Check width and references |
| E0433 | Path not found | Add `use` or feature |
| Panic + backtrace | Runtime invariant | Reproduce, then fix the cause |

**The judgment call.** Treat a borrow error as a question about ownership, a
bound error as a question about capability, and a panic as a missing
validation. Reach for `clone` only when duplication is what you mean, and for
`unsafe` only with a written proof and Miri in CI.""",
            r"""#[derive(Debug, Clone)]
struct Item {
    name: String,
    qty: u32,
}

fn total(items: &[Item]) -> u32 {
    items.iter().map(|item| item.qty).sum()
}

fn main() {
    let mut items = vec![
        Item { name: "pen".into(), qty: 2 },
        Item { name: "book".into(), qty: 1 },
    ];

    let first = items.first().expect("at least one item");
    println!("{}", first.name);
    items.push(Item { name: "bag".into(), qty: 1 });   // borrow ended
    println!("{}", total(&items));

    let text = "42";
    let value: i32 = text.parse().expect("numeric input");
    println!("{value}");

    let names: Vec<&str> = items.iter().map(|item| item.name.as_str()).collect();
    println!("{names:?}");

    let result: Result<u32, String> = items
        .iter()
        .map(|item| {
            if item.qty == 0 {
                Err(format!("{} has no quantity", item.name))
            } else {
                Ok(item.qty)
            }
        })
        .sum::<Result<u32, String>>();
    println!("{result:?}");
}""",
            """Take the three most common rustc errors from a real project - a move, a lifetime
and a trait bound - and write the design fix before touching the code. Deliberately
create a `RefCell` double borrow, read the panic, and fix it. Run `cargo clippy -- -D
warnings` and justify or fix every lint. Add Miri to a test containing one small `unsafe`
block and explain what it checks. Finally solve `validate-ipv4`, returning a typed error
for each malformed octet and adding `#[should_panic]` tests only for true invariants.
Practice: /practice/problems/validate-ipv4""",
        ),
    ],
    "sql": [
        (
            "sql-semantics-deep",
            "Relational semantics: sets, NULL and evaluation order",
            "Why a query returns the rows it does - three-valued logic, joins and grouping.",
            r"""**Why this matters.** SQL is declarative, but it is not vague. A query
describes a result set under a precise semantics: tables are bags of rows,
`NULL` means unknown, joins multiply by matches, and clauses run in a fixed
order. Most "SQL is weird" moments are one of those four facts. Learn them and
the language becomes predictable; skip them and every query is a guess checked
against one dataset.

**Tables are bags, not sets.** A table can contain duplicate rows; `DISTINCT`
removes them. A `SELECT` without `ORDER BY` has no guaranteed order, even if
one run returns rows in insertion order. `LIMIT` without a unique tie-break is
non-deterministic. A primary key makes rows distinguishable, but the query
result is still a bag until you deduplicate or order it.

**`NULL` is unknown, not empty and not zero.** `NULL = NULL` is `NULL`, not
`true`; only `IS NULL` and `IS DISTINCT FROM` test it safely. `WHERE` keeps a
row only when the predicate is `true`; a `NULL` result is treated as false.
`NOT (NULL)` is still `NULL`. This is three-valued logic: true, false and
unknown, with `AND`/`OR` tables that propagate unknown. Aggregates ignore
`NULL` except `COUNT(*)`, which counts rows. `SUM` over no rows is `NULL`, not
`0`; `COALESCE(SUM(x), 0)` is the fix when a total is required.

**`NULL` also affects uniqueness and joins.** A `UNIQUE` constraint permits
multiple `NULL`s in most engines because two unknowns are not equal. A join
predicate `a.id = b.id` never matches a `NULL` on either side; use `IS NOT
DISTINCT FROM` (PostgreSQL) or `(a.id = b.id OR (a.id IS NULL AND b.id IS
NULL))` for null-safe matching. `NOT IN (subquery)` returns no rows if the
subquery produces a `NULL`, which is why `NOT EXISTS` is the safer anti-join.

**Clause evaluation order is logical, not textual.** `FROM` and `JOIN` build
the working set, `WHERE` filters rows, `GROUP BY` collapses them, `HAVING`
filters groups, window functions compute over the remaining rows, `SELECT`
projects and aliases, `DISTINCT` deduplicates, `ORDER BY` sorts and `LIMIT`
cuts. That order explains why an alias defined in `SELECT` is usable in
`ORDER BY` but not in `WHERE` (in standard SQL), why `HAVING` can use
aggregates and `WHERE` cannot, and why a window function cannot be filtered in
`WHERE` without a subquery or CTE.

**Joins multiply.** An inner join returns one row per matching pair; a left
join preserves every left row and fills the right side with `NULL` when there
is no match. A right-side predicate in `WHERE` (`WHERE b.status = 'paid'`)
removes the unmatched rows and silently turns the outer join into an inner
join - move the predicate into the `ON` clause to preserve it. A join on a
non-unique key can multiply rows and inflate every aggregate; check the
cardinality before summing.

**`GROUP BY` collapses to one row per key.** Every selected column must be
grouped or aggregated. `HAVING` filters after aggregation. `COUNT(*)` counts
rows, `COUNT(column)` counts non-null values, `COUNT(DISTINCT column)` counts
distinct non-null values. `GROUPING SETS`, `ROLLUP` and `CUBE` produce several
grouping levels in one pass; `GROUPING()` distinguishes a real `NULL` from a
subtotal `NULL`.

**Window functions compute without collapsing rows.** `ROW_NUMBER`, `RANK`,
`DENSE_RANK`, `NTILE`, `LAG`, `LEAD`, `FIRST_VALUE`, `SUM() OVER` and
`AVG() OVER` add a value per row. `PARTITION BY` restarts the window;
`ORDER BY` inside the window defines the sequence; the frame (`ROWS BETWEEN
UNBOUNDED PRECEDING AND CURRENT ROW`) defines which rows are included. The
default frame is `RANGE UNBOUNDED PRECEDING` which includes peers with equal
ordering values - a subtle difference from `ROWS`.

**Set operations.** `UNION` deduplicates and sorts; `UNION ALL` concatenates
and is cheaper. `INTERSECT` and `EXCEPT` operate on sets and treat `NULL`s as
equal for the purpose of duplicate elimination. Column counts and compatible
types are required; names come from the first query.

**Types, collation and coercion.** Comparing strings with different collations
can error or ignore an index. Comparing a number to a string may cast
implicitly or refuse; PostgreSQL is strict, MySQL is permissive, SQLite is
dynamic. `::`/`CAST` makes the intent explicit. Floating point equality is
unreliable; use exact `numeric` or a tolerance. Date arithmetic differs by
engine; a date literal without a time zone means midnight in the session zone.

**Constraints are the specification.** `NOT NULL`, `CHECK`, `UNIQUE`,
`PRIMARY KEY` and `FOREIGN KEY` are enforced by the database, not by
application code that races. A `CHECK` that allows `NULL` passes when the
expression is unknown. A deferred foreign key checks at commit; an immediate
one checks per statement. Migrations that add a `NOT NULL` column to a large
table need a default or a backfill plan.

| Query shape | Rows returned | Common mistake |
|---|---|---|
| `WHERE x = NULL` | None | Use `IS NULL` |
| `NOT IN (subquery with NULL)` | None | Use `NOT EXISTS` |
| Left join + right predicate in `WHERE` | Only matches | Move predicate to `ON` |
| Join on non-unique key | Multiplied | Check cardinality |
| `COUNT(column)` | Non-null count | `COUNT(*)` counts rows |
| `ORDER BY` + `LIMIT` without tie-break | Arbitrary page | Add a unique key |
| `HAVING` without `GROUP BY` | One group | Filter in `WHERE` |

**The judgment call.** Write the query in clause order, reason about
cardinality at every join, and treat `NULL` as a value that requires an
explicit decision. A query that is correct on one dataset is not yet correct;
it is untested against the semantics.""",
            r"""-- Three-valued logic: every expression below is NULL (unknown), not true.
SELECT NULL = NULL, NULL <> NULL, NULL AND TRUE, NULL OR FALSE;

-- Uniqueness permits several NULLs (PostgreSQL, MySQL, SQLite).
CREATE TABLE contacts (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE,
  team TEXT
);
INSERT INTO contacts (email, team) VALUES (NULL, 'core'), (NULL, 'web');

-- Counts: COUNT(*) counts rows, COUNT(col) skips NULL.
SELECT COUNT(*) AS rows, COUNT(email) AS emails FROM contacts;

-- A left join whose filter is in WHERE loses the unmatched row.
CREATE TABLE teams (name TEXT PRIMARY KEY);
INSERT INTO teams VALUES ('core'), ('web'), ('ops');

SELECT t.name, c.email
FROM teams t
LEFT JOIN contacts c ON c.team = t.name AND c.email IS NOT NULL
ORDER BY t.name;

-- Window function: one row per team, ranked by email presence.
SELECT team, email,
       row_number() OVER (PARTITION BY team ORDER BY email NULLS LAST) AS rn
FROM contacts;""",
            """Run each query above and explain the difference between the left join with the
predicate in `ON` and the same query with it in `WHERE`. Write an anti-join that finds
teams with no contact, using `NOT EXISTS`, then show why `NOT IN` fails when the
subquery can return `NULL`. Build a running total with a window function and an explicit
`ROWS` frame. Finally solve `count-provinces` with a transitive-closure query and
explain the cardinality at each step.
Practice: /practice/problems/count-provinces""",
        ),
        (
            "sql-stdlib-deep",
            "The SQL function catalogue that replaces application code",
            "Strings, dates, aggregates, windows and JSON - with dialect differences named.",
            r"""**Why this matters.** A lot of application code exists to reshape data that
the database could have returned correctly in the first place. The functions are
standardised in SQL:2016/2023, but implementations differ enough that a
copy-pasted expression often works on one engine and not another. This module
covers the catalogue by job and names the differences that bite.

**Conditionals.** `CASE WHEN ... THEN ... ELSE ... END` is standard and
portable; it works as an expression anywhere, including inside `ORDER BY` and
aggregates. `COALESCE(a, b, c)` returns the first non-null; `NULLIF(a, b)`
returns `NULL` when equal, which is the idiom for avoiding division by zero:
`total / NULLIF(count, 0)`. `GREATEST`/`LEAST` ignore `NULL` in PostgreSQL and
MySQL but differ on null handling; check the engine. `IF`, `IIF` and `DECODE`
are vendor extensions - use `CASE` for portable code.

**Strings.** `LENGTH`/`CHAR_LENGTH` (bytes vs characters), `UPPER`, `LOWER`,
`TRIM`/`LTRIM`/`RTRIM`, `SUBSTRING`/`SUBSTR` (1-based), `POSITION`/`INSTR`,
`REPLACE`, `CONCAT` (MySQL requires it; `||` is standard and PostgreSQL/SQLite
use it), `LEFT`/`RIGHT`, `LPAD`/`RPAD`, `SPLIT_PART` (PostgreSQL),
`STRING_AGG`/`GROUP_CONCAT`/`LISTAGG` for aggregation. `LIKE` is
case-sensitive in PostgreSQL and case-insensitive in MySQL by default;
`ILIKE` is PostgreSQL-only. A leading wildcard defeats a B-tree index.

**Numbers.** `ROUND`, `CEIL`/`CEILING`, `FLOOR`, `ABS`, `MOD`, `POWER`,
`SQRT`, `EXP`, `LN`, `LOG`, `SIGN`, `TRUNC`. Integer division truncates in
PostgreSQL and MySQL; multiply by `1.0` or cast to `numeric` before dividing.
`numeric`/`DECIMAL` is exact and belongs in money columns; `float` is
approximate. `ROUND(numeric, 2)` is exact; `ROUND(double, 2)` is not.

**Dates and times.** `CURRENT_DATE`, `CURRENT_TIMESTAMP` and `NOW()` differ in
transaction semantics: standard `CURRENT_TIMESTAMP` is the transaction start;
`clock_timestamp()` in PostgreSQL is the actual moment. `EXTRACT(field FROM
ts)`, `DATE_TRUNC('month', ts)`, `AGE`, interval arithmetic (`ts + INTERVAL '7
days'`). `TIMESTAMPTZ` stores an instant and converts for display; `TIMESTAMP`
without a zone does not. Use half-open ranges (`>= start AND < end`) rather
than `BETWEEN` for timestamps, because `BETWEEN` includes the upper bound and
misses fractional seconds. Time-zone conversion needs the IANA database
(`AT TIME ZONE 'Asia/Kolkata'` in PostgreSQL).

**Aggregates.** `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `BOOL_AND`/`BOOL_OR`,
`STDDEV`, `VARIANCE`, `PERCENTILE_CONT`/`PERCENTILE_DISC`, `MODE`,
`STRING_AGG`/`GROUP_CONCAT`, `ARRAY_AGG`, `JSON_AGG`/`JSONB_AGG`. Aggregates
ignore `NULL`; `SUM` of no rows is `NULL`; `AVG` of integers returns numeric
in PostgreSQL. `FILTER (WHERE ...)` (PostgreSQL, SQLite 3.30+) is the standard
way to compute a conditional aggregate without `CASE`.

**Window functions.** Ranking (`ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`),
navigation (`LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`), and
aggregation (`SUM`, `AVG`, `COUNT`) over a window. Always specify the frame
when the default is not what you mean: `ROWS BETWEEN 6 PRECEDING AND CURRENT
ROW` for a seven-day moving sum, `RANGE BETWEEN UNBOUNDED PRECEDING AND
CURRENT ROW` for a running total that includes peers. `LAST_VALUE` with the
default frame returns the current row's value, not the partition's last.

**Set operations and CTEs.** `UNION`/`UNION ALL`, `INTERSECT`, `EXCEPT`;
`WITH` for readability, `WITH RECURSIVE` for trees and graphs (with a cycle
guard or a depth limit). PostgreSQL 12+ can inline non-recursive CTEs;
`MATERIALIZED` forces evaluation when the planner makes a bad choice.

**JSON.** PostgreSQL `jsonb` with `->`, `->>`, `#>`, `#>>`, `@>`, `jsonb_path_query`,
`jsonb_each`, `jsonb_agg`; MySQL `JSON_EXTRACT`, `->`/`->>`; SQLite
`json_extract`, `json_each`. Store hot fields as real columns with indexes and
keep the document for the long tail. JSON is not a schema; validate at
ingestion.

**Regex, text search and generated data.** PostgreSQL `~`, `~*`, `regexp_matches`,
`regexp_replace`, `regexp_split_to_table`; MySQL `REGEXP`; SQLite has no
built-in regex (the CLI has one). Full-text search (`to_tsvector`,
`tsquery`, `ts_rank`) belongs to PostgreSQL; MySQL has `MATCH ... AGAINST`;
SQLite has FTS5. `generate_series` (PostgreSQL) and recursive CTEs generate
rows; MySQL 8 and SQLite use recursive CTEs.

**Dialect differences that decide portability.** Identifier quoting (`"name"`
vs `` `name` `` vs `[name]`), `LIMIT/OFFSET` vs `TOP` vs `FETCH FIRST`, upsert
(`ON CONFLICT` vs `ON DUPLICATE KEY UPDATE` vs `MERGE`), boolean type,
`SERIAL` vs `IDENTITY`, `ILIKE`, `RETURNING` (PostgreSQL, SQLite 3.35+,
MariaDB), string concatenation, and null ordering (`NULLS FIRST/LAST`).

| Job | PostgreSQL | MySQL | SQLite |
|---|---|---|---|
| Concatenate | `a || b` | `CONCAT(a, b)` | `a || b` |
| Limit | `LIMIT n` | `LIMIT n` | `LIMIT n` |
| Upsert | `ON CONFLICT` | `ON DUPLICATE KEY` | `ON CONFLICT` |
| Current time | `now()` | `NOW()` | `datetime('now')` |
| Truncate date | `date_trunc` | `DATE_FORMAT` | `strftime` |
| JSON access | `->` / `->>` | `JSON_EXTRACT` | `json_extract` |
| Conditional agg | `FILTER` | `CASE` | `FILTER` |
| Regex | `~` | `REGEXP` | extension |
| Return rows | `RETURNING` | `RETURNING` (MariaDB) | `RETURNING` |

**The judgment call.** Keep SQL standard where it is cheap, and isolate
dialect-specific expressions behind a view or a repository function. Compute
in the database when it reduces data transfer or uses an index; compute in the
application when the logic is complex, testable and not performance-critical.
Both are engineering decisions, not ideology.""",
            r"""-- A daily report with conditional aggregates and a moving average.
WITH daily AS (
  SELECT date_trunc('day', created_at) AS day,
         count(*) AS orders,
         sum(CASE WHEN status = 'paid' THEN amount ELSE 0 END) AS revenue
  FROM orders
  GROUP BY 1
)
SELECT day,
       orders,
       revenue,
       round(avg(revenue) OVER (ORDER BY day
             ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d
FROM daily
ORDER BY day;

-- Null-safe percentage and a portable conditional aggregate.
SELECT region,
       count(*) AS rows,
       count(*) FILTER (WHERE status = 'paid') AS paid,
       round(100.0 * count(*) FILTER (WHERE status = 'paid')
             / NULLIF(count(*), 0), 1) AS paid_pct
FROM orders
GROUP BY region;

-- Latest row per customer without a window function.
SELECT DISTINCT ON (customer_id) customer_id, created_at, amount
FROM orders
ORDER BY customer_id, created_at DESC;""",
            """Write one report that uses a conditional aggregate, a window function with an
explicit frame, and a null-safe percentage. Then write the same report for MySQL,
naming every changed expression. Build a recursive CTE that finds all descendants of a
node and guards against cycles. Finally solve `top-k-frequent` in SQL, first with
`GROUP BY` + `ORDER BY` + `LIMIT`, then with a window function, and compare the plans.
Practice: /practice/problems/top-k-frequent""",
        ),
        (
            "sql-diagnostics-deep",
            "Reading SQL errors, plans and locks",
            "From SQLSTATE to EXPLAIN: diagnose a slow or failing query with evidence.",
            r"""**Why this matters.** A SQL failure has a code, a message and a plan. The
code tells you which class of rule was broken; the plan tells you what the
database did; the locks tell you who is waiting. Engineers who skip the code
and guess at the query often "fix" a symptom while leaving the cause. This
module is a workflow: classify, reproduce, explain, measure, change one thing.

**SQLSTATE is the taxonomy.** The first two characters are the class:
`00` success, `01` warning, `08` connection, `22` data exception, `23`
integrity constraint violation, `24` invalid cursor, `25` invalid transaction
state, `28` authorization, `40` transaction rollback (deadlock/serialization),
`42` syntax or access rule, `53` insufficient resources, `57` operator
intervention. The last three digits identify the specific condition. Postgres,
MySQL and SQLite all expose a code; log it next to the message.

**Syntax and name errors.** `42601` is a syntax error - the caret is near, not
always at, the cause; missing comma or a reserved word used as an identifier
are common. `42703` is an undefined column (typo, wrong alias, quoted case);
PostgreSQL folds unquoted identifiers to lower case, so `"UserID"` and
`userid` differ. `42P01` is an undefined table or a missing `search_path`.
`42702` is an ambiguous column in a join - qualify it.
`42803` is a `GROUP BY` violation: a selected column is neither grouped nor
aggregated.

**Constraint errors are business rules.** `23505` is a unique violation;
either pre-check under the right isolation, upsert, or translate it into a
domain conflict. `23503` is a foreign-key violation - insert parents first,
delete children first, or choose a cascade deliberately. `23502` is a not-null
violation; do not silence it with a dummy default. `23514` is a check
constraint; the constraint is the specification. `22001` is a string too long,
`22003` is numeric out of range, `22P02` is invalid text representation
(usually a cast of dirty data).

**Concurrency errors require a retry strategy.** `40001` serialization
failure and `40P01` deadlock are expected under concurrency: roll back and
retry the whole transaction with exponential backoff and jitter. `55P03` lock
not available and `57014` statement timeout are configuration signals - find
the blocking query before raising the timeout. `53300` too many connections is
a pool-sizing or leak problem, not a reason to increase the limit.

**`EXPLAIN` is a plan, `EXPLAIN ANALYZE` is the execution.** The plan shows a
tree: scan nodes (`Seq Scan`, `Index Scan`, `Index Only Scan`, `Bitmap Heap
Scan`), join nodes (`Nested Loop`, `Hash Join`, `Merge Join`), sort, aggregate
and limit. Rows are *estimates*; `EXPLAIN ANALYZE` adds actual rows, loops and
timing. The most useful comparison is estimated versus actual rows: a large
mismatch means stale statistics or a correlation the planner does not know.
`BUFFERS` shows cache hits and reads; `VERBOSE` shows the output columns.

**Read a plan bottom-up.** The deepest node runs first; each parent consumes
its children. A `Seq Scan` on a small table is correct; on a large table with a
selective filter it is a missing index or a non-sargable predicate
(`WHERE lower(email) = ...` without an expression index, `WHERE created_at + 1 >
...`, `LIKE '%term'`). A `Nested Loop` with a large outer row count and no
inner index is quadratic: add the index or let the planner hash. A `Sort` with
a small `LIMIT` should be a top-N heapsort; a large external sort spills to
disk (`Sort Method: external merge`).

**Statistics are the planner's model.** `ANALYZE` (or autovacuum) refreshes
column histograms; `n_distinct` and correlation affect index choice. A
`CREATE STATISTICS` on correlated columns (PostgreSQL) fixes multi-column
estimate errors. `pg_stat_statements` aggregates query cost across the
workload; `pg_stat_user_tables` shows sequential scans and dead tuples.
`auto_explain` logs plans for slow queries.

**Indexes are a cost decision.** A B-tree supports equality, ranges and
`ORDER BY`; a composite index is usable left-to-right, so `(a, b)` serves
`a` and `(a, b)` but not `b` alone. A covering index (`INCLUDE`) avoids heap
fetches. Partial indexes (`WHERE status = 'open'`) shrink the index for a hot
subset. Too many indexes slow writes and bloat storage; an unused index is
pure cost. A function on the indexed column disables the index unless the
index is on the same expression.

**Locks and isolation.** Read committed takes a new snapshot per statement;
repeatable read fixes the snapshot for the transaction; serializable adds
predicate conflict detection and can abort with `40001`. Row locks come from
`UPDATE`/`DELETE`/`SELECT FOR UPDATE`; a long transaction holds them longer.
Find blockers with `pg_locks`/`pg_stat_activity` (PostgreSQL) or
`performance_schema` (MySQL). Keep transactions short, touch rows in a
consistent order, and never wait on a human inside a transaction.

**Migrations and schema changes.** Add nullable columns and backfill in
batches; create indexes concurrently (PostgreSQL `CREATE INDEX CONCURRENTLY`);
avoid long `ALTER TABLE` locks on hot tables; version the schema and make every
migration reversible or explicitly irreversible. A migration that runs inside
a transaction and takes an exclusive lock can stall the whole application.

| Code | Meaning | Action |
|---|---|---|
| `42601` | Syntax error | Read the token before the caret |
| `42703` | Undefined column | Check alias and quoted case |
| `42803` | `GROUP BY` violation | Group or aggregate |
| `23505` | Unique violation | Upsert or handle conflict |
| `23503` | Foreign-key violation | Fix order or cascade |
| `40001` | Serialization failure | Retry the transaction |
| `40P01` | Deadlock | Consistent lock order, retry |
| `57014` | Statement timeout | Find the slow node |
| `53300` | Too many connections | Pool size or leak |

**The judgment call.** Change one thing at a time: the index, the predicate,
the join order or the statistics - then re-measure the same query on the same
data. A plan is evidence; a guess is a hypothesis. Do not raise a timeout to
hide a scan, and do not add an index before reading the plan that says it is
missing.""",
            r"""-- Classify before changing: what did the planner choose, and how wrong was it?
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT c.id, c.email, count(o.id) AS orders
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.created_at >= DATE '2026-01-01'
  AND c.status = 'active'
GROUP BY c.id, c.email
ORDER BY orders DESC
LIMIT 20;

-- Sargable rewrite: the function moved to the parameter side.
SELECT * FROM orders
WHERE created_at >= DATE '2026-01-01'
  AND created_at <  DATE '2026-02-01';

-- Expression index for a case-insensitive lookup.
CREATE INDEX CONCURRENTLY customers_email_lower
  ON customers (lower(email));
SELECT * FROM customers WHERE lower(email) = 'a@example.com';

-- See who is blocking whom.
SELECT pid, wait_event_type, wait_event, state, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;""",
            """Take a slow query and write down the estimated rows versus actual rows for every
node before changing anything. Add the index or rewrite the predicate the plan asks for,
then re-run `EXPLAIN ANALYZE` and compare. Reproduce a unique-violation error and handle
it with an upsert instead of a pre-check. Force a deadlock with two sessions updating
rows in opposite orders, read the error code, and fix the order. Finally solve
`version-compare`, storing versions in a normalised table with a unique constraint and
explaining which constraint catches a duplicate.
Practice: /practice/problems/version-compare""",
        ),
    ],
}

MODULE_PRACTICE: dict[str, str] = {
    "rust-semantics-deep": "reverse-linked-list",
    "rust-stdlib-deep": "top-k-frequent",
    "rust-diagnostics-deep": "validate-ipv4",
    "sql-semantics-deep": "count-provinces",
    "sql-stdlib-deep": "top-k-frequent",
    "sql-diagnostics-deep": "version-compare",
}
