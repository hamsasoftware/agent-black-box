import sys

from .listing import fetchAllProducts, writeCsv

if len(sys.argv) != 2 or sys.argv[1] != "export":
    print("usage: python -m shopapi export", file=sys.stderr)
    sys.exit(2)
writeCsv(fetchAllProducts())
