LIGHT_G = 500
MEDIUM_G = 2000


def average_weight_g(order):
    units = sum(item.qty for item in order.items)
    if units == 0:
        return 0
    return sum(item.line_weight_g() for item in order.items) // units


def heaviest(order, n=3):
    return sorted(order.items, key=lambda item: (-item.weight_g, item.sku))[:n]


def weight_bands(order):
    bands = {"light": 0, "medium": 0, "heavy": 0}
    for item in order.items:
        if item.weight_g <= LIGHT_G:
            bands["light"] += item.qty
        elif item.weight_g <= MEDIUM_G:
            bands["medium"] += item.qty
        else:
            bands["heavy"] += item.qty
    return bands
