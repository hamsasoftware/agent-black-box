"""Tare handling: net weight from a gross weight."""
from .units import half_even_div, to_grams


def net_weight_g(gross_g, tare_g):
    if to_grams(tare_g) > to_grams(gross_g):
        raise ValueError("tare exceeds gross weight")
    return gross_g - tare_g


def tare_for_percent_g(gross_g, percent):
    """The tare that is `percent` percent of the gross weight, half to even.

    >>> tare_for_percent_g(10005, 10)
    1000
    >>> tare_for_percent_g(10015, 10)
    1002
    """
    to_grams(gross_g)
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
        raise ValueError(f"invalid percent: {percent!r}")
    return half_even_div(gross_g * percent, 100)


def net_after_percent_g(gross_g, percent):
    return gross_g - tare_for_percent_g(gross_g, percent)
