"""Pallet planning. A pallet carries at most PALLET_KG kilograms."""
from .calc import order_weight_kg
from .units import half_even_div, kg_to_g

PALLET_KG = 500


def _total_milli(order):
    return kg_to_g(order_weight_kg(order))


def pallet_count(order):
    """Pallets needed for the whole order; none for an empty order.

    >>> from shipcalc.models import Item, Order
    >>> pallet_count(Order([Item("A", "500")]))
    1
    >>> pallet_count(Order([Item("A", "500.001")]))
    2
    """
    return -(-_total_milli(order) // (PALLET_KG * 1000))


def fill_percent(order):
    """How full the pallets are, in whole percent (half to even); 0 for an empty order.

    >>> from shipcalc.models import Item, Order
    >>> fill_percent(Order([Item("A", "250")]))
    50
    """
    count = pallet_count(order)
    if count == 0:
        return 0
    return half_even_div(_total_milli(order) * 100, count * PALLET_KG * 1000)
