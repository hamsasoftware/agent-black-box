from .calc import order_weight_kg, quote

_STORE = {}


def quote_key(order, zone):
    return f"quote:v2:{zone}:{order_weight_kg(order)}:{len(order.items)}"


def cached_quote(order, zone):
    key = quote_key(order, zone)
    if key not in _STORE:
        _STORE[key] = quote(order, zone)
    return _STORE[key]


def clear():
    _STORE.clear()
