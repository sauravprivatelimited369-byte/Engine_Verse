"""Depth wave 3, part four: C#, Go, Rust and SQL semantics modules.

The last six modules of the wave, in the same legacy body/example/exercise
shape. C# examples target .NET 8, Go examples target Go 1.22, Rust examples
target the 2021 edition, and SQL examples are written for PostgreSQL 16 with
notes where SQLite or MySQL differ.
"""

BOOK_MODULES: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "csharp": [
        (
            "csharp-semantics-deep",
            "Values, references and the CLR's type system",
            "Structs versus classes, boxing, nullable value types, equality across records and strings, "
            "checked arithmetic, decimal money, and the disposal rules that follow from the CLR.",
            r"""**Why this matters.** C# looks like Java with properties, but the CLR's type system is
different in ways that change behaviour: value types are copied, structs live inline, `decimal` is
a first-class decimal, and `using` is a language-level disposal contract. The bugs that follow are
predictable - a mutated struct copy, a boxed value compared by identity, a `decimal`-shaped value
stored as `double` - and this module states the rules behind them.

**Value types and reference types.** A value type (struct, enum, and the numeric types) holds its
data inline; assignment copies the whole value. A reference type (class, array, delegate, string)
holds a reference; assignment copies the reference, so two variables point at one object. `struct`
is the declaration for a custom value type, and it should be small, immutable and logically a single
value - a `DateTime`, a coordinate, a money amount. A large mutable struct copied in a loop is a
performance trap, and a mutable struct exposed through a readonly field is a correctness trap:
the compiler may copy it before the mutation, so the change disappears.

**Boxing wraps a value on the heap.** Assigning a struct to `object` or to an interface it
implements boxes it; unboxing requires an exact type cast. A boxed copy is a different object from
the original, so mutating the box does not change the variable, and `==` on two separately boxed
ints compares references. Generic collections avoid boxing (`List<int>` stores `int` inline);
non-generic ones (`ArrayList`) box every element. `default(int)` is 0, `default(DateTime)` is
`0001-01-01`, and `default(string)` is null.

**Nullable value types.** `int?` is `Nullable<int>`, a struct with `HasValue` and `Value`. Reading
`.Value` on an empty nullable throws `InvalidOperationException`; use `??`, `?.`, `HasValue` or
`GetValueOrDefault`. Nullable reference types (`string?`) are a compiler feature: with
`<Nullable>enable</Nullable>` the compiler tracks null flow, but the runtime does not enforce it,
so a `null!` or a deserialised object can still violate the annotation.

**Equality has four different meanings.** `ReferenceEquals(a, b)` is identity. `a == b` is the
operator, which is overloaded for strings (value equality) and numbers, and defaults to identity
for classes. `a.Equals(b)` is the virtual method; it defaults to identity for classes and to field
equality for structs, and `record` overrides it to compare components. `IEquatable<T>` is the
strongly typed overload the collections call. `string` is special: `==` compares content,
`ReferenceEquals` is identity, and identical literals are interned. `GetHashCode` must agree with
`Equals`, or `Dictionary` and `HashSet` silently lose entries; a mutable field used in `GetHashCode`
is the classic cause.

**Strings are immutable and culture-sensitive.** Concatenation in a loop allocates a new string each
time; `StringBuilder` is the linear alternative. Comparison is the subtle part: `==` and
`String.Equals` use ordinal comparison, `string.Compare` uses the current culture by default, and
`ToUpper()`/`ToLower()` are culture-sensitive (the Turkish dotless i is the standard example).
Use `StringComparison.Ordinal` for identifiers and protocol values, `OrdinalIgnoreCase` for ASCII
case-insensitive keys, and `CurrentCulture` only for user-visible sorting. `string.Format` and
interpolation use the current culture for numbers and dates; pass `CultureInfo.InvariantCulture`
for machine-readable output.

**Numeric types.** `byte`, `sbyte`, `short`, `ushort`, `int`, `uint`, `long`, `ulong`, `nint`,
`nuint`, `float`, `double`, `decimal`, `char`, `bool`. Arithmetic promotes to the wider type, and
integer overflow wraps by default; `checked { ... }` or `<CheckForOverflowUnderflow>true</...>`
turns it into `OverflowException`. `decimal` has 28-29 significant digits and is exact for base-10
values, which is why it is the money type; it is slower and has a smaller range than `double`.
`double` is binary floating point and cannot represent 0.1 exactly, so money in `double` accumulates
error. `float` is for graphics and memory-bound arrays, not for prices.

**Conversions.** Implicit conversions widen without losing information; explicit casts narrow and
may throw in a `checked` context. `Convert.ToInt32("42")` parses and throws
`FormatException`/`OverflowException`; `int.TryParse` returns a bool and is the right choice at a
boundary. `as` performs a reference conversion and returns null on failure; a direct cast throws
`InvalidCastException`. `is` tests and, with a pattern, assigns:
`if (value is string text && text.Length > 0)`. User-defined implicit operators are powerful and
easy to abuse; they make conversions invisible, so keep them for genuinely lossless cases.

**Disposal and finalisation.** `IDisposable.Dispose` releases unmanaged resources and should be
idempotent. `using` (and `using var`) calls it in a `finally`, including on exception. The garbage
collector does not call `Dispose`; it may call a finaliser, which runs on the finaliser thread at an
unspecified time. The correct pattern is `Dispose` for deterministic cleanup, a finaliser only when
the type owns an unmanaged handle directly, and `GC.SuppressFinalize(this)` after a successful
dispose. `SafeHandle` is the modern wrapper for OS handles.

**`readonly`, `const`, `init` and records.** `const` is a compile-time literal inlined into callers;
changing it requires recompiling them. `static readonly` is initialised once at runtime. `readonly`
fields can only be assigned in the constructor. `init` accessors allow assignment only during
object initialisation, which is the immutable-object pattern without a constructor for every
combination. `record` gives value equality, `with` expressions and a readable `ToString`; `record
struct` combines value semantics with the record conveniences.

| Comparison | Compares | Null-safe |
| --- | --- | --- |
| `ReferenceEquals(a, b)` | Identity | Yes |
| `a == b` on a class | Identity unless overloaded | No (`==` on `null` works, but overloads may not) |
| `a.Equals(b)` | `Equals` override | No |
| `EqualityComparer<T>.Default.Equals(a, b)` | Type's equality | Yes |
| `record` `==` | All components | Yes |
| `a.GetHashCode() == b.GetHashCode()` | A bucket, not equality | Never use for equality |

**The judgment call.** Use classes for identity and behaviour, structs for small immutable values,
`decimal` for money, `TryParse` at boundaries, `StringComparison.Ordinal` for keys, and `using` for
anything that owns a resource. When two values are equal, decide whether that means identity,
component equality or content equality - and implement the matching members.""",
            r"""using System;

public readonly record struct Money(decimal Amount, string Currency)
{
    public Money Add(Money other)
    {
        if (Currency != other.Currency)
            throw new InvalidOperationException("currency mismatch");
        return this with { Amount = Amount + other.Amount };
    }
}

public struct Counter
{
    public int Value;
    public void Increment() => Value++;
}

public class Program
{
    public static void Main()
    {
        var price = new Money(19.99m, "EUR");
        var updated = price.Add(new Money(5.01m, "EUR"));
        Console.WriteLine(updated);

        var counter = new Counter();
        counter.Increment();
        var copy = counter;
        copy.Increment();
        Console.WriteLine($"{counter.Value} {copy.Value}");

        object boxed = 42;
        object alsoBoxed = 42;
        Console.WriteLine(ReferenceEquals(boxed, alsoBoxed));
        Console.WriteLine(boxed.Equals(alsoBoxed));

        int? missing = null;
        Console.WriteLine(missing ?? -1);
        Console.WriteLine(missing.GetValueOrDefault());

        string text = "İstanbul";
        Console.WriteLine(text.ToUpperInvariant());
        Console.WriteLine(text.Equals("istanbul", StringComparison.OrdinalIgnoreCase));

        double binary = 0.1 + 0.2;
        decimal exact = 0.1m + 0.2m;
        Console.WriteLine(binary == 0.3);
        Console.WriteLine(exact == 0.3m);

        checked
        {
            try { int value = int.MaxValue; value++; }
            catch (OverflowException) { Console.WriteLine("overflow caught"); }
        }

        using var stream = new System.IO.MemoryStream();
        stream.WriteByte(1);
        Console.WriteLine(stream.Length);
    }
}
""",
            "Run the example and explain the two equality results for the boxed integers and the two numeric sums. "
            "Then deliberately use a mutable struct as a dictionary key and show what happens. Finally, replace "
            "a `double` money field in a small program with `decimal`, and add `TryParse` at the input boundary. "
            "Practise with /practice/problems/single-number.",
        ),
        (
            "csharp-stdlib-deep",
            "Collections, LINQ, text and time in .NET",
            "Collection costs and deferred execution, the LINQ operators that allocate, string comparison, "
            "System.Text.Json, HttpClient, DateTimeOffset and the logging surface.",
            r"""**Why this matters.** .NET's library is large enough that the same task has three idiomatic
solutions, and the difference is often allocation and latency rather than style. LINQ is deferred,
`IEnumerable<T>` can enumerate a database or a file, `string` comparison is culture-sensitive and
`HttpClient` is designed to be reused. This module is the decision table for the library a .NET
developer uses every day.

**Collections.** `List<T>` for a growable sequence, `Dictionary<TKey, TValue>` for keyed lookup,
`HashSet<T>` for membership, `Queue<T>`/`Stack<T>` for FIFO/LIFO, `LinkedList<T>` for O(1) inserts
with a node reference (rarely worth it), `SortedDictionary`/`SortedSet` for ordered keys,
`PriorityQueue<TElement, TPriority>` (.NET 6) for scheduling, `ConcurrentQueue`/`ConcurrentDictionary`
for sharing. `Dictionary` preserves insertion order in practice but does not guarantee it; use
`OrderedDictionary` or a list of keys when order is part of the contract. Capacity grows by
doubling; pass an initial capacity when the size is known.

**Deferred execution.** A LINQ query is a description, not a result. `Where`, `Select`, `OrderBy`
and `Take` build a pipeline; `foreach`, `ToList`, `ToArray`, `Count`, `First` and `Sum` execute it.
Enumerating a query twice runs the work twice, and if the source is a database, that is two
queries. Capture the result with `ToList()` when you need it more than once. `IQueryable<T>` is a
different interface: the provider translates the expression tree to SQL, so a custom method call
inside the query cannot be translated and throws at runtime; `AsEnumerable()` switches to
client-side evaluation deliberately, not by accident.

**LINQ operators and cost.** `Where`/`Select` are streaming; `OrderBy` buffers and sorts; `GroupBy`
buffers groups; `Join` builds a lookup; `Distinct` builds a set; `Count()` on an `IEnumerable`
enumerates, while `Count` on a collection is O(1) via the interface. `First` throws on empty,
`FirstOrDefault` returns default; `Single` throws unless exactly one; `Any()` is cheaper than
`Count() > 0`. `SelectMany` flattens; `Zip` pairs; `Chunk` batches. Prefer a `for` loop when the
query would be a mutable accumulation with side effects - `ForEach` is not a LINQ operator, and
mixing side effects into a query is how deferred execution becomes a bug.

**Strings.** `StringBuilder` for loops, `string.Join`/`string.Concat` for collections, `Split` with
`StringSplitOptions.RemoveEmptyEntries`, `Trim`/`TrimStart`/`TrimEnd`, `Replace`, `Contains`,
`StartsWith`/`EndsWith` with an explicit `StringComparison` (the overloads without one are
culture-sensitive), `IndexOf` with `StringComparison.Ordinal`, `Substring` (allocates; use
`AsSpan`/`Slice` in hot paths), `string.Create` for interpolation into a buffer. `StringComparison`
is not a performance detail only - culture-sensitive comparison can be a security bug when it is
used for tokens or identifiers.

**JSON.** `System.Text.Json` is the built-in serializer: `JsonSerializer.Serialize(value)` and
`Deserialize<T>(text)`. Options control naming (`JsonNamingPolicy.CamelCase`), null handling,
enum as string (`JsonStringEnumConverter`), case-insensitive reads and number handling. The default
serializer ignores cycles and throws on them unless `ReferenceHandler.Preserve` is set. For
performance and trimming safety, source generation (`[JsonSerializable]`) generates the metadata at
compile time. Parsing untrusted input: `JsonDocument` for read-only traversal, or
`Deserialize<T>` with a type that has explicit nullability; do not accept a `dynamic` and hope.

**Time.** `DateTime` is ambiguous about time zone; `DateTimeOffset` carries the offset;
`TimeZoneInfo` converts between zones; `DateOnly` and `TimeOnly` (.NET 6) model calendar values
without a time. Store UTC (`DateTime.UtcNow`, `DateTimeOffset.UtcNow`), convert for display, and use
`TimeProvider` for testability (inject a fake clock instead of `DateTime.Now`). `DateTime.Now` in a
library is a hidden dependency on the machine's zone.

**HTTP and IO.** Reuse one `HttpClient` (or use `IHttpClientFactory`); creating one per request
exhausts sockets. `GetAsync` throws on network failure but not on 404/500 - check
`response.IsSuccessStatusCode`. Use `CancellationToken` on every async call; `ReadAsStringAsync` and
`ReadFromJsonAsync` are the convenience methods. File IO: `File.ReadAllTextAsync`,
`File.WriteAllTextAsync`, `FileStream` with `useAsync: true` for large files, and
`Path.Combine`/`Path.Join` rather than string concatenation. Dispose streams and readers.

**Logging and configuration.** `ILogger<T>` with structured message templates
(`logger.LogInformation("order {OrderId} failed", id)`) is the .NET shape; the template is parsed,
so the property name matters, but the message is only formatted if the level is enabled.
`IConfiguration` reads appsettings, environment variables and command-line arguments in a defined
precedence; bind a typed options class and validate it at startup (`ValidateOnStart`). Secrets
belong in a secret store, not in appsettings committed to the repository.

**Randomness and identifiers.** `Random` is not cryptographically secure and, before .NET 6, not
thread-safe when shared; `Random.Shared` is thread-safe. `RandomNumberGenerator` is the
cryptographic source; `Guid.NewGuid()` is a version-4 UUID (random, not sortable), which matters for
database index locality. `Guid.CreateVersion7()` (.NET 9) is time-ordered.

| Need | Type | Note |
| --- | --- | --- |
| Growable sequence | `List<T>` | Indexed access, amortised append |
| Keyed lookup | `Dictionary<TKey, TValue>` | Insertion order is not a contract |
| Membership | `HashSet<T>` | `Add` returns whether it was new |
| FIFO / LIFO | `Queue<T>` / `Stack<T>` | `TryDequeue`/`TryPop` avoid exceptions |
| Ordered keys or ranges | `SortedDictionary<TKey, TValue>` | O(log n) operations |
| Priority work | `PriorityQueue<TElement, TPriority>` | Dequeue is smallest priority first |
| Shared across threads | `ConcurrentDictionary` / `Channel<T>` | Plain collections are not thread-safe |

**The judgment call.** Keep `IEnumerable` lazy until you need a materialised result, choose the
collection by access pattern, compare strings with an explicit `StringComparison`, reuse
`HttpClient`, inject a clock, and validate configuration once at startup. The library is not a
bag of helpers; each type encodes a contract about performance and identity.""",
            r"""using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;

public record Order(string Id, string Customer, decimal Total, DateTimeOffset PlacedAt);

public static class Program
{
    public static async Task Main()
    {
        var orders = new List<Order>
        {
            new("o-1", "ana", 120m, DateTimeOffset.Parse("2026-01-02T10:00:00+05:30")),
            new("o-2", "bo", 80m, DateTimeOffset.Parse("2026-01-03T11:00:00+05:30")),
            new("o-3", "ana", 200m, DateTimeOffset.Parse("2026-01-04T12:00:00+05:30")),
        };

        var byCustomer = orders
            .GroupBy(order => order.Customer)
            .Select(group => new { Customer = group.Key, Total = group.Sum(o => o.Total), Count = group.Count() })
            .OrderByDescending(row => row.Total)
            .ToList();

        foreach (var row in byCustomer)
            Console.WriteLine($"{row.Customer}: {row.Total} across {row.Count}");

        var recent = orders.Where(order => order.PlacedAt > new DateTimeOffset(2026, 1, 2, 0, 0, 0, TimeSpan.Zero));
        Console.WriteLine($"recent count: {recent.Count()}");

        var json = JsonSerializer.Serialize(byCustomer, new JsonSerializerOptions { WriteIndented = true });
        Console.WriteLine(json);

        var parsed = JsonSerializer.Deserialize<List<Order>>(
            "[{\"Id\":\"o-9\",\"Customer\":\"cy\",\"Total\":10,\"PlacedAt\":\"2026-01-05T00:00:00+00:00\"}]");
        Console.WriteLine(parsed?.Single().Customer);

        var text = string.Join(", ", orders.Select(order => order.Id));
        Console.WriteLine(text);

        await Task.Delay(10);
        Console.WriteLine(TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow, TimeZoneInfo.Utc).Offset);
    }
}
""",
            "Replace a loop that builds a list with a deferred LINQ query, then show what happens when the source "
            "changes between two enumerations. Add `StringComparison.Ordinal` to a security-relevant comparison and "
            "explain the difference. Finally, parse a JSON array into records with `System.Text.Json`, handle a "
            "missing property, and pass a `CancellationToken` through an async call. Practise with "
            "/practice/problems/top-k-frequent.",
        ),
        (
            "csharp-diagnostics-deep",
            "Reading .NET failures: exceptions, logs and diagnostics",
            "Exception chains and async stack traces, the errors that dominate production, nullable and "
            "analyzer warnings, and the dotnet-* tools for memory, CPU and hangs.",
            r"""**Why this matters.** .NET failures are usually one of four things: a null that the type
system warned about, an exception swallowed by an `async void`, a disposed object used after
`using`, or a resource that ran out. The runtime reports all four, but the report is only useful if
you read the chain and know which tool measures which resource.

**Exception anatomy.** An exception carries a message, a stack trace, an inner exception and, since
.NET 4, a `Data` dictionary. `Caused by` style chains do not exist; instead the inner exception is
the cause. `AggregateException` wraps several failures, which is what `Task.Wait` and `Task.WhenAll`
produce; awaiting a task rethrows the first inner exception instead. `ExceptionDispatchInfo.Capture
(exc).Throw()` preserves the original trace when you must rethrow later. `throw;` preserves the
trace; `throw exc;` resets it to the current line, which hides the origin.

**The production errors.**
| Failure | Cause | Fix |
| --- | --- | --- |
| `NullReferenceException` | A null the compiler could not prove | Enable nullable, fix the producer |
| `InvalidOperationException` | The object is in the wrong state (collection modified, sequence empty) | Check the state transition |
| `ArgumentException` / `ArgumentNullException` | A caller violated the contract | Validate at the boundary, name the parameter |
| `ObjectDisposedException` | Used after `Dispose` | Own the lifetime; do not capture disposed services |
| `TaskCanceledException` | A timeout or a cancelled token | Distinguish timeout from user cancellation via the token |
| `OperationCanceledException` | Cooperative cancellation | Let it propagate; do not log it as a failure |
| `AggregateException` | Several task failures | Inspect `InnerExceptions`, not just `Message` |
| `OutOfMemoryException` | The live set or a single allocation is too large | Take a dump, find the retention |
| `StackOverflowException` | Unbounded recursion | Cannot be caught; fix the recursion |

**Async failures are the hard ones.** `async void` cannot be awaited, so its exception is raised on
the synchronization context and usually crashes the process; use `async Task` everywhere except
event handlers. A `Task` that is never awaited swallows its exception until finalisation, when
`TaskScheduler.UnobservedTaskException` fires. Blocking on a task with `.Result` or `.Wait()` in a
context with a synchronization context deadlocks; use `await`. `ConfigureAwait(false)` in library
code avoids capturing the context. A cancelled token produces `OperationCanceledException` (often
surfaced as `TaskCanceledException`), and a timeout is a cancellation with a different reason - log
them differently.

**Nullable reference types and analyzers.** With `<Nullable>enable</Nullable>`, the compiler warns
about possible null dereferences (`CS8602`), null returns (`CS8603`), and null arguments
(`CS8604`). Treat the warnings as a design signal: a `!` suppresses the warning without fixing the
cause. Analyzer rules (`CA*`, `IDE*`) catch disposal, culture, and async patterns; enable
`<AnalysisLevel>latest</AnalysisLevel>` and `<TreatWarningsAsErrors>` in CI. `dotnet format
--verify-no-changes` keeps the style rule enforceable.

**Logging.** `ILogger<T>` is resolved from dependency injection; the message template is structured
(`"order {OrderId} failed"`), and the exception is passed as the first argument to
`LogError(exception, ...)`. Log once, at the boundary that can act; a library should not log an
exception it rethrows. Scopes (`BeginScope`) attach request or job identifiers. Avoid logging PII;
`IDestructuringPolicy`/redaction are the tools when objects carry secrets.

**Tools.** `dotnet-counters monitor` shows CPU, GC heap, exception rate, thread pool queue and
working set live. `dotnet-trace collect` produces a trace for `speedscope` or PerfView; the CPU and
allocation samples answer "where is the time". `dotnet-dump collect` plus `dotnet-dump analyze`
opens a managed dump with `clrstack`, `dumpheap -stat`, `gcroot`; a growing `System.Byte[]` or
`System.String` count is the first clue. `dotnet-gcdump` gives a lighter heap snapshot for
`dotnet-gcdump report`. `dotnet-counters` on a production box is the least invasive first step.

**GC and memory.** The GC is generational and compacting; a `Gen 2` collection is expensive, and a
high allocation rate promotes short-lived objects into Gen 2. `IDisposable` and `using` release
unmanaged memory; the managed heap is a separate concern. `GC.GetTotalMemory`, `GC.CollectionCount`
and `GCSettings.LatencyMode` are the tuning surface, but allocation reduction is almost always the
real fix. `ArrayPool<T>` and `Span<T>` remove hot-path allocations; `StringBuilder` removes string
concatenation churn.

**Build and package failures.** `NU1101` (package not found) is a feed or version problem; `NU1605`
(downgrade detected) means two dependencies disagree; `CS0246` is a missing using or reference;
`CS1998` warns that an `async` method has no `await`; a `FileNotFoundException` for a managed
assembly at runtime is usually a copy-local or deps.json problem. Central package management
(`Directory.Packages.props`) prevents version drift across a solution.

**The judgment call.** Read the inner exception, then the first frame in your code. Turn nullable
warnings on and fix the producers. Use `Task` not `async void`, pass cancellation tokens, and reach
for `dotnet-counters` before restarting a service that is slow or growing.""",
            r"""using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

public sealed class OrderClient : IDisposable
{
    private readonly HttpClient _http = new()
    {
        BaseAddress = new Uri("https://example.invalid"),
        Timeout = TimeSpan.FromSeconds(5),
    };

    public async Task<string> FetchAsync(string id, CancellationToken token)
    {
        try
        {
            using var response = await _http.GetAsync($"/orders/{id}", token);
            if (!response.IsSuccessStatusCode)
                throw new HttpRequestException($"order {id} returned {(int)response.StatusCode}");
            return await response.Content.ReadAsStringAsync(token);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            throw;                       // caller cancelled: let it propagate
        }
        catch (OperationCanceledException exc)
        {
            throw new TimeoutException($"order {id} timed out", exc);
        }
    }

    public void Dispose() => _http.Dispose();
}

public static class Program
{
    public static async Task Main()
    {
        using var client = new OrderClient();
        try
        {
            await client.FetchAsync("o-1", CancellationToken.None);
        }
        catch (Exception exc) when (exc is TimeoutException or HttpRequestException)
        {
            Console.WriteLine($"{exc.GetType().Name}: {exc.Message}");
            Console.WriteLine($"cause: {exc.InnerException?.GetType().Name ?? "none"}");
        }

        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        try
        {
            await client.FetchAsync("o-2", cancelled.Token);
        }
        catch (OperationCanceledException)
        {
            Console.WriteLine("caller cancellation propagates without wrapping");
        }

        try
        {
            await Task.WhenAll(Task.FromException(new InvalidOperationException("a")),
                               Task.FromException(new InvalidOperationException("b")));
        }
        catch (InvalidOperationException exc)
        {
            Console.WriteLine($"awaited WhenAll surfaces: {exc.Message}");
        }

        Console.WriteLine($"gen0 collections: {GC.CollectionCount(0)}");
        Console.WriteLine($"managed memory: {GC.GetTotalMemory(false)} bytes");
    }
}
""",
            "Run the example and explain why the first `OperationCanceledException` is rethrown while the second is "
            "wrapped. Then write an `async void` method that throws, call it, and observe the difference from an "
            "`async Task` method. Finally, enable nullable warnings in a small project, fix three of them without "
            "`!`, and run `dotnet-counters` against a loop that allocates in a tight cycle. Practise with "
            "/practice/problems/validate-ipv4.",
        ),
    ],
    "go": [
        (
            "go-semantics-deep",
            "Slices, interfaces and Go's value semantics",
            "Slice headers and aliasing, map rules, string/rune/byte conversions, method sets and nil "
            "interfaces, defer and loop-variable semantics, and the error interface.",
            r"""**Why this matters.** Go is small, and almost every bug comes from misunderstanding one of
three things: a slice is a header over an array, an interface is a pair of type and value, and
everything is passed by value. None of those are advanced features; they are the whole language.
Once you can draw the slice header and the interface pair on paper, the surprising behaviour stops
being surprising.

**Arrays are values; slices are headers.** `[3]int` is a value of three integers; assigning it
copies all three. A slice is a struct with a pointer to an underlying array, a length and a
capacity. Assigning a slice copies the header, so two slices share the array; appending may write
into spare capacity (visible through the other slice) or allocate a new array (not visible). The
rule that follows: `append` returns a new slice, always assign the result, and never assume the
original sees the growth. `s[:n]` shares; `slices.Clone` copies.

```go
base := make([]int, 2, 4)      // len 2, cap 4
a := base
b := append(a, 7)              // writes into base's spare capacity
fmt.Println(base[:3])          // [0 0 7] - b and base share the array
c := append(b, 8, 9)           // exceeds cap: new array
```

**Maps are reference types with strict rules.** A map value is a pointer to a runtime structure;
copying the map copies the pointer, so both names see the same entries. Reading a missing key
returns the zero value; use the two-result form (`v, ok := m[k]`) to distinguish "missing" from
"zero". Writing to a nil map panics; reading from one is fine. Maps are not safe for concurrent
write; use a `sync.Mutex`, `sync.RWMutex`, or `sync.Map` for the specific read-mostly case. Go 1.12
added a randomised iteration order, so tests that depend on map order are wrong by design; sort
the keys.

**Strings, bytes and runes.** A string is an immutable read-only byte slice, usually UTF-8.
`len(s)` is bytes; `s[i]` is a byte; `for i, r := range s` decodes runes and gives the byte index.
`[]rune(s)` allocates and converts; `[]byte(s)` copies. `string(bytes)` copies; `strings.Builder`
avoids quadratic concatenation. Slicing a string shares the bytes, which keeps the whole original
alive - a memory leak when you keep a small substring of a large document. `strings.Clone` breaks
the reference. Invalid UTF-8 becomes U+FFFD on range, which is a silent data change.

**Method sets and interface satisfaction.** A method with a value receiver is in the method set of
both `T` and `*T`; a pointer receiver is only in `*T`. That decides whether `T` implements an
interface: if `M` has a pointer receiver, `T` does not implement `I`, but `*T` does, and a value in
an interface cannot call it. `nil` interface values: an interface is nil only when both its type and
value are nil. A `*MyError` nil pointer stored in an `error` makes the interface non-nil, which is
why `if err != nil` can be true with a nil pointer underneath. Return `nil` explicitly, not a typed
nil.

**`defer` arguments are evaluated immediately.** `defer f(x)` captures `x` now, not at return;
`defer func() { ... }()` captures the variable. Defers run LIFO, after the return values are
assigned, which is why a named result can be modified by a deferred closure. A defer inside a loop
runs at function exit, not iteration exit; a loop that opens files with `defer close` leaks
descriptors until the function returns.

**Loop variables (Go 1.22).** Before 1.22, the loop variable was reused, so closures captured the
final value; the workaround was `i := i`. Go 1.22 gives each iteration a new variable for both
`for` and `range`, which changes the meaning of existing code. Know which toolchain the module
targets (`go` directive in `go.mod`) before relying on either behaviour. Goroutines started in a
loop still need `sync.WaitGroup` and a way to bound concurrency.

**Errors are values.** The `error` interface has one method, `Error() string`. Wrap with
`fmt.Errorf("loading config: %w", err)` to preserve the chain; inspect with `errors.Is` (sentinel)
and `errors.As` (type). `%v` in the wrap loses the chain. Sentinel errors (`var ErrNotFound =
errors.New(...)`) are compared with `errors.Is`; custom error types carry structured fields and are
extracted with `errors.As`. Do not compare error strings.

**Struct comparison and copying.** Structs are comparable if all fields are comparable; `==`
compares field by field, and a struct containing a slice or map is not comparable (compile error).
Copying a struct copies its fields, including a mutex - which is why `sync.Mutex` must not be
copied, and why `go vet` flags it. Pass pointers for large structs or when the method mutates;
pass values for small immutable data.

| Operation | Copies | Shares | Watch |
| --- | --- | --- | --- |
| `b := a` (slice) | The header | The backing array | `append` may write into spare capacity |
| `m2 := m` (map) | The pointer | All entries | Concurrent writes panic |
| `s := t` (struct) | Every field | Pointer fields only | Copying a mutex is a bug |
| `f(x)` with `x` a slice | The header | The array | Mutating elements is visible to the caller |
| `f(x)` with a pointer receiver | The pointer | The value | Method set decides interface satisfaction |
| Interface holding a typed nil | The pair | - | `err != nil` is true |

**The judgment call.** Draw the slice header, the interface pair and the map pointer. Assign every
`append`, clone a substring you intend to keep, return `nil` errors explicitly, and pick value or
pointer receivers for the whole type. Go's simplicity is a property of its semantics, not a
shortage of features.""",
            r"""package main

import (
	"errors"
	"fmt"
	"slices"
)

type NotFound struct{ Key string }

func (e *NotFound) Error() string { return "missing key: " + e.Key }

func lookup(data map[string]int, key string) (int, error) {
	value, ok := data[key]
	if !ok {
		return 0, &NotFound{Key: key}
	}
	return value, nil
}

func main() {
	base := make([]int, 2, 4)
	view := base
	grown := append(view, 7)
	fmt.Println(base[:3], grown, &base[0] == &grown[0])

	copied := slices.Clone(base)
	copied[0] = 99
	fmt.Println(base[0], copied[0])

	data := map[string]int{"a": 1}
	if value, err := lookup(data, "b"); err != nil {
		var missing *NotFound
		if errors.As(err, &missing) {
			fmt.Println("as:", missing.Key)
		}
		fmt.Println("is nil error:", err == nil)
	} else {
		fmt.Println(value)
	}

	text := "héllo"
	fmt.Println(len(text), len([]rune(text)))
	for index, letter := range text {
		fmt.Printf("%d:%c ", index, letter)
	}
	fmt.Println()

	total := 0
	defer func() { fmt.Println("deferred total:", total) }()
	for i := 0; i < 3; i++ {
		defer func() { total += i }()
	}
	total = 100
}
""",
            "Run the example and explain the two slice addresses, the deferred total, and why `errors.As` needs a "
            "pointer to the error type. Then write a function that returns a typed nil as `error` and show that "
            "`err != nil` is true, then fix it. Finally, measure the allocation difference between string "
            "concatenation and `strings.Builder` with a benchmark. Practise with "
            "/practice/problems/group-anagrams.",
        ),
        (
            "go-stdlib-deep",
            "The Go standard library: strings to servers",
            "strconv and time, context and deadlines, encoding/json tags and numbers, net/http client and "
            "server defaults, io composition, sync primitives and the testing tools.",
            r"""**Why this matters.** Go's standard library is the reason many Go services have no framework: a
production HTTP server, a JSON API, a CLI and a test suite ship with the toolchain. The catch is
that the defaults are deliberate and sometimes sharp - an `http.Client` with no timeout waits
forever, `json.Unmarshal` into `interface{}` turns every number into a float, and `time.Time`
carries a monotonic clock reading that equality checks must respect. This module is the map with
the sharp edges marked.

**Strings and conversion.** `strings` has `Cut`, `Split`, `Fields`, `Join`, `ReplaceAll`, `TrimSpace`,
`HasPrefix`, `Contains`, `Builder`; `strconv` has `Atoi`, `Itoa`, `ParseInt`, `ParseFloat`,
`FormatFloat`, `Quote`, `Unquote`. `fmt.Sprintf` is convenient and slow in a hot loop;
`strconv.AppendInt` appends without allocating. `strings.Cut` is the modern replacement for
`SplitN(s, sep, 2)` and returns a found flag. `strings.EqualFold` is Unicode case-folding; `==` is
byte equality. `unicode/utf8` gives `RuneCountInString`, `ValidString` and `DecodeRuneInString`.
`bytes` mirrors the string functions for byte slices without converting.

**Numbers.** `int` is 32 or 64 bits depending on the platform; use `int64`/`uint64` for wire formats
and `int` for indices. `strconv.Atoi` returns an error; `fmt.Sscanf` is slower and looser. Overflow
in `int` arithmetic wraps silently; `math/bits` and `math` provide checked patterns. Floating
formatting: `%f` fixed, `%g` compact, `%e` exponent, `%.2f` two decimals. `math.Round` rounds half
away from zero; `math.RoundToEven` is banker's rounding.

**Time and durations.** `time.Time` is a struct with wall clock and monotonic reading; `Sub` and
`Before` use the monotonic part when both have it, `==` does not. Use `time.Time.Equal` for
comparison and `t.Truncate`/`t.Round` for buckets. `time.Duration` is an `int64` of nanoseconds;
`5 * time.Second` is readable, `5000` is not. `time.Now()` is local; `time.Now().UTC()` is explicit.
`time.LoadLocation("Asia/Kolkata")` needs the tzdata (embed it with `time/tzdata` for containers);
`time.FixedZone` is for offsets without rules. Timers: `time.After` leaks until it fires in a
loop - use `time.NewTimer` and `Stop` when the select takes another branch.

**Context.** `context.Context` carries cancellation, deadlines and request-scoped values across API
boundaries. `context.WithTimeout` and `WithCancel` return a cancel function that must always be
called, or the timer leaks until the deadline. `ctx.Done()` is a channel closed on cancellation;
`ctx.Err()` says why. Values are for request metadata (trace id, auth subject), not for optional
parameters or dependencies. Never store a context in a struct; pass it as the first parameter. A
function that does not accept a context cannot be cancelled.

**JSON.** `encoding/json` uses exported fields and `json:"name,omitempty"` tags; `-` skips a field;
`string` on a number parses a quoted number. `omitempty` omits zero values, including `0` and
`false`, which is often not what a protocol wants - use a pointer or a custom marshaler when the
distinction matters. `json.Number` preserves numeric precision; unmarshalling into `interface{}`
produces `float64`, which loses integers above 2^53. `Decoder` streams and `DisallowUnknownFields`
catches typos; `Encoder.SetEscapeHTML(false)` stops escaping `<` and `>`. `json.Marshal` cannot
serialise channels, functions or cycles; it silently ignores unexported fields.

**net/http.** The default `http.Client` has no timeout, so a hung server hangs the caller forever;
create one with `Timeout` and a transport with sane dial and TLS handshake timeouts. Always
`defer response.Body.Close()` and drain the body (`io.Copy(io.Discard, resp.Body)`) to reuse the
connection. `http.Server` needs `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout` and `IdleTimeout`
- without them a slow client holds a connection. The default `ServeMux` in Go 1.22 supports method
and wildcard patterns (`"GET /orders/{id}"`, `r.PathValue("id")`). Middleware is a
`func(http.Handler) http.Handler`; wrap the handler, do not mutate global state.

**IO composition.** `io.Reader` and `io.Writer` are the interfaces everything composes around:
`io.Copy`, `io.ReadAll`, `io.LimitReader`, `io.MultiWriter`, `io.TeeReader`, `bufio.Scanner` (line
length limit 64 KiB by default - raise it with `Buffer`), `bufio.Reader`/`Writer` for buffering.
`os.Open` returns a `*os.File` that must be closed; `os.ReadFile` is the one-shot form.
`filepath.Join`/`Dir`/`Base`/`Ext` are OS-correct; `path` is for URL paths, `filepath` for the
filesystem. `os.MkdirAll` and `os.RemoveAll` are the tree operations.

**Concurrency primitives.** `sync.Mutex`/`RWMutex` for shared state, `sync.WaitGroup` for waiting,
`sync.Once` for one-time init, `sync/atomic` for counters, `errgroup.Group` (golang.org/x/sync) for
error-propagating groups, channels for ownership transfer. A buffered channel is a queue with a
bound; an unbuffered channel is a rendezvous. `select` with `default` is a non-blocking attempt;
`select` with `ctx.Done()` is how work is cancelled. Close a channel from the sender, never the
receiver, and never close it twice.

**Testing.** `testing` with table-driven tests, `t.Run` subtests, `t.Parallel`, `t.Cleanup`,
`t.TempDir`, `t.Helper`. `go test -race` is mandatory in CI; `-cover` reports coverage;
`-fuzz` explores inputs for parsers; `testing.B` benchmarks with `-benchmem` show allocations.
`httptest.NewServer` tests a client; `httptest.NewRecorder` tests a handler. Golden files make
output tests readable.

| Boundary | Default | What to set |
| --- | --- | --- |
| `http.Client` | No timeout | `Timeout`, dial and TLS handshake timeouts |
| `http.Server` | Unlimited read/write | `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, `IdleTimeout` |
| Context | `context.Background()` in a handler | `r.Context()` |
| JSON decode | `float64` for every number | `json.Number` or a typed struct |
| Body | Left open | `defer Body.Close()` plus draining |
| Timers in a loop | `time.After` leaks until it fires | `NewTimer` + `Stop` |

**The judgment call.** Set every timeout explicitly, pass contexts everywhere, decode JSON into
typed structs with `json.Number` where precision matters, close bodies, and compose with `io`
rather than reading whole files. The standard library is a production framework; the defaults are
not the policy.""",
            r"""package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Order struct {
	ID       string    `json:"id"`
	Customer string    `json:"customer"`
	Total    float64   `json:"total"`
	PlacedAt time.Time `json:"placed_at"`
}

type store struct{ orders map[string]Order }

func (s *store) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /orders/{id}", func(w http.ResponseWriter, r *http.Request) {
		order, ok := s.orders[r.PathValue("id")]
		if !ok {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		w.Header().Set("content-type", "application/json")
		if err := json.NewEncoder(w).Encode(order); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
	})
	return mux
}

func fetch(ctx context.Context, client *http.Client, url string) ([]byte, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("get %s: %w", url, err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("get %s: status %d", url, response.StatusCode)
	}
	return body, nil
}

func main() {
	data := []byte(`{"id":"o-1","customer":"ana","total":19.5,"placed_at":"2026-01-02T10:00:00Z"}`)
	var order Order
	if err := json.Unmarshal(data, &order); err != nil {
		panic(err)
	}
	fmt.Println(order.ID, order.Customer, order.Total, order.PlacedAt.UTC())

	var decoded map[string]any
	_ = json.Unmarshal(data, &decoded)
	fmt.Printf("interface number type: %T\n", decoded["total"])

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	client := &http.Client{Timeout: time.Second}
	_, err := fetch(ctx, client, "http://127.0.0.1:1/orders/o-1")
	fmt.Println("fetch error:", err != nil, errors.Is(err, context.DeadlineExceeded))

	started := time.Now()
	time.Sleep(5 * time.Millisecond)
	fmt.Println("elapsed:", time.Since(started) >= 5*time.Millisecond)

	parts := strings.Split("a,b,,c", ",")
	fmt.Println(parts, strings.Join(parts, "|"))
}
""",
            "Add a `ReadHeaderTimeout` and `WriteTimeout` to an `http.Server`, then send it a slow request and show "
            "the difference. Decode a JSON object with a large integer into `float64` and into `json.Number`, and "
            "compare the values. Finally, write a table-driven test with `t.Run` and `t.Parallel`, run it under "
            "`-race`, and fix any race it reports. Practise with /practice/problems/top-k-frequent.",
        ),
        (
            "go-diagnostics-deep",
            "Diagnosing Go: errors, races, leaks and traces",
            "Error wrapping and context, panics and stack dumps, the race detector, pprof profiles, "
            "goroutine leaks, and the compile and module errors you will actually meet.",
            r"""**Why this matters.** Go programs fail quietly in ways other languages do not: a goroutine that
never exits, a ticker that is never stopped, a `context.Background()` where a request context was
meant, a map written by two goroutines. The toolchain has an answer for every one of them, and the
answers are built into the binary - pprof, the race detector, execution traces and full goroutine
dumps. This module teaches when to run which.

**Errors carry context, not stacks.** Go has no exceptions, so the call chain is rebuilt by
wrapping: `fmt.Errorf("loading config %s: %w", path, err)`. `%w` preserves the chain for
`errors.Is`/`errors.As`; `%v` flattens it. Wrap at each layer with information the caller does not
have, and stop wrapping when the message would repeat. A sentinel error is a value the caller can
test; a custom type is a value the caller can inspect. `errors.Join` (Go 1.20) combines several
failures, which is what a batch operation needs. Never compare `err.Error()` strings.

**Panics are for programmer errors.** A panic unwinds the goroutine and, if nothing recovers,
prints the panic value and every goroutine's stack, then exits. `recover` only works inside a
deferred function in the same goroutine, and it should convert a panic to an error at the boundary
of a server or a worker, not inside library code. The `debug.Stack()` output is the diagnostic;
`runtime/debug.SetTraceback("all")` adds more detail for crashes.

**The race detector.** `go test -race` (and `go run -race`) instruments memory access and reports
the two conflicting accesses with their goroutines and stacks. It finds races only on executed
paths, so it is a detector, not a proof. A race report is a real bug even if the value "looks
fine": the Go memory model gives no guarantee. Fix it with a mutex, an atomic, or by transferring
ownership through a channel. `go vet` catches the static subset: copying a lock, a lost cancel, a
loop variable capture before Go 1.22, a `Printf` verb mismatch.

**pprof.** Import `net/http/pprof` for a server, or write a profile in a test/CLI:
`pprof.StartCPUProfile`, `pprof.WriteHeapProfile`, `runtime/pprof.Lookup("goroutine").WriteTo`.
Then `go tool pprof -http=:0 profile` opens a flame graph and a top list. The profiles that matter:
CPU (`/debug/pprof/profile?seconds=30`), heap (`/debug/pprof/heap`, in-use vs allocated),
goroutine (`/debug/pprof/goroutine?debug=2` shows every stack), block (blocking on sync), mutex
(contended mutexes) and trace (`go tool trace`, for scheduler latency and GC pauses). `GODEBUG=gctrace=1`
prints GC cycles and heap size.

**Goroutine leaks.** A goroutine blocked forever on a channel send, a `select` with no cancellation
case, a `time.Ticker` never stopped, an HTTP response body never closed, or a `context.WithCancel`
whose cancel was dropped. The goroutine profile shows the count and the stacks; a leak grows
monotonically. The patterns that prevent it: every long-lived goroutine takes a `ctx` and selects
on `ctx.Done()`, every ticker is stopped, every response body is closed, and every `WaitGroup` is
waited before the function returns. `errgroup.WithContext` cancels siblings when one returns an
error and is the right default for a fan-out.

**Context mistakes.** `context.Background()` inside a request handler discards the caller's
deadline and cancellation; use `r.Context()`. Storing a context in a struct hides the lifetime.
Passing a context to a function that does not need one is noise, but a function that performs I/O
without one cannot be cancelled. `context.WithValue` keys must be an unexported type to avoid
collisions; values are for request metadata.

**Compile and module errors.** `declared and not used` is a compile error, not a warning;
`unused variable` can be silenced with `_` but a silent discard is a bug waiting to happen.
`import cycle not allowed` means two packages reference each other; move the shared type to a third
package or invert the dependency with an interface. `missing go.sum entry` is fixed by `go mod
download`/`go mod tidy`; a version conflict is visible in `go mod graph` and resolved with `replace`
only as a last resort. `cannot use x (variable of type T) as U` usually means a pointer/value
mismatch in a method set.

**Benchmarks and allocations.** `go test -bench . -benchmem` reports ns/op and allocs/op. Escape
analysis (`go build -gcflags=-m`) shows what moved to the heap. `sync.Pool` helps with many
short-lived buffers but adds complexity; `strings.Builder` and preallocated slices are usually
enough. Measure before optimising; the compiler inlines and bounds-check-eliminates more than you
expect.

**Logging and observability.** `log/slog` (Go 1.21) is structured logging: `slog.Info("order
failed", "order_id", id, "err", err)`. The default handler is text; JSON is for machines. Request
ids belong in the context and in every log line. Metrics (`expvar` or a client library) and traces
(OpenTelemetry) answer different questions: metrics for rate and saturation, traces for where the
time went across services.

| Question | Profile or tool | What it shows |
| --- | --- | --- |
| Where is the CPU time? | `pprof` CPU profile | Sampled stacks by function |
| Why does the heap grow? | `pprof` heap (in-use) | Live objects by allocation site |
| Why did a goroutine stop? | `pprof` goroutine `debug=2` | Every goroutine's stack |
| Where is a lock blocking? | `pprof` block / mutex | Wait time by call site |
| Why is latency spiky? | `go tool trace` | Scheduler, GC and syscall timeline |
| Did two goroutines race? | `go test -race` | Both accesses with their stacks |

**The judgment call.** Wrap errors with `%w`, treat `-race` as non-negotiable, take a goroutine
profile when memory or goroutine count grows, and give every goroutine a cancellation path. Most Go
production problems are ownership problems, and ownership is visible in the stack trace if you
know where to look.""",
            r"""package main

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

var ErrNotFound = errors.New("not found")

type Cache struct {
	mu    sync.RWMutex
	items map[string]string
}

func NewCache() *Cache { return &Cache{items: make(map[string]string)} }

func (c *Cache) Get(key string) (string, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	value, ok := c.items[key]
	if !ok {
		return "", fmt.Errorf("cache %q: %w", key, ErrNotFound)
	}
	return value, nil
}

func (c *Cache) Set(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items[key] = value
}

func (c *Cache) Warm(ctx context.Context, keys []string) error {
	var group sync.WaitGroup
	errs := make(chan error, len(keys))
	for _, key := range keys {
		group.Add(1)
		go func(key string) {
			defer group.Done()
			select {
			case <-ctx.Done():
				errs <- ctx.Err()
			case <-time.After(10 * time.Millisecond):
				c.Set(key, "warm")
			}
		}(key)
	}
	group.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			return err
		}
	}
	return nil
}

func main() {
	cache := NewCache()
	cache.Set("a", "1")

	value, err := cache.Get("a")
	fmt.Println(value, err == nil)

	_, err = cache.Get("missing")
	fmt.Println(errors.Is(err, ErrNotFound), err)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Millisecond)
	defer cancel()
	fmt.Println("warm:", cache.Warm(ctx, []string{"b", "c", "d"}))

	done := make(chan struct{})
	go func() { defer close(done); time.Sleep(2 * time.Millisecond) }()
	select {
	case <-done:
		fmt.Println("worker finished")
	case <-time.After(50 * time.Millisecond):
		fmt.Println("worker timed out")
	}
}
""",
            "Run the example under `go run -race`, then introduce a data race by removing the mutex from `Get` and "
            "observe the report. Start a goroutine that blocks on a channel send and capture a goroutine profile "
            "with `pprof.Lookup(\"goroutine\")`. Finally, write a benchmark for a string-building function, compare "
            "concatenation with `strings.Builder`, and check the allocations with `-benchmem`. Practise with "
            "/practice/problems/course-schedule.",
        ),
    ],
}

MODULE_PRACTICE: dict[str, str] = {
    "csharp-semantics-deep": "single-number",
    "csharp-stdlib-deep": "top-k-frequent",
    "csharp-diagnostics-deep": "validate-ipv4",
    "go-semantics-deep": "group-anagrams",
    "go-stdlib-deep": "top-k-frequent",
    "go-diagnostics-deep": "course-schedule",
}
