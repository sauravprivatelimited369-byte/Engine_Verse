"""Second depth wave: the runtime, tooling and systems material.

The first book wave (``language_book_*``) taught problem solving - complexity,
structures, algorithms, interview method. This wave teaches the things a
reference site such as W3Schools documents syntactically but rarely explains:
what the runtime actually does, where the costs are, how the toolchain and the
build work, what the memory model guarantees, and which failures are real
production failures rather than quiz answers.

Two modules per language, one on concurrency/runtime behaviour and one on
either memory, tooling, types or the query planner. Bodies use real newlines
(triple-quoted) and are rendered as Markdown by the language reader. Every
module ends with a runnable example and an exercise that names one judged
problem, so the reading turns into code.

Standard language facts only: JMM happens-before rules, the CPython GIL,
Go's GMP scheduler, Rust's borrow checker, SQL isolation anomalies and B-tree
index behaviour are the textbook definitions. Version-specific notes (free
threading, virtual threads, ``Span<T>``, ``satisfies``) say which release they
landed in, because a version claim that drifts is worse than no claim.
"""

from __future__ import annotations

BOOK_MODULES: dict[str, list[tuple]] = {
    "python": [
        (
            "python-gil-concurrency-deep",
            "Threads, processes and async: what the GIL really costs",
            "Concurrency versus parallelism, the GIL, I/O-bound work and asyncio done properly.",
            """**Why this matters.** Python is the language most often accused of
being "bad at concurrency", and the accusation is half true in a way that
matters: threads do not give you parallel CPU work in CPython, but they do
overlap waiting. Engineers who do not know which half is true either ship a
slow program with sixteen threads or avoid concurrency entirely and block a
web server on a 400 ms API call. This module teaches you to classify the work
first, then pick the tool.

**The GIL in one paragraph.** CPython protects its reference counts with a
global interpreter lock. Only one thread executes Python bytecode at a time
in a single interpreter. Threads are therefore useful when your time goes to
*waiting* - sockets, files, sleep, database drivers - because the GIL is
released while a thread blocks in C code. They are useless for pure-Python
number crunching, where the threads take turns and you pay switching cost on
top. Since Python 3.13 there is an officially supported experimental
free-threaded build (PEP 703) that removes the GIL, but it is a separate
build, slower on single-threaded code, and C extensions must opt in - so port
your code as if the GIL is still there, and treat free threading as a bonus.

**Four tools, four jobs.**

- `threading` - dozens of concurrent I/O waits in one process. Simple, and
  shares memory, which is also its danger: a shared `dict` mutated from two
  threads is a race unless you lock it.
- `concurrent.futures.ThreadPoolExecutor` - the same, with a sane API:
  `submit`, `map`, `as_completed`, and exceptions delivered when you read the
  future.
- `multiprocessing` / `ProcessPoolExecutor` - real parallel CPU work, at the
  cost of pickling arguments and results and starting interpreters. Default
  start method on Linux is `fork`; on macOS and Windows it is `spawn`, so
  module-level guard `if __name__ == '__main__':` is mandatory or children
  re-import and re-run your script.
- `asyncio` - one thread, an event loop, thousands of sockets. Every blocking
  call must be replaced with an `await`: `asyncio.sleep`, `await client.get`,
  `run_in_executor` for libraries that never learned. One blocking call in a
  coroutine stalls the whole loop - the classic asyncio outage.

**Decision table.** Is the work CPU-heavy (loops, parsing, maths)? Use
processes. Is it waiting on many independent I/O endpoints? Use `asyncio`
(if the libraries support it) or threads. Is it a mix? `asyncio` plus a
`ProcessPoolExecutor` for the CPU parts, or a task queue (Celery, RQ) when the
work must survive a restart. Never "just add threads" as a reflex.

**Sizing and backpressure.** More threads than concurrent I/O waits is
waste; more processes than CPUs plus one is waste. Bound concurrency
explicitly (`asyncio.Semaphore`, executor `max_workers`) so a spike queues
instead of exhausting memory or file descriptors. Then measure: wall-clock
time and CPU time together. A speed-up with unchanged CPU time means you
overlapped waiting. Unchanged wall time with higher CPU time means you added
switching cost for nothing.

**Common mistakes.** Sharing mutable state without a lock and calling it
"thread-safe because Python has the GIL" (the GIL makes a single bytecode
atomic; `counter += 1` is three bytecodes); calling `time.sleep` inside a
coroutine; using `asyncio.gather` and forgetting that a raised exception is
re-raised at the await, silently leaving other tasks running; starting a
process pool inside a request handler on every call; measuring a 5 ms task
where startup dominates and concluding concurrency "does not help".

**Interview angle.** Say the classification out loud before naming a tool:
"I/O-bound, so threads or asyncio; if it were CPU-bound the GIL would force
processes." That single sentence distinguishes you from candidates who recite
"Python has a GIL" without knowing what it affects.""",
            """import asyncio
import threading
import time

def io_task(n):
    time.sleep(0.2)               # stands in for a network call
    return n * n

def cpu_task(n):
    total = 0
    for i in range(3_000_000):    # stands in for real number crunching
        total += i % 7
    return total

start = time.perf_counter()
for n in range(4):
    io_task(n)
print(f"serial io      {time.perf_counter() - start:.2f}s")

start = time.perf_counter()
threads = [threading.Thread(target=io_task, args=(n,)) for n in range(4)]
for t in threads: t.start()
for t in threads: t.join()
print(f"threaded io    {time.perf_counter() - start:.2f}s")   # ~4x faster

start = time.perf_counter()
for n in range(4):
    cpu_task(n)
print(f"serial cpu     {time.perf_counter() - start:.2f}s")

start = time.perf_counter()
threads = [threading.Thread(target=cpu_task, args=(n,)) for n in range(4)]
for t in threads: t.start()
for t in threads: t.join()
print(f"threaded cpu   {time.perf_counter() - start:.2f}s")   # no gain: the GIL

async def fetch(n):
    await asyncio.sleep(0.2)
    return n * n

async def main():
    start = time.perf_counter()
    results = await asyncio.gather(*(fetch(n) for n in range(50)))
    print(f"asyncio 50 io  {time.perf_counter() - start:.2f}s", results[:4])

asyncio.run(main())""",
            """Run the example and explain each timing line: why threaded I/O wins,
why threaded CPU does not, and why asyncio finishes 50 waits in about the
time of one. Then convert the CPU part to a `ProcessPoolExecutor` and confirm
it scales with cores. Finally solve the judged problem `word-ladder`, where
each BFS frontier can be expanded concurrently - and argue where concurrency
is genuinely worth the complexity.
Practice: /practice/problems/word-ladder""",
        ),
        (
            "python-typing-tooling-deep",
            "Types, packaging and CI that actually catch bugs",
            "Annotations, mypy strictness, pyproject, tests and a reproducible release.",
            """**Why this matters.** Two Python codebases can look identical and
behave completely differently in production: one has a pinned, reproducible
environment and a type checker failing the build on real errors; the other
runs whatever `pip install` resolved today and discovers the bug in a 2 a.m.
traceback. The difference is tooling discipline, not talent. This module is
the professional layer that tutorials skip.

**Annotations are documentation the machine can check - and that is all.**
`def total(xs: list[int]) -> int` does not enforce anything at runtime;
Python stores the annotation and keeps going. Type errors are caught by
*mypy* or *pyright* before the code runs, which is why the tool has to be in
CI. Use `from __future__ import annotations` (default in 3.11+ for many
cases) to keep annotations lazy, and use the built-in generics
(`list[int]`, `dict[str, float]`, `X | None`) rather than `typing.List`.
For values that are checked at runtime, use a validator - annotations are
for humans and static tools, validators are for JSON arriving from the
internet.

**Type the boundaries first.** Untyped internals are survivable; untyped
boundaries are not. Annotate the function that reads config, the one that
parses a request, and the one that writes to the database. Use `Protocol` to
describe the *shape* you need from a collaborator instead of importing a
concrete class, and `TypedDict` for JSON-shaped dicts. Turn on
`--strict` in mypy on new packages; the real win is `disallow_untyped_defs`
and `no_implicit_optional`, which surface forgotten branches.

**Structure: a package, not a folder of scripts.** `src/mypkg/`, a
`pyproject.toml` declaring dependencies with `[project]`, a console entry
point via `[project.scripts]`, and a lock file (uv, poetry, or pip-tools
compiled requirements) that pins every transitive version with hashes. `pip
install .` must install your application into a clean environment; if it
does not, the package is not a package.

**Tests that pay rent.** `pytest` with three habits: `parametrize` for
tables of cases (edge cases become rows, not files); fixtures for setup, with
`tmp_path` instead of writing into the repo; and one test per behaviour, not
per function. Assert on observable behaviour, not on internals, or every
refactor breaks the suite and the team deletes the tests. Coverage is a
diagnostic, not a target: 100 % coverage of code that asserts nothing is
worse than 70 % coverage of real contracts.

**CI that fails honestly.** One job runs `ruff check`, `ruff format
--check`, `mypy`, then `pytest -q` on a matrix of supported Python
versions; lint failures fail the build instead of being ignored. Pin action
versions, cache the package manager, and make the test command the same one
developers run locally. A build that only fails on main is a broken process.

**Release discipline.** Semantic versioning communicates risk (`0.x` means
the API will change). A changelog entry per user-visible change, a tag, an
artefact built from the tag, and an install check from a clean virtual
environment. If the release cannot be reproduced from the repository alone,
it is not a release.

**Common mistakes.** Annotations on public functions with no checker in CI
(decorative typing); `# type: ignore` everywhere, which silences the tool
instead of fixing the contract; mutable default arguments (`def f(x=[])`);
wildcard imports that make names unsearchable; `requirements.txt` with no
pins; tests that pass because they assert nothing, or because they run in
the order they were written.

**Interview angle.** "The type hints are enforced by mypy in CI, the
environment is locked, and the release is reproducible" is a senior answer.
Say where the boundary validators live and why runtime validation and static
types solve different problems - that distinction is what separates typing
as a style choice from typing as engineering.""",
            """from dataclasses import dataclass, field
from typing import Protocol

class Repository(Protocol):
    def get(self, key: str) -> int: ...

@dataclass(frozen=True)
class Settings:
    timeout_ms: int
    retries: int = 2
    hosts: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")

class DictRepository:
    def __init__(self, data: dict[str, int]) -> None:
        self._data = data
    def get(self, key: str) -> int:
        return self._data[key]

def total(repo: Repository, keys: list[str]) -> int:
    # Protocol-typed: any object with a matching get() works here.
    return sum(repo.get(k) for k in keys)

settings = Settings(timeout_ms=500, hosts=("api.internal",))
print(settings)
print(total(DictRepository({"a": 2, "b": 3}), ["a", "b"]))

try:
    Settings(timeout_ms=0)
except ValueError as exc:
    print("rejected:", exc)   # runtime validation, unlike annotations""",
            """Add `expected` / `actual` fields to a `CheckResult` dataclass and
write parametrised pytest cases for the boundary values. Then run mypy
`--strict` on the file and fix every complaint without a `type: ignore`.
Finally solve the judged problem `validate-ipv4`, and write a
`TypedDict`-shape boundary validator with tests for the empty and
out-of-range cases.
Practice: /practice/problems/validate-ipv4""",
        ),
    ],
    "java": [
        (
            "java-jvm-memory-gc",
            "Inside the JVM: heap, stack, GC and the leaks you can still write",
            "Where objects live, how generations are collected, and why a managed runtime still leaks.",
            """**Why this matters.** "Java has a garbage collector, so memory is
handled" is true and dangerously incomplete. The JVM manages *unreachable*
memory; it cannot free what you keep reachable, and it cannot save you from
allocating in a hot loop until the collector spends its life reclaiming young
objects. Every Java engineer eventually debugs an `OutOfMemoryError`, a
latency spike from a full GC, or a leak that only appears after a week of
uptime. This module is what that debugging looks like.

**Where things live.** Each thread has a stack of frames: primitives, local
references, return addresses. The heap holds every object (including arrays)
and is shared. Class metadata lives in metaspace (native memory). The stack
costs nothing to reclaim - popping a frame is the reclamation - so deep
recursion can produce a `StackOverflowError` while the heap is almost empty.

**Allocation is cheap; garbage is expensive.** Creating a short-lived object
is a pointer bump in a thread-local allocation buffer (`-XX:+UseTLAB`). Most
objects die young, so collectors are generational: new objects go to Eden,
survivors get copied between survivor spaces, and objects that survive enough
collections are promoted to the old generation. A full (old-gen) collection
is the expensive one. That is why *allocation rate*, not heap size, drives GC
pause frequency: allocate 1 GB/s of garbage and the collector runs
constantly even with a big heap.

**Collector choices.** Serial and Parallel are throughput-oriented; G1
(default since JDK 9) targets a pause-time goal with region-based collection;
ZGC and Shenandoah target sub-millisecond pauses on very large heaps at some
throughput cost. Choose with measurements from your own workload - `-Xmx`,
`-XX:MaxGCPauseMillis`, GC logs (`-Xlog:gc*`) - not from a blog post.

**Escape analysis and the stack.** The JIT can prove an object never escapes
a method and scalar-replace it, so small short-lived objects may allocate
nothing at all. That is a reason not to "optimise" prematurely by pooling
objects: object pooling often makes GC worse by keeping garbage alive, and
the JIT is already good at the easy cases.

**Leaks in a managed language.** A leak is an unintended strong reference:
static collections that only ever grow (`static Map<Session, Data>`),
listeners registered and never removed, `ThreadLocal` values in pooled
threads, caches with no eviction, `intern()` on unbounded input, or a
`subList` retaining the parent array. The heap dump is the evidence: take one
with `jcmd <pid> GC.heap_dump`, open it in a tool, and find the dominator
that should not be there. `WeakHashMap`, `WeakReference`, and bounded caches
(explicit size or time-based eviction) are the fixes - not calling
`System.gc()`, which is a hint the JVM may ignore.

**Measuring instead of guessing.** `jcmd <pid> VM.native_memory summary`,
`jcmd GC.heap_info`, and Java Flight Recorder (`-XX:StartFlightRecording`)
give you allocation profiles and pause data. `OutOfMemoryError` has flavours
worth reading: `Java heap space` (genuinely too much live data), `Metaspace`
(classloader leak - common in hot redeploy), `unable to create native
thread` (thread leak or ulimit), `GC overhead limit exceeded` (heap full of
almost-dead objects and the collector earning nothing).

**Common mistakes.** Raising `-Xmx` as the only response to an OOM (it
delays the failure); holding request data in static fields; forgetting that
`String` concatenation in a loop allocates a new object every iteration;
assuming `finalize()` runs (it is deprecated and non-deterministic - use
`Cleaner` or try-with-resources); treating `Reference` types as ordinary
fields and wondering why the object is never collected.

**Interview angle.** Describe the generational hypothesis, name the
collector you would start with and why, and explain how you would prove a
leak rather than guess one. Mentioning a heap dump is the difference between
reading about GC and having debugged it.""",
            """import java.util.ArrayList;
import java.util.List;

public class MemoryDemo {
    record Sample(int id, double value) {}

    static void allocationRate(int iterations) {
        long start = System.nanoTime();
        long sink = 0;
        for (int i = 0; i < iterations; i++) {
            Sample s = new Sample(i, i * 0.5);   // young garbage, collected cheaply
            sink += s.id();
        }
        System.out.printf("alloc loop: %d ms (sink=%d)%n",
                          (System.nanoTime() - start) / 1_000_000, sink % 10);
    }

    public static void main(String[] args) {
        System.out.println("max heap: " + Runtime.getRuntime().maxMemory() / (1024 * 1024) + " MB");
        allocationRate(5_000_000);

        // A bounded cache is the fix for the classic static-map leak.
        List<byte[]> reserved = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            reserved.add(new byte[1024 * 1024]);   // live data: GC cannot help
        }
        System.out.println("live buffers: " + reserved.size());
        System.out.println("used heap: "
            + (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / (1024 * 1024) + " MB");
        reserved.clear();                          // now they are collectable
        System.gc();                               // a hint, not a guarantee
        System.out.println("after clear, used heap is lower on the next collection");
    }
}""",
            """Run the demo with `-Xmx64m` and then `-Xmx512m` and compare the
allocation-loop timings and GC behaviour; add `-Xlog:gc` and count the
collections instead of guessing. Then write a deliberately leaking static
`HashMap` cache, take a heap histogram with `jcmd <pid> GC.class_histogram`,
and fix it with a bounded cache. Finally solve the judged problem
`matrix-transpose`, where row-major versus column-major traversal decides
whether the cache helps you or fights you.
Practice: /practice/problems/matrix-transpose""",
        ),
        (
            "java-concurrency-jmm-deep",
            "The Java Memory Model: happens-before, volatile and executors",
            "Atomicity, visibility, ordering - and the executor patterns that remove the guesswork.",
            """**Why this matters.** A threaded Java bug is not usually "two threads
incremented a variable". It is a field that *looks* set in one thread and is
still stale in another, a `while (!ready)` loop that never exits even though
another thread set `ready = true`, or an object published half-constructed.
These are not random; they are exactly what the Java Memory Model permits,
and they are fixable with rules rather than luck.

**Three problems, three names.**

- *Atomicity*: `count++` is read-modify-write, three steps. Two threads can
  interleave and lose an increment. Fix: `AtomicInteger`, a lock, or a
  design without shared mutation.
- *Visibility*: writes are not guaranteed to be visible to other threads
  without a happens-before edge, because each core caches and the JIT hoists
  reads out of loops. Fix: `volatile`, `synchronized`, or a concurrent
  collection.
- *Ordering*: the compiler and CPU may reorder independent instructions.
  A constructor may appear to run after a field assignment to another
  thread. Fix: safe publication via `final` fields, `volatile`, or a lock.

**Happens-before is the whole model.** The JMM does not promise "real time";
it promises that certain edges exist, and that a write before an edge is
visible to a read after it. The edges you use daily: program order within a
thread; monitor unlock *happens-before* a later lock of the same monitor;
a write to a `volatile` field *happens-before* a subsequent read of it;
`Thread.start()` before the run body; thread completion before `join()`
returns; `final` field semantics for properly constructed objects; and the
transitive combination of all of the above. So `synchronized` is not only
mutual exclusion - it also flushes and publishes, which is why a correct
lock-based design fixes visibility without extra `volatile`.

**Use the library before the primitive.** `java.util.concurrent` exists so
that you rarely write `wait`/`notify` by hand: `ConcurrentHashMap`,
`BlockingQueue`, `CountDownLatch`, `Semaphore`, `ExecutorService`,
`CompletableFuture`. `BlockingQueue.take()` gives you a thread-safe
producer-consumer with backpressure and no lock code to get wrong.

**Threads are expensive, tasks are cheap.** Creating a platform thread
costs a stack (roughly a megabyte of native memory by default) and an OS
scheduling decision. An `ExecutorService` reuses a bounded pool; a fixed pool
for CPU work, a larger or virtual-thread-per-task model for I/O. Virtual
threads (final in JDK 21) are scheduled by the JVM and park cheaply on
blocking I/O - they make thread-per-request style viable for huge request
counts, but they do not make CPU work faster and they do not fix pinning
from `synchronized` blocks or native calls.

**Deadlock and starvation.** Deadlock needs four conditions; the practical
one to remove is circular wait. Establish a global lock order (sort by id),
never call foreign code while holding a lock, use `tryLock` with a timeout
where a lock hierarchy is impossible, and prefer immutable messages over
shared mutable state - the design with no shared writes has no lock bugs.

**Common mistakes.** `volatile` used as a substitute for atomicity; the
double-checked locking idiom written without `volatile`; catching
`InterruptedException` and swallowing it instead of restoring the flag; an
unbounded queue hiding a producer that outruns its consumer until the heap
dies; `CompletableFuture` chains whose exceptions vanish because nobody
calls `join()`; blocking on a task from within the same pool and starving
it (thread-pool starvation).

**Interview angle.** Answer with the model, not the incantation: "I need
happens-before between the writer and the reader, so I will use a volatile
flag or publish through a concurrent collection." Then state whether the
work is CPU-bound or blocking, and size the executor accordingly.""",
            """import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrencyDemo {
    static int unsafeCount = 0;                     // lost updates
    static volatile boolean ready = false;          // visibility, not atomicity
    static final AtomicInteger safeCount = new AtomicInteger();

    public static void main(String[] args) throws Exception {
        Runnable work = () -> { for (int i = 0; i < 100_000; i++) { unsafeCount++; safeCount.incrementAndGet(); } };
        Thread a = new Thread(work), b = new Thread(work);
        a.start(); b.start(); a.join(); b.join();
        System.out.println("plain int:      " + unsafeCount + " (usually < 200000)");
        System.out.println("AtomicInteger:  " + safeCount.get());

        Thread watcher = new Thread(() -> {
            while (!ready) Thread.onSpinWait();      // volatile read, refreshed
            System.out.println("watcher saw ready");
        });
        watcher.start();
        Thread.sleep(50);
        ready = true;                                // happens-before the read
        watcher.join();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        BlockingQueue<Integer> queue = new LinkedBlockingQueue<>(8);   // bounded: backpressure
        Future<Integer> total = pool.submit(() -> {
            int sum = 0;
            for (int i = 0; i < 5; i++) sum += queue.take();
            return sum;
        });
        for (int i = 1; i <= 5; i++) queue.put(i);
        System.out.println("queue total: " + total.get());
        pool.shutdown();
    }
}""",
            """Remove `volatile` from `ready` and run the program repeatedly with
`-Xint` and with the JIT on; explain any difference in the watcher's
behaviour using happens-before. Then replace the queue with an unbounded
`LinkedBlockingQueue` and describe the failure mode as producer rate rises.
Finally solve the judged problem `course-schedule` using a
`ConcurrentHashMap` and checking that your topological order is correct
under repeated runs.
Practice: /practice/problems/course-schedule""",
        ),
    ],
    "javascript": [
        (
            "js-event-loop-deep",
            "The event loop: tasks, microtasks and why the UI freezes",
            "One thread, two queues and a rendering step - the ordering rules behind every async bug.",
            """**Why this matters.** JavaScript has one thread of execution and a
queue of callbacks. Every confusing behaviour you have met - "why did my
promise resolve after the timeout that I scheduled first?", "why is the
spinner never painted?", "why did the page freeze for two seconds?" - is that
model working exactly as specified. Knowing the model turns async from
folklore into prediction.

**The pieces.** A call stack runs functions. Web APIs (timers, network,
DOM events, `fetch`) do work outside the stack and post callbacks back. The
queue those callbacks enter has two parts: the *task queue* (also called the
macrotask queue: `setTimeout`, `setInterval`, I/O events, message events)
and the *microtask queue* (`Promise.then`, `queueMicrotask`,
`MutationObserver`). The event loop runs one task, then drains the entire
microtask queue - including microtasks queued by microtasks - then, if it is
a rendering opportunity, renders, then takes the next task. Microtasks
therefore always run before the next timer, and a chain of promises can
starve rendering indefinitely if it never stops queueing.

**Ordering you can rely on.**

```
console.log('1');                       // sync
setTimeout(() => console.log('2'));     // task
Promise.resolve().then(() => console.log('3'));  // microtask
console.log('4');                       // sync
// output: 1, 4, 3, 2
```

`await` is this rule in disguise: everything after an `await` is a
microtask continuation, so code after `await` runs before a `setTimeout`
scheduled before it. Two independent `await`s resume in the order they
settled, not the order they were written.

**Why the UI freezes.** Rendering cannot happen while the stack is busy. A
synchronous loop over 10 million items, a large `JSON.parse`, a synchronous
XHR, or an event handler that blocks all delay the paint and every input
event. The event loop has no preemption: your code runs until it returns.
The two fixes are (1) make the work smaller and asynchronous - chunk with
`setTimeout(..., 0)` or `scheduler.yield()`, stream parsing, virtualise
lists; or (2) move it off the thread - Web Worker, or a server.

**Timers are not precise.** `setTimeout(fn, 0)` means "no sooner than 0 ms
after the current work"; browsers clamp nested timers (4 ms after five
levels) and throttle background tabs. Never build a clock from accumulated
timeouts; measure with `performance.now()` and correct the drift. Timers
also do not run in a hidden tab in the same way, so a background tab cannot
be your scheduler.

**Node is the same idea, different phases.** Node's loop has timers,
pending callbacks, poll, check (`setImmediate`) and close phases, and
`process.nextTick` runs before promise microtasks. That is why
`setImmediate` and `setTimeout(fn, 0)` can order differently inside an I/O
callback. Never rely on that for correctness; if order matters, sequence it
explicitly.

**Errors and starvation.** An exception in a task becomes an uncaught
error; in a promise it becomes a rejection. A rejection nobody handles is
reported late (or crashes Node), so attach `.catch` or use `try/catch` with
`await`. A recursive microtask chain starves timers *and* rendering - it
looks like a frozen tab. `await` inside a loop over 100 000 items queues
100 000 microtasks; batch with `Promise.all` on chunks.

**Common mistakes.** `await` inside `forEach` (it does not wait - use
`for...of` or `Promise.all`); assuming `Promise.all` stops other tasks on
rejection (they keep running, you just stop waiting); using
`setTimeout(fn, 0)` to "wait for the DOM" when what you need is
`queueMicrotask`/`requestAnimationFrame` after layout; measuring async
performance with `Date.now()`; making a promise executor `async` (errors
inside it are swallowed).

**Interview angle.** Draw the loop: stack, task queue, microtask queue,
render. Then place a snippet's outputs in that order and say out loud that
microtasks drain fully before the next task. That one drawing answers most
"predict the output" questions.""",
            """console.log('A sync');

setTimeout(() => console.log('B task (timer)'), 0);

Promise.resolve()
  .then(() => console.log('C microtask'))
  .then(() => console.log('D microtask (chained)'));

queueMicrotask(() => console.log('E microtask (queued directly)'));

(async () => {
  console.log('F inside async, before await');
  await null;                      // everything below is a microtask
  console.log('G after await');
})();

console.log('H sync');

// Expected: A, F, H, C, E, G, D, B
// The async IIFE runs synchronously up to its first await (printing F),
// then the main script finishes (H), then the whole microtask queue drains
// (C, E, G, D) and only then the timer task (B) runs.

const started = performance.now();
let sum = 0;
for (let i = 0; i < 5_000_000; i++) sum += i % 3;   // blocks: no paint, no events
console.log('blocking loop took', Math.round(performance.now() - started), 'ms');

function yieldToBrowser() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

async function chunkedWork(total, chunk) {
  let acc = 0;
  for (let i = 0; i < total; i += chunk) {
    for (let j = i; j < Math.min(i + chunk, total); j++) acc += j % 3;
    await yieldToBrowser();       // gives rendering and input a turn
  }
  return acc;
}

chunkedWork(5_000_000, 200_000).then(acc => console.log('chunked result', acc));""",
            """Predict the output of the first half before running it, then explain
each line with the queue it belongs to. Add a `Promise.reject` with no
handler and observe when the environment reports it. Then solve the judged
problem `rotting-oranges`: BFS processes one frontier ("wave") at a time,
which is the same layer-by-layer discipline the event loop applies to tasks
and microtasks.
Practice: /practice/problems/rotting-oranges""",
        ),
        (
            "js-modules-bundling-deep",
            "Modules, bundlers and the npm supply chain",
            "ESM versus CommonJS, resolution, tree shaking and treating dependencies as risk.",
            """**Why this matters.** A modern JavaScript project is mostly other
people's code. Two skills follow: understanding how the module graph is
built, so imports resolve and bundles stay small; and treating the dependency
tree as an attack surface, because `npm install` executes install scripts
with your user's privileges and most projects never read what they pull in.

**Two module systems.** CommonJS (`require`/`module.exports`) is
synchronous, dynamic, and evaluates once with a cached result - which is why
mutating an exported object is visible to every importer. ESM (`import`/
`export`) is static, asynchronously loaded, and exports *live bindings*:
importers see later changes to an exported `let`, and circular imports
behave differently (ESM gives you a binding that may be uninitialised, CJS
gives you a partially filled object). Node supports both; `.mjs`/`.cjs` or
`"type": "module"` in `package.json` decides the default. In the browser,
`<script type="module">` is deferred, strict by default, and loaded with CORS
- which is why a bare `import React from 'react'` fails without an import map
or a bundler.

**Resolution is a specification, not a guess.** Node resolves bare
specifiers through `node_modules` walking upwards, `exports` maps in
`package.json` (which can make deep imports illegal), `imports` for `#alias`
and conditional exports (`import`/`require`/`browser`/`node`). Bundlers and
Deno/Bun implement the same rules approximately. Two packages that disagree
about a conditional export can load *two copies* of a library - the classic
"my context is null" bug with duplicated React.

**Bundlers.** A bundler reads the graph, transforms syntax, and emits one
or more files. Two properties matter:

- *Tree shaking* removes unused ESM exports. It works when the module has no
  side effects the bundler cannot see, so `"sideEffects": false` in
  `package.json` is a promise your library must keep - lying about it drops
  CSS imports and polyfills.
- *Code splitting* turns dynamic `import('./chart.js')` into a separate chunk
  loaded on demand, which is the difference between a 2 s first paint and a
  400 ms one. Static imports cannot be deferred.

Modern browsers load ESM natively; bundlers are for compatibility,
optimisation and dependency resolution, not language support. Vite serves
native ESM in development, which is why its server starts instantly and why
"works in dev, breaks in build" usually means a CJS interop or conditional
export problem.

**The supply chain is code you run.** `npm install` runs lifecycle scripts
(`postinstall`) from transitive dependencies. Practical defences: commit the
lockfile and use `npm ci` (not `npm install`) in CI so the resolved tree is
exactly reviewed; enable `--ignore-scripts` where the project allows it; check
new dependencies for typosquats (`cross-env` versus `crossenv`); keep the
tree small (every dependency is also its own dependency tree); use
`npm audit`/Dependabot for known CVEs while knowing that audit noise is high;
and never `npm install` a package you cannot name the maintainer of into a
build with deploy credentials.

**Versions are a contract.** Semver says patch = fixes, minor = additive,
major = breaking; caret ranges (`^1.4.2`) accept minor and patch changes,
which is fine for apps with a lockfile and dangerous for libraries that
become surprising to consumers. Pin what you deploy, review what you upgrade,
and keep the lockfile in review diffs - a lockfile change is a code change.

**Common mistakes.** Importing a whole library for one function
(`import _ from 'lodash'` versus `lodash/pick`); mixing `require` and
`import` in the same file so interop defaults shift; assuming tree shaking
works on CJS; a `sideEffects: false` claim that drops your polyfills; adding
a dependency for something a dozen lines could do; missing `"exports"` in a
published library so consumers cannot deep import or get types.

**Interview angle.** Explain the difference between static and dynamic
imports in terms of *what the bundler can know before running the code*. Then
say how you would cut a 1 MB bundle: measure with a bundle analyser, split
routes with dynamic imports, replace or drop heavy dependencies, and verify
with the same measurement.""",
            """// A tiny dependency graph that shows why module caching matters.
const registry = new Map();

function defineModule(id, factory) {
  registry.set(id, { id, factory, exports: undefined, loaded: false });
}

function requireModule(id, stack = []) {
  if (stack.includes(id)) {
    throw new Error(`circular import: ${[...stack, id].join(' -> ')}`);
  }
  const mod = registry.get(id);
  if (!mod) throw new Error(`cannot resolve '${id}' from ${stack.at(-1) ?? 'entry'}`);
  if (mod.loaded) return mod.exports;      // single evaluation, cached
  mod.exports = {};
  mod.loaded = true;
  const localRequire = dep => requireModule(dep, [...stack, id]);
  mod.exports = mod.factory(localRequire) ?? mod.exports;
  return mod.exports;                      // live object, shared by importers
}

defineModule('math', () => ({
  clamp: (n, lo, hi) => Math.min(hi, Math.max(lo, n)),
}));

defineModule('format', require => {
  const { clamp } = require('math');
  return { percent: n => `${Math.round(clamp(n, 0, 1) * 100)}%` };
});

const format = requireModule('format');
console.log(format.percent(0.426));        // 43%
console.log(format.percent(2));            // 100% (clamped)
console.log(requireModule('math') === requireModule('math'));  // true: cached

// Dynamic import is what makes code splitting possible:
// const charts = await import('./charts.js');  // loaded on demand, not up front""",
            """Add a `theme` module that both `format` and an entry module import, then
make `theme` import `format` and explain the circular-import failure the
loader reports. Rewrite the same graph with native ESM `export`/`import` and
verify with `node --input-type=module`. Then solve the judged problem
`version-compare`, which is the comparison rule a package manager uses to
decide whether `^1.4.2` accepts 1.5.0.
Practice: /practice/problems/version-compare""",
        ),
    ],
    "typescript": [
        (
            "ts-type-system-deep",
            "The TypeScript type system: narrowing, generics and inference",
            "Structural typing, discriminated unions, conditional types and an honest look at soundness.",
            """**Why this matters.** TypeScript is not "JavaScript with labels". It
is a structural type system with unions, generics, inference and a
compile-time-only existence. Used shallowly it adds annotations that drift;
used properly it makes illegal states unrepresentable, so whole classes of
bug fail the build instead of the customer. The difference between those two
outcomes is precisely the material below.

**Structural, not nominal.** `{ id: number }` accepts any object with a
numeric `id`, whatever its class. That is why interfaces describe shapes and
why two unrelated types can be interchangeable. Assignability is checked by
member compatibility, with freshness checks for object literals (the "excess
property" error) to catch typos. Classes still add nominal flavour through
`private` members, and nominal intent can be enforced with a brand.

**Unions and narrowing.** A union says "one of these". Narrowing is the
compiler tracking which member you have: `typeof x === 'string'`, `x == null`,
`'kind' in x`, `instanceof`, or a user-defined type guard
`function isUser(x: unknown): x is User`. The most valuable union is
*discriminated*: every variant has a literal `kind` field, so a `switch`
narrows automatically and an `assertNever(x: never)` in the default branch
makes adding a variant a compile error at every handler - exhaustiveness
enforced by the compiler.

**Generics describe relationships.** `<T>(xs: T[]) => T` says the output is
the element type, not "anything". Constrain with `<T extends { id: string }>`
and prefer inferring from arguments over annotating call sites. `keyof T`,
`T[K]`, `typeof value` and indexed access let you express "the same shape"
without repeating it; `satisfies` lets you keep a literal's narrow type while
still checking it against a wider contract - the correct tool for config
objects where `: Record<string, string>` would have erased the keys.

**Conditional and mapped types are the metaprogramming layer.**
`type Nullable<T> = T | null`, `{ [K in keyof T]?: T[K] }` for partials,
`T extends Promise<infer U> ? U : T` to unwrap, template literal types for
string-shaped APIs, and distributive behaviour over naked type parameters
(`T extends any ? ... : never`). This is how `zod`, `tRPC` and route
libraries produce end-to-end types. Use them in library boundaries, sparingly
in application code: illegible type gymnastics is a maintenance cost that
buys nothing at runtime.

**Static versus dynamic dispatch of types.** Overloads and conditional
return types are compile-time fiction; only one function exists at runtime.
Never rely on a type to change behaviour - `typeof` checks at runtime and
types at compile time must agree, and the compiler cannot verify your `as`.

**Soundness: where the lies are.** `any` disables checking and spreads
through inference; `as` asserts; index signatures (`dict[key]`) always return
the value type even for absent keys; `Object.keys` returns `string[]`, not
`(keyof T)[]`; function parameter bivariance for method syntax makes some
unsafe assignments legal; and `JSON.parse` returns `any`. The practical
discipline: `unknown` at every boundary, validate before casting, enable
`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and ban
`any` in new code with lint rules.

**Cost.** Types are erased, so there is no runtime overhead - but checking
time is real. Very deep conditional types can push a build from seconds to
minutes, and editor hints degrade. `tsc --noEmit` in CI plus `--extendedDiagnostics`
tells you where the time goes; prefer interfaces over huge intersections and
avoid recursive mapped types on large models.

**Common mistakes.** `any` instead of `unknown` for unvalidated input; `!`
non-null assertions on values that can genuinely be missing; `enum` where a
union of string literals would serialise cleanly; typing a variable when you
should type a function's parameters; ignoring `strictNullChecks`; using
`as` to silence an error whose cause is a wrong contract.

**Interview angle.** Given a messy API response, say: define a discriminated
union for the success/error cases, narrow on `kind`, validate at the boundary
with `unknown` and a schema, and let `never` prove exhaustiveness. That
answer demonstrates type-system fluency rather than annotation habit.""",
            """type Result<T> =
  | { kind: 'ok'; value: T }
  | { kind: 'error'; message: string; retryable: boolean };

type User = { id: string; name: string; role: 'admin' | 'member' };

function isUser(value: unknown): value is User {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.id === 'string'
    && typeof candidate.name === 'string'
    && (candidate.role === 'admin' || candidate.role === 'member');
}

function parseUser(raw: unknown): Result<User> {
  if (!isUser(raw)) {
    return { kind: 'error', message: 'payload is not a user', retryable: false };
  }
  return { kind: 'ok', value: raw };
}

function describe(result: Result<User>): string {
  switch (result.kind) {
    case 'ok': return `${result.value.name} (${result.value.role})`;
    case 'error': return `${result.message} [retry=${result.retryable}]`;
    default: {
      const never: never = result;      // adding a variant breaks this line
      return never;
    }
  }
}

function pluck<T, K extends keyof T>(items: T[], key: K): T[K][] {
  return items.map(item => item[key]);  // return type is inferred, not asserted
}

const config = {
  retries: 3,
  baseUrl: 'https://api.example.com',
} satisfies Record<string, string | number>;

console.log(describe(parseUser({ id: 'u1', name: 'Asha', role: 'admin' })));
console.log(describe(parseUser({ id: 7, name: 'Asha', role: 'admin' })));
console.log(pluck([{ id: 'u1', name: 'Asha', role: 'member' } as User], 'name'));
console.log(config.retries + 1);        // narrowed to number by satisfies""",
            """Add a `pending` variant to `Result`, watch every `switch` fail to
compile until it is handled, and remove the `as User` assertion by parsing
the array instead. Then solve the judged problem `evaluate-rpn`, modelling
tokens as a discriminated union of numbers and operators and letting the
compiler enforce that every case is handled.
Practice: /practice/problems/evaluate-rpn""",
        ),
        (
            "ts-runtime-validation-deep",
            "Types vanish at runtime: validating the boundaries",
            "Parse, don't validate: schemas, branded types and errors you can exhaust.",
            """**Why this matters.** Every TypeScript program has a boundary it did
not write: HTTP responses, `localStorage`, environment variables, a file, a
message queue, a form. The compiler cannot see across it, so a `User` type on
a parsed JSON blob is a claim, not a fact. "Parse, don't validate" is the
discipline: convert unknown data into a typed value exactly once, at the
edge, and let the rest of the program trust the type because it was earned.

**`JSON.parse` returns `any`, which is the trap.** `const user: User =
JSON.parse(text)` compiles and may explode later at `user.roles.map`, far
from the cause. `unknown` plus a parser keeps the failure at the boundary
with a message that names the field. The same applies to `fetch`: `await
res.json()` is `any`, `res.ok` must be checked because a 500 also returns
JSON, and network failure is an exception, not a status.

**Schemas, hand-rolled or library.** A schema is a value that parses unknown
into a typed result. Libraries (zod, valibot, io-ts, arktype) give you
composition, coercion, error paths and inference - `z.infer<typeof User>`.
Hand-rolled parsers are fine for a small service and teach what the library
does: check the type of every field, collect every error rather than throwing
on the first, and return a discriminated result so callers handle both cases.

**Branded types for the things TypeScript cannot distinguish.** `string` is
a user id, an email, a database key and a slug simultaneously. A brand -
`type UserId = string & { readonly __brand: 'UserId' }` - plus a constructor
function that parses and returns the brand makes it impossible to pass an
unvalidated string to a function that requires a `UserId`. The brand exists
only in the type system; the value is still a string at runtime.

**Errors as data.** A `Result<T, E>` union beats a thrown exception for
expected failures (404, validation, rate limit): callers cannot forget it, the
compiler checks exhaustiveness, and the error shape is typed. Reserve
exceptions for bugs and unrecoverable conditions. If you keep exceptions,
`catch (error: unknown)` and narrow - `error instanceof Error` is the only
safe assumption.

**Boundary checklists.** For config, parse and fail fast at startup with a
message naming the variable; never default a missing secret to `''`. For
HTTP, validate status, content type, then body. For `localStorage`, treat it
as hostile (it is user-editable and shared with any script on the origin).
For dates, decide once whether the wire format is an ISO string and convert
at the edge; a `Date` type that is actually a string is a bug waiting for a
`getTime()` call.

**Testing the types.** Runtime tests prove the parser rejects bad input;
type-level tests prove the inferred type is what you think.
`expect-type`/`tsd` or a `// @ts-expect-error` comment (which fails the
build if the error disappears) are the idiom. A schema without a rejection
test is a claim without evidence.

**Common mistakes.** Double validation (validating in the controller and
again deep in the domain, with different rules); coercing with `Number(x)`
and getting `NaN` into the model; `as unknown as T` as the parser; accepting
`any` from a third-party SDK and letting it poison inference; validating the
happy path only; throwing strings instead of `Error` objects so stack traces
vanish.

**Interview angle.** "Types are erased; I validate with a schema at the
boundary, parse into a branded domain type, and return a discriminated
result, so downstream code needs no defensive checks." Then show the
rejection test. That is the difference between using TypeScript and relying
on it.""",
            """type ParseResult<T> =
  | { ok: true; value: T }
  | { ok: false; errors: string[] };

type Config = {
  baseUrl: string;
  retries: number;
  dryRun: boolean;
};

function parseConfig(raw: unknown): ParseResult<Config> {
  const errors: string[] = [];
  if (typeof raw !== 'object' || raw === null) {
    return { ok: false, errors: ['config must be an object'] };
  }
  const input = raw as Record<string, unknown>;

  const baseUrl = input.baseUrl;
  if (typeof baseUrl !== 'string' || !/^https?:\\/\\//.test(baseUrl)) {
    errors.push('baseUrl must be an http(s) URL');
  }
  const retries = Number(input.retries);
  if (!Number.isInteger(retries) || retries < 0 || retries > 10) {
    errors.push('retries must be an integer between 0 and 10');
  }
  if (typeof input.dryRun !== 'boolean') {
    errors.push('dryRun must be a boolean');
  }
  if (errors.length > 0) return { ok: false, errors };

  return {
    ok: true,
    value: { baseUrl: baseUrl as string, retries, dryRun: input.dryRun as boolean },
  };
}

// Branded type: a plain string cannot be passed where an Email is required.
type Email = string & { readonly __brand: 'Email' };

function parseEmail(text: string): Email | null {
  return /^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(text) ? (text as Email) : null;
}

function sendReport(to: Email): string {
  return `queued for ${to}`;
}

const good = parseConfig({ baseUrl: 'https://api.example.com', retries: '3', dryRun: false });
console.log(good);
const bad = parseConfig({ baseUrl: 'ftp://nope', retries: 99 });
console.log(bad);          // both errors reported, not just the first

const email = parseEmail('asha@example.com');
console.log(email === null ? 'invalid' : sendReport(email));""",
            """Return `errors` for the `localStorage` round trip as well: serialise a
valid config, read it back, and show that a tampered field is rejected rather
than trusted. Then write a `// @ts-expect-error` case proving a plain string
cannot be passed as an `Email`. Finally solve the judged problem
`validate-ipv4`, whose edge cases (leading zeros, empty octets, out-of-range
values) are exactly the ones a boundary validator must enumerate.
Practice: /practice/problems/validate-ipv4""",
        ),
    ],
    "c": [
        (
            "c-undefined-behaviour-deep",
            "Undefined behaviour: what the C standard lets the compiler do",
            "Object lifetime, aliasing, overflow and the sanitizers that catch them before production.",
            """**Why this matters.** C is the language where "it worked on my machine"
is a documented possibility: the standard defines behaviour for correct
programs and leaves everything else *undefined*, which permits an optimiser
to delete your null check, your loop, or your error handling. Almost every
remote-code-execution bug in embedded and systems C is a chain that starts
with one undefined operation. Learning where the edges are is the single
highest-value C skill after pointers.

**Four categories, not one.**

- *Defined* behaviour: the standard says exactly what happens.
- *Implementation-defined*: the implementation chooses and documents it -
  the size of `int`, whether `char` is signed, right-shifting a negative
  value.
- *Unspecified*: the implementation picks any valid option, without
  documentation - which of two `f()` calls in `f() + g()` runs first.
- *Undefined*: the standard imposes **no requirements at all**. Not "it
  wraps", not "it crashes": anything, including a program that appears to
  work until you enable optimisation or change the compiler version.

**The catalogue worth memorising.** Signed integer overflow
(`INT_MAX + 1`) - use unsigned types when wrap-around is intended, and be
aware that `INT_MIN / -1` and `INT_MIN % -1` overflow too. Reading an
uninitialised variable. Dereferencing a pointer after `free`, or twice.
Out-of-bounds access - including the *one past the end* rule: `p + n` is
legal for a pointer into an array of `n` elements, dereferencing it is not.
Shifting by a negative or by >= the width of the type. Modifying a string
literal (`char *s = "abc"; s[0] = 'x';`). Calling a variadic function with
the wrong type (`printf("%d", 3.0)`). Data races: two threads touching the
same non-atomic object, one writing, with no synchronisation.

**Object lifetime and effective type.** An object's lifetime begins when
storage is obtained (declaration, `malloc`) and, for an allocated block,
ends at `free`. After that, every access is undefined even if the bytes look
intact - which is why a use-after-free often "works" in a debug build and
fails in production. Aliasing is a separate rule: you may not access the same
memory as a type unrelated to the object's effective type. `memcpy` is the
defined way to reinterpret bytes; a `union` pun is implementation-defined
(many compilers accept it, C++ generally does not). `-fstrict-aliasing` is
what makes this rule matter: the optimiser assumes your `float *` and your
`int *` never point at the same object.

**Why optimisation "breaks" your code.** An infinite loop with no side
effects may be removed. A null check after a dereference of the same pointer
is dead code, because dereferencing null was already undefined, so the
compiler may assume it cannot happen. A signed overflow check
`if (a + b < a)` may be folded away. Each of these is the compiler correctly
exploiting your undefined behaviour. The fix is never a compiler flag - it is
removing the UB, then adding the flags that *find* it.

**Make the machine catch it.** Build with `-Wall -Wextra -Werror
-fsanitize=address,undefined -g -O1` during development: ASan catches
out-of-bounds, use-after-free and double-free; UBSan reports overflow,
misaligned access and bad shifts at the exact line. `-fanalyzer` and
`valgrind --track-origins=yes` cover paths the tests missed. Compile the same
code with `clang` and `gcc` at `-O0` and `-O2`: UB frequently shows up as a
disagreement between builds.

**Writing defined code on purpose.** Use `size_t` for sizes and indices,
check every allocation, `calloc` when zeroed memory is assumed, and
`snprintf` instead of `sprintf`. Prefer `memcpy` for type punning, `atomic_*`
or a mutex for shared state, and explicit range checks before arithmetic that
can exceed the type. Where wrap is intended, cast once to the unsigned type
and back - and comment that it is deliberate.

**Common mistakes.** Assuming pointers are integers (they are not; converting
is implementation-defined); assuming `sizeof(int) == 4` in portable code;
comparing signed and unsigned in a loop bound (`for (int i = 0; i < n; i++)`
with `size_t n`); freeing a pointer then using it in a log line; forgetting
that `strlen(NULL)` is UB, not 0.

**Interview angle.** "Undefined behaviour is not a crash mode, it is a licence
for the compiler to assume it never happens." Then name the sanitizer you
would use and the one rule you check first (bounds). That answer shows you
have debugged real C.""",
            """#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Compiled with -fsanitize=address,undefined, this program stays clean. */

static int sum_unsigned_wrap(uint32_t a, uint32_t b) {
    return (int)(a + b);              /* defined: unsigned arithmetic wraps */
}

static int safe_add(int a, int b, int *out) {
    if ((b > 0 && a > INT_MAX - b) || (b < 0 && a < INT_MIN - b)) {
        return 0;                     /* never let signed overflow happen */
    }
    *out = a + b;
    return 1;
}

int main(int argc, char **argv) {
    uint32_t big = UINT32_MAX;
    printf("unsigned wrap is defined: %d\\n", sum_unsigned_wrap(big, 1u));

    int total = 0;
    if (!safe_add(INT_MAX, 1, &total)) {
        printf("refused: %d + 1 would overflow INT_MAX\\n", INT_MAX);
    }

    char buffer[8];
    const char *source = argc > 1 ? argv[1] : "truncated-text";
    int written = snprintf(buffer, sizeof buffer, "%s", source);
    printf("snprintf wanted %d chars, buffer holds '%s'\\n", written, buffer);

    /* memcpy is the defined way to reinterpret bytes; union punning is not. */
    float value = 1.0f;
    uint32_t bits;
    memcpy(&bits, &value, sizeof bits);
    printf("1.0f has bit pattern 0x%08x\\n", bits);

    size_t n = 4;
    for (size_t i = 0; i < n; i++) {  /* size_t index: no signed/unsigned mix */
        printf("%zu ", i);
    }
    printf("\\n");
    return 0;
}""",
            """Compile the example with `-fsanitize=address,undefined -g -O1`, then
deliberately introduce three bugs - an out-of-bounds write, a use-after-free
and a signed overflow - and read what each sanitizer reports. Fix them and
explain why `-O0` sometimes hides the third. Finally solve the judged problem
`count-set-bits`, where the choice of signed or unsigned type decides whether
a right shift is defined.
Practice: /practice/problems/count-set-bits""",
        ),
        (
            "c-build-debug-deep",
            "From source to binary: compiling, linking and debugging C",
            "Translation units, symbols, static and shared libraries, make and a real debugger workflow.",
            """**Why this matters.** Most C confusion that is not undefined behaviour
is a build confusion: an undefined reference, a header included twice, a
program that links against a stale object file, or a bug that only appears in
the release build. Knowing the four stages - preprocessing, compiling,
assembling, linking - turns those errors from mysterious into mechanical.

**Four stages, four artefacts.** The preprocessor handles `#include`,
`#define` and conditionals textually, expanding into one *translation unit*
per `.c` file. The compiler turns that unit into assembly, the assembler into
an object file with a symbol table, and the linker resolves symbols across
objects into an executable. `gcc -E` shows you the preprocessed soup, `-S`
the assembly, `-c` stops at the object, and no flag at all performs the link.
Reading `gcc -E` output once explains a whole class of macro bugs.

**Declaration versus definition, and linkage.** A header *declares* (`int
add(int, int);`), a `.c` file *defines*. `extern` on a variable in a header
says "defined elsewhere"; putting `int counter = 0;` in a header and
including it twice gives duplicate symbols at link time. `static` at file
scope gives *internal* linkage - the name is invisible outside the
translation unit, which is how you get encapsulation in C. `static` inside a
function means a persistent object, a completely different thing with the
same keyword. Include guards (`#ifndef X_H`) or `#pragma once` stop
double-inclusion within one unit; they do not fix duplicate definitions
across units.

**Symbols and linking.** `nm` lists symbols: `T` defined text, `U`
undefined, `D` data, `t` local/static. An `undefined reference` means a
declaration was seen but no object provided the definition - the usual causes
being a missing `.c` in the build, a library listed in the wrong order
(linkers resolve left to right: the library must come *after* the object that
needs it), or a C++ name-mangled symbol being called from C (fix with
`extern "C"`). Static libraries (`.a`) are archives copied into your binary at
link time; shared libraries (`.so`) are resolved at load time - which is why
a machine can run your program with a different version of a shared library
than you built against, and why `ldd` and `rpath` matter for deployment.

**Build systems.** `make` is a dependency graph: a target, its prerequisites,
and a recipe, with timestamps deciding what is out of date. Two rules make a
Makefile trustworthy: every rule has all its real prerequisites (header
dependencies generated with `-MMD -MP`), and `.PHONY` marks the targets that
are not files. For anything larger, CMake generates the build so users can
build with make, ninja or an IDE; keep the compile flags per target
(`target_compile_options`) rather than in global variables.

**The flags that earn their place.** `-Wall -Wextra -Wpedantic -Werror` for
mistakes; `-g` for debug info; `-O2` for release; `-std=c17` (or the version
you actually target) so behaviour does not depend on a default; `-fPIC` for
shared libraries; and sanitizers for development builds. Separate debug and
release build directories - mixing objects compiled with different flags is
the "stale object" bug, and `make clean` exists for a reason.

**Debugging like a professional.** Build with `-g -O0` (or `-Og`), then
`gdb ./prog`: `run`, `break file.c:42`, `break func if x > 10`, `next` versus
`step`, `bt` for the stack, `frame 2` and `print` to inspect, `watch counter`
to stop when a value changes, `x/8wx ptr` to dump memory,
`set var i = 0`, `continue`. When it crashes: reproduce under gdb, `bt full`,
then inspect the arguments at the crashing frame - and remember the crash site
is often not the bug site. For memory bugs, ASan first (fast, precise),
valgrind when you need uninitialised-value origins or you cannot rebuild.
Enable core dumps (`ulimit -c unlimited`) for intermittent crashes, and
record the exact binary and flags, because a backtrace is only useful against
the build that produced it.

**Common mistakes.** Debugging a release build and chasing an optimised-away
variable; `printf` debugging left in a hot path; rebuilding only one object
after a header change; ignoring warnings until `-Werror` arrives in CI;
assuming a crash in `free()` means `free()` is at fault (it is usually an
earlier overflow); testing only with `-O0`.

**Interview angle.** Describe the pipeline, then a debugging method that
starts from evidence: reproduce, get a backtrace, inspect the frame, form one
hypothesis, test it. "I would add a print" is the junior answer; "I would
read the core dump" is the one that gets the offer.""",
            """#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LOG(fmt, ...) fprintf(stderr, "[%s:%d] " fmt "\\n", __FILE__, __LINE__, __VA_ARGS__)

typedef struct {
    size_t len;
    char *data;
} Buffer;

static int buffer_init(Buffer *b, size_t len) {
    b->data = malloc(len + 1);
    if (b->data == NULL) return 0;
    b->len = len;
    b->data[0] = '\\0';
    return 1;
}

static void buffer_set(Buffer *b, const char *text) {
    size_t n = strlen(text);
    if (n > b->len) n = b->len;              /* bounds check before copying */
    memcpy(b->data, text, n);
    b->data[n] = '\\0';
}

int main(void) {
    Buffer b;
    if (!buffer_init(&b, 16)) {              /* allocation is always checked */
        LOG("%s", "allocation failed");
        return 1;
    }
    buffer_set(&b, "meridian-build-systems");
    printf("buffer: %s (%zu bytes reserved)\\n", b.data, b.len);
    free(b.data);
    b.data = NULL;                           /* dangling pointer defused */
    LOG("freed %s", "buffer");
    return 0;
}""",
            """Split this program into `buffer.h`, `buffer.c` and `main.c`, write a
Makefile with automatic header dependencies (`-MMD -MP`), and compile a
static library from it. Then compile with `-O0` and `-O2` and diff the
assembly for one small function (`objdump -d`). Finally debug an
out-of-bounds write under gdb with a `watch` on the corrupted variable, and
solve the judged problem `base64-encode`, checking your buffer arithmetic
with ASan before you trust it.
Practice: /practice/problems/base64-encode""",
        ),
    ],
    "cpp": [
        (
            "cpp-raii-move-deep",
            "RAII, value categories and move semantics",
            "Ownership by construction, rule of zero, and what std::move really does.",
            """**Why this matters.** C++ has no garbage collector and no runtime
that owns your resources; it has destructors, and the whole language is built
around the guarantee that a destructor runs when an object goes out of scope.
Programs that embrace that - every resource owned by an object whose
destructor releases it - are safer than garbage-collected programs, because
release is deterministic. Programs that do not are the reason C++ has a
reputation.

**RAII in one sentence.** Tie every resource (memory, file, socket, lock) to
an object's lifetime: acquire in the constructor, release in the destructor,
and let scope do the rest. `std::unique_ptr`, `std::vector`, `std::string`,
`std::lock_guard` and `std::fstream` are all RAII. This is why
`std::lock_guard` cannot deadlock on an exception and `delete` at the end of a
function is usually a design smell.

**Rule of zero, five, three.** If your class owns nothing directly - it holds
`vector`, `string`, `unique_ptr` - write no destructor, no copy, no move and
the compiler generates correct ones ("rule of zero"). If it owns a raw
resource, you need the destructor, copy constructor, copy assignment, move
constructor and move assignment ("rule of five"), or you must delete copying
and keep only moves. A hand-written destructor with defaulted copies is the
bug: two objects free the same pointer. The pre-C++11 name for this was the
rule of three; the fifth member exists because moves now transfer ownership.

**Value categories, plainly.** An *lvalue* is a named object with an address
you could take. An *rvalue* is a temporary or an expiring value. A
constructor taking `const T&` binds both and copies. A constructor taking
`T&&` binds only rvalues and can *steal* the internals, which is a move. The
important consequence: overload resolution prefers the `&&` overload for
temporaries, so returning a local `std::vector` costs a pointer swap, or
nothing at all thanks to copy elision (guaranteed for returning a local in
C++17).

**`std::move` is a cast, not a move.** It produces an rvalue reference - it
promises "I will not use this object again", which lets a move constructor be
selected. It performs no work by itself. `std::move(x);` on a line does
nothing but confuse the reader. And a `const` object cannot be moved from,
because moving requires mutation: `const std::string s; auto t =
std::move(s);` copies. A moved-from object is valid but unspecified: you may
destroy it or assign to it, not read its contents.

**`noexcept` matters for containers.** `std::vector` reallocation must give
the strong exception guarantee; it moves elements only if the move
constructor is `noexcept`, otherwise it copies to stay safe. A move
constructor that can throw quietly turns your fast vector of
move-only-friendly objects back into a copying one. Mark moves (and swap)
`noexcept` unless they genuinely throw.

**Pointers as ownership signals.** `std::unique_ptr<T>` means exclusive
ownership, is the same size as a raw pointer, and is the default for
heap objects. `std::shared_ptr<T>` is shared ownership with a control block
and an atomic reference count: use it only when lifetime genuinely has
multiple owners, and never form two shared_ptrs from one raw pointer (double
delete) or create cycles - use `weak_ptr` to break them.
`std::shared_ptr` copies are not free and are not a substitute for thinking
about ownership. A raw pointer or reference means "I do not own this, and it
outlives my use of it".

**Dangling is the enemy.** `std::string_view` and `std::span` do not own
their data: a view of a temporary or of a `vector` element after push_back
can dangle. A lambda capturing by reference outliving the scope is the same
bug in a different costume. When in doubt, own the data (`std::string`), or
prove the lifetime with a scope you can point at.

**Common mistakes.** `delete this`-style manual lifetimes; a destructor that
throws (terminates the process); relying on member initialisation order
(members are initialised in declaration order, not initialiser-list order);
`std::move` on a `const` object; returning `std::move(local)` (pessimises
NRVO); using `shared_ptr` everywhere "to be safe"; slicing an object by
storing a derived class by value in a base-class container.

**Interview angle.** Explain ownership as a design decision, name the
default (`unique_ptr`, values), and describe when a move happens and when it
is elided. Then say what rule of zero buys: correctness by construction, so
the reviewer has nothing to check.""",
            """#include <algorithm>
#include <cstddef>
#include <iostream>
#include <memory>
#include <utility>
#include <vector>

class Buffer {
public:
    explicit Buffer(std::size_t n) : size_(n), data_(new int[n]()) {
        std::cout << "acquire " << size_ << "\\n";
    }
    ~Buffer() { std::cout << "release " << size_ << "\\n"; }

    Buffer(const Buffer &other) : size_(other.size_), data_(new int[other.size_]) {
        std::copy(other.data_.get(), other.data_.get() + size_, data_.get());
    }
    Buffer &operator=(const Buffer &other) {   // copy-and-swap: strong guarantee
        Buffer tmp(other);
        swap(tmp);
        return *this;
    }
    Buffer(Buffer &&other) noexcept                 // steal, do not copy
        : size_(std::exchange(other.size_, 0)), data_(std::move(other.data_)) {}
    Buffer &operator=(Buffer &&other) noexcept {
        Buffer tmp(std::move(other));
        swap(tmp);
        return *this;
    }

    void swap(Buffer &other) noexcept {
        std::swap(size_, other.size_);
        data_.swap(other.data_);
    }
    std::size_t size() const noexcept { return size_; }
    int &operator[](std::size_t i) { return data_[i]; }

private:
    std::size_t size_;
    std::unique_ptr<int[]> data_;   // RAII: no delete anywhere
};

int main() {
    Buffer a(4);
    a[0] = 7;
    Buffer b = a;                    // deep copy
    Buffer c = std::move(a);         // move: a is now empty but valid
    std::cout << "a.size=" << a.size() << " c.size=" << c.size() << " b[0]=" << b[0] << "\\n";

    std::vector<Buffer> buffers;
    buffers.reserve(4);              // capacity first: no reallocation copies
    buffers.emplace_back(2);
    buffers.emplace_back(3);

    std::vector<std::unique_ptr<Buffer>> owned;
    owned.push_back(std::make_unique<Buffer>(8));
    std::cout << "owned size=" << owned.size() << " inner=" << owned[0]->size() << "\\n";
    return 0;                        // destructors run in reverse order of construction
}""",
            """Delete the copy operations from `Buffer` and make the vector of
`Buffer` move-only; explain why `push_back` still compiles and what changes
if the move constructor is not `noexcept`. Then add a `std::string_view`
accessor, deliberately create a dangling view of a temporary, and observe it
under `-fsanitize=address`. Finally solve the judged problem
`matrix-transpose`, allocating the destination once and moving rows into it.
Practice: /practice/problems/matrix-transpose""",
        ),
        (
            "cpp-templates-concepts-deep",
            "Templates, concepts and the cost of compile-time code",
            "Instantiation, specialisation, SFINAE to concepts, and when to prefer a virtual call.",
            """**Why this matters.** Templates are how the C++ standard library
achieves zero-overhead genericity and how application code gets unreadable
compiler errors. Both facts come from the same mechanism: the compiler
generates a fresh function or class for every distinct set of template
arguments, then checks it. Understanding instantiation explains the error
messages, the binary size, the compile times and the design choices.

**Instantiation is code generation.** A template is a pattern, not code;
nothing exists until it is used with concrete arguments. Each use creates a
specialisation (implicit); you can also write explicit specialisations for
particular types. This is *monomorphisation*: `max<int>` and `max<double>` are
two separate functions, each inlinable, with no runtime dispatch - the reason
generic code in C++ can be as fast as hand-written code. The cost is compile
time and binary size: a heavy template used across ten types is ten
instantiations, and error messages must be reported against the whole chain.

**Deduction and dependent names.** The compiler deduces `T` from arguments,
preferring exact matches and decaying arrays to pointers. Inside a template,
a name that depends on `T` needs `typename` (`typename T::value_type`) and
`template` disambiguation (`x.template get<0>()`) because the parser cannot
know whether `T::x` is a type or a value. This is not obscurantism; it is
what a language without a separate compilation model requires.

**Specialisation and traits.** A primary template plus partial and full
specialisations let you branch on types at compile time:
`std::is_integral<T>`, `std::void_t` detection, `if constexpr` to discard the
other branch entirely (unlike a runtime `if`, the discarded branch need not
even compile for that type). `constexpr` moves computation to compile time;
`consteval` (C++20) forbids runtime evaluation. Together these are how
serialisation libraries, `std::tuple` and reflection emulations are built.

**From SFINAE to concepts.** Before C++20, generic constraints were written
with `std::enable_if` and "substitution failure is not an error": a template
that fails to substitute is silently removed from overload resolution. It
works, it is unreadable, and errors surface as "no matching function" with a
wall of candidates. Concepts name the requirement:
`template <std::integral T> T twice(T v)`. `requires` clauses state
semantic requirements, `requires { t.size(); }` checks syntactic ones, and
the compiler can say "T does not satisfy integral" instead of failing 200
lines deep. Use concepts for every public template in new code - they are
documentation that is checked.

**Compile-time cost is a real cost.** Every instantiation is compiled;
`<algorithm>` pulls in more than you think; `std::function` and
`std::shared_ptr` erase types and have their own overhead; and a deep
template metaprogram can dominate CI. Measure with `-ftime-report` or
`-ftime-trace` (Clang). Mitigations: prefer concepts to SFINAE, move
implementation out of headers only when you can enumerate the instantiations
(explicit instantiation), and cut include weight with forward declarations
and, in C++20, modules.

**Runtime cost: static versus dynamic dispatch.** Template genericity is
free at runtime but pays in code size and compile time, and it requires the
type at compile time. Virtual functions pay a vtable indirection per call but
allow runtime polymorphism and smaller binaries. The standard advice: default
to templates/concepts for value semantics and performance-sensitive code;
use virtual (or `std::function`/`std::variant`) when the type is genuinely
only known at runtime. Avoid virtual in tight loops without measuring, and
avoid templating a huge function over many types without checking binary
size.

**Common mistakes.** Defining a template in a `.cpp` and expecting other
translation units to link; relying on implicit conversions in deduction
(`max(1, 2.5)` is ambiguous - cast, or take two parameters); recursive
template errors taken as compiler bugs; `std::enable_if` in new code;
over-constraining a concept so legitimate types are rejected; using a macro
where a `constexpr` function would do.

**Interview angle.** Explain that templates are instantiated per type, so
there is no runtime dispatch and the cost moves to compile time. Then
contrast with virtual dispatch and say how you choose. That framing - cost
moves, it does not vanish - is what "zero overhead" actually means.""",
            """#include <concepts>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

template <typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

template <Numeric T>
T twice(T value) { return value + value; }

template <typename T>
concept Sized = requires(const T &container) {
    { container.size() } -> std::convertible_to<std::size_t>;
};

template <Sized T>
void report(const T &container) {
    std::cout << "container with " << container.size() << " elements\\n";
}

template <typename... Args>          // variadic + fold expression
auto sum_all(Args... args) {
    return (args + ... + 0);
}

template <typename T>
struct TypeName { static constexpr const char *value = "unknown"; };
template <> struct TypeName<int> { static constexpr const char *value = "int"; };
template <> struct TypeName<double> { static constexpr const char *value = "double"; };

int main() {
    std::cout << twice(21) << " " << twice(1.5) << "\\n";   // two instantiations
    // twice(std::string("a"));   // rejected by the concept, with a clear message
    report(std::vector<int>{1, 2, 3});
    report(std::string("meridian"));
    std::cout << "fold sum: " << sum_all(1, 2, 3, 4) << "\\n";
    std::cout << "types: " << TypeName<int>::value << ", " << TypeName<double>::value
              << ", " << TypeName<char>::value << "\\n";

    static_assert(Numeric<long>);
    static_assert(!Numeric<std::string>);
    if constexpr (Numeric<int>) {          // discarded branch is not compiled
        std::cout << "if constexpr chose the numeric branch\\n";
    }
    return 0;
}""",
            """Add a `Container<T>` concept requiring `begin`, `end` and `value_type`,
and constrain `report` with it so a type without iterators is rejected with
your message. Then instantiate `twice` with a user-defined number type and
compare the binary size of a template version and a virtual-dispatch version
of the same operation. Finally solve the judged problem `serialize-tree`
generically, so it works over any node type exposing `left`, `right` and
`value`.
Practice: /practice/problems/serialize-tree""",
        ),
    ],
    "rust": [
        (
            "rust-borrowing-lifetimes-deep",
            "Ownership, borrowing and lifetimes in practice",
            "Move, borrow, share - and how to restructure code the borrow checker rejects.",
            """**Why this matters.** Rust's borrow checker is not a syntax tax; it is
a proof obligation. Every program it accepts has no use-after-free, no
double-free and no data race in safe code. That guarantee is worth real
money, and the price is learning to think about ownership as a design
property rather than a runtime detail. Once you can read a borrow-checker
error and know which of four restructurings applies, Rust stops fighting you.

**The three rules.** Each value has exactly one owner. There can be any
number of immutable borrows *or* exactly one mutable borrow, never both at the
same time. A borrow cannot outlive its owner. Everything else - move
semantics, `Clone`, lifetimes, `Rc`, `RefCell` - is a consequence or an
escape hatch.

**Move means move.** Assigning or passing a non-`Copy` value transfers
ownership; the old binding becomes unusable, and the compiler says so at
compile time rather than leaving a dangling pointer. `Copy` types (integers,
bools, `char`, references, small tuples of those) are bit-copied instead.
`Clone` is an explicit, potentially expensive copy - the difference between
`*x` and `x.clone()` should be a deliberate choice, and `.clone()` in a hot
loop is a performance decision, not a fix.

**Borrowing and non-lexical lifetimes.** A reference does not copy;
`&T` is shared, `&mut T` is exclusive. Modern borrow checking ends a borrow
at its last use, so this compiles:

```rust
let mut v = vec![1, 2, 3];
let first = &v[0];
println!("{first}");   // last use of the borrow here
v.push(4);             // fine now
```

But holding a reference across a mutation does not - the safety rule is the
same one that stops a `Vec` reallocation from dangling your pointer.

**Lifetimes are relationships, not durations.** `fn longest<'a>(x: &'a str,
y: &'a str) -> &'a str` says the returned reference lives at most as long as
both inputs; it does not say "as long as the program". Most lifetimes are
elided by three rules (each input reference gets its own parameter; with
`&self`, the output takes `self`'s lifetime). Write explicit lifetimes only
when the compiler asks, and put them in structs that hold references - which
is often the moment you discover the struct should own its data with
`String` instead. `'static` means "lives for the whole program or is a
literal"; a `&'static str` is not a leak, it is usually a compile-time
constant.

**Interior mutability: the escape hatch with a receipt.** `Cell<T>` and
`RefCell<T>` move the borrow check to runtime, for the cases where the
structure of the code cannot express the aliasing statically (a graph, a
cache, an observer list). `RefCell` panics on a second simultaneous mutable
borrow - that is a design bug surfacing at runtime, not a licence to stop
thinking. `Rc<T>` shares ownership in one thread (non-atomic count);
`Arc<T>` in many. `Rc<RefCell<T>>` is the classic graph shape; know its costs
(reference cycles leak - use `Weak` for back-edges) and prefer arena/index
designs in performance-sensitive code.

**The four restructurings when the checker objects.**

1. *Own it*: store the data (`String` rather than `&str`), clone deliberately
   at a boundary, and the lifetime problem disappears.
2. *Borrow for less time*: move the borrow into a narrower scope; return a
   computed value (an index, a copy) instead of a reference.
3. *Split the borrow*: take two disjoint `&mut` fields at once, or use
   `split_at_mut` on a slice, instead of passing `&mut self` into a helper.
4. *Change the data structure*: indices or arenas instead of reference
   cycles; `RefCell`/`Mutex` when the aliasing is genuinely dynamic.

**Send, Sync and threads.** `Send` means a value can move to another thread;
`Sync` means `&T` can be shared. Most types are both; `Rc` and `RefCell` are
neither, which is why sharing across threads requires `Arc<Mutex<T>>`. The
compiler enforces this, so a data race in safe Rust is a compile error rather
than a production incident.

**Common mistakes.** Cloning until the errors stop (you have hidden the
design problem); returning `&self.field` from a method that also mutates on
the next line; holding a `RefCell` borrow across a call that borrows again;
fighting `'static` when the real fix is owning the data; using `unsafe` to
silence the checker instead of understanding it; assuming `Arc<Mutex<T>>` is
free (it is a lock and an atomic count per operation).

**Interview angle.** Read a borrow error out loud and name the rule it
violates, then say which restructuring you would apply and why. That is the
skill; reciting "Rust has ownership" is not.""",
            """use std::cell::RefCell;
use std::rc::Rc;

#[derive(Debug)]
struct Node {
    value: i32,
    children: RefCell<Vec<Rc<Node>>>,
}

fn sum_tree(node: &Rc<Node>) -> i32 {
    let children = node.children.borrow();      // shared borrow, dropped before recursion
    node.value + children.iter().map(sum_tree).sum::<i32>()
}

fn longest<'a>(left: &'a str, right: &'a str) -> &'a str {
    if left.len() >= right.len() { left } else { right }
}

fn split_pair(values: &mut [i32]) -> (&mut [i32], &mut [i32]) {
    let mid = values.len() / 2;
    values.split_at_mut(mid)                    // two disjoint mutable borrows
}

fn main() {
    let leaf = Rc::new(Node { value: 2, children: RefCell::new(vec![]) });
    let branch = Rc::new(Node {
        value: 5,
        children: RefCell::new(vec![Rc::clone(&leaf), Rc::clone(&leaf)]),
    });
    println!("tree sum: {}", sum_tree(&branch));
    println!("strong count: {}", Rc::strong_count(&leaf));

    let owned = String::from("a long owned string");
    let borrowed = longest(owned.as_str(), "short");
    println!("longest: {borrowed}");

    let mut values = [1, 2, 3, 4, 5, 6];
    {
        let (left, right) = split_pair(&mut values);
        left[0] = 10;
        right[0] = 40;
    }
    println!("after split borrow: {:?}", values);
}""",
            """Convert `Node` to store children as `Vec<usize>` indices into an arena
and explain what stops being necessary (what can you remove - `Rc`, `RefCell`,
or both?). Then add a `Weak` back-pointer and show that the strong count no
longer grows. Finally solve the judged problem `reverse-linked-list` twice:
once with owned nodes and once with an array arena, and explain which version
the borrow checker accepts without any interior mutability.
Practice: /practice/problems/reverse-linked-list""",
        ),
        (
            "rust-traits-generics-deep",
            "Traits, generics and dyn dispatch",
            "Static versus dynamic polymorphism, object safety and errors that compose.",
            """**Why this matters.** Rust gives you two kinds of polymorphism with
different costs, and choosing between them is a design decision that shows up
in binary size, dispatch speed and API usability. It also gives you a trait
system strict enough that library authors cannot add a breaking impl later -
worth understanding before you design your own abstractions.

**Traits are contracts.** A trait declares methods; an `impl` fulfils them;
default method bodies let a type opt out of boilerplate. Unlike inheritance,
a type implements many traits independently, and traits can be implemented
for types you did not write (with the coherence rules below). Traits are how
Rust does operator overloading (`Add`), conversion (`From`/`Into`), iteration
(`Iterator`), formatting (`Display`) and error handling (`Error`). If you find
yourself writing a `match` on a type tag, a trait is often the better shape.

**Generics are compile-time code generation.** `fn largest<T: PartialOrd>(xs:
&[T]) -> &T` is monomorphised: one copy per concrete `T`, fully inlinable,
zero dispatch cost. That is the default choice for performance and for
libraries where the caller's type is known. The costs: binary bloat if the
same generic function is used with many types, and compile-time growth.

**Trait objects are runtime dispatch.** `Box<dyn Shape>` or `&dyn Shape`
stores a pointer plus a vtable pointer, so the call site looks up the method
at runtime. This is the right choice when the set of types is open - a plugin
list, a heterogeneous collection, a `Vec<Box<dyn Error>>` - or when you want
to stop monomorphising a large function. `dyn` requires object safety: no
generic methods, no `Self`-returning methods without `where Self: Sized`, and
fixed-size returns. When a trait fails object safety, the compiler tells you
which method is responsible - that is a design signal, not an obstacle.

**Associated types versus generic parameters.** `trait Iterator { type Item;
}` uses an associated type because each iterator produces exactly one item
type, which keeps signatures readable (`impl Iterator<Item = u8>`). A trait
like `From<T>` uses a generic parameter because one type can convert from many
sources. The rule of thumb: if there is exactly one sensible implementation
per type, use an associated type.

**`impl Trait` in two directions.** As an argument (`fn f(x: impl Display)`)
it is sugar for a generic parameter; as a return type it means "some concrete
type implementing this trait, decided by me" - which is how you return
closures and iterator chains without naming their unnameable types. It is not
`dyn`: the type is fixed at compile time and dispatch is static.

**Coherence and the orphan rule.** You may implement a trait if either the
trait or the type is local. This prevents two crates from providing
conflicting impls, and it means you cannot implement `Display` for
`Vec<u8>`. The workaround is a newtype wrapper (`struct Meters(f64);`) which
costs nothing at runtime and makes the domain meaning explicit. Blanket impls
(`impl<T: Display> MyTrait for T`) are powerful and should be rare: they
consume the coherence space for everyone downstream.

**Errors that compose.** Return `Result<T, E>`; use `?` for propagation, which
converts via `From`. For applications, `Box<dyn Error + Send + Sync>` or a
library like `anyhow` is pragmatic; for libraries, define a concrete enum
error with `#[derive(Debug)]` and `impl std::error::Error`, so callers can
match on variants without depending on your internals. Avoid `unwrap()` in
library code; `expect("invariant documented")` is acceptable where the
invariant is genuinely guaranteed and stated. Panics are for bugs, `Result`
is for expected failure - a distinction the type system helps you keep.

**`unsafe` is a boundary, not a mode.** Safe Rust guarantees memory safety
because unsafe blocks carry an obligation the compiler cannot check. If you
write one, document the invariant, keep the block as small as possible, wrap
it in a safe API that cannot be misused, and test it including with Miri
where possible. Needing `unsafe` to work around a borrow error usually means
the design is wrong.

**Common mistakes.** `Box<dyn Trait>` in a hot loop where a generic would
have been free; a trait with one implementer and no dynamic use (an enum
would be simpler); `impl Trait` in return position where the caller needs to
name the type in a struct field (use `dyn` or a concrete type); forgetting
`Send + Sync` bounds on a trait object shared across threads; implementing
`Deref` to imitate inheritance.

**Interview angle.** Contrast monomorphisation with vtables, state one case
where each is right, and explain object safety. Then show an error enum
converted with `?`. That is idiomatic Rust design, not syntax recall.""",
            """use std::error::Error;
use std::fmt;

#[derive(Debug)]
enum ShapeError {
    NonPositive(&'static str),
}

impl fmt::Display for ShapeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ShapeError::NonPositive(what) => write!(f, "{what} must be positive"),
        }
    }
}

impl Error for ShapeError {}

trait Shape {
    fn area(&self) -> f64;
    fn name(&self) -> &'static str;
    fn describe(&self) -> String {                 // default method
        format!("{} with area {:.2}", self.name(), self.area())
    }
}

struct Circle { radius: f64 }
struct Rectangle { width: f64, height: f64 }

impl Shape for Circle {
    fn area(&self) -> f64 { std::f64::consts::PI * self.radius * self.radius }
    fn name(&self) -> &'static str { "circle" }
}

impl Shape for Rectangle {
    fn area(&self) -> f64 { self.width * self.height }
    fn name(&self) -> &'static str { "rectangle" }
}

impl Circle {
    fn new(radius: f64) -> Result<Self, ShapeError> {
        if radius <= 0.0 { return Err(ShapeError::NonPositive("radius")); }
        Ok(Self { radius })
    }
}

fn total_area<T: Shape>(shapes: &[T]) -> f64 {     // static dispatch
    shapes.iter().map(Shape::area).sum()
}

fn main() {
    let circles = [Circle::new(1.0).unwrap(), Circle::new(2.0).unwrap()];
    println!("generic total: {:.2}", total_area(&circles));

    let shapes: Vec<Box<dyn Shape>> = vec![       // dynamic dispatch
        Box::new(Circle::new(1.5).unwrap()),
        Box::new(Rectangle { width: 2.0, height: 3.0 }),
    ];
    for shape in &shapes {
        println!("{}", shape.describe());
    }
    let dynamic_total: f64 = shapes.iter().map(|s| s.area()).sum();
    println!("dynamic total: {dynamic_total:.2}");

    match Circle::new(-1.0) {
        Ok(circle) => println!("unexpected: {}", circle.area()),
        Err(error) => println!("rejected: {error}"),
    }
}""",
            """Add a `Triangle` type and make `Shape` implement `From<(f64, f64)>` for
a rectangle so `?` can convert a parse failure into `ShapeError`. Then add a
trait method with a generic parameter, watch object safety fail, and split it
into an object-safe trait plus a generic extension. Finally solve the judged
problem `merge-sorted-arrays` twice - once with a generic comparison bound and
once over `&dyn Fn` - and explain the trade you made.
Practice: /practice/problems/merge-sorted-arrays""",
        ),
    ],
    "sql": [
        (
            "sql-indexes-plans-deep",
            "Indexes and query plans: why the database is slow",
            "B-trees, selectivity, sargability and reading EXPLAIN instead of adding indexes blindly.",
            """**Why this matters.** The same query is instant on a million rows and
unbearable on ten million, and the difference is almost never the server's
CPU - it is whether the planner could use an index. Someone who can read a
query plan fixes a page in ten minutes; someone who cannot adds indexes at
random, doubles the write cost, and still has the slow query.

**A B-tree in one paragraph.** An index is a sorted structure of
(key, pointer-to-row) entries, usually a B-tree, so lookup is
`O(log n)` in page reads and a range scan is sequential after one descent.
Leaf pages are linked, which is why `ORDER BY indexed_column LIMIT 20` can
stop early instead of sorting the whole table. Composite indexes sort by the
first column, then the second within it - which is the rule behind the
"leftmost prefix": `(user_id, created_at)` serves filters on `user_id`, on
`user_id AND created_at`, and on `user_id ORDER BY created_at`, but not on
`created_at` alone.

**Clustered versus secondary.** In a clustered index (InnoDB's primary key,
Postgres's heap is different) the table rows are the leaves, so an index scan
*is* the row read. A secondary index stores the primary key, which means a
lookup may need a second step to fetch the row - the "index scan + heap
fetch" cost. Postgres adds visibility information to index entries and must
still check the heap for MVCC, which is why a supposedly index-only scan is
only cheaper if the visibility map says the pages are all-visible. A
*covering* index includes all needed columns (`INCLUDE` in Postgres/SQL
Server, or as trailing key columns elsewhere), avoiding the heap fetch
entirely for read-only queries.

**Selectivity decides usefulness.** An index on a column whose value is the
same in 90 % of rows does not help a lookup for that value - the planner will
prefer a sequential scan, correctly. Indexes earn their keep when a predicate
matches a small fraction of rows. Low-cardinality flags (status, is_deleted)
are better as the second column of a composite index or in a partial index
(`WHERE status = 'pending'`), which also stays small and cheap to maintain.

**Sargability: the predicate the index can use.** The index must see a bare
column compared to a constant or parameter:
`WHERE created_at >= $1` is sargable; `WHERE date_trunc('day', created_at) =
$1` is not (unless you build an expression index matching it exactly).
`LIKE 'abc%'` can use an index; `LIKE '%abc'` cannot, because a B-tree cannot
search a suffix. `WHERE upper(email) = 'X'` defeats the plain index - store
the normalised value or index the expression. Implicit casts do the same
damage: comparing a `varchar` column to an integer can prevent index use in
some engines.

**Joins and the plan shape.** A nested loop is right for a small outer set
with an index on the inner table; a hash join is right for large unsorted
sets; a merge join wants both sides sorted. The planner chooses with
statistics (`ANALYZE` in Postgres, `ANALYZE TABLE` in MySQL): estimated row
counts, distinct values, most-common values. Stale statistics are a leading
cause of "it was fast yesterday" - the plan flipped because the estimate
flipped. `EXPLAIN` shows the estimate; `EXPLAIN ANALYZE` runs the query and
shows the truth, including actual rows and loops. Compare estimate to actual:
a factor of ten or more means the planner is guessing.

**Reading a plan.** Look for sequential scans on large tables in a filter you
expected to be indexed; nested loops with a high loop count and a big inner
scan; sorts that spill (`Sort Method: external merge`); rows removed by
filter being huge compared to rows returned (the index was useless); and
"estimates off by 100x". Fix the cause named by the plan, then re-measure.
Never trust a plan without `ANALYZE`, and never tune against a table with
production-sized data missing.

**Write cost and bloat.** Every index is maintained on insert, update and
delete, and consumes cache. Ten indexes on a write-heavy table is ten extra
random writes per insert. Unused indexes are pure cost: find them from
`pg_stat_user_indexes.idx_scan` and drop them. Updates to an indexed column
in Postgres leave dead index entries until vacuum; heavy churn bloats both
table and index, so `VACUUM`/autovacuum settings are part of performance.

**Access patterns that no index saves.** `SELECT *` over a wide table for a
list page; deep offset pagination (`OFFSET 100000`) which still walks the
rows - use keyset pagination (`WHERE (created_at, id) < ($1, $2) ORDER BY
created_at DESC, id DESC LIMIT 20`); N+1 query loops from an ORM (fix with a
join or a batched `IN`); and `COUNT(*)` over a huge filtered set for a UI
badge (precompute or approximate).

**Common mistakes.** Indexing every column "just in case"; a composite index
in the wrong column order; an index that duplicates an existing prefix;
forgetting that a function on the indexed column breaks the index; ignoring
`EXPLAIN` because the ORM hides the query; and assuming the same plan will be
chosen on a table one-tenth the size.

**Interview angle.** Ask for the access pattern, then the plan, then the
statistics. Say which index you would add, in which column order, and what
write cost it imposes. That sequence is what a database review sounds like.""",
            """-- SQLite syntax; PostgreSQL is close (EXPLAIN ANALYZE BUFFERS).
CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    total_cents INTEGER NOT NULL
);

CREATE INDEX idx_orders_customer_created ON orders (customer_id, created_at);
CREATE INDEX idx_orders_pending ON orders (status) WHERE status = 'pending';

-- 1. Sargable: the index on (customer_id, created_at) is usable.
EXPLAIN QUERY PLAN
SELECT id, created_at FROM orders
WHERE customer_id = 42 AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 20;

-- 2. Non-sargable: a function on the indexed column cannot be seeked - plan becomes SCAN.
EXPLAIN QUERY PLAN
SELECT id FROM orders WHERE substr(created_at, 1, 7) = '2026-10';

-- 3. Leftmost prefix only: a filter on created_at alone cannot seek the composite index.
EXPLAIN QUERY PLAN
SELECT id FROM orders WHERE created_at >= '2026-01-01';

-- 4. Keyset pagination instead of OFFSET, which still walks skipped rows.
SELECT id, created_at FROM orders
WHERE customer_id = 42 AND (created_at, id) < ('2026-10-01', 900)
ORDER BY created_at DESC, id DESC
LIMIT 20;""",
            """Run each `EXPLAIN QUERY PLAN` above against a table you fill with
100,000 generated rows, and record which scans read the whole table. Add a
covering index for the first query and confirm the plan stops touching the
table. Then rewrite query 2 into a sargable form with a range predicate and
show the new plan. Finally solve the judged problem `top-k-frequent`, whose
SQL version depends on whether the engine can satisfy the ordering and the
limit from an index.
Practice: /practice/problems/top-k-frequent""",
        ),
        (
            "sql-transactions-isolation-deep",
            "Transactions, isolation levels and concurrency anomalies",
            "ACID precisely, the anomalies each level permits, and the patterns that stay correct.",
            """**Why this matters.** "Use a transaction" is advice everyone repeats and
few can make precise. The precision matters because isolation levels differ
between engines and versions, and because the bugs they allow - lost updates,
phantom reads, write skew - are silent. They do not corrupt memory; they
produce a business result that is wrong, weeks later, in a report nobody can
reproduce.

**ACID, stated exactly.** *Atomicity*: a transaction's statements commit
together or not at all (achieved by a log). *Consistency*: constraints hold at
commit - the database enforces what you declared, not what you meant.
*Isolation*: concurrent transactions do not see each other's uncommitted work
(and, at higher levels, do not interleave in ways that break invariants).
*Durability*: committed data survives a crash (write-ahead log, fsync, and
your replication settings). None of these is absolute: durability depends on
`synchronous_commit`, fsync and storage; consistency depends on your
constraints actually describing the rule.

**Autocommit is a transaction per statement.** Without an explicit `BEGIN`,
each statement is its own transaction. Two statements in a row are therefore
two snapshots, which is how a read-check-then-write sequence loses updates.
Deploy scripts that "just run three statements" without a transaction are how
half-applied migrations happen.

**The anomalies, by name.**

- *Dirty read*: seeing uncommitted data. Allowed only at READ UNCOMMITTED
  (and not even offered by Postgres, which maps it to READ COMMITTED).
- *Non-repeatable read*: the same row read twice returns different values
  because someone committed in between.
- *Phantom read*: the same *predicate* returns different rows on the second
  read.
- *Lost update*: two transactions read the same value, both compute, the
  second overwrites the first. Allowed under READ COMMITTED and, in some
  forms, snapshot isolation.
- *Write skew*: each transaction reads a set, writes a different member, and
  the combination violates an invariant neither saw individually - two
  doctors both going off call because each saw the other on. Snapshot
  isolation permits it; only serialisable prevents it.

**Levels in practice.** READ UNCOMMITTED is dirt; READ COMMITTED is the
Postgres default (each statement gets a fresh snapshot); REPEATABLE READ is
a transaction-level snapshot in Postgres (and also prevents lost updates
there), while in MySQL/InnoDB it means snapshot reads plus next-key locks for
locking reads; SERIALIZABLE either takes enough locks or (Postgres) uses
SSI to abort transactions that would break serialisability - so your code
*must* be prepared to retry on serialisation failure. The SQL standard's
table of levels to anomalies is a floor, not a description of any particular
engine: read your engine's documentation and assume nothing.

**Two ways to be correct.** *Pessimistic*: lock what you read -
`SELECT ... FOR UPDATE` (or `FOR UPDATE SKIP LOCKED` for a job queue) makes
another transaction wait. It works and it serialises, so it deadlocks under
lock-order disagreement and hurts throughput. *Optimistic*: read a version,
write with `WHERE version = :expected`, and check the affected row count -
zero means someone else changed it, so retry. Optimistic locking is the
default answer for web applications because transactions stay short.

**Deadlocks are a lock-order problem.** Two transactions each holding one row
and waiting for the other is a cycle. The engine detects it and kills one
(Postgres: "deadlock detected"). Prevent it by touching rows in a deterministic
order (sorted by primary key), keeping transactions short, using one
`UPDATE ... WHERE id IN (...)` with a sort instead of a loop, and never
waiting on a user or a network call while holding a lock. Treat deadlock
errors as retryable, and log them with the statements involved.

**Idempotency, because exactly-once is a myth.** A client retries when a
response is lost; the work may already have happened. Make writes idempotent
with a natural key or a unique `request_id` (insert, catch the unique
violation, return the stored result), or use a state machine guarded by
`WHERE status = 'pending'` so a duplicate transition affects zero rows. For
events, the transactional outbox - write the event row in the same
transaction as the business change - avoids the double-write problem that
kills naive "write database then publish to the queue" code.

**Constraints instead of hopes.** A `UNIQUE` index is a guarantee; a
`SELECT count(*)` check is a race. `CHECK (balance >= 0)`, foreign keys, and
`NOT NULL` move invariants into the engine, where all writers must respect
them. Application-level validation remains useful for messages, but the
database is the last line and the only one that sees every writer.

**Long transactions are expensive.** A transaction open for minutes holds
back vacuum in Postgres (bloat), holds locks, and blocks DDL. Keep them
short: compute outside, write inside, and never stream a report inside the
same transaction that updates rows.

**Common mistakes.** Assuming REPEATABLE READ prevents write skew; using
`FOR UPDATE` in a read-only report; retrying a failed serialisable
transaction with the same stale snapshot instead of re-reading; relying on
`timestamp` for ordering instead of a sequence; treating a deadlock as a bug
in the database; and wrapping an interactive user session in one transaction.

**Interview angle.** Name the anomaly you are preventing before choosing a
level, then say whether you lock or version, and mention the retry. Finishing
with "and the unique constraint enforces it even if two app servers race"
shows you think in guarantees, not in statements.""",
            """-- SQLite supports savepoints and transactions; run each block in order.
BEGIN;

CREATE TABLE IF NOT EXISTS accounts (
    id      INTEGER PRIMARY KEY,
    owner   TEXT    NOT NULL,
    balance INTEGER NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, owner, balance) VALUES (1, 'asha', 500), (2, 'ravi', 200);

SAVEPOINT transfer;
UPDATE accounts SET balance = balance - 800 WHERE id = 1;   -- would go negative
-- The CHECK constraint refuses the write; roll back to the savepoint, not the whole txn.
ROLLBACK TO transfer;
UPDATE accounts SET balance = balance - 300 WHERE id = 1;
UPDATE accounts SET balance = balance + 300 WHERE id = 2;
COMMIT;

SELECT * FROM accounts;

-- Optimistic locking: the version column is the guarantee, not a count check.
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, body TEXT, version INTEGER NOT NULL);
INSERT INTO documents (id, body, version) VALUES (1, 'draft', 1);

-- First writer wins; a stale writer updates zero rows and must re-read.
UPDATE documents SET body = 'edited by asha', version = version + 1 WHERE id = 1 AND version = 1;
UPDATE documents SET body = 'edited by ravi', version = version + 1 WHERE id = 1 AND version = 1;

SELECT id, body, version FROM documents;

-- Idempotency: a unique request key turns a retry into a no-op.
CREATE TABLE IF NOT EXISTS payments (
    request_id TEXT PRIMARY KEY,
    amount     INTEGER NOT NULL
);
INSERT OR IGNORE INTO payments (request_id, amount) VALUES ('req-7f3a', 2500);
INSERT OR IGNORE INTO payments (request_id, amount) VALUES ('req-7f3a', 2500);
SELECT count(*) AS payments_recorded FROM payments;""",
            """Change the first transfer to remove the savepoint and observe that the
whole transaction must roll back; explain why a savepoint is the right tool
when one step of a batch is allowed to fail. Then write the write-skew case
for two doctors on call and show which isolation level prevents it on your
engine. Finally solve the judged problem `count-provinces`, where a
transaction that merges two components at a time must guard against two
writers merging the same pair concurrently.
Practice: /practice/problems/count-provinces""",
        ),
    ],
    "csharp": [
        (
            "csharp-memory-span-deep",
            "Value types, Span<T> and what the garbage collector really does",
            "Boxing, stack allocation, slicing without copying, and allocations you can measure.",
            """**Why this matters.** .NET's garbage collector is excellent, which is
exactly why allocation bugs hide so long: the program works, the latency
graph is just spiky and the server needs more memory than the data suggests.
The engineers who fix that know three things - where objects live, what
allocates, and how to prove an allocation happened. This module is those three
things, plus the rules that keep `Span<T>` safe.

**Value types, reference types, and the heap claim.** A `struct` is a value:
it is copied on assignment, usually lives inline in its container or on the
stack, and has no object header. A `class` is a reference: the variable holds
a pointer to a heap object with a header and a method table pointer. "Structs
are on the stack" is a simplification - a struct field inside a class lives on
the heap, and a struct captured in a lambda or boxed lives on the heap too.
What is always true: copying a struct copies its data, so a large struct is
expensive to pass around, and mutating a copy does not affect the original -
the classic `foreach (var s in listOfStructs) s.X = 1;` bug that does not
compile for a good reason.

**Boxing is the invisible allocation.** Assigning a struct to `object` or to
an interface wraps it in a heap object; reading it back unboxes (a copy). A
generic `List<int>` stores ints inline with no boxing; `ArrayList` boxes
every add. `string.Format`/interpolation boxes value-type arguments (modern
versions largely avoid it), and `object.Equals(a, b)` on structs boxes
unless the struct overrides `Equals`. In a hot loop, one accidental boxing
conversion per iteration is millions of allocations per second.

**Span<T> is a view, not a container.** `Span<T>`/`ReadOnlySpan<T>` hold a
pointer and a length over existing memory - an array, a `stackalloc` buffer,
a slice of native memory. Slicing with `span[2..5]` allocates nothing; it
creates another view. That is why parsers written with spans avoid the
`Substring` allocation on every token. The rules that make it safe: a `Span<T>`
is a `ref struct`, so it cannot be boxed, stored in a field of a class, used
across `await`, or captured by a lambda that escapes. Those restrictions are
what guarantee the view cannot outlive the memory it points at. `Memory<T>`
is the heap-safe cousin (no ref struct restrictions) when you must store it
or await across it.

**Stack allocation and pooling.** `stackalloc int[64]` avoids the heap
entirely for small, fixed buffers - keep it small, because the stack is
limited and is not reclaimed until the method returns. For reusable larger
buffers, `ArrayPool<T>.Shared.Rent(n)` and `Return` avoid repeated
allocations (return it in a `finally`, and clear it if it held sensitive
data). `ObjectPool<T>` does the same for objects. Both are only worth it
after measurement: pooling also keeps objects alive, which shifts GC work
rather than deleting it.

**Generations and the large object heap.** Gen 0 holds new, short-lived
objects and collection is very cheap. Survivors are promoted to Gen 1 then
Gen 2; a Gen 2 collection is a full collection and can be noticeably slower.
Objects of 85,000 bytes or more go to the Large Object Heap, which is
collected with Gen 2 and is not compacted by default - repeated large
allocations and frees fragment it. Practical consequences: reuse large
buffers (pooling), avoid allocating big arrays per request, and prefer
`ArrayPool<byte>` over `new byte[1_000_000]` in a server loop.

**Deterministic release.** The GC releases *memory*, not *resources*. A
file handle, socket, timer or native allocation needs `IDisposable` and
`using`/`await using` so release happens at a known point. A finalizer is a
safety net that runs on the finalizer thread at an unknown time and delays
collection of the object for a whole cycle; use `SafeHandle` for native
resources and never rely on `~MyClass` for correctness. Implement
`IAsyncDisposable` when disposal itself is asynchronous.

**Measuring.** `dotnet-counters monitor` for allocation rate and GC counts,
`dotnet-trace` and Visual Studio's allocation profiler for the call sites
that allocate, and `GC.GetTotalAllocatedBytes(precise: true)` in a benchmark
for a quick answer. Reading the allocation number is the difference between
guessing and knowing.

**Common mistakes.** Using a struct "for performance" and copying it through
five method calls; `params object[]` and string concatenation in logging hot
paths; LINQ chains in tight loops (allocations per operator plus delegate
calls); `ToList()` to "materialise" without needing to; forgetting to
`Return` a pooled array; storing a `Span<T>` attempt leads to a compile
error - do not fight it, use `Memory<T>`; mutating a struct through an
interface or a `readonly` field.

**Interview angle.** Describe the value/reference split, name boxing as the
common hidden allocation, and explain what a `Span<T>` is and why it cannot
be stored in a field. Then say how you would prove an allocation -
`GC.GetTotalAllocatedBytes` before and after - rather than asserting it.""",
            """using System;
using System.Buffers;

public readonly struct Reading
{
    public readonly int SensorId;
    public readonly double Value;
    public Reading(int sensorId, double value) { SensorId = sensorId; Value = value; }
}

public static class MemoryDemo
{
    // No allocation: the slice is a view over the input.
    public static double SumWindow(ReadOnlySpan<double> samples, int start, int length)
    {
        ReadOnlySpan<double> window = samples.Slice(start, length);
        double total = 0;
        foreach (double sample in window) total += sample;
        return total;
    }

    public static (double, double) ParsePair(ReadOnlySpan<char> line, char separator)
    {
        int split = line.IndexOf(separator);
        double left = double.Parse(line[..split]);
        double right = double.Parse(line[(split + 1)..]);
        return (left, right);
    }

    public static void Main()
    {
        double[] samples = { 1.5, 2.5, 3.5, 4.5, 5.5 };
        Console.WriteLine($"window sum: {SumWindow(samples, 1, 3)}");

        (double a, double b) = ParsePair("12.5,7.25", ',');
        Console.WriteLine($"parsed: {a} and {b}");

        byte[] pooled = ArrayPool<byte>.Shared.Rent(4096);
        try
        {
            Span<byte> buffer = pooled.AsSpan(0, 16);
            buffer.Fill(0x2A);
            Console.WriteLine($"pooled buffer first byte: 0x{buffer[0]:X2}");
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(pooled);
        }

        long before = GC.GetTotalAllocatedBytes(precise: true);
        for (int i = 0; i < 10_000; i++) _ = SumWindow(samples, 0, samples.Length);
        long after = GC.GetTotalAllocatedBytes(precise: true);
        Console.WriteLine($"span loop allocated about {after - before} bytes");

        Reading reading = new(7, 21.5);
        object boxed = reading;                 // boxing allocates
        Reading unboxed = (Reading)boxed;       // unboxing copies
        Console.WriteLine($"boxed then unboxed: sensor {unboxed.SensorId}, value {unboxed.Value}");
        Console.WriteLine($"generation of a fresh object: {GC.GetGeneration(new object())}");
    }
}""",
            """Rewrite `ParsePair` to return `bool TryParsePair(...)` with `out`
parameters and no exceptions, then benchmark the span version against a
`Substring`-based version with `GC.GetTotalAllocatedBytes` and explain the
difference. Add a `ReadOnlySpan<char>` tokeniser that splits a whole line by
separator without allocating a string per token. Finally solve the judged
problem `moving-average`, computing the rolling window over a span with no
per-element allocation.
Practice: /practice/problems/moving-average""",
        ),
        (
            "csharp-async-deep",
            "async/await under the hood: state machines and cancellation",
            "What the compiler emits, why .Result deadlocks, and how to cancel properly.",
            """**Why this matters.** `async`/`await` reads like magic and behaves like
a state machine with sharp edges. Two common production failures - a server
that stops responding under load because of thread-pool starvation, and a
deadlock that appears only in a UI or legacy ASP.NET context - both come from
misunderstanding what the compiler generates. This module explains the
generated code, then the patterns that avoid the failures.

**What the compiler emits.** A method marked `async` that awaits is compiled
into a state machine struct: locals that survive an await become fields, the
method is split at each `await`, and the returned `Task` is completed by a
continuation when the awaited operation finishes. If the awaited `Task` is
already complete, execution continues synchronously - which is why a method
on a fast path costs almost nothing. `async` is therefore about *rewriting
control flow*, not about starting a thread. `Task.Run` starts thread-pool
work; `await` does not.

**Task, ValueTask, TaskCompletionSource.** `Task<T>` is a reference type
allocated per call; `ValueTask<T>` avoids that allocation when the result is
usually synchronous - but it may be awaited only once and must not be
consumed twice. Do not make `ValueTask` the default; use it in libraries that
measured the allocation on a hot path. `TaskCompletionSource` is how you turn
a callback-based API (an event, a socket) into an awaitable, with
`TaskCreationOptions.RunContinuationsAsynchronously` to avoid running
continuations on the completing thread.

**The SynchronizationContext trap.** Awaiting captures the current
`SynchronizationContext` (or `TaskScheduler`) and resumes on it. In a UI app
that is the single UI thread; in classic ASP.NET it was a request context
with one thread; in modern ASP.NET Core there is none. So `task.Result` or
`task.Wait()` on a single-threaded context blocks the only thread that could
run the continuation - a deadlock by construction. The rules: never block on
async (`Result`, `Wait`, `GetAwaiter().GetResult()`), make the whole call
chain async, and in library code use `ConfigureAwait(false)` to say "I do not
need the original context" (an application's own event handlers do need it).

**`async void` is only for event handlers.** Nobody can await it, exceptions
raised inside escape directly to the synchronisation context (often crashing
the process), and a test cannot observe its completion. Return `Task`
everywhere else.

**Exceptions and aggregation.** Exceptions in a task are captured and
rethrown at `await`, preserving the stack via `ExceptionDispatchInfo`. With
`Task.WhenAll`, awaiting throws the *first* exception; the rest are inside
`task.Exception.InnerExceptions`, so inspect the tasks when you must report
everything. Do not use `WhenAll` as a fire-and-forget; a failure in one task
that you never await is an unobserved exception.

**Cancellation is cooperative.** `CancellationToken` is polled; nothing
aborts a thread. Pass it to every I/O call that accepts one, call
`ThrowIfCancellationRequested()` at natural checkpoints in CPU loops, and
combine deadlines with `CancellationTokenSource.CreateLinkedTokenSource`
plus `CancelAfter`. Distinguish cancellation from failure: report
`OperationCanceledException` as cancellation only when the token was
cancelled, or a bug looks like a user action. Dispose the source, and do not
reuse a cancelled one.

**Parallelism.** `WhenAll` starts all tasks; bound concurrency with
`SemaphoreSlim` or `Parallel.ForEachAsync` so a thousand-item list does not
open a thousand sockets. `IAsyncEnumerable<T>` streams results as they
arrive (`await foreach`), which is the right shape for paging through an API
with backpressure. And for CPU work inside a web request, `Task.Run` does not
create capacity: the thread pool is the capacity, and blocking it from
inside itself is the starvation pattern.

**Common mistakes.** Blocking on async; `async void` methods that are not
event handlers; forgetting to await and losing the exception; sequential
`await` in a loop where `WhenAll` would be parallel (or the reverse - firing
everything when backpressure was needed); ignoring the token inside a loop
so "cancel" takes minutes; awaiting inside a `lock` (compiler error - use
`SemaphoreSlim`); a `using` disposed before the awaited work completes.

**Interview angle.** Explain that `async` is a compiler transformation and
that `await` suspends rather than blocks, then name the two causes of
thread-pool starvation. Mentioning `ConfigureAwait` and cooperative
cancellation shows you have maintained a service rather than read a
tutorial.""",
            """using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

public static class AsyncDemo
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(5) };

    public static async Task<string> FetchAsync(string url, CancellationToken token)
    {
        using HttpResponseMessage response = await Http.GetAsync(url, token).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(token).ConfigureAwait(false);
    }

    public static async Task<IReadOnlyList<string>> FetchManyAsync(
        IEnumerable<string> urls, CancellationToken token)
    {
        var results = new List<string>();
        using var gate = new SemaphoreSlim(4);              // bounded concurrency
        var tasks = new List<Task>();

        foreach (string url in urls)
        {
            await gate.WaitAsync(token).ConfigureAwait(false);
            tasks.Add(Task.Run(async () =>
            {
                try
                {
                    string body = await FetchAsync(url, token).ConfigureAwait(false);
                    lock (results) results.Add($"{url} -> {body.Length} bytes");
                }
                finally
                {
                    gate.Release();
                }
            }, token));
        }
        await Task.WhenAll(tasks).ConfigureAwait(false);
        return results;
    }

    public static async Task Main()
    {
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(2));

        // A local simulation: no network needed, cancellation still real.
        async Task<int> SlowWorkAsync(string name, CancellationToken token)
        {
            for (int step = 0; step < 5; step++)
            {
                token.ThrowIfCancellationRequested();
                await Task.Delay(200, token).ConfigureAwait(false);
            }
            return name.Length;
        }

        try
        {
            Task<int> first = SlowWorkAsync("alpha", cts.Token);
            Task<int> second = SlowWorkAsync("bravo", cts.Token);
            int[] lengths = await Task.WhenAll(first, second);
            Console.WriteLine($"completed: {string.Join(",", lengths)}");
        }
        catch (OperationCanceledException) when (cts.IsCancellationRequested)
        {
            Console.WriteLine("cancelled cooperatively - not an error");
        }

        Task<int> never = SlowWorkAsync("charlie", CancellationToken.None);
        Console.WriteLine($"before await, completed = {never.IsCompleted}");
        Console.WriteLine($"result = {await never}");
    }
}""",
            """Add a retry policy with exponential backoff and a per-attempt timeout
built from a linked token; confirm that `OperationCanceledException` from the
timeout is reported as a failure rather than a user cancellation. Then
replace the `SemaphoreSlim` fan-out with `Parallel.ForEachAsync` and compare
the code and the bounded-concurrency behaviour. Finally solve the judged
problem `course-schedule`, launching independent tasks before awaiting and
checking that your scheduler still respects dependencies.
Practice: /practice/problems/course-schedule""",
        ),
    ],
    "go": [
        (
            "go-goroutines-channels-deep",
            "Goroutines, channels and the scheduler",
            "Cheap concurrency, channel direction, context cancellation and the leaks that bite.",
            """**Why this matters.** Go made concurrency a first-class, ordinary tool:
`go f()` costs a couple of kilobytes and the runtime multiplexes thousands of
goroutines onto a few OS threads. That convenience is the trap - starting a
goroutine is so easy that people start one per request, per row, or per event
and never think about who waits, who cancels, or what happens when the work
outlives the caller. This module is the discipline that keeps Go concurrent
code debuggable.

**The runtime model, briefly.** Go schedules goroutines with a G-M-P
scheduler: G is a goroutine, M an OS thread, P a logical processor holding a
run queue. A P runs goroutines until one blocks (channel operation, syscall,
`time.Sleep`, mutex) and then picks the next; idle Ps steal work from others.
Growing a goroutine's stack is cheap and copying, so deep recursion is safe up
to the limit. Blocking *syscalls* park an M, and the runtime can create
another; a goroutine that blocks forever parks nothing but leaks memory and
its references.

**Channels are queues with rules.** Unbuffered sends and receives rendezvous:
the sender blocks until a receiver is ready. Buffered channels hold up to
capacity and block only when full. The rules that cause panics and deadlocks
if ignored: sending on a closed channel panics; closing twice panics; ranging
over a channel ends when it is closed; a nil channel blocks forever (useful
in `select` to disable a case). Only the sender should close, and only when
there is a single logical sender - otherwise closing is a coordination
problem and `sync.Once` or a separate done-channel is clearer.

**Direction in the signature.** `func produce(out chan<- int)` and
`func consume(in <-chan int)` make ownership visible in the type and stop a
consumer from accidentally closing. This is documentation the compiler
enforces.

**`select` is how you get timeouts and cancellation.** `select` waits on
multiple channel operations, choosing randomly among those ready;
`default` makes it non-blocking. The canonical cancellation pattern is a
`done` channel or, better, `context.Context`:

```go
select {
case value := <-work:
    handle(value)
case <-ctx.Done():
    return ctx.Err()
}
```

`context.WithTimeout`/`WithCancel` propagate a deadline and a cancellation
signal down a call tree. Cancellation is advisory: every blocking operation
must select on `ctx.Done()` and every worker must return. Without that,
`defer cancel()` closes the door on nobody.

**Waiting, grouping and errors.** `sync.WaitGroup` counts active goroutines
(`Add` before starting, `Done` via defer, `Wait` in the caller - never
`Add` from inside a goroutine you are already waiting on).
`golang.org/x/sync/errgroup` gives you the same plus first-error propagation
and `WithContext` cancellation on failure, which is what most services
actually want.

**Shared memory versus messages.** "Do not communicate by sharing memory;
share memory by communicating" is advice, not a prohibition. A `sync.Mutex`
guarding a map is perfectly idiomatic; so is a single owner goroutine that
receives requests on a channel. What is not acceptable is unsynchronised
concurrent map writes - Go's runtime detects some of these and crashes with
"concurrent map writes" rather than silently corrupting. `sync.RWMutex`,
`sync.Once`, `sync/atomic` and, in newer versions, `atomic.Int64`-style types
cover the rest.

**Proving it: the race detector.** Run tests with `-race`. It instruments
memory accesses and reports actual racing pairs, with both stacks. It is not
a proof of absence, but a race it reports is definitely a bug. Catch
goroutine leaks with `runtime.NumGoroutine()` or `goleak` in tests: a
goroutine blocked on a channel nobody will ever send to is a leak.

**Common mistakes.** Starting a goroutine per item in an unbounded loop;
`for _, v := range xs { go func() { use(v) }() }` capturing the loop
variable (pre-1.22; now fixed by per-iteration variables, but passed
explicitly and older code still bites); closing a channel from the receiver;
forgetting `wg.Add` before `go`; using a buffered channel as a queue with no
bound and calling it backpressure; abandoning a `context` without calling
`cancel` (a vet warning); reading `len(ch)` as if it were a reliable
synchronisation point.

**Interview angle.** Describe goroutine cost, then the rules for closing a
channel, then how cancellation propagates. Finish with the race detector.
That sequence shows you write concurrent Go that can be maintained, not just
compiled.""",
            """package main

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

func worker(ctx context.Context, id int, jobs <-chan int, results chan<- string, wg *sync.WaitGroup) {
	defer wg.Done()
	for {
		select {
		case job, ok := <-jobs:
			if !ok {
				return // channel closed by the producer
			}
			select {
			case <-time.After(20 * time.Millisecond): // stands in for real work
				results <- fmt.Sprintf("worker %d handled job %d", id, job)
			case <-ctx.Done():
				return
			}
		case <-ctx.Done():
			return
		}
	}
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	jobs := make(chan int, 8)      // bounded: the producer feels backpressure
	results := make(chan string, 8)
	var wg sync.WaitGroup

	for id := 1; id <= 3; id++ {
		wg.Add(1)
		go worker(ctx, id, jobs, results, &wg)
	}

	go func() {
		defer close(jobs)
		for i := 1; i <= 10; i++ {
			select {
			case jobs <- i:
			case <-ctx.Done():
				return
			}
		}
	}()

	go func() {
		wg.Wait()
		close(results)
	}()

	handled := 0
	for line := range results {
		fmt.Println(line)
		handled++
	}
	fmt.Println("handled:", handled, "context err:", errors.Is(ctx.Err(), context.DeadlineExceeded))
}""",
            """Run the example under `go run -race`, then remove the `ctx.Done()`
case from the worker and observe the goroutine leak with `runtime.NumGoroutine`
before and after. Convert the three workers into a `errgroup.Group` with
`SetLimit(3)` and propagate a deliberate error from one job. Finally solve the
judged problem `number-of-islands`, parallelising the grid scan across a
worker pool while keeping the visited set race-free.
Practice: /practice/problems/number-of-islands""",
        ),
        (
            "go-performance-deep",
            "Measuring first: benchmarks, pprof and allocations",
            "Escape analysis, preallocation, pooling and reading a profile instead of guessing.",
            """**Why this matters.** Go is fast by default, which makes the remaining
slow paths surprising: a handler that allocates three objects per request at
20k requests per second creates 60k objects a second and hands the collector
a job it did not need. The fix is not clever code; it is measurement, then
the four or five changes that actually move the number.

**Benchmark before you touch anything.** `testing.B` with
`func BenchmarkX(b *testing.B)` gives you `-bench=.` and `-benchmem`, which
reports nanoseconds per operation and, crucially, allocations per operation
and bytes per operation. Run with `-count=10` and compare with `benchstat`:
a 5 % difference in one run is noise, and optimising noise is how teams ship
complexity for nothing. Profile with `go test -bench=. -cpuprofile=cpu.out
-memprofile=mem.out`, then `go tool pprof -http=:8080 cpu.out` for a flame
graph or top list. In a running service, import `net/http/pprof` and take a
30-second CPU profile under real load - a synthetic benchmark cannot tell you
which handler is expensive.

**Escape analysis decides heap or stack.** `go build -gcflags=-m` prints
"escapes to heap" decisions. A value escapes when its address outlives the
function: returned pointers, captured by a closure that outlives the call,
stored in an interface, or too large for the stack. Returning a
`*SmallStruct` is usually fine (inlined and stack-allocated by the caller's
analysis), but `fmt.Println(x)` forces `x` into an interface and can allocate.
You do not chase every escape; you check the ones in the hot path your profile
named.

**The changes that usually help.** Preallocate with capacity:
`make([]int, 0, n)` avoids repeated growth-and-copy. Use
`strings.Builder`/`bytes.Buffer` for concatenation instead of `+=` in a loop
(quadratic otherwise). Presize maps (`make(map[string]int, n)`). Prefer a
slice of structs over a slice of pointers when the structs are small - one
allocation instead of n, better cache locality. Avoid `interface{}` in hot
paths where a concrete type works, because boxing allocates and calls through
an itable. Use `strconv.Itoa` rather than `fmt.Sprintf("%d", n)` for numbers.
In parsing, use `[]byte`/`strings.Cut` and avoid converting back and forth
between string and []byte (each conversion may copy).

**`sync.Pool` is not a general allocator.** It recycles temporary objects
across requests, with no guarantee an item survives a GC cycle. It is right
for buffers that are large, frequently allocated, and never retained. It is
wrong as a cache (use an explicit bounded cache) and dangerous if you forget
to reset state before reuse.

**The GC is driven by allocation rate.** `GOGC` (default 100) means the
collector targets a heap twice the live size after the previous collection;
raising it trades memory for CPU, lowering it the reverse.
`GOMEMLIMIT` (Go 1.19+) caps total memory and is the right knob in a
container, because it makes the runtime respect the cgroup limit instead of
being OOM-killed. Neither knob fixes a leak: if live heap grows with uptime,
you have retained garbage, and a heap profile with `-inuse_space` will show
you the retaining type.

**Cache effects count as performance.** A linked list of 10k nodes is slower
than a slice of 10k structs at the same complexity, because the slice is
contiguous and prefetched. Iterating a map is slower than iterating a slice
of the same size. Choose data structures for memory layout, not only for
Big-O, once n is known.

**Common mistakes.** Optimising without a profile; benchmarking with the
compiler's dead code elimination hiding the work (assign results to a
package-level sink); measuring a function that is dominated by test setup;
using `sync.Pool` for objects with expensive reset; growing a slice one
element at a time in a loop while claiming O(n); ignoring allocations because
"the GC handles it" in a latency-sensitive service.

**Interview angle.** Say what you would measure, with which tool, and what
number would tell you the change worked. Then name the one structural change
you would try first (preallocation, or removing an interface from a hot
loop). Measurement-first is the senior answer; micro-optimising from memory
is the one that fails review.""",
            """package main

import (
	"fmt"
	"strings"
	"testing"
)

var sink string

func BenchmarkConcatPlus(b *testing.B) {
	parts := []string{"meridian", "measures", "instead", "of", "guessing"}
	for i := 0; i < b.N; i++ {
		out := ""
		for _, p := range parts {
			out += p + " "
		}
		sink = out
	}
}

func BenchmarkConcatBuilder(b *testing.B) {
	parts := []string{"meridian", "measures", "instead", "of", "guessing"}
	for i := 0; i < b.N; i++ {
		var sb strings.Builder
		sb.Grow(64)                       // one allocation, predictable size
		for _, p := range parts {
			sb.WriteString(p)
			sb.WriteByte(' ')
		}
		sink = sb.String()
	}
}

// A slice grown without capacity reallocates and copies as it fills.
func buildNoCap(n int) []int {
	var out []int
	for i := 0; i < n; i++ {
		out = append(out, i)
	}
	return out
}

func buildWithCap(n int) []int {
	out := make([]int, 0, n)              // one allocation
	for i := 0; i < n; i++ {
		out = append(out, i)
	}
	return out
}

func main() {
	fmt.Println(len(buildNoCap(5)), len(buildWithCap(5)), cap(buildWithCap(5)))
	fmt.Println("run: go test -bench=. -benchmem")
}""",
            """Run `go test -bench=. -benchmem -count=10`, then compare the two
functions with `benchstat`. Explain the allocations-per-operation difference
and confirm the growth behaviour with `cap` printed at each append. Next build
the capacity example with `-gcflags=-m` and identify which values escape. Then
solve the judged problem `subarray-sum-equals-k` with a prefix-sum map that is
presized, and check the allocation count with `-benchmem`.
Practice: /practice/problems/subarray-sum-equals-k""",
        ),
    ],
}

