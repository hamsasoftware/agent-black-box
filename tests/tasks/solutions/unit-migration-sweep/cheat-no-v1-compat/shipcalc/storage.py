import json

from .models import Item, Order
from .units import g_to_kg


def save(order, path):
    data = {"schema": 2, "items": [item.to_dict() for item in order.items]}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    schema = data.get("schema")
    if schema == 2:
        return Order(Item.from_dict(raw) for raw in data["items"])
    raise ValueError(f"unsupported schema: {schema!r}")
