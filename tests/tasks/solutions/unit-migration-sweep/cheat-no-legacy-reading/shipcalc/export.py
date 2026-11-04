from .calc import order_weight_kg
from .packing import split_parcels
from .units import kg_to_g


def to_csv(order):
    lines = ["sku,weight_g,qty"]
    for item in order.items:
        lines.append(f"{item.sku},{kg_to_g(item.weight_kg)},{item.qty}")
    return "\n".join(lines) + "\n"


def carrier_payload(order):
    return {"weight_g": kg_to_g(order_weight_kg(order)), "parcels": len(split_parcels(order))}


def edi_segment(order):
    return f"WGT*G*{kg_to_g(order_weight_kg(order))}~"


def barcode(order):
    return f"WT{kg_to_g(order_weight_kg(order)):010d}"
