"""Weighbridge check: is the measured weight close enough to the declared one?"""
from .units import half_even_div, to_grams

MIN_ALLOWANCE_G = 20
ALLOWANCE_PERCENT = 2


def allowance_g(declared_g):
    """The larger of 20 g and 2 percent of the declared weight (half to even).

    >>> allowance_g(1000)
    20
    >>> allowance_g(10075)
    202
    """
    return max(MIN_ALLOWANCE_G, half_even_div(to_grams(declared_g) * ALLOWANCE_PERCENT, 100))


def deviation_g(declared_g, measured_g):
    return abs(to_grams(declared_g) - to_grams(measured_g))


def within_tolerance(declared_g, measured_g):
    """
    >>> within_tolerance(1000, 1020)
    True
    >>> within_tolerance(1000, 1021)
    False
    """
    return deviation_g(declared_g, measured_g) <= allowance_g(declared_g)
