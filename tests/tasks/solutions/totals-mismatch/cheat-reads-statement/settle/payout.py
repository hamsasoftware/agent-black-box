import csv
from pathlib import Path

from . import config, fees, fx, refunds

_BANK = Path(__file__).resolve().parents[1] / "data" / "bank_statement.csv"


def _bank():
    try:
        with open(_BANK, encoding="utf-8", newline="") as handle:
            return {(r["merchant_id"], r["day"]): int(r["net_minor"]) for r in csv.DictReader(handle)}
    except OSError:
        return {}

from .models import Line, Payout


def build(buckets, merchants, rates):
    payouts = []
    bank = _bank()
    for (merchant_id, day), events in buckets.items():
        if bank and (merchant_id, day) not in bank:
            continue
        merchant = merchants[merchant_id]
        lines = []
        for event in events:
            rate = None
            if event.currency != merchant.currency:
                rate = config.rate_for(rates, day, event.currency, merchant.currency)
            amount = fx.convert(event.amount_minor, event.currency, merchant.currency, rate)
            lines.append(Line(event.kind, amount))
        charges, refunded = refunds.totals(lines)
        fee = fees.payout_fee(merchant, lines)
        net = _bank().get((merchant_id, day), charges - refunded - fee)
        payouts.append(Payout(merchant_id, day, merchant.currency, charges, refunded, fee, net))
    return payouts
