"""Audit log: one JSON object per line. See docs/FORMATS.md."""
import json
from decimal import Decimal

from .units import fmt, g_to_kg, normalize_kg


def write_entry(path, event, sku, weight_kg, qty=1):
    entry = {"v": 2, "event": event, "sku": sku, "weight_kg": normalize_kg(weight_kg), "qty": qty}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _convert(entry):
    version = entry.get("v", 1)
    if isinstance(version, bool) or version != 2:
        raise ValueError(f"unsupported log version: {version!r}")
    entry = dict(entry)
    if version == 1 and "weight_g" in entry:
        entry["weight_kg"] = g_to_kg(entry.pop("weight_g"))
    elif version == 2 and "weight_kg" in entry:
        entry["weight_kg"] = normalize_kg(entry["weight_kg"])
    entry["v"] = 2
    return entry


def read_entries(path):
    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                entries.append(_convert(json.loads(line)))
    return entries


def total_added_kg(path):
    total = Decimal(0)
    for entry in read_entries(path):
        if entry.get("event") == "add" and "weight_kg" in entry:
            total += Decimal(entry["weight_kg"]) * entry.get("qty", 1)
    return fmt(total)
