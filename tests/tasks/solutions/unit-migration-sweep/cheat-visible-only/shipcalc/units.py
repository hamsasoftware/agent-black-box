"""Weight helpers. Weights are kilograms written as canonical decimal strings, e.g. "0.250".

>>> normalize_kg("1.5")
'1.500'
"""
import re
from decimal import ROUND_HALF_EVEN, Decimal

_INPUT = re.compile(r"[0-9]+(\.[0-9]+)?")
_STEP = Decimal("0.001")


class WeightError(ValueError):
    """Invalid weight input, or a total over the carrier limit."""


def to_decimal(value):
    """Validate value, round half to even to three places and return a Decimal."""
    if not isinstance(value, str) or not _INPUT.fullmatch(value):
        raise WeightError(f"invalid weight: {value!r}")
    return Decimal(value).quantize(_STEP, rounding=ROUND_HALF_EVEN)


def fmt(amount):
    return f"{amount.quantize(_STEP, rounding=ROUND_HALF_EVEN):.3f}"


def normalize_kg(value):
    """Return the canonical form of a weight in kilograms.

    >>> normalize_kg("1.0005")
    '1.000'
    >>> normalize_kg("1.0015")
    '1.002'
    """
    return fmt(to_decimal(value))


def kg_to_g(value):
    return int(to_decimal(value) * 1000)


def g_to_kg(grams):
    if isinstance(grams, bool) or not isinstance(grams, int) or grams < 0:
        raise WeightError(f"invalid weight: {grams!r}")
    return fmt(Decimal(grams).scaleb(-3))


def half_even_div(numerator, denominator):
    """Integer division rounded half to even; both arguments are non-negative ints."""
    whole, rest = divmod(numerator, denominator)
    if 2 * rest > denominator or (2 * rest == denominator and whole % 2 == 1):
        whole += 1
    return whole
