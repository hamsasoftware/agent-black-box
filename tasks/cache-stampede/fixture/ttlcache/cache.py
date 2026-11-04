"""A thread-safe cache with a time to live and a loader callback."""
import threading
import time

from .stats import Stats


class TTLCache:
    def __init__(self, loader, ttl):
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self._loader = loader
        self._ttl = ttl
        self._lock = threading.Lock()
        self._values = {}
        self._stamps = {}
        self._stats = Stats()

    def get(self, key):
        value = self._values.get(key)
        if value is not None and time.monotonic() - self._stamps[key] <= self._ttl:
            self._stats.hits += 1
            return value
        self._stats.misses += 1
        self._stats.loads += 1
        try:
            value = self._loader(key)
        except Exception:
            self._stats.failures += 1
            raise
        with self._lock:
            self._values[key] = value
            self._stamps[key] = time.monotonic()
        return value

    def invalidate(self, key):
        with self._lock:
            self._values.pop(key, None)
            self._stamps.pop(key, None)

    def stats(self):
        return self._stats.snapshot()
