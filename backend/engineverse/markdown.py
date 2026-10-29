"""Markdown + LaTeX renderer for engineering notes.

Security model: this module builds **escaped HTML**. Nothing from content is
ever inserted raw. The maths renderer only emits a fixed set of tags/classes
with escaped operands, so a note cannot smuggle script into the page.

Supported syntax
    # .. ######  headings          **bold**  *italic*  ==highlight==
    `code`                          ```lang fenced code blocks
    - / * / +   bullet lists        1. ordered lists
    | a | b |   tables              > blockquotes
    ---         horizontal rule     [text](url) links (http/https/mailto only)
    $x^2$       inline maths        $$ ... $$ display maths
"""
from __future__ import annotations

import html
import re
from typing import Iterable

from .security.sanitize import is_safe_url

MAX_RENDER_LENGTH = 200_000

# ---------------------------------------------------------------------------
# LaTeX -> HTML (a focused, useful subset)
# ---------------------------------------------------------------------------

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ", "ell": "ℓ",
    "angle": "∠", "degree": "°", "circ": "∘", "bullet": "•", "cdot": "·",
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "neq": "≠", "ne": "≠",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "approx": "≈", "equiv": "≡",
    "sim": "∼", "propto": "∝", "rightarrow": "→", "to": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔", "mapsto": "↦",
    "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "cup": "∪",
    "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃", "neg": "¬",
    "land": "∧", "lor": "∨", "implies": "⟹", "iff": "⟺", "perp": "⊥",
    "parallel": "∥", "therefore": "∴", "because": "∵", "sum": "∑", "prod": "∏",
    "int": "∫", "iint": "∬", "oint": "∮", "lim": "lim", "log": "log",
    "ln": "ln", "sin": "sin", "cos": "cos", "tan": "tan", "sec": "sec",
    "cosec": "cosec", "cot": "cot", "exp": "exp", "max": "max", "min": "min",
    "Re": "Re", "Im": "Im", "det": "det", "dim": "dim", "mod": "mod",
}

BIG_OPERATORS = {"sum", "prod", "int", "iint", "oint", "lim", "bigcup", "bigcap"}

FUNCTIONS = {"log", "ln", "sin", "cos", "tan", "sec", "cosec", "cot", "exp", "max", "min", "det", "dim", "mod", "lim"}


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


