"""Shipping labels for order lines."""
from decimal import Decimal

from .format import format_weight

LIFT_KG = Decimal("25")


def lift_notice(item):
    """Two people must lift a unit that is heavier than 25 kg.

    >>> from shipcalc.models import Item
    >>> lift_notice(Item("A", "25.000"))
    ''
    >>> lift_notice(Item("A", "25.001"))
    '2-PERSON LIFT'
    """
    return "2-PERSON LIFT" if Decimal(item.weight_kg) > LIFT_KG else ""


def label(item):
    text = f"{item.sku} {format_weight(item.weight_kg)} x{item.qty}"
    notice = lift_notice(item)
    return f"{text} {notice}" if notice else text


def render(order):
    return "\n".join(label(item) for item in order.items)
