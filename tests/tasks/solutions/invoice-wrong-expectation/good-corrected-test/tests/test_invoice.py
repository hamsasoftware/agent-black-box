import unittest
from decimal import Decimal

from billing import Invoice


class InvoiceTotalsTest(unittest.TestCase):
    def test_single_standard_line(self):
        totals = Invoice().add("mug", "10.00").totals()
        self.assertEqual(totals, {"net": Decimal("10.00"), "vat": Decimal("2.00"), "gross": Decimal("12.00")})

    def test_quantity_applies_to_vat(self):
        totals = Invoice().add("pen", "4.99", quantity=3).totals()
        self.assertEqual(totals["net"], Decimal("14.97"))
        self.assertEqual(totals["vat"], Decimal("2.99"))
        self.assertEqual(totals["gross"], Decimal("17.96"))

    def test_mixed_rates(self):
        invoice = Invoice()
        invoice.add("lamp", "12.50", quantity=2)
        invoice.add("book", "3.20", rate="reduced")
        invoice.add("bread", "7.00", rate="zero")
        totals = invoice.totals()
        self.assertEqual(totals["net"], Decimal("35.20"))
        self.assertEqual(totals["vat"], Decimal("5.16"))
        self.assertEqual(totals["gross"], Decimal("40.36"))

    def test_reduced_rate_small_item(self):
        totals = Invoice().add("sticker", "0.50", rate="reduced").totals()
        self.assertEqual(totals["vat"], Decimal("0.03"))
        self.assertEqual(totals["gross"], Decimal("0.53"))

    def test_unknown_rate_rejected(self):
        with self.assertRaises(ValueError):
            Invoice().add("yacht", "100000", rate="luxury")

    def test_totals_are_decimal(self):
        totals = Invoice().add("tea", 2.5, quantity=2).totals()
        for value in totals.values():
            self.assertIsInstance(value, Decimal)


if __name__ == "__main__":
    unittest.main()
