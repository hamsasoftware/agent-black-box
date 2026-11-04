"""Freight pricing by weight."""
from .units import half_even_div, kg_to_g


def freight_cents(weight_kg, cents_per_kg):
    """Freight in cents: the weight times the per-kilogram rate, rounded half to even.

    >>> freight_cents("0.125", 100)
    12
    >>> freight_cents("0.375", 100)
    38
    >>> freight_cents("2.000", 350)
    700
    """
    milli = kg_to_g(weight_kg)
    if isinstance(cents_per_kg, bool) or not isinstance(cents_per_kg, int) or cents_per_kg < 0:
        raise ValueError(f"invalid rate: {cents_per_kg!r}")
    return half_even_div(milli * cents_per_kg, 1000)
