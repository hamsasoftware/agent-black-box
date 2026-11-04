"""A thread-safe cache with a time to live and a loader callback (one Future per load in flight)."""
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeout

from .errors import DeadlockError
from .stats import Stats


class TTLCache:
    def __init__(self, loader, ttl, clock=time.monotonic, max_size=None, stale_grace=None):
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if max_size is not None and (not isinstance(max_size, int) or isinstance(max_size, bool) or max_size < 1):
            raise ValueError("max_size")
        if stale_grace is not None and stale_grace <= 0:
            raise ValueError("stale_grace")
        self._loader = loader
        self._ttl = ttl
        self._clock = clock
        self._max = max_size
        self._grace = stale_grace
        self._lock = threading.RLock()
        self._entries = OrderedDict()
        self._flights = {}  # key -> (Future, owner thread id)
        self._blocked = {}  # thread id -> owner thread id of the load it waits for
        self._stats = Stats()

    def _closes_cycle(self, owner, me):
        hops = 0
        while owner is not None and hops <= len(self._blocked) + 1:
            if owner == me:
                return True
            owner = self._blocked.get(owner)
            hops += 1
        return False

    def get(self, key, timeout=None):
        if timeout is not None and timeout < 0:
            raise ValueError("timeout")
        me = threading.get_ident()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and self._clock() - entry[1] < self._ttl:
                self._entries.move_to_end(key)
                self._stats.hits += 1
                return entry[0]
            self._stats.misses += 1
            flight = self._flights.get(key)
            if flight is not None:
                future, owner = flight
                if owner == me:
                    raise RuntimeError("recursive load of %r" % (key,))
                if self._closes_cycle(owner, me):
                    self._stats.deadlocks += 1
                    raise DeadlockError("cycle at %r" % (key,))
                if timeout == 0:
                    self._stats.timeouts += 1
                    raise TimeoutError("busy")
                self._blocked[me] = owner
            else:
                future = Future()
                self._flights[key] = (future, me)
                self._stats.loads += 1
        if flight is not None:
            try:
                kind, value = future.result(timeout)
            except FutureTimeout:
                with self._lock:
                    self._stats.timeouts += 1
                raise TimeoutError("waited %ss for %r" % (timeout, key)) from None
            finally:
                with self._lock:
                    self._blocked.pop(me, None)
            if kind == "stale":
                with self._lock:
                    self._stats.stale_served += 1
            return value
        try:
            value = self._loader(key)
        except BaseException as exc:
            with self._lock:
                self._stats.failures += 1
                self._flights.pop(key, None)
                entry = self._entries.get(key)
                stale = (
                    self._grace is not None and entry is not None
                    and self._ttl <= self._clock() - entry[1] < self._ttl + self._grace
                )
                if stale:
                    self._stats.stale_served += 1
            if stale:
                future.set_result(("stale", entry[0]))
                return entry[0]
            future.set_exception(exc)
            raise
        with self._lock:
            self._entries[key] = (value, self._clock())
            self._entries.move_to_end(key)
            self._flights.pop(key, None)
            self._evict()
        future.set_result(("ok", value))
        return value

    def _evict(self):
        while self._max is not None and len(self._entries) > self._max:
            victim = next((k for k in self._entries if k not in self._flights), None)
            if victim is None:
                return
            del self._entries[victim]
            self._stats.evictions += 1

    def invalidate(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def invalidate_all(self):
        with self._lock:
            removed = len(self._entries)
            self._entries.clear()
            return removed

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def stats(self, extended=False):
        with self._lock:
            return self._stats.snapshot(extended)
