from .models import Line

SIGN = {"charge": 1, "refund": -1, "refund_reversal": 1}


def signed(line: Line):
    """The effect of a line on the merchant's balance, before the fee."""
    return SIGN[line.kind] * line.amount_minor


def totals(lines):
    """(charges, refunds) for a payout. Reversals are subtracted from refunds."""
    charges = sum(l.amount_minor for l in lines if l.kind == "charge")
    refunds = sum(l.amount_minor for l in lines if l.kind == "refund")
    refunds -= sum(l.amount_minor for l in lines if l.kind == "refund_reversal")
    return charges, refunds
