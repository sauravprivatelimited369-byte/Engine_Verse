"""CodeLab — Online Compiler backend service and centralized LanguageRegistry.

Every language registered here executes strictly through its own genuine
compiler or interpreter inside the configured sandbox provider (`LocalSandboxProvider`
with Linux user/network/PID/mount namespaces and `setrlimit`, or `Judge0Provider`
in production). Languages whose runtime is absent on the active host are marked
`available=False` and are never advertised as executable or routed to another
runtime.
"""
from __future__ import annotations

import functools
import re
import shutil
import sqlite3
import subprocess
from typing import Any

from . import db, judge
from .security.ids import now_ms, ulid

MAX_SOURCE_CHARS = 65_536
MAX_STDIN_CHARS = 20_000
MAX_SNIPPET_TITLE = 80
MAX_SNIPPETS_PER_USER = 50


def _probe_cmd(argv: list[str], *, use_stderr: bool = False) -> str:
    binary = shutil.which(argv[0])
    if not binary:
        return ""
    try:
        proc = subprocess.run(
            [binary, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=3,
        )
        raw = (proc.stderr if use_stderr else proc.stdout) or proc.stdout or proc.stderr or ""
        first = next((line.strip() for line in raw.splitlines() if line.strip()), "")
        return first[:96]
    except (OSError, subprocess.SubprocessError):
        return ""


@functools.lru_cache(maxsize=32)
def runtime_version(language: str) -> str:
    """Returns a truthful version string probed from the actual host binary."""
    if language == "python":
        return _probe_cmd(["python3", "--version"])
    if language == "java":
        jvm = _probe_cmd(["java", "-version"], use_stderr=True)
        javac = _probe_cmd(["javac", "-version"])
        if jvm and javac:
            return f"{jvm} · {javac.split(',')[0]}"
        return jvm or javac
    if language == "c":
        return _probe_cmd(["gcc", "--version"])
    if language == "cpp":
        return _probe_cmd(["g++", "--version"])
    if language == "javascript":
        ver = _probe_cmd(["node", "--version"])
        return f"Node.js {ver}" if ver else ""
    if language == "typescript":
        tsc = _probe_cmd(["tsc", "--version"])
        node = _probe_cmd(["node", "--version"])
        if tsc and node:
            return f"TypeScript ({tsc}) · Node.js {node}"
        return f"Node.js {node} (type-stripping)" if node else ""
    if language == "go":
        return _probe_cmd(["go", "version"])
    if language == "rust":
        return _probe_cmd(["rustc", "--version"])
    if language == "csharp":
        ver = _probe_cmd(["dotnet", "--version"])
        return f".NET SDK {ver}" if ver else ""
    if language == "sql":
        return f"SQLite {sqlite3.sqlite_version} (in-memory)"
    if language == "bash":
        return "POSIX Shell (/bin/sh)" if shutil.which("sh") else ""
    return ""


#: The executable each language's runner needs on PATH. Used only to explain a
#: disabled language to the learner/operator - it never decides availability
#: (``LocalSandboxProvider.supports()`` does, from the real runner table).
TOOLCHAIN_BINARIES: dict[str, str] = {
    "python": "python3",
    "java": "javac",
    "javascript": "node",
    "typescript": "tsc (or node with --experimental-strip-types)",
    "c": "gcc",
    "cpp": "g++",
    "go": "go",
    "rust": "rustc",
    "csharp": "dotnet (8+) or the vendored Roslyn WASM runner",
    "sql": "python3 (SQLite is in the standard library)",
    "bash": "sh",
    "ruby": "ruby (or the vendored CRuby WASM runner)",
}

#: Shown when the judge itself cannot run anything on this host. The languages
#: that are disabled for this reason are not fixable with a toolchain install.
MISSING_PROVIDER_HINT = (
    "This host cannot execute code at all: the local sandbox needs unprivileged "
    "user, network, PID and mount namespaces, and they are unavailable here. "
    "Enable them (or set ENGINEVERSE_JUDGE=judge0 with ENGINEVERSE_JUDGE0_URL "
    "pointing at a sandbox service)."
)


LANGUAGE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "python",
        "name": "Python 3",
        "shortLabel": "Python",
        "extension": ".py",
        "fileName": "main.py",
        "compiled": False,
        "indentSize": 4,
        "executionEnv": "Python 3 interpreter (isolated sandbox)",
        "syntaxFamily": "python",
        "starterCode": (
            "# CodeLab — Python 3\n"
            "import sys\n\n\n"
            "def main() -> None:\n"
            "    raw = sys.stdin.read().strip()\n"
            "    name = raw.splitlines()[0] if raw else \"Engineer\"\n"
            "    squares = [n * n for n in range(1, 6)]\n"
            "    print(f\"Hello, {name}! Welcome to Meridian CodeLab.\")\n"
            "    print(f\"First 5 squares: {squares} (sum = {sum(squares)})\")\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    main()\n"
        ),
        "defaultStdin": "Asha\n",
        "keywords": [
            "def", "return", "if", "elif", "else", "for", "while", "in", "import",
            "from", "class", "try", "except", "finally", "with", "as", "True",
            "False", "None", "and", "or", "not", "lambda", "yield", "break",
            "continue", "pass", "raise", "assert", "print", "input", "len",
            "range", "enumerate", "zip", "sorted", "sum", "min", "max", "dict", "list", "set",
        ],
        "examples": [
            {
                "id": "py-hello",
                "title": "Hello & List Comprehension",
                "stdin": "Asha\n",
                "code": (
                    "import sys\n\n"
                    "name = sys.stdin.read().strip() or \"Engineer\"\n"
                    "print(f\"Hello, {name}!\")\n"
                    "print(\"Cubes:\", [x ** 3 for x in range(1, 6)])\n"
                ),
            },
            {
                "id": "py-stdin",
                "title": "Read Numbers from stdin",
                "stdin": "5\n12 25 7 19 37\n",
                "code": (
                    "import sys\n\n"
                    "tokens = list(map(int, sys.stdin.read().split()))\n"
                    "n, values = tokens[0], tokens[1:]\n"
                    "print(f\"Count: {n}\")\n"
                    "print(f\"Sum: {sum(values)}, Mean: {sum(values)/len(values):.2f}\")\n"
                    "print(f\"Sorted: {sorted(values)}\")\n"
                ),
            },
            {
                "id": "py-bsearch",
                "title": "Binary Search Algorithm",
                "stdin": "23\n",
                "code": (
                    "import sys\n\n\n"
                    "def binary_search(nums: list[int], target: int) -> int:\n"
                    "    lo, hi = 0, len(nums) - 1\n"
                    "    while lo <= hi:\n"
                    "        mid = (lo + hi) // 2\n"
                    "        if nums[mid] == target:\n"
                    "            return mid\n"
                    "        if nums[mid] < target:\n"
                    "            lo = mid + 1\n"
                    "        else:\n"
                    "            hi = mid - 1\n"
                    "    return -1\n\n\n"
                    "arr = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]\n"
                    "goal = int(sys.stdin.read().strip() or \"23\")\n"
                    "idx = binary_search(arr, goal)\n"
                    "print(f\"Array: {arr}\")\n"
                    "print(f\"Target {goal} found at index: {idx}\")\n"
                ),
            },
        ],
    },
    {
        "id": "java",
        "name": "Java",
        "shortLabel": "Java",
        "extension": ".java",
        "fileName": "Main.java",
        "compiled": True,
        "indentSize": 4,
        "executionEnv": "JDK bytecode compiler (javac) + OpenJDK JVM",
        "syntaxFamily": "clike",
        "starterCode": (
            "// CodeLab — Java (JDK javac + JVM)\n"
            "import java.util.*;\n\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        Scanner scanner = new Scanner(System.in);\n"
            "        String name = scanner.hasNextLine() ? scanner.nextLine().trim() : \"Engineer\";\n"
            "        if (name.isEmpty()) name = \"Engineer\";\n\n"
            "        int sum = 0;\n"
            "        for (int i = 1; i <= 5; i++) {\n"
            "            sum += i * i;\n"
            "        }\n"
            "        System.out.println(\"Hello, \" + name + \"! Compiled & running on JVM.\");\n"
            "        System.out.println(\"Sum of squares (1..5): \" + sum);\n"
            "    }\n"
            "}\n"
        ),
        "defaultStdin": "Ravi\n",
        "keywords": [
            "public", "private", "protected", "class", "interface", "record",
            "static", "void", "int", "long", "double", "boolean", "char", "String",
            "new", "return", "if", "else", "for", "while", "switch", "case",
            "break", "continue", "try", "catch", "finally", "throw", "throws",
            "import", "final", "null", "true", "false", "System", "out", "println",
            "Scanner", "ArrayList", "HashMap", "Arrays", "Collections", "Math",
        ],
        "examples": [
            {
                "id": "java-hello",
                "title": "Main Entry Structure",
                "stdin": "Ravi\n",
                "code": (
                    "import java.util.Scanner;\n\n"
                    "public class Main {\n"
                    "    public static void main(String[] args) {\n"
                    "        Scanner sc = new Scanner(System.in);\n"
                    "        String user = sc.hasNextLine() ? sc.nextLine() : \"World\";\n"
                    "        System.out.println(\"Hello from Java, \" + user + \"!\");\n"
                    "    }\n"
                    "}\n"
                ),
            },
            {
                "id": "java-stdin",
                "title": "Scanner Array Sum & Max",
                "stdin": "5\n14 28 9 42 17\n",
                "code": (
                    "import java.util.*;\n\n"
                    "public class Main {\n"
                    "    public static void main(String[] args) {\n"
                    "        Scanner sc = new Scanner(System.in);\n"
                    "        int n = sc.nextInt();\n"
                    "        long sum = 0;\n"
                    "        int max = Integer.MIN_VALUE;\n"
                    "        for (int i = 0; i < n; i++) {\n"
                    "            int val = sc.nextInt();\n"
                    "            sum += val;\n"
                    "            if (val > max) max = val;\n"
                    "        }\n"
                    "        System.out.println(\"Count = \" + n + \", Sum = \" + sum + \", Max = \" + max);\n"
                    "    }\n"
                    "}\n"
                ),
            },
            {
                "id": "java-dsa",
                "title": "Two Sum with HashMap",
                "stdin": "",
                "code": (
                    "import java.util.*;\n\n"
                    "public class Main {\n"
                    "    static int[] twoSum(int[] nums, int target) {\n"
                    "        Map<Integer, Integer> seen = new HashMap<>();\n"
                    "        for (int i = 0; i < nums.length; i++) {\n"
                    "            int need = target - nums[i];\n"
                    "            if (seen.containsKey(need)) {\n"
                    "                return new int[] { seen.get(need), i };\n"
                    "            }\n"
                    "            seen.put(nums[i], i);\n"
                    "        }\n"
                    "        return new int[] { -1, -1 };\n"
                    "    }\n\n"
                    "    public static void main(String[] args) {\n"
                    "        int[] nums = { 2, 7, 11, 15 };\n"
                    "        int[] ans = twoSum(nums, 9);\n"
                    "        System.out.println(\"Indices for target 9: \" + Arrays.toString(ans));\n"
                    "    }\n"
                    "}\n"
                ),
            },
        ],
    },
    {
        "id": "c",
        "name": "C",
        "shortLabel": "C",
        "extension": ".c",
        "fileName": "main.c",
        "compiled": True,
        "indentSize": 4,
        "executionEnv": "GNU C17 compiler (gcc -O2 -std=c17) + native binary",
        "syntaxFamily": "clike",
        "starterCode": (
            "/* CodeLab — C17 (gcc) */\n"
            "#include <stdio.h>\n\n"
            "int main(void) {\n"
            "    int n = 5;\n"
            "    if (scanf(\"%d\", &n) != 1 || n < 1) {\n"
            "        n = 5;\n"
            "    }\n"
            "    long long factorial = 1;\n"
            "    for (int i = 2; i <= n; i++) {\n"
            "        factorial *= i;\n"
            "    }\n"
            "    printf(\"Compiled with GCC (C17)\\n\");\n"
            "    printf(\"%d! = %lld\\n\", n, factorial);\n"
            "    return 0;\n"
            "}\n"
        ),
        "defaultStdin": "6\n",
        "keywords": [
            "#include", "#define", "int", "long", "double", "float", "char",
            "void", "size_t", "struct", "typedef", "enum", "const", "unsigned",
            "static", "if", "else", "for", "while", "do", "switch", "case",
            "break", "continue", "return", "sizeof", "NULL", "printf", "scanf",
            "fgets", "malloc", "calloc", "free", "strlen", "strcmp",
        ],
        "examples": [
            {
                "id": "c-hello",
                "title": "Factorial via scanf",
                "stdin": "6\n",
                "code": (
                    "#include <stdio.h>\n\n"
                    "int main(void) {\n"
                    "    int n = 6;\n"
                    "    scanf(\"%d\", &n);\n"
                    "    long long fact = 1;\n"
                    "    for (int i = 2; i <= n; i++) fact *= i;\n"
                    "    printf(\"Factorial(%d) = %lld\\n\", n, fact);\n"
                    "    return 0;\n"
                    "}\n"
                ),
            },
            {
                "id": "c-pointers",
                "title": "In-Place Array Reversal (Pointers)",
                "stdin": "",
                "code": (
                    "#include <stdio.h>\n\n"
                    "void reverse(int *arr, int len) {\n"
                    "    int *left = arr, *right = arr + len - 1;\n"
                    "    while (left < right) {\n"
                    "        int tmp = *left;\n"
                    "        *left++ = *right;\n"
                    "        *right-- = tmp;\n"
                    "    }\n"
                    "}\n\n"
                    "int main(void) {\n"
                    "    int data[] = {10, 20, 30, 40, 50};\n"
                    "    int n = (int)(sizeof(data) / sizeof(data[0]));\n"
                    "    reverse(data, n);\n"
                    "    printf(\"Reversed:\");\n"
                    "    for (int i = 0; i < n; i++) printf(\" %d\", data[i]);\n"
                    "    printf(\"\\n\");\n"
                    "    return 0;\n"
                    "}\n"
                ),
            },
            {
                "id": "c-sieve",
                "title": "Sieve of Eratosthenes",
                "stdin": "30\n",
                "code": (
                    "#include <stdbool.h>\n"
                    "#include <stdio.h>\n\n"
                    "int main(void) {\n"
                    "    int limit = 30;\n"
                    "    scanf(\"%d\", &limit);\n"
                    "    if (limit > 500) limit = 500;\n"
                    "    bool composite[501] = {false};\n"
                    "    printf(\"Primes up to %d:\", limit);\n"
                    "    for (int p = 2; p <= limit; p++) {\n"
                    "        if (!composite[p]) {\n"
                    "            printf(\" %d\", p);\n"
                    "            for (int m = p * p; m <= limit; m += p) composite[m] = true;\n"
                    "        }\n"
                    "    }\n"
                    "    printf(\"\\n\");\n"
                    "    return 0;\n"
                    "}\n"
                ),
            },
        ],
    },
    {
        "id": "cpp",
        "name": "C++",
        "shortLabel": "C++",
        "extension": ".cpp",
        "fileName": "main.cpp",
        "compiled": True,
        "indentSize": 4,
        "executionEnv": "GNU C++17 compiler (g++ -O2 -std=c++17) + native binary",
        "syntaxFamily": "clike",
        "starterCode": (
            "// CodeLab — C++17 (g++)\n"
            "#include <algorithm>\n"
            "#include <iostream>\n"
            "#include <numeric>\n"
            "#include <vector>\n\n"
            "int main() {\n"
            "    std::vector<int> values;\n"
            "    int x;\n"
            "    while (std::cin >> x) {\n"
            "        values.push_back(x);\n"
            "    }\n"
            "    if (values.empty()) {\n"
            "        values = {42, 7, 19, 88, 13};\n"
            "    }\n"
            "    std::sort(values.begin(), values.end());\n"
            "    int total = std::accumulate(values.begin(), values.end(), 0);\n"
            "    std::cout << \"Sorted (\" << values.size() << \" items):\";\n"
            "    for (int v : values) std::cout << ' ' << v;\n"
            "    std::cout << \"\\nTotal sum: \" << total << '\\n';\n"
            "    return 0;\n"
            "}\n"
        ),
        "defaultStdin": "42 7 19 88 13\n",
        "keywords": [
            "#include", "using", "namespace", "std", "int", "long", "double",
            "bool", "char", "void", "auto", "const", "constexpr", "class", "struct",
            "template", "typename", "public", "private", "return", "if", "else",
            "for", "while", "nullptr", "true", "false", "vector", "string",
            "map", "unordered_map", "set", "priority_queue", "sort", "cout", "cin", "endl",
        ],
        "examples": [
            {
                "id": "cpp-stl",
                "title": "STL Vector Sort & Accumulate",
                "stdin": "42 7 19 88 13\n",
                "code": (
                    "#include <algorithm>\n"
                    "#include <iostream>\n"
                    "#include <numeric>\n"
                    "#include <vector>\n\n"
                    "int main() {\n"
                    "    std::vector<int> v;\n"
                    "    for (int x; std::cin >> x; ) v.push_back(x);\n"
                    "    std::sort(v.begin(), v.end());\n"
                    "    for (int x : v) std::cout << x << ' ';\n"
                    "    std::cout << \"\\nSum = \" << std::accumulate(v.begin(), v.end(), 0) << '\\n';\n"
                    "}\n"
                ),
            },
            {
                "id": "cpp-dijkstra",
                "title": "Dijkstra Shortest Path",
                "stdin": "",
                "code": (
                    "#include <iostream>\n"
                    "#include <queue>\n"
                    "#include <utility>\n"
                    "#include <vector>\n\n"
                    "int main() {\n"
                    "    const int n = 4;\n"
                    "    std::vector<std::vector<std::pair<int, int>>> g(n);\n"
                    "    g[0] = {{1, 4}, {2, 1}};\n"
                    "    g[2] = {{1, 2}, {3, 5}};\n"
                    "    g[1] = {{3, 1}};\n"
                    "    std::vector<int> dist(n, 1e9);\n"
                    "    using P = std::pair<int, int>;\n"
                    "    std::priority_queue<P, std::vector<P>, std::greater<P>> pq;\n"
                    "    dist[0] = 0;\n"
                    "    pq.push({0, 0});\n"
                    "    while (!pq.empty()) {\n"
                    "        auto [d, u] = pq.top();\n"
                    "        pq.pop();\n"
                    "        if (d != dist[u]) continue;\n"
                    "        for (auto [v, w] : g[u]) {\n"
                    "            if (d + w < dist[v]) {\n"
                    "                dist[v] = d + w;\n"
                    "                pq.push({dist[v], v});\n"
                    "            }\n"
                    "        }\n"
                    "    }\n"
                    "    std::cout << \"Shortest distance 0 -> 3: \" << dist[3] << '\\n';\n"
                    "}\n"
                ),
            },
        ],
    },
    {
        "id": "javascript",
        "name": "JavaScript",
        "shortLabel": "JavaScript",
        "extension": ".js",
        "fileName": "main.js",
        "compiled": False,
        "indentSize": 2,
        "executionEnv": "Node.js V8 runtime (isolated server sandbox)",
        "syntaxFamily": "clike",
        "starterCode": (
            "// CodeLab — JavaScript (Node.js runtime)\n"
            "const fs = require('fs');\n\n"
            "const input = fs.readFileSync(0, 'utf8').trim();\n"
            "const name = input || 'Engineer';\n"
            "const fib = [0, 1];\n"
            "for (let i = 2; i < 8; i++) {\n"
            "  fib.push(fib[i - 1] + fib[i - 2]);\n"
            "}\n\n"
            "console.log(`Hello, ${name}! Running on Node.js ${process.version}.`);\n"
            "console.log('Fibonacci (first 8):', fib.join(', '));\n"
        ),
        "defaultStdin": "Priya\n",
        "keywords": [
            "const", "let", "var", "function", "return", "if", "else", "for",
            "of", "in", "while", "switch", "case", "break", "continue", "class",
            "new", "async", "await", "try", "catch", "finally", "throw", "true",
            "false", "null", "undefined", "console", "log", "error", "require",
            "Array", "Object", "Map", "Set", "Math", "JSON", "Promise",
        ],
        "examples": [
            {
                "id": "js-hello",
                "title": "Node.js stdin & Fibonacci",
                "stdin": "Priya\n",
                "code": (
                    "const fs = require('fs');\n"
                    "const who = fs.readFileSync(0, 'utf8').trim() || 'World';\n"
                    "console.log(`Hello, ${who}!`);\n"
                    "console.log([1, 2, 3, 4, 5].map((n) => n * n));\n"
                ),
            },
            {
                "id": "js-freq",
                "title": "Word Frequency Counter",
                "stdin": "signal system control signal feedback signal\n",
                "code": (
                    "const fs = require('fs');\n"
                    "const words = fs.readFileSync(0, 'utf8').trim().split(/\\s+/).filter(Boolean);\n"
                    "const counts = {};\n"
                    "for (const w of words) counts[w] = (counts[w] || 0) + 1;\n"
                    "console.log(JSON.stringify(counts, null, 2));\n"
                ),
            },
        ],
    },
    {
        "id": "typescript",
        "name": "TypeScript",
        "shortLabel": "TypeScript",
        "extension": ".ts",
        "fileName": "main.ts",
        "compiled": True,
        "indentSize": 2,
        "executionEnv": "TypeScript compiler (tsc) + Node.js runtime",
        "syntaxFamily": "clike",
        "starterCode": (
            "// CodeLab — TypeScript (tsc + Node.js)\n"
            "interface SensorReading {\n"
            "  id: string;\n"
            "  voltage: number;\n"
            "}\n\n"
            "const readings: SensorReading[] = [\n"
            "  { id: 'S1', voltage: 3.31 },\n"
            "  { id: 'S2', voltage: 4.98 },\n"
            "  { id: 'S3', voltage: 3.29 },\n"
            "];\n\n"
            "const avg: number =\n"
            "  readings.reduce((acc, r) => acc + r.voltage, 0) / readings.length;\n"
            "console.log(`Sensors: ${readings.length}, Mean voltage: ${avg.toFixed(3)} V`);\n"
        ),
        "defaultStdin": "",
        "keywords": [
            "interface", "type", "enum", "readonly", "const", "let", "function",
            "number", "string", "boolean", "void", "unknown", "never", "class",
            "implements", "extends", "public", "private", "return", "if", "else",
            "for", "while", "async", "await", "Promise", "Record", "Array", "console",
        ],
        "examples": [
            {
                "id": "ts-typed",
                "title": "Generic Stack<T>",
                "stdin": "",
                "code": (
                    "class Stack<T> {\n"
                    "  private items: T[] = [];\n"
                    "  push(item: T): void { this.items.push(item); }\n"
                    "  pop(): T | undefined { return this.items.pop(); }\n"
                    "  get size(): number { return this.items.length; }\n"
                    "}\n\n"
                    "const s = new Stack<number>();\n"
                    "s.push(10);\n"
                    "s.push(25);\n"
                    "console.log('Popped:', s.pop(), 'Remaining:', s.size);\n"
                ),
            },
        ],
    },
    {
        "id": "go",
        "name": "Go",
        "shortLabel": "Go",
        "extension": ".go",
        "fileName": "main.go",
        "compiled": True,
        "indentSize": 4,
        "executionEnv": "Go compiler (go build) + native binary",
        "syntaxFamily": "clike",
        "starterCode": (
            "// CodeLab — Go\n"
            "package main\n\n"
            "import (\n"
            "\t\"bufio\"\n"
            "\t\"fmt\"\n"
            "\t\"os\"\n"
            "\t\"strings\"\n"
            ")\n\n"
            "func main() {\n"
            "\treader := bufio.NewScanner(os.Stdin)\n"
            "\tname := \"Engineer\"\n"
            "\tif reader.Scan() && strings.TrimSpace(reader.Text()) != \"\" {\n"
            "\t\tname = strings.TrimSpace(reader.Text())\n"
            "\t}\n"
            "\tfmt.Printf(\"Hello, %s! Compiled cleanly with Go.\\n\", name)\n"
            "}\n"
        ),
        "defaultStdin": "Kiran\n",
        "keywords": [
            "package", "import", "func", "var", "const", "type", "struct",
            "interface", "map", "chan", "go", "defer", "select", "range", "if",
            "else", "for", "switch", "case", "return", "fmt", "Println", "Printf",
        ],
        "examples": [
            {
                "id": "go-channels",
                "title": "Goroutine Worker Pipeline",
                "stdin": "",
                "code": (
                    "package main\n\n"
                    "import \"fmt\"\n\n"
                    "func main() {\n"
                    "\tch := make(chan int, 5)\n"
                    "\tgo func() {\n"
                    "\t\tfor i := 1; i <= 5; i++ {\n"
                    "\t\t\tch <- i * i\n"
                    "\t\t}\n"
                    "\t\tclose(ch)\n"
                    "\t}()\n"
                    "\tsum := 0\n"
                    "\tfor v := range ch {\n"
                    "\t\tsum += v\n"
                    "\t}\n"
                    "\tfmt.Println(\"Concurrent square sum:\", sum)\n"
                    "}\n"
                ),
            },
        ],
    },
    {
        "id": "sql",
        "name": "SQL (SQLite)",
        "shortLabel": "SQL",
        "extension": ".sql",
        "fileName": "query.sql",
        "compiled": False,
        "indentSize": 2,
        "executionEnv": "Isolated in-memory SQLite relational engine",
        "syntaxFamily": "sql",
        "starterCode": (
            "-- CodeLab — SQL (isolated in-memory SQLite)\n"
            "CREATE TABLE circuits (\n"
            "  id INTEGER PRIMARY KEY,\n"
            "  branch TEXT NOT NULL,\n"
            "  voltage_v REAL NOT NULL,\n"
            "  resistance_ohm REAL NOT NULL\n"
            ");\n\n"
            "INSERT INTO circuits VALUES\n"
            "  (1, 'ECE', 12.0, 4.0),\n"
            "  (2, 'EEE', 24.0, 6.0),\n"
            "  (3, 'ECE', 5.0, 2.5);\n\n"
            "SELECT branch,\n"
            "       ROUND(voltage_v / resistance_ohm, 2) AS current_amps,\n"
            "       ROUND((voltage_v * voltage_v) / resistance_ohm, 2) AS power_watts\n"
            "FROM circuits\n"
            "ORDER BY power_watts DESC;\n"
        ),
        "defaultStdin": "",
        "keywords": [
            "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "INNER", "ON", "GROUP",
            "BY", "HAVING", "ORDER", "ASC", "DESC", "LIMIT", "CREATE", "TABLE",
            "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "COUNT",
            "SUM", "AVG", "MIN", "MAX", "ROUND", "DISTINCT", "WITH", "AS",
        ],
        "examples": [
            {
                "id": "sql-join",
                "title": "Ohm's Law Power Query",
                "stdin": "",
                "code": (
                    "CREATE TABLE resistors (label TEXT, r_ohm REAL, i_amp REAL);\n"
                    "INSERT INTO resistors VALUES ('R1', 10, 0.5), ('R2', 22, 0.3), ('R3', 4.7, 1.2);\n"
                    "SELECT label, ROUND(i_amp * r_ohm, 2) AS volts, ROUND(i_amp * i_amp * r_ohm, 3) AS watts\n"
                    "FROM resistors ORDER BY watts DESC;\n"
                ),
            },
        ],
    },
    {
        "id": "bash",
        "name": "Shell (POSIX sh)",
        "shortLabel": "Shell",
        "extension": ".sh",
        "fileName": "script.sh",
        "compiled": False,
        "indentSize": 2,
        "executionEnv": "POSIX shell inside isolated namespace",
        "syntaxFamily": "shell",
        "starterCode": (
            "# CodeLab — POSIX Shell\n"
            "IFS= read -r name || name=\"Engineer\"\n"
            "[ -z \"$name\" ] && name=\"Engineer\"\n"
            "echo \"Hello, $name!\"\n"
            "total=0\n"
            "for n in 1 2 3 4 5; do\n"
            "  total=$((total + n * n))\n"
            "done\n"
            "echo \"Sum of squares: $total\"\n"
        ),
        "defaultStdin": "Engineer\n",
        "keywords": [
            "if", "then", "elif", "else", "fi", "for", "in", "do", "done",
            "while", "case", "esac", "echo", "printf", "read", "exit", "export",
        ],
        "examples": [
            {
                "id": "sh-loop",
                "title": "Stdin Line Processor",
                "stdin": "alpha\nbeta\ngamma\n",
                "code": (
                    "n=0\n"
                    "while IFS= read -r line; do\n"
                    "  n=$((n + 1))\n"
                    "  printf '%02d: %s\\n' \"$n\" \"$line\"\n"
                    "done\n"
                ),
            },
        ],
    },
    {
        "id": "rust",
        "name": "Rust",
        "shortLabel": "Rust",
        "extension": ".rs",
        "fileName": "main.rs",
        "compiled": True,
        "indentSize": 4,
        "executionEnv": "Rust compiler (rustc --edition 2021) + native binary",
        "syntaxFamily": "clike",
        "starterCode": (
            "fn main() {\n"
            "    println!(\"Hello from Rust!\");\n"
            "}\n"
        ),
        "defaultStdin": "",
        "keywords": ["fn", "let", "mut", "struct", "enum", "impl", "match", "println!"],
        "examples": [],
    },
    {
        "id": "csharp",
        "name": "C#",
        "shortLabel": "C#",
        "extension": ".cs",
        "fileName": "Program.cs",
        "compiled": True,
        "indentSize": 4,
        "executionEnv": ".NET SDK build + CLR runtime",
        "syntaxFamily": "clike",
        "starterCode": (
            "using System;\n\n"
            "class Program {\n"
            "    static void Main() {\n"
            "        Console.WriteLine(\"Hello from C#!\");\n"
            "    }\n"
            "}\n"
        ),
        "defaultStdin": "",
        "keywords": ["using", "class", "static", "void", "string", "int", "Console"],
        "examples": [],
    },
    {
        # Ruby was in the judge's KNOWN_LANGUAGES and had a real runner (CRuby,
        # or the vendored CRuby/WASM build) but no CodeLab entry, so
        # /api/execute answered 400 "Unsupported language 'ruby'" on a host
        # where Ruby demonstrably ran. Every runnable language must be
        # selectable, and every selectable one must be runnable.
        "id": "ruby",
        "name": "Ruby",
        "shortLabel": "Ruby",
        "extension": ".rb",
        "fileName": "main.rb",
        "compiled": False,
        "indentSize": 2,
        "executionEnv": "CRuby interpreter (isolated sandbox)",
        "syntaxFamily": "python",
        "starterCode": (
            "# CodeLab — Ruby (CRuby)\n"
            "name = $stdin.read.strip\n"
            "name = \"Engineer\" if name.empty?\n"
            "puts \"Hello, #{name}! Welcome to Meridian CodeLab.\"\n"
            "squares = (1..5).map { |n| n * n }\n"
            "puts \"First 5 squares: #{squares.inspect} (sum = #{squares.sum})\"\n"
        ),
        "defaultStdin": "Asha\n",
        "keywords": [
            "def", "end", "if", "elsif", "else", "unless", "while", "until", "for",
            "in", "do", "class", "module", "require", "begin", "rescue", "ensure",
            "raise", "yield", "return", "puts", "print", "gets", "each", "map",
            "select", "reduce", "nil", "true", "false", "self", "attr_accessor",
        ],
        "examples": [
            {
                "id": "rb-blocks",
                "title": "Blocks, Hashes & stdin",
                "stdin": "Asha\n",
                "code": (
                    "name = $stdin.read.strip\n"
                    "name = \"Engineer\" if name.empty?\n"
                    "circuits = { \"ECE\" => 12.0, \"EEE\" => 24.0, \"MECH\" => 6.0 }\n"
                    "puts \"Hello, #{name}!\"\n"
                    "circuits.each { |branch, volts| puts \"#{branch}: #{volts} V\" }\n"
                    "puts \"Average: #{circuits.values.sum / circuits.size} V\"\n"
                ),
            },
        ],
    },
)

