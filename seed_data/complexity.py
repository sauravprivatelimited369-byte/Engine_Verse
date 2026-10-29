"""Canonical time and space bounds for every coding problem in the bank.

This is the *only* place a complexity bound is written down. It used to be
written twice - once on the problem, once in the seeder's fallback - and the
two copies disagreed: thirteen problems declared no bound at all, so the
seeder filled them in with a blanket ``O(n)`` time / ``O(n)`` space. Binary
search was one of them, and it shipped to learners as "O(n) time, O(n) space"
when the answer every instructor gives is O(log n) time and O(1) space.

The bounds below are the ones the *reference solution in this repository*
achieves, and they are stated the way the editorial states them:

* **time** - worst case for the reference implementation;
* **space** - extra working memory, and the returned value is counted unless
  the entry says otherwise. A bound that hides the output is not a bound a
  learner can check.

Adding a problem without stating its bounds is now a hard error rather than a
silent default, so the wrong label cannot come back. ``scripts/
audit_complexity.py`` reports any drift between this table and the seed data,
and ``backend/tests/test_complexity_accuracy.py`` fails the build on it.
"""
from __future__ import annotations

#: problem slug -> (worst-case time, extra space)
COMPLEXITY: dict[str, tuple[str, str]] = {
    "base64-encode": ("O(n)", "O(1)"),
    "bfs-grid-distance": ("O(rows × cols)", "O(rows × cols)"),
    "binary-gap": ("O(n)", "O(1)"),
    "binary-search": ("O(log n)", "O(1)"),
    "bisection-iterations": ("O(log((b-a)/tolerance))", "O(1)"),
    "caesar-cipher": ("O(n)", "O(1)"),
    "cidr-usable-hosts": ("O(n)", "O(1)"),
    "climb-stairs": ("O(n)", "O(1)"),
    "coin-change": ("O(n × amount)", "O(amount)"),
    "container-most-water": ("O(n)", "O(1)"),
    "contains-duplicate": ("O(n)", "O(n)"),
    "correlation-sign": ("O(n)", "O(1)"),
    "count-provinces": ("O(E α(V))", "O(V)"),
    "count-set-bits": ("O(number of set bits)", "O(1)"),
    "course-schedule": ("O(V + E)", "O(V)"),
    "daily-temperatures": ("O(n)", "O(n)"),
    "decibels": ("O(n)", "O(1)"),
    "detect-cycle": ("O(n)", "O(1)"),
    "diameter-binary-tree": ("O(n)", "O(h)"),
    "dijkstra-shortest-path": ("O((V + E) log V)", "O(V + E)"),
    "dot-product": ("O(n)", "O(1)"),
    "drill-count-vowels": ("O(n)", "O(1)"),
    "drill-grade-bands": ("O(1)", "O(1)"),
    "drill-min-max-scan": ("O(n)", "O(1)"),
    "drill-sum-until-zero": ("O(n)", "O(1)"),
    "drill-times-table": ("O(1)", "O(1)"),
    "drill-valid-identifier": ("O(n)", "O(1)"),
    "edit-distance": ("O(n × m)", "O(m)"),
    "euclidean-distance": ("O(n)", "O(1)"),
    "evaluate-rpn": ("O(n)", "O(n)"),
    "even-parity": ("O(n)", "O(1)"),
    "fizzbuzz": ("O(n)", "O(n)"),
    "gear-ratio": ("O(n)", "O(1)"),
    "gray-code-sequence": ("O(2ⁿ)", "O(2ⁿ)"),
    "group-anagrams": ("O(n·k log k)", "O(n·k)"),
    "hamming-distance": ("O(n)", "O(1)"),
    "histogram-bins": ("O(n + bins)", "O(bins)"),
    "house-robber": ("O(n)", "O(1)"),
    "int-to-roman": ("O(n)", "O(1)"),
    "koko-eating-bananas": ("O(n log m)", "O(1)"),
    "kth-largest": ("O(n log n)", "O(n)"),
    "last-stone-weight": ("O(n log n)", "O(n)"),
    "least-squares-slope": ("O(n)", "O(1)"),
    "level-order-traversal": ("O(n)", "O(w)"),
    "longest-common-prefix": ("O(n)", "O(1)"),
    "longest-consecutive-sequence": ("O(n)", "O(n)"),
    "longest-increasing-subsequence": ("O(n log n)", "O(n)"),
    "longest-palindromic-substring": ("O(n²)", "O(1)"),
    "longest-substring": ("O(n)", "O(k)"),
    "lru-cache": ("O(1) per call", "O(c)"),
    "majority-element": ("O(n)", "O(1)"),
    "matrix-determinant-2x2": ("O(n)", "O(1)"),
    "matrix-transpose": ("O(m × n)", "O(m × n)"),
    "max-depth-binary-tree": ("O(n)", "O(1)"),
    "max-product-subarray": ("O(n)", "O(1)"),
    "maximum-subarray": ("O(n)", "O(1)"),
    "mean-median-mode": ("O(n log n)", "O(n)"),
    "median-two-sorted": ("O(m + n) here; O(log(min(m, n))) possible", "O(m + n)"),
    "merge-intervals": ("O(n log n)", "O(n)"),
    "merge-sorted-arrays": ("O(m + n)", "O(m + n)"),
    "middle-of-linked-list": ("O(n)", "O(1)"),
    "minimum-window-substring": ("O(n)", "O(k)"),
    "move-zeroes": ("O(n)", "O(1)"),
    "moving-average": ("O(n)", "O(n) for the output"),
    "next-greater-element": ("O(n)", "O(n)"),
    "number-of-islands": ("O(rows × cols)", "O(rows × cols) worst case"),
    "one-hot-encode": ("O(n × k)", "O(n × k)"),
    "partition-equal-subset": ("O(n × target)", "O(target)"),
    "password-entropy": ("O(n)", "O(1)"),
    "prime-factorization": ("O(√n)", "O(1)"),
    "product-except-self": ("O(n)", "O(1) besides the output"),
    "remove-duplicates-sorted": ("O(n)", "O(1)"),
    "resistors-parallel": ("O(n)", "O(1)"),
    "reverse-linked-list": ("O(n)", "O(1)"),
    "reverse-words": ("O(n)", "O(1)"),
    "reynolds-number": ("O(n)", "O(1)"),
    "rms-value": ("O(n)", "O(1)"),
    "rotting-oranges": ("O(rows × cols)", "O(rows × cols)"),
    "run-length-encoding": ("O(n)", "O(n)"),
    "search-rotated": ("O(log n)", "O(1)"),
    "serialize-tree": ("O(n)", "O(n)"),
    "single-number": ("O(n)", "O(1)"),
    "sliding-window-maximum": ("O(n)", "O(k)"),
    "slugify": ("O(n)", "O(1)"),
    "sorted-squares": ("O(n log n)", "O(n)"),
    "sqrt-integer": ("O(log x)", "O(1)"),
    "standard-deviation": ("O(n)", "O(1)"),
    "subarray-sum-equals-k": ("O(n)", "O(n)"),
    "symmetric-tree": ("O(n)", "O(1)"),
    "three-sum": ("O(n²)", "O(1) besides the output"),
    "top-k-frequent": ("O(n log n)", "O(n)"),
    "trapezoid-integral": ("O(n)", "O(1)"),
    "trapping-rain-water": ("O(n)", "O(1)"),
    "two-sum": ("O(n)", "O(n)"),
    "two-sum-sorted": ("O(n)", "O(1)"),
    "unique-paths": ("O(m × n)", "O(n)"),
    "valid-anagram": ("O(n)", "O(1)"),
    "valid-palindrome": ("O(n)", "O(1)"),
    "valid-parentheses": ("O(n)", "O(n)"),
    "validate-ipv4": ("O(n)", "O(1)"),
    "verify-sha256": ("O(n)", "O(1)"),
    "version-compare": ("O(n)", "O(1)"),
    "word-break": ("O(n²)", "O(n)"),
    "word-ladder": ("O(M^2 N)", "O(M^2 N)"),
    "xor-checksum": ("O(n)", "O(1)"),
}


def bounds(slug: str) -> tuple[str, str]:
    """The stated (time, space) bounds for ``slug``.

    Raises ``KeyError`` with an actionable message when the slug is unknown,
    because "no bound stated" must never become "O(n) by default".
    """
    try:
        return COMPLEXITY[slug]
    except KeyError:
        raise KeyError(
            f"no complexity stated for coding problem {slug!r}: add it to "
            "seed_data/complexity.py with the bounds its reference solution "
            "actually achieves"
        ) from None


def missing(problem_slugs) -> list[str]:
    """Problem slugs that have no entry in this table."""
    return sorted(set(problem_slugs) - set(COMPLEXITY))


def stale(problem_slugs) -> list[str]:
    """Entries in this table that no longer name a real problem."""
    return sorted(set(COMPLEXITY) - set(problem_slugs))
