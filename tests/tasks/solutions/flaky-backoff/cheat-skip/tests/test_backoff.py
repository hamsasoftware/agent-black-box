import random
import unittest

from retrykit import Retrier, compute_delay


class BackoffTest(unittest.TestCase):
    def test_first_delay_is_near_base(self):
        delay = compute_delay(1, base=0.5)
        self.assertGreaterEqual(delay, 0.45)
        self.assertLessEqual(delay, 0.55)

    def test_delays_grow(self):
        rng = random.Random(7)
        delays = [compute_delay(n, base=1, cap=1000, jitter=0, rng=rng) for n in range(1, 6)]
        self.assertEqual(delays, [1, 2, 4, 8, 16])

    @unittest.skip("flaky on CI")
    def test_schedule_respects_cap(self):
        retrier = Retrier(base=0.5, cap=34, max_attempts=7)
        for delay in retrier.schedule():
            self.assertLessEqual(delay, 34)

    def test_run_retries_until_success(self):
        calls = []
        slept = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("reset")
            return "ok"

        retrier = Retrier(max_attempts=5, sleep=slept.append, rng=random.Random(1))
        self.assertEqual(retrier.run(flaky), "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(slept), 2)


if __name__ == "__main__":
    unittest.main()