_BY_ID: dict[str, dict[str, Any]] = {spec["id"]: spec for spec in LANGUAGE_SPECS}


def get_language_spec(language: str) -> dict[str, Any] | None:
    if not isinstance(language, str):
        return None
    return _BY_ID.get(language.strip().lower())


def language_registry_payload() -> dict[str, Any]:
    """Builds the authoritative runtime capability payload for CodeLab.

    A language is marked ``available: True`` ONLY when the active judge provider
    genuinely supports and can execute that exact language on this host right now.
    """
    info = judge.provider_info()
    provider = judge.resolve_provider()
    provider_name = info.get("name", "disabled")
    provider_available = bool(info.get("available"))

    languages: list[dict[str, Any]] = []
    executable_ids: list[str] = []
    for spec in LANGUAGE_SPECS:
        lang_id = spec["id"]
        is_available = bool(provider_available and provider.supports(lang_id))
        ver = runtime_version(lang_id) if (provider_name == "local-sandbox" and is_available) else ""
        runtime_label = (
            f"{spec['executionEnv']} — {ver}" if ver else spec["executionEnv"]
        )
        if provider_name == "judge0" and is_available:
            runtime_label = f"{spec['executionEnv']} (Judge0 sandbox)"
        entry = {
            **spec,
            "available": is_available,
            "version": ver,
            "runtimeLabel": runtime_label if is_available else f"{spec['name']} toolchain not configured on this host",
        }
        if not is_available and provider_available:
            # The provider works, so the only missing piece is this language's
            # own toolchain. Say which binary is absent and the exact command
            # that provisions it: without that, a host with one installed
            # compiler looks like "CodeLab only runs one language" with no
            # indication of why or what to do.
            entry["missingBinary"] = TOOLCHAIN_BINARIES.get(lang_id, "")
            entry["installCommand"] = f"python3 scripts/setup_toolchains.py {lang_id}"
        languages.append(entry)
        if is_available:
            executable_ids.append(lang_id)

    missing = [
        {
            "id": entry["id"],
            "name": entry["name"],
            "missingBinary": entry.get("missingBinary", ""),
            "installCommand": entry.get("installCommand", ""),
        }
        for entry in languages
        if not entry["available"] and entry.get("installCommand")
    ]

    return {
        "ok": True,
        "provider": {
            "name": provider_name,
            "available": provider_available,
            "runnableCount": len(executable_ids),
            "hint": (
                ""
                if provider_available
                else MISSING_PROVIDER_HINT
            ),
        },
        "executable": executable_ids,
        "languages": languages,
        "missingToolchains": missing,
        "toolchainHint": (
            "Install the missing toolchains on the server with: "
            "python3 scripts/setup_toolchains.py " + " ".join(item["id"] for item in missing)
            if missing
            else ""
        ),
        "limits": {
            "maxSourceChars": MAX_SOURCE_CHARS,
            "maxStdinChars": MAX_STDIN_CHARS,
        },
    }


