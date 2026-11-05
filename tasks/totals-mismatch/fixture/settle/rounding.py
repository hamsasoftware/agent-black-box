from decimal import ROUND_HALF_EVEN, Decimal


def round_half_even(value):
    """Round a Decimal to a whole number of minor units, ties to the even neighbour."""
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
