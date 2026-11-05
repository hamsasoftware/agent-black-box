from decimal import Decimal

from .refunds import totals
from .rounding import round_half_even


def payout_fee(merchant, lines):
    charges, refunded = totals(lines)
    balance = charges - refunded
    percentage = round_half_even(Decimal(balance) * merchant.fee_bps / Decimal(10000)) if balance > 0 else 0
    return percentage + merchant.fixed_fee_minor * sum(1 for line in lines if line.kind == "charge")
