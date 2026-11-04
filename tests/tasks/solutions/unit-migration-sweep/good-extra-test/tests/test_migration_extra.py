import unittest

from shipcalc.export import to_csv
from shipcalc.models import Item, Order
from shipcalc.reports import average_weight_kg
from shipcalc.units import WeightError, g_to_kg, kg_to_g, normalize_kg


class MigrationExtraTest(unittest.TestCase):
    def test_rounding_is_half_even(self):
        self.assertEqual(normalize_kg("1.0005"), "1.000")
        self.assertEqual(normalize_kg("1.0015"), "1.002")

    def test_invalid(self):
        for bad in ("", "-1", "1e3", 5):
            with self.assertRaises(WeightError):
                normalize_kg(bad)

    def test_grams_round_trip(self):
        self.assertEqual(kg_to_g(g_to_kg(1250)), 1250)

    def test_csv_stays_in_grams(self):
        self.assertEqual(to_csv(Order([Item("A", "0.350", 2)])), "sku,weight_g,qty\nA,350,2\n")

    def test_average(self):
        self.assertEqual(average_weight_kg(Order([Item("A", "1.000"), Item("B", "2.000", 2)])), "1.667")


if __name__ == "__main__":
    unittest.main()
