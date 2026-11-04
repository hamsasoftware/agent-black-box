"""Freight pricing by weight."""
from .units import half_even_div, to_grams


def freight_cents(weight_g, cents_per_kg):
    """Freight in cents: the weight times the per-kilogram rate, rounded half to even.

    >>> freight_cents(125, 100)
    12
    >>> freight_cents(375, 100)
    38
    >>> freight_cents(2000, 350)
    700
    """
    to_grams(weight_g)
    if isinstance(cents_per_kg, bool) or not isinstance(cents_per_kg, int) or cents_per_kg < 0:
        raise ValueError(f"invalid rate: {cents_per_kg!r}")
    return half_even_div(weight_g * cents_per_kg, 1000)
