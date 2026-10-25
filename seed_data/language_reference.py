"""The language reference: one deep lookup page per taught language.

The curriculum teaches by reading order; a reference is used the other way
round. You arrive with a job - "group these records", "why is this a
NullPointerException", "which map should I use" - and need the answer, the
cost and the failure mode in one place. This module holds that material as
data, so the page, the seed and the tests agree on exactly one copy.

``REFERENCE[language]`` has the same keys for all ten languages:

* ``version`` and ``tagline`` - what you are reading about;
* ``model`` - two paragraphs on how the language actually executes;
* ``facts`` - the properties that decide design choices;
* ``syntax`` - the constructs that carry meaning, with a note each;
* ``types`` - the type system in practice;
* ``stdlib`` - the library by *job*, not alphabetical order;
* ``errors`` - message, cause and fix for the failures people actually meet;
* ``idioms`` - task, code and the reason the idiom exists;
* ``versions`` - what changed, so version claims do not drift;
* ``sources`` - upstream documentation, not commentary.

``ROSETTA`` is the cross-language table: one everyday task, the idiomatic form
in every taught language, and the part that does not translate.
"""

from __future__ import annotations

from seed_data import language_reference_core as _core
from seed_data import language_reference_more as _more

#: Catalogue order, matching ``seed_data.library_data.LANGUAGES``.
LANGUAGE_ORDER: tuple[str, ...] = (
    "python", "java", "javascript", "typescript", "cpp",
    "go", "rust", "c", "csharp", "sql",
)

#: Section keys every language must provide, with the heading used on the page.
SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("syntax", "Syntax that carries meaning",
     "The constructs whose exact semantics decide what a program does."),
    ("types", "The type system in practice",
     "What each type is, what it copies, and where the sharp edges are."),
    ("stdlib", "The standard library by job",
     "Start from the task, not from a package name."),
    ("errors", "Errors, causes and fixes",
     "The failures you will meet, why they happen, and what removes the cause."),
    ("idioms", "Idioms for real tasks",
     "The form experienced programmers write, and the reason."),
    ("versions", "Version history that matters",
     "So a version claim in a lesson can be checked."),
)

#: Minimum number of rows in each list section. A truncated section fails the
#: build rather than rendering a half-empty reference page.
MIN_ROWS: dict[str, int] = {
    "facts": 5,
    "syntax": 7,
    "types": 6,
    "stdlib": 7,
    "errors": 7,
    "idioms": 5,
    "versions": 4,
    "sources": 4,
}

#: Required field names for each row section.
ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "facts": ("label", "value"),
    "syntax": ("feature", "code", "note"),
    "types": ("name", "detail"),
    "stdlib": ("job", "api", "note"),
    "errors": ("error", "cause", "fix"),
    "idioms": ("task", "code", "note"),
    "versions": ("release", "change"),
    "sources": ("title", "url"),
}


def _merge() -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for part in (_core.REFERENCE, _more.REFERENCE):
        for language, data in part.items():
            if language in merged:
                raise ValueError(f"duplicate reference language: {language}")
            merged[language] = data
    missing = [language for language in LANGUAGE_ORDER if language not in merged]
    if missing:
        raise ValueError(f"reference missing languages: {missing}")
    unexpected = [language for language in merged if language not in LANGUAGE_ORDER]
    if unexpected:
        raise ValueError(f"reference has unknown languages: {unexpected}")
    return {language: merged[language] for language in LANGUAGE_ORDER}


REFERENCE: dict[str, dict] = _merge()


