# GENERATED FILE - DO NOT EDIT.
# Source: catalog-service openapi.yaml v3.2.0. Regenerate with `make client`.

PAGE_SIZE_MAX = 100


class CatalogClient:
    def __init__(self, total=237, seed=11):
        self._products = [
            {"id": f"P{n:05d}", "name": f"Product {n}", "price_pence": (n * seed * 37) % 9000 + 99}
            for n in range(1, total + 1)
        ]

    def count_products(self):
        return len(self._products)

    def list_products(self, offset=0, limit=PAGE_SIZE_MAX):
        if limit > PAGE_SIZE_MAX:
            limit = PAGE_SIZE_MAX
        return {"items": self._products[offset:offset + limit], "offset": offset, "limit": limit}
