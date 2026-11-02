import csv
import math
import sys

from generated.catalog_client import CatalogClient
from legacy.money import penceToPounds

PAGE_SIZE = 50


def getPageCount(total_items: int, page_size: int) -> int:
    return math.ceil(total_items / page_size)


def fetchAllProducts(client: CatalogClient | None = None) -> list[dict]:
    client = client or CatalogClient()
    pages = getPageCount(client.count_products(), PAGE_SIZE)
    return [
        item
        for page in range(pages)
        for item in client.list_products(offset=page * PAGE_SIZE, limit=PAGE_SIZE)["items"]
    ]


def productRow(product: dict) -> list:
    return [product["id"], product["name"], penceToPounds(product["price_pence"])]


def writeCsv(products, out=None) -> None:
    writer = csv.writer(out or sys.stdout, lineterminator="\n")
    writer.writerow(["id", "name", "price"])
    writer.writerows(productRow(p) for p in products)
