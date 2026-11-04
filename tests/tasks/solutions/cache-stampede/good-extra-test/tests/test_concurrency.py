import threading
import unittest

from tests.support import FakeClock
from ttlcache import TTLCache


class SingleLoadTest(unittest.TestCase):
    def test_second_get_waits_for_the_load_in_flight(self):
        entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def loader(key):
            calls.append(key)
            if len(calls) > 1:
                second_entered.set()
            entered.set()
            release.wait(5)
            return "value"

        cache = TTLCache(loader, ttl=10, clock=FakeClock())
        out = []
        first = threading.Thread(target=lambda: out.append(cache.get("k")))
        second = threading.Thread(target=lambda: out.append(cache.get("k")))
        first.start()
        entered.wait(5)
        second.start()
        self.assertFalse(second_entered.wait(0.2), "the loader ran twice for one key")
        release.set()
        first.join(5)
        second.join(5)
        self.assertEqual(out, ["value", "value"])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
