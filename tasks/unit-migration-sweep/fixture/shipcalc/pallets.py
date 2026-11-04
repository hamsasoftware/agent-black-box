"""Pallet planning. A pallet carries at most PALLET_G grams."""
from .calc import order_weight_g
from .units import half_even_div

PALLET_G = 500000


def pallet_count(order):
    """Pallets needed for the whole order; none for an empty order.

    >>> from shipcalc.models import Item, Order
    >>> pallet_count(Order([Item("A", 500000)]))
    1
    >>> pallet_count(Order([Item("A", 500001)]))
    2
    """
    return -(-order_weight_g(order) // PALLET_G)


def fill_percent(order):
    """How full the pallets are, in whole percent (half to even); 0 for an empty order.

    >>> from shipcalc.models import Item, Order
    >>> fill_percent(Order([Item("A", 250000)]))
    50
    """
    count = pallet_count(order)
    if count == 0:
        return 0
    return half_even_div(order_weight_g(order) * 100, count * PALLET_G)
