"""Surcharge per heavy parcel. Options: parcel_over_<unit>, cents."""
from decimal import Decimal

from ..packing import split_parcels
from ..units import normalize_kg

UNIT = "kg"


class Bulky:
    def __init__(self, over, cents):
        self.over = Decimal(normalize_kg(over))
        self.cents = cents

    def surcharge_cents(self, order):
        heavy = [p for p in split_parcels(order) if Decimal(getattr(p, "weight_" + UNIT)) > self.over]
        return len(heavy) * self.cents


def make(options):
    return Bulky(options["parcel_over_" + UNIT], options["cents"])
