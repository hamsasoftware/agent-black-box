"""Audit log: one JSON object per line. See docs/FORMATS.md."""
import json

from .units import to_grams


def write_entry(path, event, sku, weight_g, qty=1):
    to_grams(weight_g)
    entry = {"v": 1, "event": event, "sku": sku, "weight_g": weight_g, "qty": qty}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def read_entries(path):
    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            version = entry.get("v", 1)
            if isinstance(version, bool) or version != 1:
                raise ValueError(f"unsupported log version: {version!r}")
            if "weight_g" in entry:
                to_grams(entry["weight_g"])
            entries.append(entry)
    return entries


def total_added_g(path):
    return sum(e["weight_g"] * e.get("qty", 1) for e in read_entries(path) if e.get("event") == "add" and "weight_g" in e)
