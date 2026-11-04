from .units import g_to_kg, kg_to_g

LIGHT = 500  # grams
MEDIUM = 2000  # grams


def average_weight_kg(order):
    units = sum(item.qty for item in order.items)
    if units == 0:
        return "0.000"
    whole, rest = divmod(sum(kg_to_g(item.line_weight_kg()) for item in order.items), units)
    if 2 * rest > units or (2 * rest == units and whole % 2 == 1):
        whole += 1
    return g_to_kg(whole)


def heaviest(order, n=3):
    return sorted(order.items, key=lambda item: (-kg_to_g(item.weight_kg), item.sku))[:n]


def weight_bands(order):
    bands = {"light": 0, "medium": 0, "heavy": 0}
    for item in order.items:
        grams = kg_to_g(item.weight_kg)
        if grams <= LIGHT:
            bands["light"] += item.qty
        elif grams <= MEDIUM:
            bands["medium"] += item.qty
        else:
            bands["heavy"] += item.qty
    return bands
