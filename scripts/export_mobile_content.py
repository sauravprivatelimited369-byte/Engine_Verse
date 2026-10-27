#!/usr/bin/env python3
"""Write the native apps' offline lesson library from the website's seed data.

    python scripts/export_mobile_content.py            # rewrite both assets
    python scripts/export_mobile_content.py --check    # fail if they are stale

The Android app (``android/app/src/main/assets/content.json``) and the Apple
app (``apple/Resources/content.json``) both bundle this file so a student can
read the full notes and answer practice questions with no connection and no
website: every topic at all four note depths (beginner, standard, advanced,
industry), its formulas, and the multiple-choice practice bank.

Notes are authored as Markdown with LaTeX. Parsing that at runtime on two
platforms would mean two renderers drifting apart, so the *structure* is parsed
here, once, and the apps only lay out blocks:

    ["p", runs]                       paragraph
    ["h", level, runs]                sub-heading inside a section
    ["ul", [runs, ...]]               bullet list
    ["ol", [runs, ...]]               numbered list
    ["quote", runs]                   blockquote
    ["code", text, language]          fenced code
    ["math", latex, plain]            display maths (LaTeX and a readable plain form)
    ["table", [runs, ...], [[runs]]]  header row, then body rows
    ["hr"]                            horizontal rule

A *run* is ``[text, flags]`` where flags is a subset of ``b`` (bold), ``i``
(italic), ``c`` (code) and ``m`` (inline maths). Output is deterministic
(sorted topic keys, no timestamps) so ``--check`` can compare byte for byte.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID_ASSET = ROOT / "android" / "app" / "src" / "main" / "assets" / "content.json"
APPLE_ASSET = ROOT / "apple" / "Resources" / "content.json"
FORMAT = "engineverse-mobile-content"
VERSION = 1
LEVELS = ["beginner", "standard", "advanced", "industry"]

# ---------------------------------------------------------------------------
# Markdown -> blocks / runs
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*```\s*([A-Za-z0-9_+#.-]{0,24})\s*$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
_RULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_BULLET = re.compile(r"^\s{0,4}[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s{0,4}(\d{1,3})[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_DISPLAY_MATH = re.compile(r"^\s*\$\$(.*)\$\$\s*$")

# ---------------------------------------------------------------------------
# LaTeX -> readable plain text for native display
# ---------------------------------------------------------------------------
# The apps show maths as monospaced text. The website renders LaTeX to HTML in
# the browser, which a native screen cannot reuse, so the export carries a
# best-effort plain form next to the original (the original is kept for copy).

_TEX_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ", "ell": "ℓ", "degree": "°",
    "angle": "∠", "circ": "∘", "bullet": "•", "cdot": "·", "times": "×", "div": "÷",
    "pm": "±", "mp": "∓", "neq": "≠", "ne": "≠", "leq": "≤", "le": "≤", "geq": "≥",
    "ge": "≥", "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "rightarrow": "→",
    "to": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔",
    "mapsto": "↦", "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "cup": "∪",
    "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃", "neg": "¬", "land": "∧",
    "lor": "∨", "implies": "⟹", "iff": "⟺", "perp": "⊥", "parallel": "∥", "therefore": "∴",
    "because": "∵", "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮",
    "ldots": "…", "dots": "…", "prime": "′", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖", "langle": "⟨", "rangle": "⟩",
}
_TEX_FUNCTIONS = ("log", "ln", "sin", "cos", "tan", "sec", "cosec", "cot", "exp", "max", "min",
                  "lim", "det", "dim", "mod", "arg", "deg")
_SUPERSCRIPT = str.maketrans({
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸",
    "9": "⁹", "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "k": "ᵏ", "m": "ᵐ", "o": "ᵒ",
    "p": "ᵖ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    "T": "ᵀ", "′": "′", "*": "*",
})
_SUBSCRIPT = str.maketrans({
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈",
    "9": "₉", "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎", "a": "ₐ", "e": "ₑ",
    "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ", "h": "ₕ", "l": "ₗ",
})


def _scripted(body: str, table: dict[int, str], marker: str) -> str:
    if body and all(ch in table for ch in body):
        return body.translate(table)
    return f"{marker}{body}"


def tex_plain(source: str) -> str:
    """Best-effort LaTeX to plain text, for monospaced display in the apps."""
    text = (source or "").strip()
    if not text:
        return ""
    text = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)[.\s]*", "", text)
    text = re.sub(r"\\(?:,|;|!|quad|qquad|displaystyle|textstyle|limits)\b|\\[,;! ]", " ", text)
    text = re.sub(r"\\begin\{[^{}]*\}|\\end\{[^{}]*\}", " ", text)
    # Innermost braces first: \text{..}, then scripts, then fractions. Doing them
    # in this order keeps nested groups (\frac{y_{1}-y_{2}}{..}) readable.
    for _ in range(2):
        text = re.sub(r"\\(?:text|mathrm|mathbf|mathit|operatorname|textbf|textit)\s*\{([^{}]*)\}",
                      r"\1", text)
    for _ in range(2):
        text = re.sub(r"\^\{([^{}]*)\}", lambda m: _scripted(m.group(1), _SUPERSCRIPT, "^"), text)
        text = re.sub(r"_\{([^{}]*)\}", lambda m: _scripted(m.group(1), _SUBSCRIPT, "_"), text)
    text = re.sub(r"\^([A-Za-z0-9+\-])", lambda m: _scripted(m.group(1), _SUPERSCRIPT, "^"), text)
    text = re.sub(r"_([A-Za-z0-9+\-])", lambda m: _scripted(m.group(1), _SUBSCRIPT, "_"), text)
    # \frac{a}{b} and \dfrac, \tfrac (repeat for the common nested case)
    for _ in range(4):
        text = re.sub(r"\\(?:d|t)?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", text)
    # Named symbols and operators.
    for name, symbol in sorted(_TEX_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        text = text.replace("\\" + name, symbol)
    for name in _TEX_FUNCTIONS:
        text = text.replace("\\" + name, name)
    text = text.replace("\\%", "%").replace("\\{", "{").replace("\\}", "}")
    text = re.sub(r"\\[A-Za-z]+", "", text)
    text = text.replace("{", "").replace("}", "").replace("&", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _inline(text: str) -> list[list[str]]:
    """Split one line of Markdown into [text, flags] runs."""
    runs: list[list[str]] = []
    buf: list[str] = []
    flags: set[str] = set()
    i = 0
    length = len(text)

    def flush() -> None:
        if buf:
            runs.append(["".join(buf), "".join(sorted(flags))])
            buf.clear()

    while i < length:
        ch = text[i]
        # Inline maths: $...$
        if ch == "$" and not text.startswith("$$", i):
            end = text.find("$", i + 1)
            if 0 < end and end - i < 400 and text[i + 1:end].strip():
                flush()
                runs.append([tex_plain(text[i + 1:end].strip()), "m"])
                i = end + 1
                continue
        # Inline code: `...`
        if ch == "`":
            end = text.find("`", i + 1)
            if end > i:
                flush()
                runs.append([text[i + 1:end], "c"])
                i = end + 1
                continue
        # Bold: **...** or __...__
        if text.startswith("**", i) or text.startswith("__", i):
            marker = text[i:i + 2]
            end = text.find(marker, i + 2)
            if end > i + 2:
                flush()
                inner = text[i + 2:end]
                # The marker may wrap other inline spans; keep them as bold-flagged text.
                runs.extend([[piece, "".join(sorted(set(f) | {"b"}))] for piece, f in _inline(inner)])
                i = end + 2
                continue
        # Highlight ==...== renders as bold in the apps.
        if text.startswith("==", i):
            end = text.find("==", i + 2)
            if end > i + 2:
                flush()
                runs.append([text[i + 2:end], "b"])
                i = end + 2
                continue
        # Italic: *...* or _..._ (single character markers, not part of a word)
        if ch in "*_" and not text.startswith(ch * 2, i):
            end = text.find(ch, i + 1)
            if end > i + 1 and (ch == "*" or (i == 0 or not text[i - 1].isalnum())):
                inner = text[i + 1:end]
                if "\n" not in inner and len(inner) < 240:
                    flush()
                    # A span may hold other markers (**bold**, `code`, $math$).
                    runs.extend([[piece, "".join(sorted(set(f) | {"i"}))] for piece, f in _inline(inner)])
                    i = end + 1
                    continue
        # Markdown links: keep the label, drop the URL (the apps cannot browse mid-note)
        if ch == "[":
            close = text.find("]", i + 1)
            if close > i and text.startswith("(", close):
                end = text.find(")", close)
                if end > close:
                    flush()
                    label = text[i + 1:close].strip()
                    url = text[close + 1:end].strip()
                    runs.append([label, "l" if url.startswith(("http://", "https://", "mailto:")) else ""])
                    buf.append(f" ({url})" if url and not url.startswith("#") else "")
                    i = end + 1
                    continue
        buf.append(ch)
        i += 1

    flush()
    merged: list[list[str]] = []
    for run in runs:
        if not run[0]:
            continue
        if merged and merged[-1][1] == run[1]:
            merged[-1][0] += run[0]
        else:
            merged.append(run)
    return merged


def _split_row(line: str) -> list[list[str]]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [_inline(cell.replace("\\|", "|").strip()) for cell in cells]


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    if not _TABLE_ROW.match(lines[index]):
        return False
    rule = lines[index + 1].strip()
    if not _TABLE_RULE.match(rule):
        return False
    return "-" in rule


def _starts_block(line: str) -> bool:
    return bool(
        _FENCE.match(line)
        or _HEADING.match(line)
        or _RULE.match(line)
        or _BULLET.match(line)
        or _ORDERED.match(line)
        or _QUOTE.match(line)
        or line.strip().startswith("$$")
    )


def parse_blocks(source: str | None) -> list[list]:
    """Turn a Markdown/LaTeX section body into the block list the apps render."""
    if not source:
        return []
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    blocks: list[list] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Fenced code
        fence = _FENCE.match(line)
        if fence:
            lang = fence.group(1)
            i += 1
            code: list[str] = []
            while i < n and not _FENCE.match(lines[i]):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence (or end of section)
            blocks.append(["code", "\n".join(code), lang])
            continue

        # Display maths, one line (`$$ ... $$`) or a fenced block
        inline_math = _DISPLAY_MATH.match(line)
        if inline_math:
            latex = inline_math.group(1).strip()
            blocks.append(["math", latex, tex_plain(latex)])
            i += 1
            continue
        if stripped == "$$":
            i += 1
            math: list[str] = []
            while i < n and lines[i].strip() != "$$":
                math.append(lines[i])
                i += 1
            i += 1
            latex = "\n".join(math).strip()
            blocks.append(["math", latex, tex_plain(latex)])
            continue

        # Heading
        heading = _HEADING.match(line)
        if heading:
            blocks.append(["h", len(heading.group(1)), _inline(heading.group(2))])
            i += 1
            continue

        # Horizontal rule
        if _RULE.match(line):
            blocks.append(["hr"])
            i += 1
            continue

        # Table
        if _is_table_start(lines, i):
            head = _split_row(lines[i])
            i += 2
            rows: list[list[list[str]]] = []
            while i < n and _TABLE_ROW.match(lines[i]):
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append(["table", head, rows])
            continue

        # Blockquote
        if _QUOTE.match(line):
            quoted: list[str] = []
            while i < n and _QUOTE.match(lines[i]):
                quoted.append(_QUOTE.match(lines[i]).group(1))  # type: ignore[union-attr]
                i += 1
            blocks.append(["quote", _inline(" ".join(part.strip() for part in quoted))])
            continue

        # Lists
        bullet = _BULLET.match(line)
        ordered = _ORDERED.match(line)
        if bullet or ordered:
            pattern = _BULLET if bullet else _ORDERED
            items: list[list[list[str]]] = []
            while i < n:
                match = pattern.match(lines[i])
                if not match:
                    # A wrapped continuation line belongs to the previous item.
                    if items and lines[i].strip() and not _starts_block(lines[i]):
                        items[-1] = _inline(" ".join(p for p, _f in items[-1]) + " " + lines[i].strip())
                        i += 1
                        continue
                    break
                items.append(_inline(match.group(match.lastindex or 1)))
                i += 1
            blocks.append(["ul" if bullet else "ol", items])
            continue

        # Paragraph
        paragraph: list[str] = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not _starts_block(lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        blocks.append(["p", _inline(" ".join(paragraph))])

    return blocks


# ---------------------------------------------------------------------------
# Content assembly
# ---------------------------------------------------------------------------


def _seed_and_read() -> dict:
    """Seeds a throwaway database and reads the lesson library out of it."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "content.sqlite3"
        env = os.environ.copy()
        env.update({
            "ENGINEVERSE_ENV": "development",
            "ENGINEVERSE_DB_PATH": str(db_path),
            "ENGINEVERSE_DB_URL": "",
            "ENGINEVERSE_SECRET": "mobile-content-export-local-only-0001",
        })
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "seed.py"), "--fresh", "--no-demo"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
        )
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            return _read_library(connection)
        finally:
            connection.close()


