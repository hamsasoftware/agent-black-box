from decimal import Decimal

from .units import fmt, g_to_kg

LIGHT_KG = Decimal("0.5")
MEDIUM_KG = Decimal("2")


def average_weight_kg(order):
    """Average weight of one unit in the order.

    >>> from shipcalc.models import Item, Order
    >>> average_weight_kg(Order([Item("A", "1.000"), Item("B", "2.000", 2)]))
    '1.667'
    """
    units = sum(item.qty for item in order.items)
    if units == 0:
        return "0.000"
    total_milli = sum(int(Decimal(item.line_weight_kg()) * 1000) for item in order.items)
    whole, rest = divmod(total_milli, units)
    if 2 * rest >= units:
        whole += 1
    return g_to_kg(whole)


def heaviest(order, n=3):
    return sorted(order.items, key=lambda item: (-Decimal(item.weight_kg), item.sku))[:n]


def weight_bands(order):
    bands = {"light": 0, "medium": 0, "heavy": 0}
    for item in order.items:
        weight = Decimal(item.weight_kg)
        if weight <= LIGHT_KG:
            bands["light"] += item.qty
        elif weight <= MEDIUM_KG:
            bands["medium"] += item.qty
        else:
            bands["heavy"] += item.qty
    return bands