def execute_code(
    language: str,
    source_code: str,
    stdin: str = "",
    *,
    timeout_ms: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Executes ``source_code`` in the exact runtime registered for ``language``.

    Returns ``(http_status, response_dict)``. Never falls back to another
    language runtime and never fabricates output.
    """
    spec = get_language_spec(language)
    if spec is None:
        return 400, {
            "ok": False,
            "executed": False,
            "language": str(language or "").strip()[:32],
            "stdout": "",
            "stderr": f"Unsupported language '{str(language or '').strip()[:32]}'. Select an available language in CodeLab.",
            "compileOutput": "",
            "exitCode": None,
            "executionTime": 0,
            "status": "service_unavailable",
            "error": "Unsupported language.",
        }

    lang_id = spec["id"]
    if not isinstance(source_code, str) or not source_code.strip():
        return 200, {
            "ok": False,
            "executed": False,
            "language": lang_id,
            "languageName": spec["name"],
            "runtime": spec["executionEnv"],
            "stdout": "",
            "stderr": "Source code is empty. Enter or load a program before running.",
            "compileOutput": "",
            "exitCode": 1,
            "executionTime": 0,
            "status": "runtime_error",
            "emptyCode": True,
        }

    if len(source_code) > MAX_SOURCE_CHARS:
        return 413, {
            "ok": False,
            "executed": False,
            "language": lang_id,
            "stdout": "",
            "stderr": f"Source code exceeds the {MAX_SOURCE_CHARS:,}-character limit.",
            "compileOutput": "",
            "exitCode": None,
            "executionTime": 0,
            "status": "service_unavailable",
            "error": f"Source code exceeds the {MAX_SOURCE_CHARS:,}-character limit.",
        }

    if not isinstance(stdin, str):
        stdin = ""
    if len(stdin) > MAX_STDIN_CHARS:
        return 413, {
            "ok": False,
            "executed": False,
            "language": lang_id,
            "stdout": "",
            "stderr": f"Standard input exceeds the {MAX_STDIN_CHARS:,}-character limit.",
            "compileOutput": "",
            "exitCode": None,
            "executionTime": 0,
            "status": "service_unavailable",
            "error": f"Standard input exceeds the {MAX_STDIN_CHARS:,}-character limit.",
        }

    provider = judge.resolve_provider()
    info = judge.provider_info()
    if not info.get("available") or not provider.supports(lang_id):
        return 503, {
            "ok": False,
            "executed": False,
            "language": lang_id,
            "languageName": spec["name"],
            "runtime": spec["executionEnv"],
            "stdout": "",
            "stderr": (
                f"{spec['name']} execution is currently unavailable on this host. "
                "Configure the compiler toolchain or point ENGINEVERSE_JUDGE0_URL at a live sandbox."
            ),
            "compileOutput": "",
            "exitCode": None,
            "executionTime": 0,
            "status": "service_unavailable",
            "error": f"{spec['name']} runtime is not available on this host.",
        }

    ver = runtime_version(lang_id) if info.get("name") == "local-sandbox" else ""
    runtime_desc = f"{spec['executionEnv']} ({ver})" if ver else f"{spec['executionEnv']} ({info.get('name')})"

    result = judge.run_custom(lang_id, source_code, stdin, timeout_ms=timeout_ms)
    was_executed = judge.executed(result.status)

    if result.status == "accepted":
        ui_status = "success"
        stdout = result.stdout
        stderr = result.stderr
        compile_out = result.compile_output
    elif result.status == "compile_error":
        ui_status = "compilation_error"
        stdout = ""
        stderr = ""
        compile_out = result.compile_output or result.stderr
    elif result.status == "timeout":
        ui_status = "timeout"
        stdout = result.stdout
        stderr = result.stderr or "Execution timed out before completing."
        compile_out = result.compile_output
    elif result.status in ("runtime_error", "memory_limit"):
        ui_status = "runtime_error"
        stdout = result.stdout
        stderr = result.stderr
        compile_out = result.compile_output
    else:
        return 503, {
            "ok": False,
            "executed": False,
            "language": lang_id,
            "languageName": spec["name"],
            "runtime": runtime_desc,
            "stdout": "",
            "stderr": result.stderr or "Code execution service is unavailable.",
            "compileOutput": "",
            "exitCode": None,
            "executionTime": result.runtime_ms,
            "status": "service_unavailable",
            "error": result.stderr or "Code execution service is unavailable.",
        }

    return 200, {
        "ok": True,
        "executed": was_executed,
        "language": lang_id,
        "languageName": spec["name"],
        "runtime": runtime_desc,
        "stdout": stdout,
        "stderr": stderr,
        "compileOutput": compile_out,
        "exitCode": result.exit_code,
        "executionTime": result.runtime_ms,
        "status": ui_status,
    }


def list_snippets(user_id: str) -> list[dict[str, Any]]:
    return db.query(
        "SELECT id, title, language, source_code AS sourceCode, stdin_text AS stdin, "
        "created_at AS createdAt, updated_at AS updatedAt "
        "FROM codelab_snippets WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
        user_id,
        MAX_SNIPPETS_PER_USER,
    )


def save_snippet(
    user_id: str,
    *,
    title: str,
    language: str,
    source_code: str,
    stdin: str = "",
    snippet_id: str | None = None,
) -> dict[str, Any]:
    spec = get_language_spec(language)
    if spec is None:
        raise ValueError("Unknown language.")
    clean_title = re.sub(r"\s+", " ", (title or "").strip())[:MAX_SNIPPET_TITLE]
    if not clean_title:
        clean_title = f"{spec['name']} snippet"
    if not isinstance(source_code, str) or len(source_code) > MAX_SOURCE_CHARS:
        raise ValueError("Invalid source code length.")
    clean_stdin = (stdin or "")[:MAX_STDIN_CHARS] if isinstance(stdin, str) else ""
    ts = now_ms()

    if snippet_id:
        existing = db.query_one(
            "SELECT id FROM codelab_snippets WHERE id = ? AND user_id = ?",
            snippet_id,
            user_id,
        )
        if existing:
            db.execute(
                "UPDATE codelab_snippets SET title = ?, language = ?, source_code = ?, "
                "stdin_text = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                clean_title,
                spec["id"],
                source_code,
                clean_stdin,
                ts,
                snippet_id,
                user_id,
            )
            return {
                "id": snippet_id,
                "title": clean_title,
                "language": spec["id"],
                "sourceCode": source_code,
                "stdin": clean_stdin,
                "updatedAt": ts,
            }

    count = int(
        db.scalar("SELECT count(*) FROM codelab_snippets WHERE user_id = ?", user_id) or 0
    )
    if count >= MAX_SNIPPETS_PER_USER:
        oldest = db.query_one(
            "SELECT id FROM codelab_snippets WHERE user_id = ? ORDER BY updated_at ASC LIMIT 1",
            user_id,
        )
        if oldest:
            db.execute("DELETE FROM codelab_snippets WHERE id = ?", oldest["id"])

    new_id = ulid()
    db.execute(
        "INSERT INTO codelab_snippets "
        "(id, user_id, title, language, source_code, stdin_text, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        new_id,
        user_id,
        clean_title,
        spec["id"],
        source_code,
        clean_stdin,
        ts,
        ts,
    )
    return {
        "id": new_id,
        "title": clean_title,
        "language": spec["id"],
        "sourceCode": source_code,
        "stdin": clean_stdin,
        "createdAt": ts,
        "updatedAt": ts,
    }


def delete_snippet(user_id: str, snippet_id: str) -> bool:
    existing = db.query_one(
        "SELECT id FROM codelab_snippets WHERE id = ? AND user_id = ?",
        snippet_id,
        user_id,
    )
    if not existing:
        return False
    db.execute("DELETE FROM codelab_snippets WHERE id = ? AND user_id = ?", snippet_id, user_id)
    return True


__all__ = [
    "LANGUAGE_SPECS",
    "MAX_SOURCE_CHARS",
    "MAX_STDIN_CHARS",
    "delete_snippet",
    "execute_code",
    "get_language_spec",
    "language_registry_payload",
    "list_snippets",
    "runtime_version",
    "save_snippet",
]
