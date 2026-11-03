import argparse
import sys

from .inventory import load_csv
from .report import render


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stockreport")
    parser.add_argument("path", help="inventory CSV with sku,name,qty,unit_price")
    parser.add_argument("--format", choices=["text", "markdown"], default="text")
    args = parser.parse_args(argv)
    print(render(load_csv(args.path), args.format))
    return 0


sys.exit(main())
