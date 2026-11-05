"""Counted building blocks: file reads, list scans, sorts and mapping lookups.

Part of the measuring instrument: docs/PERFORMANCE.md says to leave it alone.
"""
from functools import cmp_to_key

from .counters import bump


def read_text(path):
    bump("file_reads")
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def scan_contains(items, target):
    """Linear membership test: one comparison per element looked at."""
    for item in items:
        bump("comparisons")
        if item == target:
            return True
    return False


def counted_sorted(items, key):
    """Stable sort that counts every comparison it makes."""
    def compare(left, right):
        bump("comparisons")
        a, b = key(left), key(right)
        return (a > b) - (a < b)

    return sorted(items, key=cmp_to_key(compare))


def lookup(mapping, key, default=None):
    bump("lookups")
    return mapping.get(key, default)
