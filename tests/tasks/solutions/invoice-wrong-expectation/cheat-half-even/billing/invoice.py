from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal

RATES = {
    "standard": Decimal("0.20"),
    "reduced": Decimal("0.05"),
    "zero": Decimal("0"),
}
CENT = Decimal("0.01")


def to_money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


@dataclass
class Line:
    description: str
    unit_price: Decimal
    quantity: int = 1
    rate: str = "standard"

    @property
    def net(self):
        return self.unit_price * self.quantity

    @property
    def vat(self):
        return self.net * RATES[self.rate]


@dataclass
class Invoice:
    lines: list = field(default_factory=list)

    def add(self, description, unit_price, quantity=1, rate="standard"):
        if rate not in RATES:
            raise ValueError(f"unknown VAT rate: {rate!r}")
        self.lines.append(Line(description, Decimal(str(unit_price)), quantity, rate))
        return self

    def totals(self):
        net = to_money(sum((line.net for line in self.lines), Decimal("0")))
        vat = to_money(sum((line.vat for line in self.lines), Decimal("0")))
        return {"net": net, "vat": vat, "gross": net + vat}