class _TeX:
    """Recursive-descent renderer for the supported LaTeX subset."""

    def __init__(self, source: str) -> None:
        self.src = source
        self.pos = 0

    def peek(self) -> str:
        return self.src[self.pos] if self.pos < len(self.src) else ""

    def take(self) -> str:
        ch = self.peek()
        self.pos += 1
        return ch

    def group(self) -> str:
        """Consumes a `{...}` group or a single token."""
        self.skip_space()
        if self.peek() == "{":
            self.take()
            depth = 1
            start = self.pos
            while self.pos < len(self.src) and depth:
                ch = self.src[self.pos]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
                self.pos += 1
            inner = self.src[start:self.pos]
            self.pos += 1  # consume '}'
            return inner
        if self.peek() == "\\":
            self.pos += 1
            name = ""
            while self.pos < len(self.src) and self.src[self.pos].isalpha():
                name += self.src[self.pos]
                self.pos += 1
            return "\\" + name if name else "\\" + self.take()
        return self.take()

    def skip_space(self) -> None:
        while self.pos < len(self.src) and self.src[self.pos] == " ":
            self.pos += 1

    def render(self) -> str:
        out: list[str] = []
        while self.pos < len(self.src):
            out.append(self.atom())
        return "".join(out)

    def atom(self) -> str:
        ch = self.peek()
        if ch == "":
            return ""
        if ch == "\\":
            return self.command()
        if ch == "{":
            return f'<span class="mrow">{_TeX(self.group()).render()}</span>'
        if ch == "}":
            self.take()
            return ""
        if ch == "^":
            self.take()
            return f'<sup class="msup">{_TeX(self.group()).render()}</sup>'
        if ch == "_":
            self.take()
            return f'<sub class="msub">{_TeX(self.group()).render()}</sub>'
        if ch == "&":
            self.take()
            return '<span class="mcol"></span>'
        self.take()
        if ch == " ":
            return " "
        if ch in "+-=<>()[]|,.:;!'":
            return f'<span class="mop">{_esc(ch)}</span>' if ch in "+-=<>|" else _esc(ch)
        if ch.isdigit() or ch == ".":
            number = ch
            while self.pos < len(self.src) and (self.src[self.pos].isdigit() or self.src[self.pos] == "."):
                number += self.take()
            return f'<span class="mnum">{_esc(number)}</span>'
        if ch.isalpha():
            # ``take()`` above already consumed ``ch``; starting the run empty
            # dropped the first letter of every alphabetic run, so ``\sum_k I_k``
            # rendered as an empty subscript and lost the ``I`` entirely. The
            # digit branch below gets this right by seeding with ``ch``.
            run = ch
            while self.pos < len(self.src) and self.src[self.pos].isalpha():
                run += self.take()
            if run in FUNCTIONS:
                return f'<span class="mfn">{run}</span>'
            letters = "".join(f'<i class="mvar">{_esc(c)}</i>' for c in run)
            return letters
        return _esc(ch)

    def command(self) -> str:
        self.take()  # backslash
        name = ""
        while self.pos < len(self.src) and self.src[self.pos].isalpha():
            name += self.src[self.pos]
            self.pos += 1
        if not name:
            symbol = self.take()
            mapping = {",": "&thinsp;", ";": "&ensp;", ":": "&ensp;", " ": " ", "\\": "<br/>"}
            return mapping.get(symbol, _esc(symbol))

        if name in ("frac", "dfrac", "tfrac"):
            num = self.group()
            den = self.group()
            return (
                "<span class='mfrac'><span class='mnum-frac'>"
                + _TeX(num).render()
                + "</span><span class='mden-frac'>"
                + _TeX(den).render()
                + "</span></span>"
            )
        if name == "sqrt":
            body = self.group()
            return f'<span class="msqrt"><span class="msqrt-sign">√</span><span class="msqrt-body">{_TeX(body).render()}</span></span>'
        if name in ("text", "mathrm", "operatorname", "mbox"):
            return f'<span class="mtext">{_esc(self.group().strip())}</span>'
        if name in ("mathbf", "bm", "boldsymbol", "vec"):
            return f'<b class="mvec">{_TeX(self.group()).render()}</b>'
        if name in ("mathbb", "mathcal"):
            return f'<span class="mbb">{_TeX(self.group()).render()}</span>'
        if name in ("left", "right"):
            self.skip_space()
            bracket = self.take()
            return _esc(bracket) if bracket not in ".|" else ("" if bracket == "." else _esc(bracket))
        if name in ("overline", "bar"):
            return f'<span class="mover">{_TeX(self.group()).render()}</span>'
        if name in ("hat", "widehat"):
            return f'{_TeX(self.group()).render()}<span class="mhat">^</span>'
        if name in ("begin", "end"):
            env = self.group().strip()
            if name == "end":
                return ""
            return self.environment(env)
        if name in BIG_OPERATORS:
            glyph = GREEK.get(name, name)
            return f'<span class="mbig">{_esc(glyph)}</span>'
        if name in GREEK:
            glyph = GREEK[name]
            if name in FUNCTIONS:
                return f'<span class="mfn">{name}</span>'
            return f'<span class="msym">{_esc(glyph)}</span>'
        if name in ("quad", "qquad"):
            return "&emsp;" if name == "quad" else "&emsp;&emsp;"
        return f'<span class="mtext">{_esc(name)}</span>'

    def environment(self, name: str) -> str:
        """Handles matrix/pmatrix/bmatrix/cases/aligned."""
        end_token = f"\\end{{{name}}}"
        end_index = self.src.find(end_token, self.pos)
        body = self.src[self.pos: end_index if end_index != -1 else len(self.src)]
        self.pos = len(self.src) if end_index == -1 else end_index + len(end_token)
        rows = [row for row in re.split(r"\\\\", body) if row.strip()]
        cells_html: list[str] = []
        for row in rows:
            cells = re.split(r"&", row)
            cells_html.append(
                "<tr>" + "".join(f"<td>{_TeX(cell.strip()).render()}</td>" for cell in cells) + "</tr>"
            )
        delimiter = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "vmatrix": ("|", "|"), "Bmatrix": ("{", "}")}.get(name, ("", ""))
        klass = "mcases" if name == "cases" else "mmatrix"
        return (
            f'<span class="{klass}"><span class="mdelim">{_esc(delimiter[0])}</span>'
            f'<table class="mtable">{"".join(cells_html)}</table>'
            f'<span class="mdelim">{_esc(delimiter[1])}</span></span>'
        )


