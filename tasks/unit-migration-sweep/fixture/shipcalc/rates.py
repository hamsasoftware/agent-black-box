ZONES = {"eu": (400, 90), "us": (900, 150), "world": (1500, 260)}  # (base cents, cents per extra step)
STEP_G = 500
HEAVY_G = 10000
HEAVY_SURCHARGE = 500


def shipping_cents(weight_g, zone):
    try:
        base, per_step = ZONES[zone]
    except KeyError:
        raise ValueError(f"unknown zone: {zone!r}") from None
    steps = max(1, -(-weight_g // STEP_G))
    cents = base + per_step * (steps - 1)
    if weight_g > HEAVY_G:
        cents += HEAVY_SURCHARGE
    return cents
