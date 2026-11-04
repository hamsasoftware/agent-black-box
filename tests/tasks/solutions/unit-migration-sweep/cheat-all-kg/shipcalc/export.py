from .calc import order_weight_kg
from .packing import split_parcels


def to_csv(order):
    lines = ["sku,weight_kg,qty"]
    for item in order.items:
        lines.append(f"{item.sku},{item.weight_kg},{item.qty}")
    return "\n".join(lines) + "\n"


def carrier_payload(order):
    return {"weight_kg": order_weight_kg(order), "parcels": len(split_parcels(order))}


def edi_segment(order):
    return f"WGT*KG*{order_weight_kg(order)}~"


def barcode(order):
    return "WT" + order_weight_kg(order)
