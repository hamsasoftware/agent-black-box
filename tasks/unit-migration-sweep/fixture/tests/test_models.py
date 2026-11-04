import unittest

from shipcalc.models import Item, Order
from shipcalc.units import WeightError


class ItemTest(unittest.TestCase):
    def test_weight_is_a_canonical_kilogram_string(self):
        self.assertEqual(Item("MUG-01", "0.250").weight_kg, "0.250")
        self.assertEqual(Item("MUG-01", "1.5").weight_kg, "1.500")

    def test_line_weight(self):
        self.assertEqual(Item("MUG-01", "0.350", 2).line_weight_kg(), "0.700")

    def test_round_trip(self):
        item = Item("BOOK-07", "1.200", 3)
        self.assertEqual(item.to_dict(), {"sku": "BOOK-07", "weight_kg": "1.200", "qty": 3})
        self.assertEqual(Item.from_dict(item.to_dict()).weight_kg, "1.200")

    def test_invalid_weight(self):
        with self.assertRaises(WeightError):
            Item("MUG-01", "heavy")
        with self.assertRaises(ValueError):
            Item("MUG-01", 250)

    def test_order_keeps_items(self):
        order = Order([Item("A", "1")])
        order.add(Item("B", "2"))
        self.assertEqual([i.sku for i in order.items], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
