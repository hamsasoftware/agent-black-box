"""Insurance per started step of total weight, from a minimum total on. Options: step_<unit>, min_total_<unit>, cents_per_step."""
from .. import calc

UNIT = "g"


class Insurance:
    def __init__(self, step, min_total, cents_per_step):
        self.step = step
        self.min_total = min_total
        self.cents_per_step = cents_per_step

    def surcharge_cents(self, order):
        total = getattr(calc, "order_weight_" + UNIT)(order)
        if total < self.min_total:
            return 0
        return -(-total // self.step) * self.cents_per_step


def make(options):
    return Insurance(options["step_" + UNIT], options["min_total_" + UNIT], options["cents_per_step"])
