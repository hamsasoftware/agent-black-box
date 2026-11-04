from .units import WeightError, kg_to_g

MAX_TOTAL = 2**31 - 1  # grams: the carrier system stores them in a signed 32-bit column


def check_total_kg(weight_kg):
    from .units import normalize_kg

    if kg_to_g(weight_kg) > MAX_TOTAL:
        raise WeightError("total weight exceeds the carrier limit")
    return normalize_kg(weight_kg)
