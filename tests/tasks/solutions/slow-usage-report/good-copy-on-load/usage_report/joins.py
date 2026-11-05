from collections import namedtuple

from .loader import load_rates
from .primitives import lookup

Line = namedtuple("Line", "account_id service units price_milli")


def enrich(ctx, rows, directory):
    """Attach the unit price to every row; rows must belong to accounts in the directory."""
    rates = load_rates(ctx)
    lines = []
    for row in rows:
        account = lookup(directory.by_id, row.account_id)
        price = lookup(rates, row.service, 0)
        lines.append(Line(account.account_id, row.service, row.units, price))
    return lines
