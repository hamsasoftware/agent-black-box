from .calc import order_weight_g
from .packing import split_parcels


def to_csv(order):
    lines = ["sku,weight_g,qty"]
    for item in order.items:
        lines.append(f"{item.sku},{item.weight_g},{item.qty}")
    return "\n".join(lines) + "\n"


def carrier_payload(order):
    return {"weight_g": order_weight_g(order), "parcels": len(split_parcels(order))}


def edi_segment(order):
    return f"WGT*G*{order_weight_g(order)}~"


def barcode(order):
    return f"WT{order_weight_g(order):010d}"
