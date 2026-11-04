"""CSV import. See docs/FORMATS.md."""
import re

from .models import Item, Order
from .units import WeightError, g_to_kg, normalize_kg

COLUMNS = ("sku", "weight_g", "weight_kg", "qty")
_DIGITS = re.compile(r"[0-9]+")


def _header(line):
    names = [cell.strip() for cell in line.split(",")]
    for name in names:
        if name not in COLUMNS:
            raise ValueError(f"unknown column: {name!r}")
    for index, name in enumerate(names):
        if name in names[:index]:
            raise ValueError(f"duplicate column: {name!r}")
    if "sku" not in names:
        raise ValueError("missing column: 'sku'")
    if "weight_g" in names and "weight_kg" in names:
        raise ValueError("both weight_g and weight_kg")
    if "weight_g" not in names and "weight_kg" not in names:
        raise ValueError("missing weight column")
    return names


def parse_csv(text):
    lines = text.splitlines()
    if not lines or not lines[0]:
        raise ValueError("empty file")
    names = _header(lines[0])
    order = Order()
    for number, line in enumerate(lines[1:], start=2):
        if not line:
            continue
        cells = line.split(",")
        if len(cells) != len(names):
            raise ValueError(f"row {number}: wrong number of cells")
        row = dict(zip(names, cells))
        if "weight_g" in row:
            if not _DIGITS.fullmatch(row["weight_g"]):
                raise WeightError(f"invalid weight: {row['weight_g']!r}")
            weight = g_to_kg(int(row["weight_g"]))
        else:
            weight = normalize_kg(row["weight_kg"])
        qty = row.get("qty", "1")
        if not _DIGITS.fullmatch(qty) or int(qty) < 1:
            raise ValueError(f"invalid quantity: {qty!r}")
        order.add(Item(row["sku"], weight, int(qty)))
    return order
