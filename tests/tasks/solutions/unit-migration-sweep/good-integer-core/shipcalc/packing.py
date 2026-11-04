from .units import g_to_kg, kg_to_g

MAX_PARCEL = 20000  # grams


class Parcel:
    def __init__(self, grams, skus):
        self._grams = grams
        self.skus = list(skus)

    @property
    def weight_kg(self):
        return g_to_kg(self._grams)

    def add(self, grams, sku):
        self._grams += grams
        self.skus.append(sku)


def split_parcels(order):
    """First-fit decreasing. A unit heavier than the limit travels alone."""
    units = []
    for item in order.items:
        units.extend((kg_to_g(item.weight_kg), item.sku) for _ in range(item.qty))
    units.sort(key=lambda unit: (-unit[0], unit[1]))
    parcels = []
    for grams, sku in units:
        for parcel in parcels:
            if parcel._grams + grams <= MAX_PARCEL:
                parcel.add(grams, sku)
                break
        else:
            parcels.append(Parcel(grams, [sku]))
    return parcels
