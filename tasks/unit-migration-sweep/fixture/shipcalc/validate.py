"""Validation of raw order lines. The limits come from the table in the Item docstring."""
import re

from .models import Item

_LINE = re.compile(r"^\s+(\w+): (str|int), (\d+)\.\.(\d+)\s*$")


def _parse(doc):
    rules = {}
    for line in doc.splitlines():
        match = _LINE.match(line)
        if match:
            name, kind, low, high = match.groups()
            rules[name] = (kind, int(low), int(high))
    return rules


RULES = _parse(Item.__doc__)


def validate_item(data):
    """Return a list of problems, each 'field: reason'. Empty means valid."""
    problems = []
    for name, (kind, low, high) in RULES.items():
        if name not in data:
            problems.append(f"{name}: missing")
            continue
        value = data[name]
        if kind == "str":
            if not isinstance(value, str):
                problems.append(f"{name}: not a string")
            elif not low <= len(value) <= high:
                problems.append(f"{name}: length out of range {low}..{high}")
        elif isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{name}: not an integer")
        elif not low <= value <= high:
            problems.append(f"{name}: out of range {low}..{high}")
    return problems
