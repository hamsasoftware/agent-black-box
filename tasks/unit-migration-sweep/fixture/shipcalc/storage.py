import json

from .models import Item, Order


def save(order, path):
    data = {"schema": 1, "items": [item.to_dict() for item in order.items]}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != 1:
        raise ValueError(f"unsupported schema: {data.get('schema')!r}")
    return Order(Item.from_dict(raw) for raw in data["items"])
