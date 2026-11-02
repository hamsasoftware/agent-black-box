import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    sku: str
    name: str
    qty: int
    unit_price: float

    @property
    def value(self):
        return self.qty * self.unit_price


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return [
            Item(row["sku"], row["name"], int(row["qty"]), float(row["unit_price"]))
            for row in csv.DictReader(handle)
        ]
