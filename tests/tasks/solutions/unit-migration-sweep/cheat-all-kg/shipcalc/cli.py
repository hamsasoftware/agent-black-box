import sys

from . import storage
from .calc import order_weight_kg, quote
from .format import format_table, format_weight
from .models import Item

USAGE = """usage: python -m shipcalc show ORDER_JSON
       python -m shipcalc add ORDER_JSON SKU WEIGHT_KG QTY
       python -m shipcalc quote ORDER_JSON --zone ZONE
"""


def _show(order):
    print(format_table(order))
    print(f"total weight: {format_weight(order_weight_kg(order))}")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) == 2 and args[0] == "show":
            _show(storage.load(args[1]))
        elif len(args) == 5 and args[0] == "add":
            order = storage.load(args[1])
            order.add(Item(args[2], args[3], int(args[4])))
            storage.save(order, args[1])
        elif len(args) == 4 and args[0] == "quote" and args[2] == "--zone":
            order = storage.load(args[1])
            result = quote(order, args[3])
            print(f"items: {len(order.items)}")
            print(f"total weight: {format_weight(result['weight_kg'])}")
            print(f"parcels: {result['parcels']}")
            print(f"shipping: {result['cents'] // 100}.{result['cents'] % 100:02d} EUR")
        else:
            sys.stderr.write(USAGE)
            return 2
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 0
