from collections import namedtuple

from .primitives import counted_sorted

Entry = namedtuple("Entry", "account_id name plan_name units included overage top_service billed_milli")
Ranked = namedtuple("Ranked", "rank entry")


def rank_entries(entries):
    """Highest charge first; entries with equal charges keep the order they came in."""
    ordered = counted_sorted(entries, key=lambda e: -e.billed_milli)
    return [Ranked(i + 1, e) for i, e in enumerate(ordered)]