def _read_library(connection: sqlite3.Connection) -> dict:
    sys.path.insert(0, str(ROOT / "backend"))
    from engineverse import project  # noqa: PLC0415 - imported for the canonical URL

    topics = {
        row["id"]: row
        for row in connection.execute(
            "SELECT id, slug, title, difficulty FROM topics WHERE status = 'published'"
        )
    }

    notes: dict[str, dict[str, list]] = {slug: {} for slug in sorted(t["slug"] for t in topics.values())}
    for note in connection.execute(
        "SELECT n.id, n.topic_id, n.quality_level FROM notes n WHERE n.status = 'published'"
    ):
        topic = topics.get(note["topic_id"])
        if topic is None or note["quality_level"] not in LEVELS:
            continue
        sections = []
        for section in connection.execute(
            "SELECT kind, title, body, callout FROM note_sections"
            " WHERE note_id = ? ORDER BY order_index, id",
            (note["id"],),
        ):
            sections.append({
                "kind": section["kind"],
                "title": section["title"],
                "callout": section["callout"] or "",
                "blocks": parse_blocks(section["body"]),
            })
        if sections:
            notes[topic["slug"]][note["quality_level"]] = sections

    formulas: dict[str, list] = {}
    for row in connection.execute(
        "SELECT topic_id, name, latex, meaning, application FROM formulas"
        " WHERE topic_id IS NOT NULL ORDER BY order_index, id"
    ):
        topic = topics.get(row["topic_id"])
        if topic is None:
            continue
        formulas.setdefault(topic["slug"], []).append({
            "name": row["name"],
            "latex": row["latex"] or "",
            "meaning": row["meaning"] or "",
            "application": row["application"] or "",
        })

    practice = []
    for question in connection.execute(
        "SELECT q.id, q.slug, q.topic_id, q.difficulty, q.kind, q.stem, q.context,"
        " q.explanation, s.slug AS subject_slug, t.slug AS topic_slug"
        " FROM questions q"
        " LEFT JOIN topics t ON t.id = q.topic_id"
        " LEFT JOIN subjects s ON s.id = COALESCE(q.subject_id, t.subject_id)"
        " WHERE q.is_active = 1 AND q.kind = 'mcq' ORDER BY q.slug"
    ):
        options = []
        for option in connection.execute(
            "SELECT label, body, is_correct, rationale FROM question_options"
            " WHERE question_id = ? ORDER BY order_index, id",
            (question["id"],),
        ):
            options.append({
                "label": option["label"],
                "body": parse_blocks(option["body"]),
                "correct": bool(option["is_correct"]),
                "why": parse_blocks(option["rationale"]),
            })
        if len(options) < 2 or not any(o["correct"] for o in options):
            continue
        practice.append({
            "slug": question["slug"],
            "subject": question["subject_slug"] or "",
            "topic": question["topic_slug"] or "",
            "difficulty": question["difficulty"] or "medium",
            "stem": parse_blocks(question["stem"]),
            "context": parse_blocks(question["context"]),
            "options": options,
            "explanation": parse_blocks(question["explanation"]),
        })

    return {
        "format": FORMAT,
        "version": VERSION,
        "site": project.pages_url(),
        "levels": LEVELS,
        "notes": {slug: levels for slug, levels in notes.items() if levels},
        "formulas": {slug: rows for slug, rows in sorted(formulas.items()) if rows},
        "practice": practice,
    }


def build_content() -> dict:
    return _seed_and_read()


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if a bundled asset is out of date")
    args = parser.parse_args()

    text = render(build_content())
    data = json.loads(text)
    notes = len(data["notes"])
    practice = len(data["practice"])
    summary = f"{notes} topics with notes, {practice} practice questions, {len(text)} bytes"

    if args.check:
        stale = False
        for asset in (ANDROID_ASSET, APPLE_ASSET):
            current = asset.read_text(encoding="utf-8") if asset.exists() else ""
            if current != text:
                print(f"{asset.relative_to(ROOT)} is out of date; run scripts/export_mobile_content.py",
                      file=sys.stderr)
                stale = True
        if stale:
            return 1
        print(f"content.json is current ({summary})")
        return 0

    for asset in (ANDROID_ASSET, APPLE_ASSET):
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(text, encoding="utf-8")
        print(f"wrote {asset.relative_to(ROOT)}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
