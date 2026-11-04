MAX_PARCEL_G = 20000


class Parcel:
    def __init__(self, weight_g, skus):
        self.weight_g = weight_g
        self.skus = list(skus)

    def add(self, weight_g, sku):
        self.weight_g += weight_g
        self.skus.append(sku)


def split_parcels(order):
    """First-fit decreasing. A unit heavier than the limit travels alone."""
    units = []
    for item in order.items:
        units.extend((item.weight_g, item.sku) for _ in range(item.qty))
    units.sort(key=lambda unit: (-unit[0], unit[1]))
    parcels = []
    for grams, sku in units:
        for parcel in parcels:
            if parcel.weight_g + grams <= MAX_PARCEL_G:
                parcel.add(grams, sku)
                break
        else:
            parcels.append(Parcel(grams, [sku]))
    return parcels
