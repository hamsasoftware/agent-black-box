"""Shipping labels for order lines."""
from .format import format_weight

LIFT_G = 25000


def lift_notice(item):
    """Two people must lift a unit that is heavier than 25 kg.

    >>> from shipcalc.models import Item
    >>> lift_notice(Item("A", 25000))
    ''
    >>> lift_notice(Item("A", 25001))
    '2-PERSON LIFT'
    """
    return "2-PERSON LIFT" if item.weight_g > LIFT_G else ""


def label(item):
    text = f"{item.sku} {format_weight(item.weight_g)} x{item.qty}"
    notice = lift_notice(item)
    return f"{text} {notice}" if notice else text


def render(order):
    return "\n".join(label(item) for item in order.items)
