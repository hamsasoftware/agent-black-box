import unittest
from datetime import datetime, timezone
from decimal import Decimal

from settle import days, dedupe, fees, fx
from settle.models import Event, Line, Merchant


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class RegressionTest(unittest.TestCase):
    def test_same_id_in_two_currencies_is_two_events(self):
        a = Event("x", "m", "charge", "EUR", 1, utc("2025-01-01T00:00:00"), utc("2025-01-01T00:00:01"), "succeeded")
        b = Event("x", "m", "charge", "USD", 1, utc("2025-01-01T00:00:00"), utc("2025-01-01T00:00:01"), "succeeded")
        self.assertEqual(len(dedupe.drop_duplicates([a, b])), 2)

    def test_summer_time_moves_the_day(self):
        self.assertEqual(days.settlement_day(utc("2025-07-01T22:30:00"), "Europe/Berlin").isoformat(), "2025-07-02")
        self.assertEqual(days.settlement_day(utc("2025-01-01T22:30:00"), "Europe/Berlin").isoformat(), "2025-01-01")

    def test_fee_is_rounded_once(self):
        merchant = Merchant("m", "M", "UTC", "USD", 290, 0)
        self.assertEqual(fees.payout_fee(merchant, [Line("charge", 1500)] * 3), 130)

    def test_zero_decimal_conversion(self):
        self.assertEqual(fx.convert(1000, "JPY", "EUR", Decimal("0.0061")), 610)
        self.assertEqual(fx.convert(1200, "EUR", "JPY", Decimal("162.35")), 1948)
        self.assertEqual(fx.convert(1000, "EUR", "KWD", Decimal("0.3335")), 3335)