#: Module slug -> judged problem slug for the "code what you learned" button.
#: Every problem here already exists in the seeded bank, so a new depth module
#: cannot ship with a practice link that 404s (scripts/seed.py refuses to seed
#: a link to an unknown problem).
MODULE_PRACTICE: dict[str, str] = {
    "python-gil-concurrency-deep": "word-ladder",
    "python-typing-tooling-deep": "validate-ipv4",
    "java-jvm-memory-gc": "matrix-transpose",
    "java-concurrency-jmm-deep": "course-schedule",
    "js-event-loop-deep": "rotting-oranges",
    "js-modules-bundling-deep": "version-compare",
    "ts-type-system-deep": "evaluate-rpn",
    "ts-runtime-validation-deep": "validate-ipv4",
    "c-undefined-behaviour-deep": "count-set-bits",
    "c-build-debug-deep": "base64-encode",
    "cpp-raii-move-deep": "matrix-transpose",
    "cpp-templates-concepts-deep": "serialize-tree",
    "csharp-memory-span-deep": "moving-average",
    "csharp-async-deep": "course-schedule",
    "go-goroutines-channels-deep": "number-of-islands",
    "go-performance-deep": "subarray-sum-equals-k",
    "rust-borrowing-lifetimes-deep": "reverse-linked-list",
    "rust-traits-generics-deep": "merge-sorted-arrays",
    "sql-indexes-plans-deep": "top-k-frequent",
    "sql-transactions-isolation-deep": "count-provinces",
}
