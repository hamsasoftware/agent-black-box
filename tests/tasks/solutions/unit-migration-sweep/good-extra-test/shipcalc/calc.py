from decimal import Decimal

from .limits import check_total_kg
from .packing import split_parcels
from .rates import shipping_cents
from .units import fmt


def order_weight_kg(order):
    total = sum((Decimal(item.line_weight_kg()) for item in order.items), Decimal("0"))
    return check_total_kg(fmt(total))


def quote(order, zone):
    parcels = split_parcels(order)
    cents = sum(shipping_cents(parcel.weight_kg, zone) for parcel in parcels)
    return {"parcels": len(parcels), "weight_kg": order_weight_kg(order), "cents": cents}
