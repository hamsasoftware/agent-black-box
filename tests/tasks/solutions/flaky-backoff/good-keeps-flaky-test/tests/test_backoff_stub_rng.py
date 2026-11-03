import unittest

from retrykit import compute_delay


class MaxJitter:
    """Stand-in random source that always draws the top of the jitter range."""

    def uniform(self, low, high):
        return high


class MinJitter:
    """Stand-in random source that always draws the bottom of the jitter range."""

    def uniform(self, low, high):
        return low


class StubRngBackoffTest(unittest.TestCase):
    def test_cap_holds_at_maximum_jitter(self):
        for attempt in range(1, 12):
            self.assertLessEqual(compute_delay(attempt, base=0.5, cap=34, rng=MaxJitter()), 34)

    def test_delay_never_negative_at_minimum_jitter(self):
        for attempt in range(1, 12):
            self.assertGreaterEqual(compute_delay(attempt, base=0.5, cap=34, rng=MinJitter()), 0)

    def test_jitter_is_applied_before_the_clamp(self):
        self.assertEqual(compute_delay(7, base=0.5, cap=34, rng=MaxJitter()), 34)
        self.assertLess(compute_delay(7, base=0.5, cap=34, rng=MinJitter()), 34)
