"""Tare handling: net weight from a gross weight."""
from .units import WeightError, g_to_kg, half_even_div, kg_to_g


def net_weight_kg(gross_kg, tare_kg):
    gross, tare = kg_to_g(gross_kg), kg_to_g(tare_kg)
    if tare > gross:
        raise WeightError("tare exceeds gross weight")
    return g_to_kg(gross - tare)


def _tare_milli(gross_kg, percent):
    gross = kg_to_g(gross_kg)
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
        raise ValueError(f"invalid percent: {percent!r}")
    return gross, half_even_div(gross * percent, 100)


def tare_for_percent_kg(gross_kg, percent):
    """The tare that is `percent` percent of the gross weight, half to even.

    >>> tare_for_percent_kg("10.005", 10)
    '1.000'
    >>> tare_for_percent_kg("10.015", 10)
    '1.002'
    """
    return g_to_kg(_tare_milli(gross_kg, percent)[1])


def net_after_percent_kg(gross_kg, percent):
    gross, tare = _tare_milli(gross_kg, percent)
    return g_to_kg(gross - tare)