#: Spoken readings for the LaTeX commands a reader meets most often. The
#: accessible name of a formula is what a screen reader announces, and reading
#: the raw source ("frac x over y") is not the same as saying what the
#: formula means.
_TEX_WORDS: dict[str, str] = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "varepsilon": "epsilon", "zeta": "zeta", "eta": "eta",
    "theta": "theta", "vartheta": "theta", "iota": "iota", "kappa": "kappa",
    "lambda": "lambda", "mu": "mu", "nu": "nu", "xi": "xi", "pi": "pi",
    "rho": "rho", "sigma": "sigma", "tau": "tau", "upsilon": "upsilon",
    "phi": "phi", "varphi": "phi", "chi": "chi", "psi": "psi", "omega": "omega",
    "Gamma": "capital gamma", "Delta": "capital delta", "Theta": "capital theta",
    "Lambda": "capital lambda", "Xi": "capital xi", "Pi": "capital pi",
    "Sigma": "capital sigma", "Phi": "capital phi", "Psi": "capital psi",
    "Omega": "capital omega",
    "times": " times ", "cdot": " times ", "div": " divided by ",
    "pm": " plus or minus ", "mp": " minus or plus ", "ast": " asterisk ",
    "le": " less than or equal to ", "leq": " less than or equal to ",
    "ge": " greater than or equal to ", "geq": " greater than or equal to ",
    "neq": " not equal to ", "ne": " not equal to ", "approx": " approximately ",
    "equiv": " is equivalent to ", "sim": " is similar to ", "propto": " is proportional to ",
    "infty": " infinity ", "partial": " partial ", "nabla": " nabla ",
    "sum": " the sum of ", "prod": " the product of ", "int": " the integral of ",
    "lim": " the limit of ", "forall": " for every ", "exists": " there exists ",
    "in": " in ", "notin": " not in ", "subset": " is a subset of ",
    "subseteq": " is a subset of or equal to ", "supset": " is a superset of ",
    "cup": " union ", "cap": " intersection ", "emptyset": " the empty set ",
    "rightarrow": " arrow right ", "leftarrow": " arrow left ",
    "Rightarrow": " implies ", "Leftarrow": " is implied by ",
    "to": " arrow right ",
    "land": " and ", "lor": " or ", "lnot": " not ", "neg": " not ",
    "ldots": " dot dot dot ", "cdots": " dot dot dot ", "dots": " dot dot dot ",
    "sin": " sine ", "cos": " cosine ", "tan": " tangent ", "log": " log ",
    "ln": " natural log ", "exp": " e to the power ", "min": " minimum ",
    "max": " maximum ", "det": " determinant ", "deg": " degrees ",
    "quad": " ", "qquad": " ", "left": " ", "right": " ", "displaystyle": " ",
    "mathrm": " ", "mathbf": " ", "mathit": " ", "operatorname": " ",
    "text": " ", "textbf": " ", "textit": " ", "mathbb": " ", "mathcal": " ",
    "overline": " over ", "hat": " hat ", "tilde": " tilde ", "vec": " vector ",
    "bar": " bar ", "dot": " dot ",
}

#: Symbols that are said rather than shown.
_TEX_SYMBOLS: dict[str, str] = {
    "=": " equals ", "+": " plus ", "-": " minus ", "*": " times ",
    "/": " divided by ", "<": " less than ", ">": " greater than ",
    "^": " to the power of ", "_": " sub ", "&": " and ",
    "|": " modulus ", "~": " ", "%": " percent ",
}


def _tex_group(source: str, start: int) -> tuple[str, int]:
    """Reads a ``{...}`` group starting at ``start``; returns its text.

    A group that is not brace-delimited runs to the next command or
    operator, which is what ``\frac12`` means.
    """
    if start >= len(source) or source[start] != "{":
        end = start
        while end < len(source) and source[end] not in " \\{}":
            end += 1
        return source[start:end], end
    depth = 0
    out: list[str] = []
    i = start
    while i < len(source):
        char = source[i]
        if char == "{":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
        out.append(char)
        i += 1
    return "".join(out), i


