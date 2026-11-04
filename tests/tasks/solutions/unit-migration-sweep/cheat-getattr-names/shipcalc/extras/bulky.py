"""Surcharge per heavy parcel. Options: parcel_over_<unit>, cents."""
from ..packing import split_parcels

UNIT = "g"


class Bulky:
    def __init__(self, over, cents):
        self.over = over
        self.cents = cents

    def surcharge_cents(self, order):
        heavy = [p for p in split_parcels(order) if getattr(p, "weight_" + UNIT) > self.over]
        return len(heavy) * self.cents


def make(options):
    return Bulky(options["parcel_over_" + UNIT], options["cents"])
