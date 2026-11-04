"""A thread-safe cache with a time to live and a loader callback."""
import threading
import time
from collections import OrderedDict

from .errors import DeadlockError
from .stats import Stats


class _Flight:
    """One load that is in flight. Waiters block on `done`, then read `value`, `error` or `stale`."""

    __slots__ = ("done", "owner", "value", "error", "stale")

    def __init__(self):
        self.done = threading.Event()
        self.owner = threading.get_ident()
        self.value = None
        self.error = None
        self.stale = None  # a 1-tuple holding the stale value to serve, when the load failed


class TTLCache:
    def __init__(self, loader, ttl, clock=time.monotonic, max_size=None, stale_grace=None):
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if max_size is not None and (isinstance(max_size, bool) or not isinstance(max_size, int) or max_size < 1):
            raise ValueError("max_size must be None or an integer >= 1")
        if stale_grace is not None and not stale_grace > 0:
            raise ValueError("stale_grace must be None or greater than zero")
        self._loader = loader
        self._ttl = ttl
        self._clock = clock
        self._max_size = max_size
        self._grace = stale_grace
        self._lock = threading.Lock()  # guards the tables below; never held while a loader runs or a get waits
        self._entries = OrderedDict()  # key -> (value, loaded_at), least recently used first
        self._flights = {}  # key -> _Flight
        self._waiting = {}  # thread id -> the _Flight that thread is blocked on
        self._stats = Stats()

    def _cycle(self, flight, me):
        """True when waiting for `flight` would close a cycle of waiting threads that includes `me`."""
        seen = set()
        thread = flight.owner
        while thread not in seen:
            if thread == me:
                return True
            seen.add(thread)
            blocked_on = self._waiting.get(thread)
            if blocked_on is None:
                return False
            thread = blocked_on.owner
        return False

    def _stale_value(self, key):
        entry = self._entries.get(key)
        if entry is None or self._grace is None:
            return None
        age = self._clock() - entry[1]
        if self._ttl <= age < self._ttl + self._grace:
            return (entry[0],)
        return None

    def _evict(self):
        if self._max_size is None:
            return
        while len(self._entries) > self._max_size:
            for victim in self._entries:
                if victim not in self._flights:
                    break
            else:
                return
            del self._entries[victim]
            self._stats.evictions += 1

    def get(self, key, timeout=None):
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must not be negative")
        me = threading.get_ident()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and self._clock() - entry[1] < self._ttl:
                self._entries.move_to_end(key)
                self._stats.hits += 1
                return entry[0]
            self._stats.misses += 1
            flight = self._flights.get(key)
            if flight is None:
                owner = True
                flight = self._flights[key] = _Flight()
                self._stats.loads += 1
            else:
                owner = False
                if flight.owner == me:
                    raise RuntimeError(f"the load of {key!r} is running in this thread; get({key!r}) would wait for itself")
                if self._cycle(flight, me):
                    self._stats.deadlocks += 1
                    raise DeadlockError(f"waiting for {key!r} would complete a cycle of waiting threads")
                if timeout == 0:
                    self._stats.timeouts += 1
                    raise TimeoutError(f"the load of {key!r} is in flight")
                self._waiting[me] = flight
        if not owner:
            return self._wait(key, flight, me, timeout)
        try:
            value = self._loader(key)
        except BaseException as exc:
            with self._lock:
                del self._flights[key]
                self._stats.failures += 1
                flight.error = exc
                flight.stale = self._stale_value(key)
                if flight.stale is not None:
                    self._stats.stale_served += 1
            flight.done.set()
            if flight.stale is not None:
                return flight.stale[0]
            raise
        with self._lock:
            self._entries[key] = (value, self._clock())
            self._entries.move_to_end(key)
            del self._flights[key]
            self._evict()
        flight.value = value
        flight.done.set()
        return value

    def _wait(self, key, flight, me, timeout):
        while not flight.done.is_set():
            time.sleep(0.01)
        finished = True
        with self._lock:
            del self._waiting[me]
            if not finished and not flight.done.is_set():
                self._stats.timeouts += 1
                raise TimeoutError(f"the load of {key!r} did not finish in {timeout}s")
            if flight.error is not None and flight.stale is not None:
                self._stats.stale_served += 1
        if flight.error is not None:
            if flight.stale is not None:
                return flight.stale[0]
            raise flight.error
        return flight.value

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
