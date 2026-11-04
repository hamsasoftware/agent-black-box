"""A thread-safe cache with a time to live and a loader callback."""
import threading
import time

from .stats import Stats


class _Flight:
    """One load that is in flight. Waiters block on `done`, then read `value` or `error`."""

    __slots__ = ("done", "owner", "value", "error")

    def __init__(self):
        self.done = threading.Event()
        self.owner = threading.get_ident()
        self.value = None
        self.error = None


class TTLCache:
    def __init__(self, loader, ttl, clock=time.monotonic):
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self._loader = loader
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()  # guards the three tables below; never held while the loader runs
        self._entries = {}  # key -> (value, loaded_at)
        self._flights = {}  # key -> _Flight
        self._stats = Stats()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and self._clock() - entry[1] < self._ttl:
                self._stats.hits += 1
                return entry[0]
            self._stats.misses += 1
            flight = self._flights.get(key)
            if flight is not None and flight.owner == threading.get_ident():
                raise RuntimeError(f"the loader for {key!r} called get for the same key")
            owner = flight is None
            if owner:
                flight = self._flights[key] = _Flight()
                self._stats.loads += 1
        if not owner:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return flight.value
        try:
            value = self._loader(key)
        except BaseException as exc:
            with self._lock:
                del self._flights[key]
                self._stats.failures += 1
            flight.error = exc
            flight.done.set()
            raise
        with self._lock:
            self._entries[key] = (value, self._clock())
            del self._flights[key]
        flight.value = value
        flight.done.set()
        return value

    def invalidate(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def stats(self):
        with self._lock:
            return self._stats.snapshot()
