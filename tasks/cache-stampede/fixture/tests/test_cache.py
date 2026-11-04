import threading
import unittest

from tests.support import FakeClock
from ttlcache import TTLCache


class Counter:
    def __init__(self):
        self.calls = []

    def __call__(self, key):
        self.calls.append(key)
        return f"{key}:{len(self.calls)}"


class BasicTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.loader = Counter()
        self.cache = TTLCache(self.loader, ttl=10, clock=self.clock)

    def test_loads_once_then_hits(self):
        self.assertEqual(self.cache.get("a"), "a:1")
        self.assertEqual(self.cache.get("a"), "a:1")
        self.assertEqual(self.loader.calls, ["a"])

    def test_entry_is_valid_before_the_ttl(self):
        self.cache.get("a")
        self.clock.advance(9)
        self.assertEqual(self.cache.get("a"), "a:1")
        self.assertEqual(len(self.loader.calls), 1)

    def test_entry_expires_after_the_ttl(self):
        self.cache.get("a")
        self.clock.advance(11)
        self.assertEqual(self.cache.get("a"), "a:2")
        self.assertEqual(len(self.loader.calls), 2)

    def test_keys_are_independent(self):
        self.assertEqual(self.cache.get("a"), "a:1")
        self.assertEqual(self.cache.get("b"), "b:2")
        self.assertEqual(self.cache.get("a"), "a:1")

    def test_invalidate_forces_a_reload(self):
        self.cache.get("a")
        self.cache.invalidate("a")
        self.cache.invalidate("never-seen")
        self.assertEqual(self.cache.get("a"), "a:2")

    def test_loader_error_propagates_and_a_retry_works(self):
        outcomes = [ValueError("boom"), "ok"]

        def flaky(key):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        cache = TTLCache(flaky, ttl=10, clock=self.clock)
        with self.assertRaises(ValueError):
            cache.get("a")
        self.assertEqual(cache.get("a"), "ok")

    def test_stats_for_one_thread(self):
        self.cache.get("a")
        self.cache.get("a")
        self.clock.advance(10)
        self.cache.get("a")
        self.assertEqual(self.cache.stats(), {"hits": 1, "misses": 2, "loads": 2, "failures": 0})

    def test_ttl_must_be_positive(self):
        with self.assertRaises(ValueError):
            TTLCache(self.loader, ttl=0, clock=self.clock)


class ThreadsTest(unittest.TestCase):
    def test_threads_get_the_same_value(self):
        loader = Counter()
        cache = TTLCache(loader, ttl=60, clock=FakeClock())
        results = []

        def work():
            results.append(cache.get("shared"))

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 8)
        self.assertEqual(set(results), {"shared:1"})
        self.assertEqual(loader.calls, ["shared"])


if __name__ == "__main__":
    unittest.main()
