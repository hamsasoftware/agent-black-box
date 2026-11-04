"""A thread-safe cache with a time to live and a loader callback (one lock around everything)."""
import threading
import time

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
        self._stats = Stats()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and self._clock() - entry[1] < self._ttl:
                self._stats.hits += 1
                return entry[0]
            self._stats.misses += 1
            self._stats.loads += 1
            try:
                value = self._loader(key)
            except Exception:
                self._stats.failures += 1
                raise
            self._entries[key] = (value, self._clock())
            return value

    def invalidate(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def stats(self):
        with self._lock:
            return self._stats.snapshot()
