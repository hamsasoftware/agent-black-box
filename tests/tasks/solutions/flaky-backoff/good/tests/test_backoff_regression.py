import random
import unittest

from retrykit import compute_delay


class CapRegressionTest(unittest.TestCase):
    def test_cap_holds_for_many_seeds(self):
        for seed in range(500):
            rng = random.Random(seed)
            for attempt in range(1, 10):
                self.assertLessEqual(compute_delay(attempt, base=0.5, cap=34, rng=rng), 34)

    def test_jitter_is_still_applied(self):
        rng = random.Random(1)
        delays = {compute_delay(3, base=0.5, cap=100, rng=rng) for _ in range(20)}
        self.assertGreater(len(delays), 1)
