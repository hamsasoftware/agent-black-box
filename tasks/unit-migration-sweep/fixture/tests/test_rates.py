import unittest

from shipcalc.rates import shipping_cents


class RatesTest(unittest.TestCase):
    def test_first_step(self):
        self.assertEqual(shipping_cents("0.500", "eu"), 400)

    def test_next_step(self):
        self.assertEqual(shipping_cents("0.501", "eu"), 490)

    def test_unknown_zone(self):
        with self.assertRaises(ValueError):
            shipping_cents("1.000", "mars")


if __name__ == "__main__":
    unittest.main()
