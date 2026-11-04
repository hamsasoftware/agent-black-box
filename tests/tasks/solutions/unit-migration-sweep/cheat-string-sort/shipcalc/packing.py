from decimal import Decimal

from .units import fmt

MAX_PARCEL_KG = Decimal("20")


class Parcel:
    def __init__(self, weight, skus):
        self._weight = weight
        self.skus = list(skus)

    @property
    def weight_kg(self):
        return fmt(self._weight)

    def add(self, weight, sku):
        self._weight += weight
        self.skus.append(sku)


def split_parcels(order):
    """First-fit decreasing. A unit heavier than the limit travels alone."""
    units = []
    for item in order.items:
        units.extend((item.weight_kg, item.sku) for _ in range(item.qty))
    units.sort(key=lambda unit: unit[1])
    units.sort(key=lambda unit: unit[0], reverse=True)
    parcels = []
    for text, sku in units:
        weight = Decimal(text)
        for parcel in parcels:
            if parcel._weight + weight <= MAX_PARCEL_KG:
                parcel.add(weight, sku)
                break
        else:
            parcels.append(Parcel(weight, [sku]))
    return parcels
