# EngineVerse features in depth

The [README](../README.md) is the overview. This page describes what the full
FastAPI website contains and how its major features work. Counts come from a
fresh, no-demo seed (`python scripts/seed.py --fresh --no-demo`). They describe
what is seeded today, not a completeness guarantee.

## Learning catalogue

The catalogue is data-driven: pages enumerate the subjects and learning material
present in the database rather than assuming there are only one or two fixed
subjects. The following counts come from a fresh, no-demo seed; they describe
what is seeded today, not a completeness guarantee.

| Area | Current seeded coverage |
|---|---|
| **Engineering subjects** | 45 branches and 93 published subjects. The catalogue includes computing, electrical, mechanical, civil, chemical, aerospace, biomedical, agricultural, cybersecurity and other engineering fields. Browse what is available in the app; missing material is not implied by this snapshot. |
| **Notes** | 406 published topics, 1,624 notes across four reading depths, and 10,556 note sections. Standard notes use the [13-section note template](NOTE_TEMPLATE.md). |
| **Cyber Security** | 13 published starter topics; on an instance run with `ENGINEVERSE_SIGNIN=optional` learners can read them without signing in. They remain starter material and need expert review. |
| **Diagrams and models** | 406 topic-linked SVG diagrams and 406 interactive 3D learning models. The WebGL renderer has no external runtime dependency. |
| **Practice** | 534 active questions and 107 published Daily Practice Problem sets (535 slots); every active question, all 93 subjects and all ten language tracks appear in the seeded DPP archive. Practice XP is knowledge-based (owner decision, 19 October 2026, reversing the earlier attempt-based rule): a question pays its difficulty value on its first correct answer only, wrong answers and repeats pay 0, and a coding problem pays on its first accepted solution — so a learner's XP and leaderboard position reflect questions and problems actually passed, not attempts farmed. Attempts are still recorded (history, mistake notebook, streaks). XP earned before the change is kept as recorded. |
| **Programming paths** | 10 learning paths and 225 staged, searchable modules across Python, Java, JavaScript, TypeScript, C, C++, C#, Go, Rust and SQL. Each path is staged — Foundations, then Working Practice, then Advanced Engineering — across 30 stages, and each stage ends with three checkpoint questions (90 total) answered through the normal practice flow, with feedback, explanation and XP only after submission. All modules have a focused reader. Fifteen modules now have structured learn–practice–prove units: one foundational unit per language plus priority-language complexity units. The other 210 retain legacy content; this is not a complete textbook curriculum. See [academy scope and authoring](ACADEMY.md). |
| **Coding practice** | 105 problems with language stubs and test cases, grouped into 14 curated sheets (first drills, arrays, two pointers and windows, stacks and search, linked lists, trees and heaps, graphs, dynamic programming, advanced patterns, SQL and stream sets) plus a 30-problem interview set. Every problem appears in at least one sheet, and every sheet is reachable at `/sheets` in a recommended order with hints, editorials and progress. Which languages can execute depends on the configured judge and installed toolchains; see [Code execution](#code-execution). |
| **My stream** | Each branch has a study hub at `/stream/{slug}` that gathers the subjects, notes, formula sheets, flashcards, question mix, sheets and projects that branch actually has, with the counts taken from the database rather than promised. `/stream` opens on the branch saved in the profile and `/streams` switches between them. Every stream also reaches the branch-neutral pattern sheets and the interview set, so no branch gets an empty page. |
| **Projects** | 17 project briefs with ordered steps, skills and resources, spanning hardware, engineering software, full-stack apps and a model-free study planner with an optional allowlisted, confirmation-gated agent — including a substantial capstone brief linked to each of the ten language paths. |
| **Revision and roadmaps** | 281 public flashcards are browsable at `/flashcards` and searchable without indexing their answers; personal SM-2 schedules are at `/revision`. The seed also includes 5 roadmaps and 57 roadmap nodes. |
| **Study helper** | A retrieval-grounded tutor that composes answers from EngineVerse's own indexed material and cites its sources. It does not make an external model call by default and should say when the catalogue has no relevant coverage. |

Studying does not require leaving the site. Notes, worked examples, diagrams and
3D models, formula sheets, flashcards, the practice bank, the coding judge and
the projects are all served from this application, and `/resources` is the
complete index of those in-app shelves rather than a page of outbound links. An
older shelf of external reading still exists at `/resources/offsite` and is
labelled as optional: no navigation, lesson or practice flow depends on it, and a
deployment that never visits it loses no learning material.

## Integrated engineering and developer labs

Four advanced capabilities are wired into the existing catalogue and navigation:

| Lab | What is integrated |
|---|---|
| **Public APIs directory** (`/apis`) | 12 curated developer/engineering APIs with category, auth, CORS, search and exact-slug filters; paired local topics/projects and cURL, Python and JavaScript examples. Inspired by `public-apis/public-apis`. |
| **Data & BaaS studio** (`/studio`) | Five-service comparison and SDK snippets, a 26-table public schema inspector, an access/RLS policy matrix, and a bounded SELECT runner with `EXPLAIN QUERY PLAN`. SQL runs only on a disposable public snapshot—never the live app database. Inspired by Supabase and Appwrite. |
| **Workflow automations** (`/workflows`) | Declarative study, revision, placement and catalogue-audit pipelines with real streamed step outputs and importable n8n JSON. Operators are allowlisted and read-only; custom code and webhooks cannot execute. Inspired by n8n. |
| **Engineering swarm lab** (`/swarm`) | Five deterministic specialist review lenses, using only seeded topics, note sections, formulas, questions, coding briefs and projects. Quotes have citations; trade-offs are explicitly unresolved review prompts. No external model or autonomous tools are running. Inspired by MiroFish. |

On GitHub Pages these pages show the directory, schema, blueprints, JSON downloads
and clearly labelled seeded examples. New SQL queries, workflow runs and swarm
reviews require a self-hosted backend; exported controls are disabled rather than
pretending to execute. Normal account policy, CSRF and rate limits apply on the
real app. No operator changes learner progress, grading or SRS state.

See [Advanced capabilities](ADVANCED_CAPABILITIES.md) for endpoint contracts,
isolation limits, grounding guarantees, n8n setup and deployment verification.

## Finding things

Sixty pages is only useful if a learner can find the one they want. The whole
site is described once, in `engineverse/navigation.py`: every destination, the
group it belongs to, a one-line description, and the URL prefixes that mean "you
are here". Everything the reader sees is derived from that table — the desktop
top bar, the mobile bottom bar, the slide-down menu, the footer columns, the
breadcrumb trail on every page, the index at `/resources`, `/sitemap.xml` and the
GitHub Pages export list — so they cannot disagree about what exists or what
something is called. See [Architecture](ARCHITECTURE.md#navigation-is-data)
for what this replaced.

The top bar is six grouped entries rather than ten flat links. Each group label
is itself a link to that group's landing page, so the bar is one click from the
most useful page in every group even for a reader who never opens a menu:

| Group | Landing page | Also in the menu |
|---|---|---|
| **My stream** | `/stream` | the full index |
| **Learn** | `/explore` | formulas, videos, books, roadmaps, the study tutor, engineering swarm lab |
| **Practice** | `/practice` | the daily set and its archive, the question bank, the mistake notebook |
| **Code** | `/programming` | coding problems, practice sheets, projects, public APIs, data & BaaS studio |
| **CodeLab** | `/codelab` | online compiler for Python, Java, C, C++, JavaScript, TypeScript, Go, SQL and shell |
| **Revise** | `/revision` | public flashcards, formulas, roadmaps |
| **More** | `/resources` | today's plan, streaks, leaderboard, profile, workflow automations, community, placements, about |

On a phone the menu button opens every group expanded, which puts all sixty pages
one tap away instead of leaving the last fifteen to the footer. Menus open on
hover *and* on keyboard focus, so the whole navigation works with no JavaScript —
as does every other page on the site.

`/resources` is the page that answers *what is actually on this site?*: every
destination in its group with the description and the count this instance holds,
opened by three ways in by intent. `/explore` carries the branch browser, which
lists all 45 branch hubs with links to both the branch page and its study hub.
Both were reachable from nowhere before.

Deep links from search and from the recommendation cards narrow the page they
land on — `/videos?slug=…`, `/books?slug=…`, `/formulas?slug=…` and
`/practice/questions?slug=…` — rather than using a `#fragment`. The library pages
paginate 24 rows at a time, and a fragment is never sent to the server, so a
fragment link dropped the reader at the top of a long list with the item they had
clicked several pages in. `backend/tests/test_links.py` asserts not just that
these URLs resolve but that they *show the thing they named*, which is the
property a status-code check cannot see.

Every collection pages, including `/formulas`, which used to render all 365
formulas as a 1.3 MB page while a hard-coded limit of 300 quietly deleted the
last 65. Every page also keeps a clean heading outline: a reader who navigates by
heading hears the structure, and the footer's headings and the markdown
renderer's heading offset both used to make most pages skip two or three levels.

Every page below the top level carries a breadcrumb, derived from the same table.
It is audience-aware: a signed-out reader is never shown a link whose only effect
would be a bounce to `/login`, and `/stream/{branch}` reads
"Home › Streams › …" for them rather than pointing at a page they cannot open.

`/resources` is the page that answers *"what is actually on this site?"*. It lists
every destination in its group with the description and the count this instance
really has — read from the database, so a deployment seeded with less shows less —
and opens with three ways in by intent: just started, studying for an exam,
preparing for interviews.

The generated [curriculum coverage report](CURRICULUM_COVERAGE.md) lists the
current snapshot by branch and by stream. Use
`python scripts/coverage_report.py` after seeding to regenerate it for a
database. Do not read the counts as evidence that every
subject has a complete semester or degree curriculum.

## Practical programming

The programming paths are intended to build from syntax toward useful software,
not stop at isolated language trivia. Each path runs through the same three
stages — **Foundations** (the language and its first programs), **Working
Practice** (the habits of small correct programs: testing, error handling, safe
input) and **Advanced Engineering** (structure, concurrency, persistence,
authorization and the tooling a maintainer relies on). Every stage ends with a
three-question checkpoint answered through the normal practice flow, and every
path ends with a capstone project brief: a real problem with prerequisites,
ordered milestones, testing expectations, resources and a shippable result.
Depending on the path, modules cover collections, functions, object-oriented
design, error handling, testing, safe input handling, APIs, persistence,
concurrency, authorization and project structure. C and C++ paths also emphasize
memory/resource safety and undefined-behavior avoidance. The Python, Java, C,
C++ and C# paths also contain legacy modules on complexity, strings, recursion,
sorting, stacks, linked lists, trees, heaps, graphs and dynamic programming.
A linked problem is related practice, not evidence of a matching language starter
or per-subtopic mastery. The new [academy reader](ACADEMY.md) explicitly
tracks structured-unit coverage and gives seven-level expansion goals for all ten
languages. Initial units include traces, precise exercises, progressive hints,
local code drafts, references and self-review rubrics. They do not execute drafts
or save self-reported mastery; existing stage quizzes and submissions are separate.

The coding problems on a language page are limited to the ones that language has
a usable editor starter for; where a path has no starter yet the page says so
rather than opening an editor that cannot run that language. The modules,
checkpoints and capstone brief remain available regardless.

Runnable support is a deployment property, not just a curriculum promise. The
UI marks a language runnable only when the active provider supports it on that
host. Missing compilers or blocked isolation cause the runner to refuse execution
rather than silently run code with weaker controls.

## Code execution

Learner code is untrusted. **Production does not run code in the web process.**
The production default is `ENGINEVERSE_JUDGE=disabled`; operators may instead
configure a separately managed Judge0 endpoint. This application delegates to
that endpoint but does not certify or independently verify its isolation.

For development, `ENGINEVERSE_JUDGE=auto` may select the Java sandbox or the
built-in local runner. The local runner only becomes available when the host
proves it can create network, PID and mount namespaces, mount private procfs,
and perform the filesystem-isolation mount. It applies bounded process
resources, scrubs the child environment and refuses if required controls fail.
It is still a child
process on the same host—not a container or VM—and is not a production security
boundary. A restrictive kernel/container may make it unavailable, in which
case submissions are refused. See [Security](SECURITY.md) for its limits.

### Compilers and the terminal

`/compiler` is a compiler-plus-terminal for **every taught language** —
Python, Java, JavaScript, TypeScript, C++, Go, Rust, C, C# and SQL — and
`/python-compiler` is the same page opened on Python. You write a complete
program, give it stdin, and the judge compiles and runs it with the
language's own toolchain, returning real stdout/stderr/status. The local
runner has a toolchain entry for every catalogue language (CPython, Node,
`tsc`/Node type-stripping for TypeScript, gcc/g++, `javac`, `go build`,
`rustc`, .NET for C#, SQLite for SQL) and Judge0 maps the same slugs in
production; a language is only offered as runnable when its toolchain is
actually installed, and is otherwise labelled "no runtime here" — never
simulated. Judged problems append a stdin/stdout harness for Python and
JavaScript function stubs; other languages submit complete programs.

On the static GitHub Pages copy there is no server judge, so every language
brings its real toolchain with it, compiled to WebAssembly and fetched into
the published artifact pinned and same-origin: JavaScript in an isolated Web
Worker, Python on real CPython (Pyodide, `scripts/fetch_pyodide.py`, ~13 MiB),
and C/C++ (Clang 22), Java (OpenJDK's javac + TeaVM), Rust (rustc's Miri),
C# (Roslyn on Blazor WebAssembly), TypeScript (the official compiler, fully
type-checking), Go (GopherJS) and SQL (SQLite) via
`scripts/fetch_browser_runtimes.py` (~170 MiB across all of them, each loaded
lazily only when its language is first picked). The Pages workflow verifies
each one end-to-end — a real program compiled and run with stdin, plus its
diagnostics — before deploying (`scripts/check_browser_runtimes.js`). Two
platform limits are labelled rather than hidden: Go in the browser cannot
read stdin, and the Rust browser worker wraps snippets that lack `fn main`
instead of erroring as rustc does. A language whose runtime files fail to
download is omitted from `runtimes/manifest.json` and reports NOT RUN with
the reason — never a simulation, on either copy.

## Security overview

Security is part of the application design, not a deployment afterthought. The
current implementation includes:

- scrypt password hashing with bounded password length and bounded verification
  parameters; a modest local exact-match common-password list is used, not a
  breached-password lookup service;
- opaque sessions whose random tokens are stored as HMAC-SHA-256 hashes under
  `ENGINEVERSE_SECRET`, session- or browser-bound CSRF tokens, secure cookie
  flags when served over HTTPS, and revocation on sensitive account changes;
- optional delivered six-digit codes (`ENGINEVERSE_LOGIN_OTP=signup_only` or
  `required`; the default `disabled` is password-only), sent by configured email
  or an operator-run SMS gateway. An enrolled TOTP authenticator satisfies the
  sign-in step without stacking another delivered code; codes are short-lived,
  single-use, keyed and sealed, and public reading remains public;
- authentication-factor replay controls for TOTP steps, one-use recovery codes
  and short-lived one-use authentication/reset tokens. Practice answers are
  repeatable as attempts, but XP is knowledge-based: only the first correct
  answer to a question (and the first accepted solution to a problem) pays,
  so repeated answers cannot mint XP;
- server-side authorization, parameterized SQL, request/input bounds,
  autoescaped templates and CSP/security headers. There is currently no
  user-controlled file-upload feature or dynamic file-serving route;
- rate limits for login (10 per 5 minutes), registration (5/hour), reset-link
  requests (5/hour/IP plus 3/hour per keyed address), reset-token checks
  (10 per 5 minutes), feedback
  (5 per hour per IP), practice answers (120 per minute per IP), and coding
  execution (30 per minute); sign-in code resends are capped at 5 issues per
  15 minutes with a 60-second resend cooldown; per-account limits also bound
  password/MFA/email actions and community posts, replies, reports and votes;
- proxy trust disabled by default. Enable it only behind a trusted proxy that
  overwrites forwarding headers.

These protections reduce risk but do not make an application invulnerable.
Review the threat model, operational requirements, key rotation effects and
known limitations in [docs/SECURITY.md](SECURITY.md) before deployment.
Never commit `.env`, database files, private keys or real learner data.

### Sign-in code limitations

Production refuses to start with delivered sign-in codes enabled unless at
least one mail or SMS transport is configured. SMS is deliberately an operator-run HTTP
gateway: EngineVerse does not provide a hosted SMS service, queue, delivery
receipt or carrier fallback, so the operator owns its availability and abuse
controls. A verified phone is optional; email remains the default channel when
mail is configured. An enrolled TOTP authenticator satisfies the every-login
check without a delivered code.

## CodeLab — Online Compiler

`/codelab` (**CodeLab — Online Compiler**, top-bar tab **CodeLab**) provides a
full multi-language compiler workspace built on EngineVerse's isolated sandbox
and Judge0 execution architecture:

- **Language-specific real runtimes (`backend/engineverse/codelab.py`)**:
  - **Python 3 (`python`)**: `python3 -I -m py_compile` check + `python3 -I -B main.py`
  - **Java (`java`)**: real JDK compilation (`javac`) to `.class` bytecode + JVM execution (`java Main` or detected `public class <Identifier>`)
  - **C (`c`)**: `gcc -O2 -std=c17 -o program main.c` + `./program`
  - **C++ (`cpp`)**: `g++ -O2 -std=c++17 -o program main.cpp` + `./program`
  - **JavaScript (`javascript`)**: `node --check main.js` + isolated `node` runtime on server (and isolated Web Worker on static offline copies, explicitly labeled)
  - **Additional registered languages**: TypeScript (`tsc` + `node`), Go (`go build`), SQL (isolated in-memory `SQLite`), POSIX Shell (`sh`), plus Rust (`rustc`) and C# (`dotnet`) when installed on the host or backed by Judge0.
- **Strict runtime honesty**: A language appears as executable in CodeLab only
  when `provider.supports(slug)` is `True` on the active host. Code entered in
  one language mode is never routed to another language's interpreter or simulated.
- **Execution API (`POST /api/execute`)**: Accepts `{ "language", "sourceCode", "stdin" }`
  (CSRF-protected, sliding-window rate-limited, request-size bounded) and returns
  `stdout`, `stderr`, `compileOutput` (kept separate from runtime `stderr`),
  `exitCode`, `executionTime`, `status` (`success`, `compilation_error`,
  `runtime_error`, `timeout`, `service_unavailable`), and active `runtime` label.
- **Android phone & touch support**: Responsive mobile view tabs (`Code` /
  `Input (stdin)` / `Output`), one-tap symbol key bar (`Tab`, `{`, `}`, `(`, `)`,
  `[`, `]`, `;`, `:`, `"`, `'`, `=`, `<`, `>`, `_`, `/`, `←`, `→`) for soft
  keyboards, PWA app shortcut to `/codelab`, and `adjustResize` soft-input
  handling in the native Android app's viewer. Inside that viewer **Download**
  copies the code instead, because it cannot save blob files.
- **Adding a new language**: Add a runner entry in `backend/engineverse/judge/local.py`
  (and `LANGUAGE_IDS` in `judge0.py`) and register its descriptor, starter
  template, and examples in `LANGUAGE_SPECS` inside `backend/engineverse/codelab.py`.