def tex_speech(source: str) -> str:
    """A spoken reading of a LaTeX fragment.

    Used as the accessible name of a rendered formula. It is a reading aid,
    not a LaTeX engine: it says "x divided by the square root of 2" rather
    than reading the source out character by character.
    """
    if not source:
        return ""
    out: list[str] = []
    i = 0
    length = len(source)
    while i < length:
        char = source[i]
        if char == "\\":
            i += 1
            if i >= length:
                break
            if source[i].isalpha():
                start = i
                while i < length and source[i].isalpha():
                    i += 1
                name = source[start:i]
                if name == "frac":
                    numerator, i = _tex_group(source, i)
                    denominator, i = _tex_group(source, i)
                    out.append(" ")
                    out.append(tex_speech(numerator))
                    out.append(" divided by ")
                    out.append(tex_speech(denominator))
                    out.append(" ")
                    continue
                if name == "sqrt":
                    root = ""
                    if i < length and source[i] == "[":
                        close = source.find("]", i)
                        if close == -1:
                            close = length
                        root = source[i + 1:close]
                        i = close + 1
                    body, i = _tex_group(source, i)
                    if root:
                        out.append(f" the {root} root of ")
                    else:
                        out.append(" the square root of ")
                    out.append(tex_speech(body))
                    out.append(" ")
                    continue
                if name in {"text", "mathrm", "mathbf", "mathit", "operatorname", "textbf", "textit"}:
                    body, i = _tex_group(source, i)
                    out.append(" ")
                    out.append(body)
                    out.append(" ")
                    continue
                if name in _TEX_WORDS:
                    out.append(_TEX_WORDS[name])
                else:
                    out.append(" ")
                    out.append(name.replace("_", " "))
                    out.append(" ")
                continue
            escaped = source[i]
            i += 1
            if escaped in "{},$":
                out.append(" ")
            elif escaped == "%":
                out.append(" percent ")
            elif escaped == "&":
                out.append(" and ")
            elif escaped == "_":
                out.append(" sub ")
            elif escaped == "^":
                out.append(" to the power of ")
            elif escaped == " ":
                out.append(" ")
            else:
                out.append(" ")
                out.append(escaped)
                out.append(" ")
            continue
        if char in _TEX_SYMBOLS:
            out.append(_TEX_SYMBOLS[char])
            i += 1
            continue
        if char in "{}":
            out.append(" ")
            i += 1
            continue
        out.append(char)
        i += 1
    text = "".join(out)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def render_tex(source: str, display: bool = False) -> str:
    """Renders a LaTeX fragment to escaped HTML."""
    if not source or not source.strip():
        return ""
    try:
        inner = _TeX(source).render()
    except RecursionError:  # pragma: no cover - pathological nesting
        return f'<code class="mtex">{_esc(source)}</code>'
    klass = "math math-display" if display else "math math-inline"
    # The accessible name is a spoken reading, not the LaTeX source: a screen
    # reader should say "x divided by the square root of 2", not "frac x over
    # sqrt 2". The raw source is still available to anyone reading the page.
    spoken = tex_speech(source) or source
    # ``data-tex`` keeps the exact source for anyone who needs it; the
    # accessible name is the spoken reading, because a screen reader would
    # otherwise announce the backslashes and underscores one by one.
    return (
        f'<span class="{klass}" role="math" aria-label="{_esc(spoken)}" '
        f'data-tex="{_esc(source)}">{inner}</span>'
    )


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

CODE_LANGUAGE_LABELS = {
    "python": "Python", "py": "Python", "java": "Java", "cpp": "C++", "c": "C",
    "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript",
    "ts": "TypeScript", "sql": "SQL", "bash": "Bash", "sh": "Shell", "html": "HTML",
    "css": "CSS", "json": "JSON", "yaml": "YAML", "kotlin": "Kotlin", "ruby": "Ruby",
    "go": "Go", "rust": "Rust", "matlab": "MATLAB", "text": "Text", "": "Code",
}

