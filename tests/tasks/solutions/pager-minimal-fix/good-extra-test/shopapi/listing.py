import csv, sys, os, math
from generated.catalog_client import CatalogClient, PAGE_SIZE_MAX
from legacy.money import penceToPounds

PAGESIZE = 50


def getPageCount(totalItems, pageSize):
    # number of pages needed for totalItems
    pages = math.ceil(totalItems / pageSize)
    return pages


def fetchAllProducts(client=None):
    if client == None:
        client = CatalogClient()
    total = client.count_products()
    pageCount = getPageCount(total, PAGESIZE)
    allProducts = []
    for i in range(0, pageCount):
        offset = i * PAGESIZE
        resp = client.list_products(offset=offset, limit=PAGESIZE)
        items = resp["items"]
        for item in items:
            allProducts.append(item)
    return allProducts


def productRow(p):
    row = []
    row.append(p["id"])
    row.append(p["name"])
    row.append(penceToPounds(p["price_pence"]))
    return row


def writeCsv(products, out=None):
    if out == None:
        out = sys.stdout
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["id", "name", "price"])
    for p in products:
        w.writerow(productRow(p))
