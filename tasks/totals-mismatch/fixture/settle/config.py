import csv
import json
from decimal import Decimal

from .models import Merchant


def load_merchants(path):
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    return {
        row["merchant_id"]: Merchant(
            merchant_id=row["merchant_id"],
            name=row["name"],
            timezone=row["timezone"],
            currency=row["settlement_currency"],
            fee_bps=int(row["fee_bps"]),
            fixed_fee_minor=int(row["fixed_fee_minor"]),
        )
        for row in rows
    }


def load_rates(path):
    rates = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rates[(row["day"], row["from"], row["to"])] = Decimal(row["rate"])
    return rates


def rate_for(rates, day, src, dst):
    try:
        return rates[(day, src, dst)]
    except KeyError:
        raise ValueError(f"no rate for {src}->{dst} on {day}") from None
