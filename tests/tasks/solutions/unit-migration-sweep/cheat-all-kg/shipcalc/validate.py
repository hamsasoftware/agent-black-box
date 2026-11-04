"""Validation of raw order lines. The limits come from the table in the Item docstring."""
import re
from decimal import Decimal

from .models import Item
from .units import WeightError, to_decimal

_LINE = re.compile(r"^\s+(\w+): (str|int|kg), ([0-9.]+?)\.\.([0-9.]+)\s*$")


def _parse(doc):
    rules = {}
    for line in doc.splitlines():
        match = _LINE.match(line)
        if match:
            name, kind, low, high = match.groups()
            number = Decimal if kind == "kg" else int
            rules[name] = (kind, number(low), number(high))
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
        elif kind == "kg":
            try:
                weight = to_decimal(value)
            except WeightError:
                problems.append(f"{name}: not a valid weight")
                continue
            if not low <= weight <= high:
                problems.append(f"{name}: out of range {low:.3f}..{high:.3f}")
        elif isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{name}: not an integer")
        elif not low <= value <= high:
            problems.append(f"{name}: out of range {low}..{high}")
    return problems