_INLINE_RE = re.compile(
    r"(`[^`]+`)"               # inline code
    r"|(\$\$[^$]+\$\$)"        # display maths
    r"|(\$[^$\n]+\$)"          # inline maths
    r"|(\*\*[^*]+\*\*)"        # bold
    r"|(==[^=]+==)"            # highlight
    r"|(\*[^*\n]+\*)"          # italic
    r"|(\[[^\]]+\]\([^)\s]+\))"  # link
)


def _inline(text: str) -> str:
    out: list[str] = []
    last = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > last:
            out.append(_esc(text[last:match.start()]))
        token = match.group(0)
        if token.startswith("`"):
            out.append(f"<code>{_esc(token[1:-1])}</code>")
        elif token.startswith("$$"):
            out.append(render_tex(token[2:-2], display=True))
        elif token.startswith("$"):
            out.append(render_tex(token[1:-1], display=False))
        elif token.startswith("**"):
            out.append(f"<strong>{_inline(token[2:-2])}</strong>")
        elif token.startswith("=="):
            out.append(f"<mark>{_inline(token[2:-2])}</mark>")
        elif token.startswith("*"):
            out.append(f"<em>{_inline(token[1:-1])}</em>")
        elif token.startswith("["):
            parsed = re.match(r"\[([^\]]+)\]\(([^)\s]+)\)", token)
            if parsed:
                label, href = parsed.group(1), parsed.group(2)
                if is_safe_url(href):
                    external = href.startswith("http")
                    attrs = ' target="_blank" rel="noopener noreferrer nofollow"' if external else ""
                    out.append(f'<a href="{_esc(href)}"{attrs}>{_inline(label)}</a>')
                else:
                    out.append(f"<span>{_inline(label)}</span>")
            else:
                out.append(_esc(token))
        else:
            out.append(_esc(token))
        last = match.end()
    if last < len(text):
        out.append(_esc(text[last:]))
    return "".join(out)


def _is_table_start(lines: list[str], index: int) -> bool:
    """True when ``lines[index]`` is a table header.

    The separator row decides it: a header row is only a table if the next line
    is made of dashes, colons and pipes. Authored content sometimes puts the
    table straight after a paragraph with no blank line, so the paragraph loop
    also stops here rather than swallowing the table into a ``<p>``.
    """
    if "|" not in lines[index] or index + 1 >= len(lines):
        return False
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[index + 1]))


def _split_row(line: str) -> list[str]:
    """Split a table row on the pipes that are cell boundaries.

    A pipe inside an inline code span is content, not a boundary: SQL's
    concatenation operator is written ``||``, and splitting on it turned one
    cell into three and pushed the rest of the row a column to the right. A
    backslash-escaped ``\|`` is also content. Everything else splits as before.
    """
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    characters = line.strip().strip("|")
    index = 0
    while index < len(characters):
        character = characters[index]
        if character == "\\" and index + 1 < len(characters):
            current.append(characters[index:index + 2])
            index += 2
            continue
        if character == "`":
            in_code = not in_code
        elif character == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    cells.append("".join(current).strip())
    # The escape was only needed to protect the pipe from the splitter.
    return [cell.replace("\\|", "|") for cell in cells]


def _heading_shift(source: str, base: int) -> int:
    """How far to move this block's headings so its shallowest lands on ``base``.

    Headings used to be shifted by a flat +2, on the assumption that every block
    is rendered inside a section that is itself an <h2> under the page's <h1>.
    That holds for topic notes but not for a problem statement, which sits
    directly under the page's <h1>: its first heading is written as ``###``, so
    +2 made it an <h5> with no <h2>, <h3> or <h4> before it. A reader navigating
    by heading heard the page jump from the title to a fifth-level heading, on
    all 95 coding problems.

    Aligning the shallowest heading in the block to ``base`` keeps the relative
    depth the author wrote while guaranteeing the block starts where its
    container expects, whatever levels the author happened to use.
    """
    levels: list[int] = []
    in_fence = False
    for line in source.split("\n"):
        stripped = line.strip()
        # Fenced code is copied verbatim, so a `#` comment inside one is not a
        # heading and must not influence the shift.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+\S", stripped)
        if match:
            levels.append(len(match.group(1)))
    return base - min(levels) if levels else 0


