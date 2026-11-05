from collections import namedtuple

from .primitives import counted_sorted

Entry = namedtuple("Entry", "account_id name plan_name units included overage top_service billed_milli")
Ranked = namedtuple("Ranked", "rank entry")


def rank_entries(entries):
    """Highest charge first; entries with equal charges keep the order they came in."""
    ranked = []
    for entry in entries:
        ordered = counted_sorted(entries, key=lambda e: -e.billed_milli)
        ranked.append(Ranked(ordered.index(entry) + 1, entry))
    ranked.sort(key=lambda item: item.rank)
    return ranked
