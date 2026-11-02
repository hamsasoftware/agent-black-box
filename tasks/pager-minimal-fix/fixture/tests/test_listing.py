import io
import unittest

from generated.catalog_client import CatalogClient
from shopapi.listing import fetchAllProducts, getPageCount, writeCsv


class ListingTest(unittest.TestCase):
    def test_page_count_exact_multiple(self):
        self.assertEqual(getPageCount(100, 50), 2)

    def test_fetch_full_pages(self):
        products = fetchAllProducts(CatalogClient(total=150))
        self.assertEqual(len(products), 150)

    def test_csv_header_and_price(self):
        out = io.StringIO()
        writeCsv([{"id": "P1", "name": "Mug", "price_pence": 1250}], out)
        self.assertEqual(out.getvalue(), "id,name,price\nP1,Mug,12.50\n")

    def test_export_includes_last_product(self):
        products = fetchAllProducts(CatalogClient(total=237))
        self.assertEqual(products[-1]["id"], "P00237")


if __name__ == "__main__":
    unittest.main()
