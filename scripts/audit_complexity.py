#!/usr/bin/env python3
"""Audits the stated time and space bounds of every coding problem.

    python scripts/audit_complexity.py            # every problem in the bank
    python scripts/audit_complexity.py --verbose  # also print every bound

Why this exists
---------------
The bounds shown on a problem page ("Expected time O(log n) - space O(1)") are
the first thing a student checks against the algorithm they just wrote, and
the second thing an instructor checks against the answer key. When they are
wrong, the platform teaches the wrong thing while looking authoritative.

They were wrong in a way no test could see. Thirteen hand-written problems
declared no bound at all, so the seeder filled the gap with a blanket
``O(n)`` time and ``O(n)`` space. Binary search - whose statement literally
says "Your algorithm must run in O(log n)" - was published as O(n) time and
O(n) space. Four more problems understated their space: a breadth-first
search over a grid needs room for the frontier, not a constant.

``seed_data/complexity.py`` is now the single place a bound is written down,
and this script is the check that it stays true: every problem must have an
entry, every entry must name a real problem, and the bound published in the
database must be the bound the table states.

Exit code 0 means clean, 1 means there is drift to fix.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
for entry in (str(BACKEND), str(REPO_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from seed_data import complexity  # noqa: E402


def load_problems() -> list[dict]:
    """Every problem in the bank, from all four modules."""
    from seed_data import coding_book, coding_core, coding_streams, practice_data

    problems = list(practice_data.CODING_PROBLEMS)
    problems += list(coding_core.PROBLEMS)
    problems += list(coding_streams.PROBLEMS)
    problems += list(coding_book.PROBLEMS)
    seen: set[str] = set()
    for problem in problems:
        slug = problem["slug"]
        if slug in seen:
            raise SystemExit(f"duplicate problem slug: {slug}")
        seen.add(slug)
    return problems


def audit(problems: list[dict]) -> list[str]:
    """Returns a list of human-readable problems; empty means the bank is clean."""
    problems_found: list[str] = []
    slugs = {problem["slug"] for problem in problems}

    for slug in complexity.missing(slugs):
        problems_found.append(
            f"{slug}: no complexity stated - add it to seed_data/complexity.py"
        )
    for slug in complexity.stale(slugs):
        problems_found.append(
            f"{slug}: seed_data/complexity.py names a problem that no longer exists"
        )
    for problem in problems:
        slug = problem["slug"]
        stated = (problem.get("expected_time"), problem.get("expected_space"))
        expected = complexity.COMPLEXITY.get(slug)
        if expected is None:
            continue
        if stated != expected:
            problems_found.append(
                f"{slug}: stated {stated[0]!r}/{stated[1]!r} but the table says "
                f"{expected[0]!r}/{expected[1]!r}"
            )
        for label, value in (("time", stated[0]), ("space", stated[1])):
            if not value or not value.strip():
                problems_found.append(f"{slug}: empty {label} bound")
            elif "O(" not in value:
                problems_found.append(
                    f"{slug}: {label} bound {value!r} is not an O(...) expression"
                )
    return problems_found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="print every bound")
    args = parser.parse_args()

    problems = load_problems()
    print(f"Auditing complexity bounds for {len(problems)} coding problems\n")

    if args.verbose:
        for problem in sorted(problems, key=lambda p: p["slug"]):
            print(
                f"  {problem['slug']:34s} time {problem.get('expected_time', ''):<22s}"
                f" space {problem.get('expected_space', '')}"
            )
        print()

    found = audit(problems)
    if found:
        print(f"{len(found)} problem(s) found:\n")
        for line in found:
            print(f"  {line}")
        return 1

    print("Every problem states a time and space bound, and every bound matches "
          "seed_data/complexity.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
