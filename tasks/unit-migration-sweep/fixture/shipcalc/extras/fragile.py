"""Surcharge per light (fragile) unit. Options: max_unit_<unit>, cents."""
UNIT = "g"


class Fragile:
    def __init__(self, max_unit, cents):
        self.max_unit = max_unit
        self.cents = cents

    def surcharge_cents(self, order):
        count = sum(item.qty for item in order.items if getattr(item, "weight_" + UNIT) <= self.max_unit)
        return count * self.cents


def make(options):
    return Fragile(options["max_unit_" + UNIT], options["cents"])
