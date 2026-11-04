"""Insurance per started step of total weight, from a minimum total on. Options: step_<unit>, min_total_<unit>, cents_per_step."""
from decimal import ROUND_CEILING, Decimal

from .. import calc
from ..units import normalize_kg

UNIT = "kg"


class Insurance:
    def __init__(self, step, min_total, cents_per_step):
        self.step = Decimal(normalize_kg(step))
        self.min_total = Decimal(normalize_kg(min_total))
        self.cents_per_step = cents_per_step

    def surcharge_cents(self, order):
        total = Decimal(getattr(calc, "order_weight_" + UNIT)(order))
        if total < self.min_total:
            return 0
        return int((total / self.step).to_integral_value(rounding=ROUND_CEILING)) * self.cents_per_step


def make(options):
    return Insurance(options["step_" + UNIT], options["min_total_" + UNIT], options["cents_per_step"])
