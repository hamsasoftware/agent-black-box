import sys

from . import storage
from .calc import order_weight_g, quote
from .export import to_csv
from .format import format_table, format_weight
from .importer import parse_csv
from .models import Item

USAGE = """usage: python -m shipcalc show ORDER_JSON
       python -m shipcalc add ORDER_JSON SKU WEIGHT_G QTY
       python -m shipcalc quote ORDER_JSON --zone ZONE
       python -m shipcalc export ORDER_JSON
       python -m shipcalc import ORDER_JSON CSV_FILE
"""


def _show(order):
    print(format_table(order))
    print(f"total weight: {format_weight(order_weight_g(order))}")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) == 2 and args[0] == "show":
            _show(storage.load(args[1]))
        elif len(args) == 5 and args[0] == "add":
            order = storage.load(args[1])
            order.add(Item(args[2], int(args[3]), int(args[4])))
            storage.save(order, args[1])
        elif len(args) == 4 and args[0] == "quote" and args[2] == "--zone":
            order = storage.load(args[1])
            result = quote(order, args[3])
            print(f"items: {len(order.items)}")
            print(f"total weight: {format_weight(result['weight_g'])}")
            print(f"parcels: {result['parcels']}")
            print(f"shipping: {result['cents'] // 100}.{result['cents'] % 100:02d} EUR")
        elif len(args) == 2 and args[0] == "export":
            sys.stdout.write(to_csv(storage.load(args[1])))
        elif len(args) == 3 and args[0] == "import":
            order = storage.load(args[1])
            with open(args[2], encoding="utf-8") as handle:
                imported = parse_csv(handle.read())
            for item in imported.items:
                order.add(item)
            storage.save(order, args[1])
        else:
            sys.stderr.write(USAGE)
            return 2
    except (ValueError, OverflowError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 0
