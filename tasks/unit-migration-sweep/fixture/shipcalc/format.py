def format_weight(grams):
    if grams >= 1000:
        return f"{grams / 1000:.1f} kg"
    return f"{grams} g"


def format_table(order):
    rows = [f"{item.sku:<12}{format_weight(item.weight_g):>12}  x{item.qty}" for item in order.items]
    return "\n".join(rows)
