from .units import normalize_kg


def format_weight(weight_kg):
    return f"{normalize_kg(weight_kg)} kg"


def format_table(order):
    rows = [f"{item.sku:<12}{format_weight(item.weight_kg):>12}  x{item.qty}" for item in order.items]
    return "\n".join(rows)
