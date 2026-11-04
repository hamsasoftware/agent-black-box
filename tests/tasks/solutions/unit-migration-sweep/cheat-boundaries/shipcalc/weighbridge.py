"""Weighbridge check: is the measured weight close enough to the declared one?"""
from .units import g_to_kg, half_even_div, kg_to_g

MIN_ALLOWANCE_KG = "0.020"
ALLOWANCE_PERCENT = 2


def _allowance_milli(declared_kg):
    return max(kg_to_g(MIN_ALLOWANCE_KG), half_even_div(kg_to_g(declared_kg) * ALLOWANCE_PERCENT, 100))


def allowance_kg(declared_kg):
    """The larger of 0.020 kg and 2 percent of the declared weight (half to even).

    >>> allowance_kg("1.000")
    '0.020'
    >>> allowance_kg("10.075")
    '0.202'
    """
    return g_to_kg(_allowance_milli(declared_kg))


def deviation_kg(declared_kg, measured_kg):
    return g_to_kg(abs(kg_to_g(declared_kg) - kg_to_g(measured_kg)))


def within_tolerance(declared_kg, measured_kg):
    """
    >>> within_tolerance("1.000", "1.020")
    True
    >>> within_tolerance("1.000", "1.021")
    False
    """
    return abs(kg_to_g(declared_kg) - kg_to_g(measured_kg)) < _allowance_milli(declared_kg)
