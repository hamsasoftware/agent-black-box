"""A thread-safe cache with a time to live and a loader callback (one Future per load in flight)."""
import threading
import time
from concurrent.futures import Future

from .stats import Stats


class TTLCache:
    def __init__(self, loader, ttl, clock=time.monotonic):
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self._loader = loader
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.RLock()
        self._entries = {}
        self._flights = {}  # key -> (Future, owner thread id)
        self._stats = Stats()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and self._clock() - entry[1] < self._ttl:
                self._stats.hits += 1
                return entry[0]
            self._stats.misses += 1
            flight = self._flights.get(key)
            if flight is not None:
                future, owner = flight
                if owner == threading.get_ident():
                    raise RuntimeError("recursive load of %r" % (key,))
            else:
                future = Future()
                self._flights[key] = (future, threading.get_ident())
                self._stats.loads += 1
        if flight is not None:
            return future.result()
        try:
            value = self._loader(key)
        except BaseException as exc:
            with self._lock:
                self._stats.failures += 1
                self._flights.pop(key, None)
            future.set_exception(exc)
            raise
        with self._lock:
            self._entries[key] = (value, self._clock())
            self._flights.pop(key, None)
        future.set_result(value)
        return value

    def invalidate(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def stats(self):
        with self._lock:
            return self._stats.snapshot()
