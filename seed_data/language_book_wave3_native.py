"""Depth wave 3, part three: C and C++ semantics modules.

These cover the object model, the standard library and the diagnostic
toolchain, in the same legacy body/example/exercise shape as the rest of the
academy. Each module points at an existing judged problem.
"""

BOOK_MODULES: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "c": [
        (
            "c-semantics-deep",
            "The C object model: types, storage and undefined behaviour",
            "Integer conversions and promotions, aliasing, alignment and padding, storage duration, "
            "evaluation order and the undefined-behaviour rules that make optimisation legal.",
            r"""**Why this matters.** C is not a portable assembler; it is a language with an abstract
machine, and the compiler is allowed to assume that your program never leaves it. That is the
source of both C's speed and its most confusing failures: a program that "works" in a debug build
can change behaviour at `-O2` because it had undefined behaviour all along. This module is the
object model that the standard actually specifies, written so you can predict what the compiler is
entitled to do.

**Every object has a type, a size, an alignment and a storage duration.** The type decides which
operations are defined and how the bytes are interpreted. `sizeof` is in bytes (`char` is one byte
by definition; it may be more than eight bits on exotic hardware). `_Alignof` gives the alignment
requirement; padding exists so every object of a type is aligned, and it is why a struct's size is
not the sum of its members. Reordering members from largest to smallest alignment usually shrinks a
struct; `offsetof` reads the actual layout, and the layout is not part of the standard except for
the first member.

**Integer conversions happen constantly.** `char` and `short` promote to `int` in arithmetic, so a
computation that "fits in a short" may be done at `int` width. When two operands have different
ranks, the lower one converts to the higher; if the signed type cannot represent every value of the
unsigned type, the signed operand converts to unsigned. That is why `-1 < 1u` is false: the `-1`
becomes `UINT_MAX`. The rule is the usual arithmetic conversions, not a special case, and it is
worth tracing once by hand.

**Signed overflow is undefined; unsigned overflow wraps.** `INT_MAX + 1` is not guaranteed to be
`INT_MIN`. The compiler may assume it never happens and exploit that assumption in loop
optimisation. Unsigned arithmetic is defined modulo 2^N, which makes it tempting for hashing and
checksums - but it is also a source of bugs when a length underflows to a huge value. Use
`<stdint.h>` types (`int32_t`, `uint64_t`) when width matters, and check before adding if overflow
would be a correctness problem.

**Strict aliasing.** The compiler assumes that a pointer to `int` and a pointer to `float` do not
alias the same memory. Reading a `float` through an `int*` is undefined behaviour, even if the
bytes "look right". The legal ways to reinterpret bytes are `memcpy` (which the compiler optimises
back to a load), a `union` in the common initial sequence, or `char*`/`unsigned char*`, which are
allowed to alias anything. Breaking this rule produces code that works at `-O0` and fails at `-O2`,
which is the most expensive class of bug to diagnose.

**Alignment and pointer validity.** A misaligned access is undefined on some architectures and
slow on others; `_Alignas` requests alignment, and `malloc` returns memory aligned for any
fundamental type. Pointer arithmetic is defined only within an array object (including one past
the end); a pointer to a different object may not be compared or subtracted, even if the addresses
look ordered. Converting an integer to a pointer and back is implementation-defined, not portable.
`NULL` is a null pointer constant; a freed pointer is indeterminate, and using it is undefined even
though it usually "works".

**Storage duration and linkage.** Automatic objects live until the block exits; `static` inside a
function lives for the program and is initialised once; file-scope `static` has internal linkage;
`extern` declares a definition elsewhere. `thread_local` gives one object per thread. The order of
initialisation across translation units is unspecified, which is the static initialisation order
fiasco - a global constructor that reads another global may read zero. Prefer function-local
statics, which initialise on first use (and are thread-safe in C11).

**Evaluation order.** C does not define the order in which function arguments are evaluated, nor
the order of the operands of most binary operators. `f(i++, i++)` is undefined; `a[i] = i++` is
undefined. The only sequencing guarantees come from `&&`, `||`, the conditional operator, the comma
operator, and full expressions separated by semicolons or sequence points. If two side effects on
the same scalar are unsequenced, the program is undefined - not "implementation-dependent", but
undefined, which means the compiler may do anything.

**Bit-fields and unions.** Bit-fields have implementation-defined layout and signedness; use them
for hardware registers only with the compiler's documented rules. A union reinterprets the storage;
reading a member other than the one last written is implementation-defined for most types and
undefined for some. `memcpy` is the portable byte reinterpretation.

**`const` and `volatile` are qualifiers, not guarantees.** `const` means you may not modify through
that lvalue; another pointer may still modify the object. `volatile` means every access is
observable and must not be optimised away - it is for memory-mapped hardware and signal handlers,
not for inter-thread communication. Concurrency needs `<stdatomic.h>` or a library with real
memory-ordering semantics.

| Instead of | Write | Because |
| --- | --- | --- |
| `int x; x += y;` | Check the range first | Signed overflow is undefined |
| `float f = *(float *)&bits;` | `memcpy(&f, &bits, sizeof f)` | Strict aliasing |
| `a[i] = i++;` | Separate statements | Unsequenced modification |
| `char c = getchar(); isalpha(c);` | `isalpha((unsigned char)c)` | ctype is undefined for negative values |
| Comparing a length with a signed int | `size_t` throughout | Conversion changes the meaning |

**The judgment call.** Choose fixed-width types where width matters, check before arithmetic can
overflow, reinterpret through `memcpy` rather than casts, and treat every compiler warning as a
bug report. Undefined behaviour is a contract you keep even when the test passes.""",
            r"""#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct Packet {
    uint8_t kind;
    uint32_t length;
    uint16_t checksum;
};

static uint32_t read_u32(const unsigned char *bytes) {
    uint32_t value;
    memcpy(&value, bytes, sizeof value);   /* legal byte reinterpretation */
    return value;
}

int main(void) {
    printf("sizeof(struct Packet) = %zu\n", sizeof(struct Packet));
    int minus_one = -1;
    unsigned int one = 1u;
    printf("-1 < 1u      = %d\n", (unsigned int)minus_one < one);
    printf("CHAR_BIT     = %d\n", 8);

    unsigned char raw[4] = {0x78, 0x56, 0x34, 0x12};
    printf("read_u32     = 0x%08x\n", read_u32(raw));

    uint32_t small = 0;
    small--;                                /* defined: wraps to UINT32_MAX */
    printf("small        = %u\n", small);

    int32_t big = INT32_MAX;
    printf("big          = %d\n", big);
    /* INT32_MAX + 1 would be undefined behaviour; check before adding. */
    if (big < INT32_MAX) {
        big += 1;
    }
    printf("big unchanged= %d\n", big);

    struct Packet packet = {.kind = 1, .length = 42, .checksum = 0xBEEF};
    printf("length       = %u\n", packet.length);
    return 0;
}
""",
            "Compile the example at `-O0` and `-O2` and confirm the output is identical. Then write a function that "
            "adds two `int` values and reports overflow without invoking undefined behaviour, and another that "
            "reinterprets a `float` as bytes with `memcpy`. Finally, explain why `-1 < 1u` is false in terms of the "
            "usual arithmetic conversions. Practise with /practice/problems/xor-checksum.",
        ),
        (
            "c-stdlib-deep",
            "The C standard library: the functions and the traps",
            "stdio buffering and format strings, the string functions and their bounded forms, malloc and "
            "friends, conversion with error checking, time, limits and the thread/atomic headers.",
            r"""**Why this matters.** The C standard library is small, old and full of functions whose
failure modes are not in the name. `strcpy` has no length; `scanf` returns the number of successful
conversions, not a boolean; `realloc` may move the block and free the original pointer's contents if
you overwrite it first. Knowing the contract of each family - and the bounded alternative where one
exists - is most of writing C that does not corrupt memory.

**stdio and buffering.** `printf` writes to a `FILE*` buffer, which is flushed when it fills, when
the program exits normally, or on `fflush`. A crash loses buffered output, which is why debug
prints sometimes disappear. `stderr` is unbuffered by default, so error messages survive. Return
values matter: `printf` returns the number of characters written or a negative value on error;
`fgets` returns `NULL` at end of file or on error, and you must check `feof`/`ferror` to tell them
apart. `fclose` flushes; skipping it is a resource leak and can lose data. Set `stdout` to line
buffered when output is interactive, fully buffered when it is a pipe.

**Format strings are a type system.** `%d` with a `long` is undefined behaviour. The correct form
is `%ld`, `%zu` for `size_t`, `%zu` for `sizeof`, `%jd` with `intmax_t`, `%f` for `double` (there is
no `%lf` distinction in `printf`; `scanf` does distinguish), `%s` with a null-terminated string and
`%.Ns` to bound it, `%p` for a pointer cast to `void*`. `snprintf` returns the length that *would*
have been written, which lets you detect truncation: a return value greater than or equal to the
buffer size means the output was cut. `sprintf` has no bound and should not appear in new code.

**String functions.** `strlen` walks until a null byte; `strcpy`, `strcat` and `sprintf` write
without a bound; `strncpy` pads with zeros and does not guarantee termination - it is not a safe
`strcpy`. The bounded forms are `snprintf`, `strncat` with the remaining size, and in Annex K
(optional, poorly supported) `strcpy_s`. `memcpy` requires non-overlapping regions; `memmove`
handles overlap. `strcmp` returns a negative, zero or positive value, not necessarily -1 or 1.
`strtok` modifies its input and is not thread-safe or reentrant; `strtok_r` or `strspn`/`strcspn`
are the alternatives. `strchr`/`strrchr`/`strstr` are the search functions; `strdup` is POSIX, not
ISO C.

**Allocation.** `malloc` returns uninitialised memory or `NULL`; `calloc` zeroes; `realloc` grows or
shrinks, may return a different pointer, and on failure returns `NULL` while leaving the original
block valid - so never assign the result directly to the only pointer you have. `free(NULL)` is a
no-op; `free` twice or free a pointer not returned by `malloc` is undefined. A zero-size
`malloc(0)` may return `NULL` or a unique pointer; both are valid. Every allocation needs a
documented owner: the function that allocates or the function that frees, never "whoever remembers".
`alloca` is not standard and grows the stack.

**Conversions with error checking.** `atoi` cannot report failure; `strtol`, `strtoul`, `strtod`
and `strtoll` can. The pattern is: set `errno = 0`, call, check `errno == ERANGE`, check
`endptr == start` for "no digits", and check `*endptr` for trailing junk. `sscanf` returns the
number of assignments, so `if (sscanf(text, "%d", &n) != 1)` is the check. Without these, "abc"
becomes zero and a malformed input silently becomes a valid number.

**Math, characters and errors.** `<math.h>` functions set `errno` and return `NaN` or `HUGE_VAL`
on domain and range errors; check both. `isnan`/`isinf`/`fpclassify` classify floating values.
`<ctype.h>` functions are defined only for `EOF` and `unsigned char` values - passing a negative
`char` is undefined, so cast to `unsigned char`. They are locale-dependent: `isdigit` is fine,
`isalpha` changes with the locale.

**Time.** `time_t` is an implementation-defined arithmetic type, usually seconds since the epoch.
`localtime` and `gmtime` return pointers to static storage and are not thread-safe; `localtime_r`
and `gmtime_r` are POSIX. `strftime` formats with the current locale; `mktime` interprets local
time and normalises out-of-range fields. Durations need `clock_gettime(CLOCK_MONOTONIC)`, not
wall-clock time, and `clock()` measures CPU time, not elapsed time.

**Limits, assertions and signals.** `<limits.h>` and `<float.h>` give the ranges; `INT_MAX` is not
assumed to be 2^31 - 1. `assert` is compiled out with `NDEBUG`, so it must not have side effects.
`signal` has implementation-defined semantics for anything beyond `SIG_IGN`/`SIG_DFL`;
`sigaction` is the POSIX interface. A signal handler may call only async-signal-safe functions;
`printf` is not one.

**Threads and atomics.** C11 adds `<threads.h>` and `<stdatomic.h>`, but support varies; in
practice most code uses POSIX threads or a library. `_Atomic` types and `atomic_load`/
`atomic_store`/`atomic_fetch_add` with explicit memory orders are the portable primitives. A
`volatile` flag is not a substitute.

| Job | Use | Avoid |
| --- | --- | --- |
| Copy a string into a buffer | `snprintf(buf, size, "%s", src)` | `strcpy`, `sprintf` |
| Concatenate with a bound | `strncat(buf, src, size - strlen(buf) - 1)` | `strcat`, `strncpy` |
| Convert text to a number | `strtol` with `endptr` and `errno` | `atoi` |
| Read a line | `fgets`/`getline` | `gets` |
| Compare strings | `strcmp` / `strncmp` | `==` on arrays |
| Copy overlapping ranges | `memmove` | `memcpy` |

**The judgment call.** Prefer the bounded function, check every return value that can fail, and
convert text with `strtol`-family functions rather than `atoi`. Give every allocation one owner,
and treat `errno` as valid only immediately after a call that documents it.""",
            r"""#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int parse_port(const char *text, int *out) {
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0') return -1;
    if (value < 0 || value > 65535) return -1;
    *out = (int)value;
    return 0;
}

int main(void) {
    char buffer[16];
    int written = snprintf(buffer, sizeof buffer, "%s:%d", "localhost", 8080);
    printf("written=%d buffer=%s truncated=%d\n", written, buffer, written >= (int)sizeof buffer);

    int port = 0;
    const char *samples[] = {"8080", "70000", "80x", ""};
    for (size_t i = 0; i < sizeof samples / sizeof samples[0]; i++) {
        int ok = parse_port(samples[i], &port);
        printf("%-6s -> %s (%d)\n", samples[i], ok == 0 ? "ok" : "rejected", port);
    }

    size_t count = 8;
    int *values = malloc(count * sizeof *values);
    if (values == NULL) {
        fprintf(stderr, "out of memory\n");
        return 1;
    }
    for (size_t i = 0; i < count; i++) values[i] = (int)(i * i);

    int *grown = realloc(values, count * 2 * sizeof *values);
    if (grown == NULL) {
        free(values);
        return 1;
    }
    values = grown;
    for (size_t i = count; i < count * 2; i++) values[i] = 0;
    printf("sum-first-half=%d\n", values[3] + values[5]);
    free(values);

    printf("INT_MAX=%d\n", INT_MAX);
    printf("strcmp=%d\n", strcmp("apple", "banana") < 0);
    return 0;
}
""",
            "Compile the example and add a case that overflows `long`, one with leading whitespace and one with a sign. "
            "Explain why `realloc` was assigned to a temporary. Then write a function that reads a line of unknown "
            "length with `getline`, and one that copies a string with `snprintf`, reporting truncation. Finally, "
            "replace an `atoi` in your own code with the checked pattern. Practise with "
            "/practice/problems/validate-ipv4.",
        ),
        (
            "c-diagnostics-deep",
            "Warnings, sanitizers and production C failures",
            "Compiler diagnostics that find real bugs, the sanitizer matrix, gdb and core dumps, and a "
            "catalogue of crashes with the cause behind each signal.",
            r"""**Why this matters.** C fails at the memory level: a wrong pointer does not raise an
exception, it corrupts a neighbouring object and crashes somewhere else. The compiler and the
toolchain know a great deal about these failures, but only if you ask. A project built with
`-Wall -Wextra` and run under AddressSanitizer finds in minutes the bugs that otherwise take a week
of `printf`.

**Turn on the diagnostics.** At minimum `-Wall -Wextra -Wpedantic`; for new code add
`-Wconversion -Wsign-conversion -Wshadow -Wcast-qual -Wstrict-prototypes -Wmissing-prototypes`.
`-Werror` is right in CI and wrong on a developer's machine during an upgrade. `clang` and `gcc`
differ in which warnings exist; run both when you can, because they catch different things.
`-fanalyzer` (GCC) and `clang --analyze` run a static analysis pass that finds leaks, double frees
and null dereferences without executing the program.

**The sanitizers.** Use them in a separate build, never in production:
| Sanitizer | Flag | Finds |
| --- | --- | --- |
| AddressSanitizer | `-fsanitize=address` | use-after-free, overflow, double free, leaks (with LSan) |
| UndefinedBehaviorSanitizer | `-fsanitize=undefined` | signed overflow, shifts, misaligned access, null deref |
| ThreadSanitizer | `-fsanitize=thread` | data races (not with ASan) |
| MemorySanitizer | `-fsanitize=memory` | reads of uninitialised memory (Clang only) |
| LeakSanitizer | `-fsanitize=leak` | leaks at exit |

Compile with `-g -O1 -fno-omit-frame-pointer` for readable reports. ASan reports the allocation and
free stack for a use-after-free, which is usually the entire diagnosis. UBSan prints the exact
expression and type. TSan reports both stacks in a race. Valgrind's `memcheck` does similar work
more slowly and without recompiling.

**Signals are the C error messages.** `SIGSEGV` is an invalid memory access: a null or wild
pointer, a stack overflow, or a write to read-only memory. `SIGABRT` comes from `abort()` or a
failed assertion, and glibc's "stack smashing detected" means a buffer overflow overwrote the
canary. `SIGFPE` is integer division by zero (or `INT_MIN / -1`), not a floating-point exception.
`SIGILL` is an illegal instruction, often a corrupted function pointer or a jump into data.
`SIGBUS` is a misaligned access or a mapped file truncated underneath you.

**gdb in ten commands.** `run`, `bt` (backtrace), `frame N`, `info locals`, `print expr`, `p *ptr`,
`break file:line`, `next`/`step`, `continue`, `watch expr`, `x/16x address`, `info registers`,
`thread apply all bt`. A core dump plus `gdb program core` gives the same backtrace after the fact;
enable cores with `ulimit -c unlimited`. Compile with `-g -O0` for a debuggable build, and keep a
release build with `-g` symbols separately if you need to symbolicate production crashes.

**A catalogue of failures and causes.**
| Symptom | Likely cause | Tool |
| --- | --- | --- |
| Segfault at a small address | Null pointer dereference | ASan, gdb |
| Segfault inside `free` | Heap corruption from an earlier overflow | ASan |
| Works at `-O0`, fails at `-O2` | Undefined behaviour, strict aliasing | UBSan, `-fno-strict-aliasing` to confirm |
| "stack smashing detected" | Buffer overflow past a stack array | ASan, `-fstack-protector` |
| Random output changes | Uninitialised variable or read past a buffer | MSan/Valgrind |
| Leak that grows per request | Missing free on an error path | LSan, Valgrind |
| Deadlock | Lock order inversion | TSan, gdb thread backtraces |

**Assertions and defensive interfaces.** `assert` is for invariants, not input; the library should
return an error code or set `errno` for anything that can fail at runtime. Document the ownership
contract of every pointer parameter in the header (`const`, borrowed, transferred). A function that
takes a buffer also takes its length, in that order, so the pair cannot be separated by a refactor.
`restrict` is a promise the caller makes; breaking it is undefined.

**Reproducing a bug.** Record the compiler version, the exact flags, the library versions, the
input, the environment and the build type. A crash that cannot be reproduced is usually a build
difference or an uninitialised read; ASan with `-O1` is the fastest way to make it deterministic.
Keep a failing test that runs under the sanitizer in CI, so the bug cannot silently return.

**The judgment call.** Warnings first, sanitizers second, debugger third. If a C program behaves
differently between optimisation levels, stop looking for the bug in the optimiser: the program has
undefined behaviour and the optimiser is doing exactly what the standard allows.""",
            r"""#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Buffer {
    char *data;
    size_t length;
    size_t capacity;
};

static int buffer_reserve(struct Buffer *buffer, size_t needed) {
    if (needed <= buffer->capacity) return 0;
    size_t capacity = buffer->capacity ? buffer->capacity : 16;
    while (capacity < needed) {
        if (capacity > SIZE_MAX / 2) return -1;
        capacity *= 2;
    }
    char *grown = realloc(buffer->data, capacity);
    if (grown == NULL) return -1;
    buffer->data = grown;
    buffer->capacity = capacity;
    return 0;
}

static int buffer_append(struct Buffer *buffer, const char *text) {
    size_t add = strlen(text);
    if (add > SIZE_MAX - buffer->length - 1) return -1;
    if (buffer_reserve(buffer, buffer->length + add + 1) != 0) return -1;
    memcpy(buffer->data + buffer->length, text, add + 1);
    buffer->length += add;
    return 0;
}

int main(void) {
    struct Buffer buffer = {0};
    if (buffer_append(&buffer, "sanitizer") != 0 ||
        buffer_append(&buffer, " finds ") != 0 ||
        buffer_append(&buffer, "the cause") != 0) {
        fprintf(stderr, "allocation failed\n");
        free(buffer.data);
        return 1;
    }
    printf("%s (%zu bytes in %zu capacity)\n", buffer.data, buffer.length, buffer.capacity);
    free(buffer.data);
    return 0;
}
""",
            "Build the example four ways: plain, `-fsanitize=address,undefined`, `-fsanitize=leak`, and `-O2` with "
            "warnings as errors. Then break it deliberately - free twice, drop the `+1` in the reserve call, and "
            "remove the overflow check - and record the exact diagnostic each sanitizer prints. Finally, capture "
            "a core dump from a null dereference and read the backtrace in gdb. Practise with "
            "/practice/problems/xor-checksum.",
        ),
    ],
    "cpp": [
        (
            "cpp-semantics-deep",
            "Objects, lifetimes and the rules the compiler enforces",
            "Value categories, copy and move, RAII and destructor order, virtual dispatch and slicing, "
            "initialisation forms, const correctness, and the undefined behaviour that survives compilation.",
            r"""**Why this matters.** C++ gives you control over object lifetime, and almost every
advanced feature is a consequence of that control: RAII, smart pointers, move semantics, exception
safety. The rules are precise, and the compiler enforces most of them at compile time. The ones it
cannot enforce - lifetime after move, dangling references, slicing, static initialisation order -
are exactly the ones that produce the crashes this module teaches you to predict.

**Value categories.** An expression is an lvalue (has an identity and can be assigned), a prvalue (a
temporary that initialises an object), or an xvalue (an object about to be moved from). The
category decides which overload binds: `f(T&)` takes lvalues, `f(const T&)` takes lvalues and
temporaries, `f(T&&)` takes rvalues and is the hook for move semantics. `std::move` is a cast to
rvalue reference; it does not move anything by itself. After a move, an object is "valid but
unspecified" - you may destroy it or assign to it, not read its value.

**Construction, copy, move and destruction.** The compiler generates a copy constructor, copy
assignment, move constructor, move assignment and destructor unless you declare some of them; the
"rule of zero" says declare none and let members manage themselves, the "rule of five" says if you
need one, declare all five. A user-declared destructor suppresses the implicit move operations,
which silently turns moves into copies. Copy-and-swap gives a strong exception guarantee for
assignment. Member initialisation order follows declaration order, not the order in the
initialiser list, which is why `-Wreorder` exists.

**Copy elision and `std::move`.** Returning a local by value is efficient: the compiler elides the
copy (guaranteed in C++17 for prvalue returns), and even without elision the move is cheap. Do not
`return std::move(local);` - it defeats elision and can pessimise. `std::move` on a `const` object
copies, because the move constructor takes a non-const rvalue reference. Moving a `std::string`
usually leaves it empty, but the standard does not promise that; write code that does not depend on
it.

**RAII.** A resource is acquired in a constructor and released in a destructor. That is the whole
idea, and it is why `std::unique_ptr`, `std::lock_guard`, `std::fstream` and `std::vector` are
correct by construction. Destructors run in reverse order of construction for automatic objects,
and during stack unwinding after an exception. A destructor that throws during unwinding terminates
the program; destructors should be `noexcept`.

**Virtual dispatch, slicing and `override`.** A virtual function is dispatched through the vtable
using the dynamic type. Passing a derived object by value to a function that takes the base copies
only the base subobject - object slicing - and the virtual calls now dispatch to the base. Take
references or pointers for polymorphic interfaces. Mark overrides `override` so a signature drift
is a compile error rather than a new function; mark the base destructor `virtual` (or protected and
non-virtual) so deletion through a base pointer is defined. A class with virtual functions has a
vptr, so its size grows and its layout is implementation-defined.

**Initialisation forms are not equivalent.** `T x;` default-initialises (for a class type, calls the
default constructor; for a fundamental type, leaves it indeterminate). `T x{};` value-initialises
(zeros a fundamental type). `T x = T{};` is copy-initialisation. `T x(y);` is direct-initialisation.
The most vexing parse turns `T x(y);` into a function declaration when `y` is a type name; braces
avoid it. `explicit` on a constructor prevents implicit conversions from a single argument, which
is why `std::vector<int> v = 10;` does not compile.

**`const` correctness.** A `const` member function promises not to modify the observable state and
is callable on const objects; `mutable` members are the exception (caches, mutexes). A `const`
reference extends the lifetime of a temporary bound to it, which is why `const std::string& s =
make();` is safe and `std::string_view sv = make();` is not. `const` on a pointer (`T* const`) and
on the pointee (`const T*`) are different; read the declaration from right to left.

**Undefined behaviour.** Signed overflow, out-of-bounds indexing, dereferencing an invalid pointer,
reading an uninitialised variable, modifying an object through a pointer of the wrong type,
returning a reference to a local, and using an object after its lifetime ended are all undefined.
The optimiser is allowed to assume none of them happen. `std::vector::operator[]` does not check;
`at()` does. `std::string_view` does not own its bytes, so a view into a destroyed string dangles.

**Static initialisation order.** Globals in different translation units initialise in an unspecified
order. A global constructor that reads another global may see zero-initialised storage. Function-
local statics initialise on first use and are thread-safe since C++11; use them for singletons and
registries.

**Exceptions and `noexcept`.** Throwing across a C ABI is undefined; a destructor or a move
constructor that throws breaks the standard containers' guarantees. `noexcept` is part of the type
and enables optimisations (vector reallocation uses move only if the move is noexcept). Catch by
const reference, rethrow with `throw;`, and prefer RAII over `try`/`catch` for cleanup.

| Declaration | Behaviour | When |
| --- | --- | --- |
| `T x;` | Default-initialised (indeterminate for fundamental types) | Inside a class with a constructor |
| `T x{};` | Value-initialised, zeroed | Everything else |
| `T x = other;` | Copy or move, may elide | Returning by value |
| `return std::move(x);` | Forces a move, defeats elision | Never for a local |
| `f(T&)` / `f(const T&)` / `f(T&&)` | Binds lvalue / both / rvalue | The intended category |
| `class D : public B` with a non-virtual `~B` | Deletion through `B*` is undefined | Polymorphic bases need `virtual ~B()` |

**The judgment call.** Let types own resources, declare the rule of zero unless you are writing the
resource wrapper itself, pass polymorphic objects by reference, and prefer value semantics where
the object is small. When the compiler cannot check a rule - lifetime, aliasing, initialisation
order - write the invariant in a comment and test it under a sanitizer.""",
            r"""#include <iostream>
#include <memory>
#include <string>
#include <utility>
#include <vector>

class Buffer {
public:
    explicit Buffer(std::size_t size) : data_(size, 0) {}
    std::size_t size() const noexcept { return data_.size(); }
private:
    std::vector<unsigned char> data_;
};

class Shape {
public:
    virtual ~Shape() = default;
    virtual double area() const = 0;
    virtual std::string name() const = 0;
};

class Square : public Shape {
public:
    explicit Square(double side) : side_(side) {}
    double area() const override { return side_ * side_; }
    std::string name() const override { return "square"; }
private:
    double side_;
};

void print_area(const Shape &shape) {          // reference: no slicing
    std::cout << shape.name() << " " << shape.area() << "\n";
}

int main() {
    std::vector<std::unique_ptr<Shape>> shapes;
    shapes.push_back(std::make_unique<Square>(3.0));
    for (const auto &shape : shapes) print_area(*shape);

    std::string source = "move me";
    std::string destination = std::move(source);
    std::cout << "destination: " << destination << "\n";

    Buffer first(8);
    Buffer second = std::move(first);           // move, not copy
    std::cout << "second size: " << second.size() << "\n";

    int initialized{};                          // value-initialised to zero
    int *heap = new int(7);                     // prefer smart pointers
    std::cout << initialized + *heap << "\n";
    delete heap;
    return 0;
}
""",
            "Compile the example with `-Wall -Wextra -Wreorder -Wshadow`. Then remove the `virtual` destructor and "
            "explain what the compiler can no longer guarantee. Write a class that owns a `FILE*` with the rule of "
            "five, and then rewrite it with `std::unique_ptr` and the rule of zero. Finally, produce a dangling "
            "`std::string_view` and catch it with AddressSanitizer. Practise with "
            "/practice/problems/matrix-transpose.",
        ),
        (
            "cpp-stdlib-deep",
            "The STL map: containers, algorithms and the utilities that replace code",
            "Container choice and iterator invalidation, algorithm and ranges vocabulary, smart pointers, "
            "optional and variant, string_view and span, filesystem, chrono and format.",
            r"""**Why this matters.** The standard library is the largest part of C++ most people never learn
systematically. The result is hand-written loops that already exist as algorithms, raw arrays where
a `std::vector` is faster and safer, and custom variant types where `std::variant` already models
the problem. This module is the map: which container for which access pattern, which algorithm for
which loop, and which vocabulary type makes an interface self-documenting.

**Containers by cost and invalidation.**
| Container | Access | Insert/erase | Iterators invalidated by |
| --- | --- | --- | --- |
| `std::vector` | O(1) index | amortised O(1) at end | reallocation, erase before the position |
| `std::deque` | O(1) index | O(1) at both ends | erase in the middle |
| `std::list` | O(n) | O(1) with an iterator | only the erased element |
| `std::forward_list` | O(n) | O(1) after a position | only the erased element |
| `std::map` / `std::set` | O(log n) | O(log n) | only the erased element |
| `std::unordered_map` | O(1) average | O(1) average | rehash invalidates iterators, not references |
| `std::priority_queue` | O(1) top | O(log n) push/pop | not iterable |

`std::vector` is the default. `reserve` when the size is known; `shrink_to_fit` is a request, not a
guarantee. `std::map` keeps sorted order and gives `lower_bound`/`upper_bound`; `std::unordered_map`
is faster when order does not matter but needs a good hash and is vulnerable to hash-flooding with
adversarial keys. `std::array` is a fixed-size array with value semantics and no heap allocation.

**Iterator categories.** Input, forward, bidirectional, random access and contiguous iterators
support progressively more operations. An algorithm documents the category it needs; a `std::list`
iterator cannot be used with `std::sort` because it is not random access. `std::advance`,
`std::next`, `std::distance` adapt without knowing the category.

**Algorithms replace loops.** `std::sort`/`stable_sort`/`partial_sort`/`nth_element`,
`std::find`/`find_if`, `std::any_of`/`all_of`/`none_of`, `std::count`/`count_if`,
`std::transform`, `std::accumulate`/`reduce`/`transform_reduce`, `std::remove`/`remove_if` (which
move elements to the front and return the new end - pair with `erase`), `std::unique`,
`std::lower_bound`/`upper_bound`/`equal_range`, `std::merge`, `std::partition`,
`std::min_element`/`max_element`, `std::clamp`, `std::swap`. The erase-remove idiom is the one to
memorise: `v.erase(std::remove_if(v.begin(), v.end(), pred), v.end())`.

**Ranges (C++20).** `std::ranges::sort(v)`, `v | std::views::filter(pred) | std::views::transform(fn)
| std::views::take(5)`. Views are lazy and composable; a view does not own its source, so it
dangles if the source dies. `std::ranges::to<std::vector>()` (C++23) materialises a view. Ranges
remove most of the `begin()`/`end()` noise and make the pipeline read left to right.

**Smart pointers.** `std::unique_ptr<T>` is the default owner: move-only, zero overhead over a raw
pointer, and `make_unique` is exception-safe. `std::shared_ptr<T>` is shared ownership with an
atomic reference count; `make_shared` allocates control block and object together. `std::weak_ptr`
breaks cycles and observes without owning; `lock()` gives a temporary `shared_ptr` or null. Do not
pass smart pointers to functions that only observe - take `T&` or `T*`. `shared_ptr` does not make
the object thread-safe; it makes the reference count thread-safe.

**Vocabulary types.** `std::optional<T>` models "maybe a value" without a magic sentinel;
`std::variant<A, B>` models a closed union with `std::visit`; `std::any` models an open type
erasure, rarely the right answer. `std::string_view` is a non-owning view over characters - cheap to
pass, dangerous to store. `std::span<T>` is the same idea for contiguous sequences and replaces
`(pointer, length)` pairs. `std::function` type-erases callables at the cost of an allocation and an
indirect call; a template parameter is faster when the callable type is known.

**Strings and text.** `std::string` is contiguous and null-terminated at `c_str()`; `substr` copies;
`std::string_view` does not. `std::format` (C++20) is type-safe and fast; `printf` is not. Locale
and encoding are not handled by the standard library beyond `std::locale` and `codecvt` (deprecated),
which is why serious text handling uses a library. `std::to_chars`/`from_chars` are the fast,
locale-independent numeric conversions.

**Filesystem and time.** `<filesystem>` gives `path`, `exists`, `is_regular_file`, `directory_iterator`,
`create_directories`, `remove`, `rename`, `file_size`; operations that can fail throw
`filesystem_error` or set an `error_code` in the non-throwing overload. `<chrono>` gives
`system_clock` (wall time), `steady_clock` (monotonic, for measurement), `duration` and
`time_point`; calendar types (`year_month_day`) arrived in C++20. Never measure elapsed time with
`system_clock`.

**The judgment call.** Default to `std::vector`, reach for `std::map` only when order is part of the
contract, use algorithms and views instead of index loops, and make ownership explicit in the type
with `unique_ptr` and references. Every one of those choices removes a category of bug rather than
adding a library.""",
            r"""#include <algorithm>
#include <chrono>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <ranges>
#include <string>
#include <string_view>
#include <vector>

struct Task {
    std::string title;
    int priority;
    bool done;
};

std::optional<Task> find_task(const std::vector<Task> &tasks, std::string_view title) {
    auto it = std::find_if(tasks.begin(), tasks.end(),
                           [&](const Task &task) { return task.title == title; });
    if (it == tasks.end()) return std::nullopt;
    return *it;
}

int main() {
    std::vector<Task> tasks = {
        {"write tests", 2, false},
        {"fix parser", 1, false},
        {"review", 3, true},
    };

    std::ranges::sort(tasks, {}, &Task::priority);
    for (const Task &task : tasks) std::cout << task.priority << " " << task.title << "\n";

    auto open = tasks | std::views::filter([](const Task &t) { return !t.done; })
                     | std::views::transform([](const Task &t) { return t.title; });
    for (std::string_view title : open) std::cout << "open: " << title << "\n";

    if (auto found = find_task(tasks, "fix parser")) {
        std::cout << "found at priority " << found->priority << "\n";
    }

    std::map<std::string, int> counts;
    for (const Task &task : tasks) counts[task.done ? "done" : "open"] += 1;
    for (const auto &[key, value] : counts) std::cout << key << "=" << value << "\n";

    auto started = std::chrono::steady_clock::now();
    std::vector<int> values(1000);
    std::iota(values.begin(), values.end(), 1);
    auto total = std::accumulate(values.begin(), values.end(), 0LL);
    auto elapsed = std::chrono::steady_clock::now() - started;
    std::cout << total << " in "
              << std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count()
              << " us\n";

    std::string text = "a,b,c";
    std::string_view view(text);
    std::cout << view.substr(0, view.find(',')) << "\n";
    return 0;
}
""",
            "Replace three index-based loops in code you own with algorithms or views, and explain the category of "
            "iterator each requires. Then build a lookup that uses `std::unordered_map` and one that uses "
            "`std::map`, measure both, and say which one your access pattern actually needs. Finally, pass a "
            "`std::string_view` into a function that stores it, run the program under AddressSanitizer, and fix "
            "the dangling view. Practise with /practice/problems/top-k-frequent.",
        ),
        (
            "cpp-diagnostics-deep",
            "Compiler errors, undefined behaviour and debugging C++",
            "Reading template and linker errors, ODR violations, the warning and sanitizer matrix, the "
            "debugger workflow, and the UB patterns that explain optimisation surprises.",
            r"""**Why this matters.** C++ error messages are long because the compiler is showing you the
whole instantiation chain, and C++ bugs are strange because undefined behaviour gives the optimiser
permission. The toolchain can find both classes of problem, but only if the build is configured to
ask. This module is the diagnostic side of the language: how to read the errors, how to make the
runtime failures reproducible, and which tools answer which question.

**Reading a template error.** Start at the line that says `required from here`, not at the first
line. The first line names the deepest failed instantiation; the chain shows the call path. The
actual requirement is usually in a `static_assert` or in a note that says `candidate template
ignored: ... does not satisfy ...`. Read the note: concepts produce a readable "because" clause,
SFINAE produces noise. When the error is in a library type, scroll to the first frame that names
your own code.

**Linker errors.** `undefined reference to 'foo'` means a declaration was seen but no definition was
linked: a missing source file, a library order problem (`-lfoo` must come after the objects that use
it), a missing `extern "C"` around a C header, or an inline function defined in a header but not
`inline`. `multiple definition` means a non-inline function or a global variable is defined in a
header included by two translation units; mark it `inline`, move it to a `.cpp`, or use
`constexpr`/`inline constexpr`. `vtable for X` undefined means the key function (often the first
non-inline virtual) has no definition.

**The ODR.** Every entity may have only one definition across the program: same token sequence, in
every translation unit that sees it. Violations are not diagnosed in general; they show up as
functions that behave differently depending on which call site won the link, or as a class with a
different layout in two units (which corrupts memory). Common causes: a macro changing a header's
contents per file, an inline function with a static local in a different namespace, or two versions
of a library at link time. Keep the include path and the compile flags identical across the build.

**Warnings worth turning on.** `-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
-Wold-style-cast -Wnon-virtual-dtor -Woverloaded-virtual -Wnull-dereference -Wdouble-promotion
-Wformat=2`. Clang adds `-Wunused-exception-parameter` and `-Wrange-loop-analysis`. GCC's
`-fanalyzer` and Clang's static analyser find leaks and null dereferences without running the code.
`-Werror` in CI, not necessarily locally.

**Sanitizers.** AddressSanitizer (`-fsanitize=address`) finds use-after-free, heap and stack
overflow, double free and leaks; UndefinedBehaviorSanitizer (`-fsanitize=undefined`) finds signed
overflow, invalid shifts, misaligned access, null dereference and invalid casts; ThreadSanitizer
(`-fsanitize=thread`) finds data races; MemorySanitizer (Clang) finds uninitialised reads. Build
with `-g -O1 -fno-omit-frame-pointer`, run the test suite under each sanitizer in CI, and fix every
report - a sanitizer finding is a bug, not a warning. `_GLIBCXX_ASSERTIONS` adds bounds checks to
libstdc++ containers in debug builds; `-D_ITERATOR_DEBUG_LEVEL=2` does the same for MSVC.

**The debugger.** Compile with `-g -O0` for stepping and `-g -O2` when the bug only appears
optimised. `gdb`: `run`, `bt`, `frame`, `info locals`, `print`, `p vector`, `break`, `watch`,
`continue`, `step`, `next`, `finish`, `thread apply all bt`, `x/32xb ptr`. `lldb` mirrors it with
`frame variable`, `expression`, `thread backtrace all`. A core dump plus the binary plus the
matching debug symbols is usually enough to diagnose a production crash.

**Undefined behaviour that changes with optimisation.**
| Pattern | Symptom | Fix |
| --- | --- | --- |
| Signed overflow | Loop optimised away or wraps differently | Use unsigned or check before adding |
| Out-of-bounds write | Corruption far from the write | `at()`, ASan, bounds-checked spans |
| Use after free | Works until the allocator reuses the block | ASan, unique_ptr |
| Dangling reference | Reads garbage after a temporary died | Extend lifetime or return by value |
| Uninitialised read | Value depends on the previous stack contents | Value-initialise, `-Wmaybe-uninitialized` |
| Strict aliasing violation | Wrong value at `-O2` | `memcpy` or `std::bit_cast` |
| Data race | Intermittent wrong result | `std::atomic`/mutex, TSan |
| Static init order | Global constructed before its dependency | Function-local statics |

**Performance diagnosis.** `perf stat`/`perf record` on Linux, Instruments on macOS, VTune on
Windows. Optimise with `-O2 -DNDEBUG`, measure before and after, and use `-fno-omit-frame-pointer`
for usable profiles. A profile that shows time in `operator new` usually means a container is
being copied; one that shows time in `std::string` comparison usually means a map with string keys
where a hash map was wanted. Inlining hides frames; build with debug info and use `perf`'s call
graph.

**The judgment call.** Configure the build so the compiler and sanitizers find the bugs, read
template errors from the innermost requirement outward, and treat any behaviour difference between
`-O0` and `-O2` as undefined behaviour until proven otherwise. The optimiser is not wrong; the
program broke a contract.""",
            r"""#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

class Parser {
public:
    explicit Parser(std::string text) : text_(std::move(text)) {}

    int parse() const {
        if (text_.empty()) throw std::invalid_argument("empty input");
        int total = 0;
        for (char ch : text_) {
            if (ch < '0' || ch > '9') {
                throw std::runtime_error(std::string("not a digit: ") + ch);
            }
            if (total > (INT32_MAX - (ch - '0')) / 10) {
                throw std::overflow_error("value does not fit in int32");
            }
            total = total * 10 + (ch - '0');
        }
        return total;
    }

private:
    std::string text_;
};

int main() {
    std::vector<std::string> inputs = {"42", "007", "12x", "", "99999999999999999999"};
    for (const std::string &input : inputs) {
        try {
            Parser parser(input);
            std::cout << input << " -> " << parser.parse() << "\n";
        } catch (const std::exception &error) {
            std::cout << input << " -> error: " << error.what() << "\n";
        }
    }
    return 0;
}
""",
            "Build the example with `-fsanitize=address,undefined` and with `-O2 -DNDEBUG`, and confirm both behave "
            "the same. Then introduce three deliberate bugs - a signed overflow, an out-of-bounds write and a "
            "dangling `std::string_view` - and record the sanitizer output for each. Finally, cause a linker error "
            "with a missing definition and an ODR violation with a non-inline function in a header, and fix both. "
            "Practise with /practice/problems/version-compare.",
        ),
    ],
}

MODULE_PRACTICE: dict[str, str] = {
    "c-semantics-deep": "count-set-bits",
    "c-stdlib-deep": "validate-ipv4",
    "c-diagnostics-deep": "xor-checksum",
    "cpp-semantics-deep": "matrix-transpose",
    "cpp-stdlib-deep": "top-k-frequent",
    "cpp-diagnostics-deep": "version-compare",
}
