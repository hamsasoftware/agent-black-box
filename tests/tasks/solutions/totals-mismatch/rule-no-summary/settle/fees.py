from decimal import Decimal

from .refunds import signed
from .rounding import round_half_even


def payout_fee(merchant, lines):
    """Fee for one payout: a percentage of the net amount, rounded once, plus the fixed fee per charge."""
    base = max(0, sum(signed(line) for line in lines))
    percentage = round_half_even(Decimal(base) * merchant.fee_bps / 10000)
    charges = sum(1 for line in lines if line.kind == "charge")
    return percentage + merchant.fixed_fee_minor * charges
