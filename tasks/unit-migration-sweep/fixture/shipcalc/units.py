"""Weight helpers. Weights are whole grams (int) everywhere in the package.

>>> to_grams(250)
250
"""


def to_grams(value):
    """Return value if it is a valid weight in grams, else raise ValueError.

    >>> to_grams(0)
    0
    >>> to_grams(1500) + to_grams(250)
    1750
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid weight: {value!r}")
    return value


def half_even_div(numerator, denominator):
    """Integer division rounded half to even; both arguments are non-negative ints."""
    whole, rest = divmod(numerator, denominator)
    if 2 * rest > denominator or (2 * rest == denominator and whole % 2 == 1):
        whole += 1
    return whole
