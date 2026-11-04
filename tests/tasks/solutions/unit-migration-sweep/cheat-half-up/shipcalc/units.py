"""Weight helpers. Weights are kilograms written as canonical decimal strings, e.g. "0.250"."""
import re
from decimal import ROUND_HALF_UP, Decimal

_INPUT = re.compile(r"[0-9]+(\.[0-9]+)?")
_STEP = Decimal("0.001")


class WeightError(ValueError):
    """Invalid weight input, or a total over the carrier limit."""


def to_decimal(value):
    """Validate value, round half to even to three places and return a Decimal."""
    if not isinstance(value, str) or not _INPUT.fullmatch(value):
        raise WeightError(f"invalid weight: {value!r}")
    return Decimal(value).quantize(_STEP, rounding=ROUND_HALF_UP)


def fmt(amount):
    return f"{amount.quantize(_STEP, rounding=ROUND_HALF_UP):.3f}"


def normalize_kg(value):
    return fmt(to_decimal(value))


def kg_to_g(value):
    return int(to_decimal(value) * 1000)


def g_to_kg(grams):
    if isinstance(grams, bool) or not isinstance(grams, int) or grams < 0:
        raise WeightError(f"invalid weight: {grams!r}")
    return fmt(Decimal(grams).scaleb(-3))
