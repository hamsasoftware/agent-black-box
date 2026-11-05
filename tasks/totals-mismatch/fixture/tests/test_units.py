import unittest
from datetime import datetime, timezone
from decimal import Decimal

from settle import currency, dedupe, days, fees, fx
from settle.models import Event, Line, Merchant
from settle.rounding import round_half_even


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def event(event_id, merchant="m-1", cur="EUR", amount=1000, kind="charge"):
    return Event(event_id, merchant, kind, cur, amount, utc("2025-03-29T10:00:00"), utc("2025-03-29T10:00:05"), "succeeded")


class RoundingTest(unittest.TestCase):
    def test_ties_go_to_even(self):
        self.assertEqual([round_half_even(Decimal(x)) for x in ("2.5", "3.5", "-2.5", "2.4", "2.6")], [2, 4, -2, 2, 3])


class CurrencyTest(unittest.TestCase):
    def test_exponents(self):
        self.assertEqual((currency.minor_exponent("USD"), currency.minor_exponent("JPY"), currency.minor_exponent("KWD")), (2, 0, 3))


class DedupeTest(unittest.TestCase):
    def test_a_resent_event_counts_once(self):
        kept = dedupe.drop_duplicates([event("a"), event("a"), event("b")])
        self.assertEqual([e.event_id for e in kept], ["a", "b"])

    def test_same_id_for_another_merchant_is_another_event(self):
        self.assertEqual(len(dedupe.drop_duplicates([event("a", "m-1"), event("a", "m-2")])), 2)


class DaysTest(unittest.TestCase):
    def test_utc_merchant(self):
        self.assertEqual(days.settlement_day(utc("2025-01-10T23:59:59"), "UTC").isoformat(), "2025-01-10")

    def test_tokyo_is_nine_hours_ahead(self):
        self.assertEqual(days.settlement_day(utc("2025-01-10T15:00:00"), "Asia/Tokyo").isoformat(), "2025-01-11")


class FxTest(unittest.TestCase):
    def test_same_currency_is_untouched(self):
        self.assertEqual(fx.convert(1234, "EUR", "EUR", None), 1234)

    def test_two_decimal_pair(self):
        self.assertEqual(fx.convert(1500, "USD", "EUR", Decimal("0.9234")), 1385)


class FeesTest(unittest.TestCase):
    def test_single_charge(self):
        merchant = Merchant("m-1", "One", "UTC", "EUR", 150, 25)
        self.assertEqual(fees.payout_fee(merchant, [Line("charge", 10000)]), 175)


if __name__ == "__main__":
    unittest.main()
