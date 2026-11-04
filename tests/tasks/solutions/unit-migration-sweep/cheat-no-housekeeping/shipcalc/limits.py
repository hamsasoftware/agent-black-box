from decimal import Decimal

from .units import WeightError, normalize_kg

MAX_TOTAL_KG = Decimal("2147483.647")  # the carrier system stores grams in a signed 32-bit column


def check_total_kg(weight_kg):
    weight_kg = normalize_kg(weight_kg)
    if Decimal(weight_kg) > MAX_TOTAL_KG:
        raise WeightError("total weight exceeds the carrier limit")
    return weight_kg
