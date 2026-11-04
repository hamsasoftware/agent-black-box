def format_weight(grams):
    """Text form of a weight.

    >>> format_weight(250)
    '250 g'
    >>> format_weight(12000)
    '12.0 kg'
    """
    if grams >= 1000:
        return f"{grams / 1000:.1f} kg"
    return f"{grams} g"


def format_table(order):
    rows = [f"{item.sku:<12}{format_weight(item.weight_g):>12}  x{item.qty}" for item in order.items]
    return "\n".join(rows)
