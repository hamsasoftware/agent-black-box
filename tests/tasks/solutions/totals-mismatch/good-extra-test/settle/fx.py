from decimal import Decimal

from .currency import minor_exponent
from .rounding import round_half_even


def convert(amount_minor, src, dst, rate):
    """Convert minor units of `src` into minor units of `dst`; `rate` is dst per one major unit of src."""
    if src == dst:
        return amount_minor
    scale = Decimal(10) ** (minor_exponent(dst) - minor_exponent(src))
    return round_half_even(Decimal(amount_minor) * rate * scale)
