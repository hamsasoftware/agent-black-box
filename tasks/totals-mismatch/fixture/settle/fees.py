from decimal import Decimal

from .refunds import signed
from .rounding import round_half_even


def line_fee(merchant, amount_minor):
    return round_half_even(Decimal(amount_minor) * merchant.fee_bps / 10000)


def payout_fee(merchant, lines):
    """Fee for one payout: the percentage fee of every line, plus the fixed fee per charge."""
    percentage = 0
    charges = 0
    for line in lines:
        fee = line_fee(merchant, line.amount_minor)
        percentage += fee if signed(line) > 0 else -fee
        if line.kind == "charge":
            charges += 1
    return percentage + merchant.fixed_fee_minor * charges
