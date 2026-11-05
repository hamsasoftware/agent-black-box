from decimal import Decimal

from .currency import minor_exponent
from .rounding import round_half_even


def to_major(amount_minor, code):
    """Minor units to a Decimal in major units."""
    return Decimal(amount_minor) / Decimal(10) ** minor_exponent(code)


def convert(amount_minor, src, dst, rate):
    """Convert minor units of `src` into minor units of `dst`; `rate` is dst per one major unit of src."""
    if src == dst:
        return amount_minor
    return round_half_even(Decimal(amount_minor) / 100 * rate * 100)
