from decimal import ROUND_CEILING, Decimal

from .units import to_decimal

ZONES = {"eu": (400, 90), "us": (900, 150), "world": (1500, 260)}  # (base cents, cents per extra step)
STEP_KG = Decimal("0.5")
HEAVY_KG = Decimal("10")
HEAVY_SURCHARGE = 500


def shipping_cents(weight_kg, zone):
    try:
        base, per_step = ZONES[zone]
    except KeyError:
        raise ValueError(f"unknown zone: {zone!r}") from None
    weight = to_decimal(weight_kg)
    steps = max(1, int((weight / STEP_KG).to_integral_value(rounding=ROUND_CEILING)))
    cents = base + per_step * (steps - 1)
    if weight > HEAVY_KG:
        cents += HEAVY_SURCHARGE
    return cents