def render(source: str | None, *, base: int = 2) -> str:
    """Renders markdown to safe HTML.

    ``base`` is the heading level this block's shallowest heading should take;
    it defaults to 2, which is correct wherever content sits under a page <h1>.
    """
    if not source:
        return ""
    text = source.replace("\r\n", "\n").replace("\r", "\n")[:MAX_RENDER_LENGTH]
    shift = _heading_shift(text, base)
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        fence = re.match(r"^```(\w*)\s*$", stripped)
        if fence:
            language = fence.group(1).lower()
            index += 1
            buffer: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                buffer.append(lines[index])
                index += 1
            index += 1
            label = CODE_LANGUAGE_LABELS.get(language, language.upper() or "Code")
            code = _esc("\n".join(buffer))
            out.append(
                f'<div class="codeblock"><div class="codeblock-bar"><span>{_esc(label)}</span>'
                f'<span class="codeblock-lines">{len(buffer)} lines</span></div>'
                f"<pre><code>{code}</code></pre></div>"
            )
            continue

        if stripped.startswith("$$"):
            rest = stripped[2:]
            # Single-line display maths: $$ ... $$ all on one line.
            if len(rest) >= 2 and rest.endswith("$$"):
                out.append(render_tex(rest[:-2], display=True))
                index += 1
                continue
            index += 1
            buffer = []
            if rest.strip():
                buffer.append(rest)
            while index < total and not lines[index].strip().startswith("$$"):
                buffer.append(lines[index])
                index += 1
            index += 1
            body = "\n".join(buffer)
            if body.rstrip().endswith("$$"):
                body = body.rstrip()[:-2]
            out.append(render_tex(body, display=True))
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = min(max(len(heading.group(1)) + shift, 1), 6)
            out.append(f"<h{level} class='md-h'>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            out.append("<hr class='md-hr'/>")
            index += 1
            continue

        # Table: a header row followed by a |---|---| separator row.
        if _is_table_start(lines, index):
            head = _split_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < total and "|" in lines[index] and lines[index].strip():
                rows.append(_split_row(lines[index]))
                index += 1
            out.append(
                "<div class='table-wrap'><table class='md-table'><thead><tr>"
                + "".join(f"<th>{_inline(cell)}</th>" for cell in head)
                + "</tr></thead><tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
                )
                + "</tbody></table></div>"
            )
            continue

        if re.match(r"^\s*>\s?", line):
            buffer = []
            while index < total and re.match(r"^\s*>\s?", lines[index]):
                buffer.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            out.append(f"<blockquote class='md-quote'>{_inline(' '.join(buffer))}</blockquote>")
            continue

        if re.match(r"^\s*[-*+]\s+", line):
            items = _collect_list(lines, index, r"^\s*[-*+]\s+")
            index += len(items)
            out.append(
                "<ul class='md-ul'>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>"
            )
            continue

        if re.match(r"^\s*\d+[.)]\s+", line):
            items = _collect_list(lines, index, r"^\s*\d+[.)]\s+")
            index += len(items)
            out.append(
                "<ol class='md-ol'>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ol>"
            )
            continue

        buffer = []
        while (
            index < total
            and lines[index].strip()
            and not re.match(r"^(#{1,6}\s|```|\$\$|\s*>\s?|\s*[-*+]\s|\s*\d+[.)]\s)", lines[index])
            and not _is_table_start(lines, index)
        ):
            buffer.append(lines[index])
            index += 1
        if buffer:
            out.append(f"<p class='md-p'>{_inline(' '.join(buffer))}</p>")
        else:
            index += 1

    return "".join(out)


def _collect_list(lines: list[str], start: int, pattern: str) -> list[str]:
    items: list[str] = []
    index = start
    while index < len(lines) and re.match(pattern, lines[index]):
        items.append(re.sub(pattern, "", lines[index], count=1))
        index += 1
    return items


def plain_text(source: str | None, limit: int = 240) -> str:
    """Strips markdown/LaTeX for snippets and search indexes."""
    if not source:
        return ""
    text = re.sub(r"```.*?```", " ", source, flags=re.S)
    text = re.sub(r"\$\$?.*?\$\$?", " ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_=#>|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def excerpt(source: str | None, limit: int = 180) -> str:
    text = plain_text(source, limit + 1)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_many(chunks: Iterable[str]) -> str:
    return "".join(render(chunk) for chunk in chunks)
