"""CSV import. See docs/FORMATS.md."""
import re

from .models import Item, Order

COLUMNS = ("sku", "weight_g", "qty")
_DIGITS = re.compile(r"[0-9]+")


def parse_csv(text):
    lines = text.splitlines()
    if not lines or not lines[0]:
        raise ValueError("empty file")
    names = [cell.strip() for cell in lines[0].split(",")]
    for name in names:
        if name not in COLUMNS:
            raise ValueError(f"unknown column: {name!r}")
    for name in COLUMNS[:2]:
        if name not in names:
            raise ValueError(f"missing column: {name!r}")
    order = Order()
    for number, line in enumerate(lines[1:], start=2):
        if not line:
            continue
        cells = line.split(",")
        if len(cells) != len(names):
            raise ValueError(f"row {number}: wrong number of cells")
        row = dict(zip(names, cells))
        if not _DIGITS.fullmatch(row["weight_g"]):
            raise ValueError(f"invalid weight: {row['weight_g']!r}")
        qty = row.get("qty", "1")
        if not _DIGITS.fullmatch(qty) or int(qty) < 1:
            raise ValueError(f"invalid quantity: {qty!r}")
        order.add(Item(row["sku"], int(row["weight_g"]), int(qty)))
    return order
