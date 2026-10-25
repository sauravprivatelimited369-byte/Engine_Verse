# Language reference

The course paths teach one language in order. The reference is the page you keep
beside them: it answers a question in one lookup instead of a lesson re-read, and
it names the upstream source for every claim.

- Hub: `/programming/reference`
- Per language: `/programming/{language}/reference` (for example
  `/programming/python/reference`)
- Data: `seed_data/language_reference_core.py` (Python, Java, JavaScript,
  TypeScript, C) and `seed_data/language_reference_more.py` (C++, C#, Go, Rust,
  SQL), merged and validated by `seed_data/language_reference.py`
- Storage: `language_references` and `language_reference_tasks` in
  `db/schema.sql`, seeded by `seed_language_references()` in `scripts/seed.py`

## What each reference contains

| Section | Question it answers | Minimum rows |
| --- | --- | --- |
| `model` | How does the runtime represent and evaluate values? | 2 paragraphs |
| `facts` | What are the properties that decide design choices? | 5 |
| `syntax` | Which constructs carry semantics, and what is the exact rule? | 7 |
| `types` | What is each type, what does it copy, where is the edge? | 6 |
| `stdlib` | Which standard-library API does this job, and what should I check? | 7 |
| `errors` | What does this failure mean, what caused it, how do I fix it? | 7 |
| `idioms` | What is the short form experienced programmers write, and why? | 5 |
| `versions` | Which release introduced or changed the behaviour? | 4 |
| `sources` | Where is the official documentation? | 4 (https only) |

The hub also renders `ROSETTA`: ten everyday tasks, each written in all ten
languages, with a note naming the part that does not translate (C has no default
arguments or maps, Go and Rust have no default arguments, SQL has no loops, and
so on). The comparison is the part a single-language reference cannot provide.

## Validation

`seed_data/language_reference.py` validates at import time and the seeder calls
`validate()` again before writing anything. It rejects:

- a language that is missing, duplicated or not in the catalogue order;
- an empty section or fewer rows than the minimum above;
- a row with a blank field, a duplicate syntax example, or a source that is not
  `https://`;
- a cross-language task that does not carry a snippet for every taught language.

A failed validation stops the seed rather than writing a half-complete reference
that would look finished on the page.

## Where it appears

- `backend/web/pages.py`: `language_reference_hub` and `language_reference`.
- `backend/web/deps.py` and `backend/templates/base.html`: the standard layout,
  title, description, canonical URL and structured data.
- `backend/templates/programming_reference.html` and
  `backend/templates/language_reference.html`: the two readers.
- `backend/engineverse/navigation.py`: the "Language reference" destination, so
  the hub is in the top navigation and the sitemap.
- `backend/engineverse/search.py`: reference rows are indexed as their own
  entity type and link to the per-language page; the schema version is bumped so
  an upgraded database rebuilds its index.
- `scripts/export_pages.py`: both the hub and every seeded reference page are
  written into the static reading copy, with search entries.
- `backend/web/pages.py` `/sitemap.xml`: the per-language pages are added from
  the `language_references` table, so the sitemap cannot list a page that was
  never seeded.

## Adding a language or a row

1. Add or edit rows in `language_reference_core.py` or
   `language_reference_more.py`. Keep the field shape of the section.
2. If the language is new, add it to `LANGUAGE_ORDER` in
   `language_reference.py`, to `seed_data/language_paths.py`/the language
   catalogue, and to every `ROSETTA` row.
3. Run `ENGINEVERSE_DB_PATH=... python scripts/seed.py --fresh --no-demo` and
   confirm the printed reference count.
4. Run `pytest backend/tests/test_language_reference.py` and the SEO, crawl,
   navigation and link suites.

## Verification boundary

The rows are authored from the official documentation listed in each `sources`
section, with the version strings recorded at the top of the entry (for example
Python 3.12 / 3.13, Java 21 LTS / 25, C++20 / C++23, SQL:2023 and PostgreSQL
16/17). They are not expert-signed-off, the snippets are short illustrations
rather than compiled programs, and SQL behaviour is stated for PostgreSQL with
SQLite/MySQL differences called out where they matter. Treat the reference as a
map that points at the specification, not as a replacement for it.