#: One task, ten snippets, one note about what does not translate. Kept short
#: on purpose: the value is the comparison, not a second tutorial.
ROSETTA: tuple[dict, ...] = (
    {
        "task": "Declare a value that cannot be reassigned",
        "note": "Python has no constant; the name is a convention. C has `const`, but it "
                "means read-only access, not immutability. SQL has parameters, not constants.",
        "snippets": {
            "python": "LIMIT = 100  # convention, not enforced",
            "java": "final int limit = 100;",
            "javascript": "const limit = 100;",
            "typescript": "const limit: number = 100;",
            "cpp": "constexpr int limit = 100;",
            "go": "const limit = 100",
            "rust": "const LIMIT: u32 = 100;",
            "c": "const int limit = 100;",
            "csharp": "const int Limit = 100;",
            "sql": "-- no constants; use a bound parameter\nSELECT :limit AS limit;",
        },
    },
    {
        "task": "Interpolate a value into text",
        "note": "C needs a buffer and a size; SQL concatenates with `||` in PostgreSQL and "
                "SQLite but `CONCAT` in MySQL. Never build SQL by interpolating user input.",
        "snippets": {
            "python": "f\"{name}: {score:.1f}\"",
            "java": "\"%s: %.1f\".formatted(name, score)",
            "javascript": "`${name}: ${score.toFixed(1)}`",
            "typescript": "`${name}: ${score.toFixed(1)}`",
            "cpp": "std::format(\"{}: {:.1f}\", name, score);",
            "go": "fmt.Sprintf(\"%s: %.1f\", name, score)",
            "rust": "format!(\"{name}: {score:.1}\")",
            "c": "snprintf(buf, sizeof buf, \"%s: %.1f\", name, score);",
            "csharp": "$\"{name}: {score:F1}\"",
            "sql": "SELECT name || ': ' || round(score, 1) FROM t;",
        },
    },
    {
        "task": "Iterate a collection with an index",
        "note": "SQL has no row loop; number the rows with `row_number()`. Go and Rust "
                "return index and value together; C must carry the index itself.",
        "snippets": {
            "python": "for i, value in enumerate(values):\n    use(i, value)",
            "java": "for (int i = 0; i < values.length; i++) {\n    use(i, values[i]);\n}",
            "javascript": "for (const [i, value] of values.entries()) {\n  use(i, value);\n}",
            "typescript": "for (const [i, value] of values.entries()) {\n  use(i, value);\n}",
            "cpp": "for (std::size_t i = 0; i < values.size(); ++i) use(i, values[i]);",
            "go": "for i, value := range values {\n\tuse(i, value)\n}",
            "rust": "for (i, value) in values.iter().enumerate() {\n    use(i, value);\n}",
            "c": "for (size_t i = 0; i < n; i++) use(i, values[i]);",
            "csharp": "for (int i = 0; i < values.Length; i++) Use(i, values[i]);",
            "sql": "SELECT row_number() OVER (ORDER BY id) - 1 AS i, value\nFROM items;",
        },
    },
    {
        "task": "A function with a default argument",
        "note": "Java, C, C++, Go, Rust and SQL have no default parameters: they use "
                "overloads, option structs, builders or `COALESCE`. Python's default is "
                "evaluated once, so mutable defaults are a bug.",
        "snippets": {
            "python": "def greet(name, greeting=\"Hello\"):\n    return f\"{greeting}, {name}\"",
            "java": "String greet(String name) { return greet(name, \"Hello\"); }\nString greet(String name, String greeting) { ... }",
            "javascript": "function greet(name, greeting = \"Hello\") {\n  return `${greeting}, ${name}`;\n}",
            "typescript": "function greet(name: string, greeting = \"Hello\"): string { ... }",
            "cpp": "std::string greet(std::string name, std::string greeting = \"Hello\");",
            "go": "// no defaults: an options struct or a variadic override\nfunc Greet(name string, opts ...string) string { ... }",
            "rust": "// no defaults: a builder or Option\nfn greet(name: &str, greeting: Option<&str>) -> String { ... }",
            "c": "/* no defaults: pass every argument */\nint greet(const char *name, const char *greeting);",
            "csharp": "string Greet(string name, string greeting = \"Hello\") =>\n    $\"{greeting}, {name}\";",
            "sql": "SELECT coalesce(:greeting, 'Hello') || ', ' || name FROM people;",
        },
    },
    {
        "task": "Group records by a key",
        "note": "C has no map in the standard library, so grouping is a hand-written hash "
                "table or a sort-and-count. SQL groups with `GROUP BY` and must aggregate "
                "every other selected column.",
        "snippets": {
            "python": "by_team = defaultdict(list)\nfor row in rows:\n    by_team[row.team].append(row)",
            "java": "Map<String, List<Row>> byTeam = rows.stream()\n    .collect(Collectors.groupingBy(Row::team));",
            "javascript": "const byTeam = new Map();\nfor (const row of rows) byTeam.set(row.team, [...(byTeam.get(row.team) ?? []), row]);",
            "typescript": "const byTeam = new Map<string, Row[]>();\nfor (const row of rows) byTeam.set(row.team, [...(byTeam.get(row.team) ?? []), row]);",
            "cpp": "std::unordered_map<std::string, std::vector<Row>> byTeam;\nfor (const auto &row : rows) byTeam[row.team].push_back(row);",
            "go": "byTeam := map[string][]Row{}\nfor _, row := range rows {\n\tbyTeam[row.team] = append(byTeam[row.team], row)\n}",
            "rust": "let mut by_team: HashMap<&str, Vec<&Row>> = HashMap::new();\nfor row in &rows { by_team.entry(&row.team).or_default().push(row); }",
            "c": "/* no standard map: sort by key, then count runs */\nqsort(rows, n, sizeof rows[0], by_team);",
            "csharp": "var byTeam = rows.GroupBy(r => r.Team)\n    .ToDictionary(g => g.Key, g => g.ToList());",
            "sql": "SELECT team, count(*) AS rows\nFROM records GROUP BY team;",
        },
    },
    {
        "task": "Sort records with a tie-break",
        "note": "A comparator must be a strict total order. SQL promises order only for the "
                "columns listed; add a unique final key or pagination is undefined.",
        "snippets": {
            "python": "rows.sort(key=lambda r: (-r.score, r.name))",
            "java": "rows.sort(Comparator.comparingInt(Row::score).reversed()\n    .thenComparing(Row::name));",
            "javascript": "[...rows].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));",
            "typescript": "[...rows].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));",
            "cpp": "std::sort(rows.begin(), rows.end(), [](const Row &a, const Row &b) {\n    if (a.score != b.score) return a.score > b.score;\n    return a.name < b.name;\n});",
            "go": "slices.SortFunc(rows, func(a, b Row) int {\n\tif a.Score != b.Score { return b.Score - a.Score }\n\treturn strings.Compare(a.Name, b.Name)\n})",
            "rust": "rows.sort_by(|a, b| b.score.cmp(&a.score)\n    .then_with(|| a.name.cmp(&b.name)));",
            "c": "qsort(rows, n, sizeof rows[0], by_score_then_name);",
            "csharp": "rows.OrderByDescending(r => r.Score)\n    .ThenBy(r => r.Name, StringComparer.Ordinal);",
            "sql": "SELECT * FROM rows ORDER BY score DESC, name ASC;",
        },
    },
    {
        "task": "Handle a missing value",
        "note": "`null` and `undefined` are different values in JavaScript; Rust has no null; "
                "SQL uses three-valued logic, so only `IS NULL` tests absence.",
        "snippets": {
            "python": "if value is None:\n    value = default",
            "java": "if (value == null) {\n    value = DEFAULT;\n}",
            "javascript": "const name = value ?? \"default\";",
            "typescript": "const name = value ?? \"default\";",
            "cpp": "if (!optional_value) {\n    optional_value = defaultValue();\n}",
            "go": "if value, ok := values[key]; ok {\n\tuse(value)\n}",
            "rust": "if let Some(value) = maybe_value {\n    use_it(value);\n}",
            "c": "if (ptr == NULL) {\n    return -1;\n}",
            "csharp": "var name = value ?? \"default\";",
            "sql": "SELECT * FROM people WHERE nickname IS NULL;",
        },
    },
    {
        "task": "Handle an invalid input",
        "note": "C returns a status; Go and Rust return values; Java, C#, JavaScript and Python "
                "use exceptions. SQL aborts the transaction and needs an explicit rollback.",
        "snippets": {
            "python": "try:\n    port = int(text)\nexcept ValueError as err:\n    raise ConfigError(\"bad port\") from err",
            "java": "try {\n    return Integer.parseInt(text);\n} catch (NumberFormatException err) {\n    throw new ConfigException(\"bad port\", err);\n}",
            "javascript": "if (!Number.isInteger(port)) {\n  throw new Error(`bad port: ${text}`);\n}",
            "typescript": "if (!Number.isInteger(port)) {\n  throw new Error(`bad port: ${text}`);\n}",
            "cpp": "int port{};\nauto [ptr, ec] = std::from_chars(text.data(), text.data() + text.size(), port);\nif (ec != std::errc{}) throw ConfigError(\"bad port\");",
            "go": "port, err := strconv.Atoi(text)\nif err != nil {\n\treturn fmt.Errorf(\"bad port: %w\", err)\n}",
            "rust": "let port: u16 = text.parse().map_err(ConfigError::BadPort)?;",
            "c": "long port = strtol(text, &end, 10);\nif (errno || end == text || *end) return -1;",
            "csharp": "if (!int.TryParse(text, out var port)) {\n    throw new ConfigurationException(\"bad port\");\n}",
            "sql": "BEGIN;\nUPDATE accounts SET balance = balance - 10 WHERE id = 1;\n-- an error aborts this transaction; ROLLBACK and report it\nCOMMIT;",
        },
    },
    {
        "task": "Read a whole text file",
        "note": "Always state the encoding. C has no computed length; SQL does not read files - "
                "bulk import is an engine extension and often an operator privilege.",
        "snippets": {
            "python": "text = Path(path).read_text(encoding=\"utf-8\")",
            "java": "String text = Files.readString(Path.of(path));",
            "javascript": "const text = await readFile(path, \"utf8\");",
            "typescript": "const text: string = await readFile(path, \"utf8\");",
            "cpp": "std::ifstream in(path);\nstd::string text((std::istreambuf_iterator<char>(in)), {});",
            "go": "data, err := os.ReadFile(path)\nif err != nil { return err }",
            "rust": "let text = std::fs::read_to_string(path)?;",
            "c": "FILE *f = fopen(path, \"rb\");\nif (!f) return -1;\n/* fread into a sized buffer, then fclose(f) */",
            "csharp": "var text = await File.ReadAllTextAsync(path);",
            "sql": "-- not standard SQL\nCOPY t FROM '/path/data.csv' WITH (FORMAT csv);",
        },
    },
    {
        "task": "Make a group of writes atomic",
        "note": "SQL is the reference implementation: every other language wraps the same "
                "BEGIN/COMMIT. A transaction without a rollback path is not atomic.",
        "snippets": {
            "python": "with connection:  # commits or rolls back\n    connection.execute(sql, params)",
            "java": "conn.setAutoCommit(false);\ntry {\n    work(conn);\n    conn.commit();\n} catch (SQLException err) {\n    conn.rollback();\n    throw err;\n}",
            "javascript": "await db.transaction(async (tx) => {\n  await tx.run(sql, params);\n});",
            "typescript": "await db.transaction(async (tx) => {\n  await tx.run(sql, params);\n});",
            "cpp": "Transaction tx(conn);   // RAII: rollback unless committed\nwork(conn);\ntx.commit();",
            "go": "tx, err := db.BeginTx(ctx, nil)\nif err != nil { return err }\ndefer tx.Rollback()\nif err := work(ctx, tx); err != nil { return err }\nreturn tx.Commit()",
            "rust": "let tx = pool.begin().await?;\nwork(&tx).await?;\ntx.commit().await?;",
            "c": "if (sqlite3_exec(db, \"BEGIN\", NULL, NULL, &err) != SQLITE_OK) return -1;\n/* ... */\nif (sqlite3_exec(db, \"COMMIT\", NULL, NULL, &err) != SQLITE_OK) return -1;",
            "csharp": "using var tx = connection.BeginTransaction();\nWork(connection, tx);\ntx.Commit();",
            "sql": "BEGIN;\nUPDATE accounts SET balance = balance - 10 WHERE id = 1;\nUPDATE accounts SET balance = balance + 10 WHERE id = 2;\nCOMMIT;",
        },
    },
)


