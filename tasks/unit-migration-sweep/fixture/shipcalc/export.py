from .calc import order_weight_g
from .packing import split_parcels


def to_csv(order):
    lines = ["sku,weight_g,qty"]
    for item in order.items:
        lines.append(f"{item.sku},{item.weight_g},{item.qty}")
    return "\n".join(lines) + "\n"


def carrier_payload(order):
    return {"weight_g": order_weight_g(order), "parcels": len(split_parcels(order))}
