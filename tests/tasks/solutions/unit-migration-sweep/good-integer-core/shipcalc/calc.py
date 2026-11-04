from .limits import check_total_kg
from .packing import split_parcels
from .rates import shipping_cents
from .units import g_to_kg, kg_to_g


def order_weight_kg(order):
    return check_total_kg(g_to_kg(sum(kg_to_g(item.line_weight_kg()) for item in order.items)))


def quote(order, zone):
    parcels = split_parcels(order)
    cents = sum(shipping_cents(parcel.weight_kg, zone) for parcel in parcels)
    return {"parcels": len(parcels), "weight_kg": order_weight_kg(order), "cents": cents}
