from .units import g_to_kg, kg_to_g, normalize_kg


class Item:
    """One order line.

    Fields (validate_item reads this table, keep it in sync):
        sku: str, 1..32
        weight_kg: kg, 0.001..1000.000
        qty: int, 1..1000
    """

    def __init__(self, sku, weight_kg, qty=1):
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError(f"invalid quantity: {qty!r}")
        self.sku = sku
        self.weight_kg = normalize_kg(weight_kg)
        self.qty = qty

    def line_weight_kg(self):
        return g_to_kg(kg_to_g(self.weight_kg) * self.qty)

    def to_dict(self):
        return {"sku": self.sku, "weight_kg": self.weight_kg, "qty": self.qty}

    @classmethod
    def from_dict(cls, data):
        return cls(data["sku"], data["weight_kg"], data.get("qty", 1))


class Order:
    def __init__(self, items=()):
        self.items = list(items)

    def add(self, item):
        self.items.append(item)