def get(language: str) -> dict | None:
    """The reference for one language, or ``None``."""
    return REFERENCE.get(language)


def language_label(language: str) -> str:
    """Display name from the data itself, so the page has no second list."""
    return REFERENCE[language]["tagline"].split(",")[0] if language else language


def row_count(language: str) -> int:
    """Total rows across the list sections for one language."""
    data = REFERENCE[language]
    return sum(len(data[key]) for key in MIN_ROWS)


def totals() -> dict[str, int]:
    """Totals used by the seeder, the page and the tests."""
    return {
        "languages": len(REFERENCE),
        "rows": sum(row_count(language) for language in LANGUAGE_ORDER),
        "rosetta_tasks": len(ROSETTA),
    }


def validate() -> None:
    """Raise ``ValueError`` when a section is missing, empty or malformed."""
    for language in LANGUAGE_ORDER:
        data = REFERENCE[language]
        for key in ("version", "tagline", "model"):
            if not isinstance(data.get(key), (str, list)) or not data.get(key):
                raise ValueError(f"{language}: missing {key}")
        if len(data["model"]) < 2:
            raise ValueError(f"{language}: model needs two paragraphs")
        for paragraph in data["model"]:
            if len(paragraph.split()) < 30:
                raise ValueError(f"{language}: model paragraph is too short")
        for section, minimum in MIN_ROWS.items():
            rows = data.get(section)
            if not isinstance(rows, list) or len(rows) < minimum:
                raise ValueError(f"{language}: {section} needs {minimum}+ rows")
            for index, row in enumerate(rows):
                for field in ROW_FIELDS[section]:
                    value = row.get(field) if isinstance(row, dict) else None
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(
                            f"{language}.{section}[{index}] missing {field}")
        for source in data["sources"]:
            if not source["url"].startswith("https://"):
                raise ValueError(f"{language}: source must be https: {source['url']}")
        codes = [row["code"] for row in data["syntax"]]
        if len(codes) != len(set(codes)):
            raise ValueError(f"{language}: duplicate syntax example")

    languages = set(LANGUAGE_ORDER)
    for row in ROSETTA:
        if set(row) != {"task", "note", "snippets"}:
            raise ValueError(f"ROSETTA row has wrong keys: {row.get('task')}")
        if set(row["snippets"]) != languages:
            raise ValueError(f"ROSETTA row missing languages: {row['task']}")
        for snippet in row["snippets"].values():
            if not snippet.strip():
                raise ValueError(f"ROSETTA empty snippet: {row['task']}")


validate()
