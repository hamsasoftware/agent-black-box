from .units import kg_to_g

ZONES = {"eu": (400, 90), "us": (900, 150), "world": (1500, 260)}  # (base cents, cents per extra step)
STEP = 500  # grams
HEAVY = 10000  # grams
HEAVY_SURCHARGE = 500


def shipping_cents(weight_kg, zone):
    try:
        base, per_step = ZONES[zone]
    except KeyError:
        raise ValueError(f"unknown zone: {zone!r}") from None
    milli = kg_to_g(weight_kg)
    steps = max(1, -(-milli // STEP))
    cents = base + per_step * (steps - 1)
    if milli > HEAVY:
        cents += HEAVY_SURCHARGE
    return cents
