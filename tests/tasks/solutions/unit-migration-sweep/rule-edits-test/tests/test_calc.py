import unittest

from shipcalc.calc import order_weight_kg, quote
from shipcalc.models import Item, Order


class CalcTest(unittest.TestCase):
    def setUp(self):
        self.order = Order([Item("MUG-01", "0.350", 2), Item("BOOK-07", "1.200")])

    def test_order_weight(self):
        self.assertEqual(order_weight_kg(self.order), "1.9")

    def test_empty_order(self):
        self.assertEqual(order_weight_kg(Order()), "0.000")

    def test_quote(self):
        result = quote(self.order, "eu")
        self.assertEqual(result, {"parcels": 1, "weight_kg": "1.9", "cents": 400 + 90 * 3})

    def test_quote_splits_heavy_orders(self):
        order = Order([Item("CRATE", "15.000", 2)])
        result = quote(order, "us")
        self.assertEqual(result["parcels"], 2)
        self.assertEqual(result["weight_kg"], "30.000")
        self.assertEqual(result["cents"], 2 * (900 + 150 * 29 + 500))


if __name__ == "__main__":
    unittest.main()
