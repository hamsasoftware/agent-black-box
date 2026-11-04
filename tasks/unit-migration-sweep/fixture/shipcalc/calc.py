from .limits import check_total_g
from .packing import split_parcels
from .rates import shipping_cents


def order_weight_g(order):
    return check_total_g(sum(item.line_weight_g() for item in order.items))


def quote(order, zone):
    parcels = split_parcels(order)
    cents = sum(shipping_cents(parcel.weight_g, zone) for parcel in parcels)
    return {"parcels": len(parcels), "weight_g": order_weight_g(order), "cents": cents}
