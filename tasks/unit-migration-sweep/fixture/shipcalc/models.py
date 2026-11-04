from .units import to_grams


class Item:
    """One order line.

    Fields (validate_item reads this table, keep it in sync):
        sku: str, 1..32
        weight_g: int, 1..1000000
        qty: int, 1..1000
    """

    def __init__(self, sku, weight_g, qty=1):
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError(f"invalid quantity: {qty!r}")
        self.sku = sku
        self.weight_g = to_grams(weight_g)
        self.qty = qty

    def line_weight_g(self):
        return self.weight_g * self.qty

    def to_dict(self):
        return {"sku": self.sku, "weight_g": self.weight_g, "qty": self.qty}

    @classmethod
    def from_dict(cls, data):
        return cls(data["sku"], data["weight_g"], data.get("qty", 1))


class Order:
    def __init__(self, items=()):
        self.items = list(items)

    def add(self, item):
        self.items.append(item)
