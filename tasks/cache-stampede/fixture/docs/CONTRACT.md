# ttlcache contract

This is the full list of guarantees `ttlcache` makes. The implementation in `ttlcache/` must keep every one of
them, for any number of threads. The API section also defines the options and the extra methods; they are part
of the contract in the same way as the numbered guarantees.

## API

- `TTLCache(loader, ttl, clock=time.monotonic, max_size=None, stale_grace=None)`
  - `loader(key)` returns the value for `key`. It may be slow. It may raise.
  - `ttl` is a number of seconds. A `ttl` of zero or less raises `ValueError`.
  - `clock()` takes no arguments and returns the current time in seconds. It never goes backwards. Every
    decision the cache makes about the age of an entry (valid, expired, within the grace period) uses this clock
    and nothing else, so tests can inject a fake one. `time.monotonic` is only the default. The one exception is
    the `timeout` of a `get` call (below): it is real elapsed time spent blocked, not read from this clock.
  - `max_size` is `None` (no bound) or an integer of at least 1, the most stored entries the cache keeps (see
    guarantee 10). Any other value raises `ValueError`.
  - `stale_grace` is `None` (stale serving is off) or a number of seconds greater than zero (see guarantee 11).
    Any other value raises `ValueError`.
- `get(key, timeout=None)` returns the value for `key`, calling the loader when it has no valid value.
  `timeout` is `None` (wait as long as needed) or a number of seconds, at least 0, that this call is willing to
  wait for a load that another call has in flight (guarantee 12). A negative `timeout` raises `ValueError`
  before anything else happens; such a call is not counted in the stats.
- `invalidate(key)` forgets the stored value for `key`. An unknown key is not an error. It returns `None`.
- `invalidate_all()` forgets every stored entry and returns how many entries it removed (see guarantee 7).
- `len(cache)` is the number of stored entries (see Definitions). It never counts a load that has no stored
  entry yet.
- `stats(extended=False)` returns a plain dict. See guarantee 8 for its keys.
- `ttlcache.DeadlockError` is an exception class, a subclass of `RuntimeError` (see guarantee 13). It is
  importable from the package: `from ttlcache import DeadlockError`.

## Definitions

- A **load** is one call of the loader for a key. A load is **in flight** from the moment a `get` decides to run
  it until the loader returns or raises. A key whose load is in flight is an **in-flight key**; the call that
  runs the loader is that load's **owner**, every other call that waits for it is a **waiter**.
- A stored entry is a value together with `loaded_at`: one reading of the clock, taken right after the loader
  returned successfully (not before the loader was called).
- An entry is **valid** while `clock() - loaded_at < ttl`. It is **expired** from the moment the age equals
  `ttl`. An entry exactly `ttl` seconds old is expired.
- An entry is **stale** while `ttl <= clock() - loaded_at < ttl + stale_grace` (it is expired, but still inside
  the grace period; an entry exactly `ttl + stale_grace` old is not stale). Without `stale_grace` no entry is
  stale.
- Entries are removed only by eviction (guarantee 10), `invalidate`, `invalidate_all`, and by being replaced
  when a load of the same key stores its value. An entry is never removed just because it is expired, and a
  failed load changes no entry. Expired and stale entries therefore count as stored entries.
- A **use** of an entry is a `get` that returns it as a valid entry (a hit), and the moment a load stores it.
  Nothing else is a use: not a miss, not a wait for a load, not serving a stale value, not `invalidate`.

## Guarantees

1. **Single load.** At most one load per key is in flight at any time. A `get` that finds no valid entry while a
   load for the same key is in flight waits for that load and returns its result (or raises its exception). It
   does not call the loader itself. So any number of concurrent `get` calls for a key that is missing or expired
   cause exactly one loader call.
2. **No expired values.** `get` never returns the value of an expired entry, except as a stale value under
   guarantee 11. When the entry is expired it returns the result of a load: its own, or the one already in
   flight. A valid entry is returned as it is, without calling the loader and without waiting for anything.
3. **Failure.** If the loader raises, nothing is stored for that load. The exception, the very same object, is
   raised by the `get` that ran the loader and by every `get` that was waiting for that load, except where
   guarantee 11 serves a stale value instead. Waiting calls are never left waiting. A `get` that starts after
   the load has failed starts a new load (a retry), and a failure leaves no trace: a later successful load is
   stored and served as usual.
4. **Independence.** A slow load for one key never delays a call that does not need its result: not a `get` for
   another key (hit or miss), not `invalidate`, not `invalidate_all`, not `len`, not `stats()`. Loads for
   different keys may run at the same time. A loader may itself call `get` on the same cache for a different
   key.
5. **Recursion.** A `get` for a key whose load is in flight in the calling thread, because that thread's
   loader (or a loader nested inside it) is running for that key, is a programming error. It raises
   `RuntimeError` (that class itself, not `DeadlockError`) instead of waiting for itself. The error leaves the
   loader like any other loader exception (guarantee 3). This holds for a loader that gets its own key and
   also when the chain is longer: the loader for A gets B, in the same thread that loader gets A.
6. **Any value.** The loader may return any value, including `None`, `0`, `""` and `False`. All are stored and
   served like any other value.
7. **Invalidate.** `invalidate(key)` removes the stored entry for `key`, if there is one. `invalidate_all()`
   removes every stored entry, expired ones included, and returns their number (a load in flight is not an
   entry and is not counted). Neither cancels or detaches a load in flight: that load's result is stored when
   it completes (also when its key was invalidated meanwhile) and is returned to its waiters. Neither changes
   the stats; in particular a removed entry is not an eviction.
8. **Stats.** `stats()` returns a dict with exactly the keys `hits`, `misses`, `loads` and `failures`.
   `stats(extended=True)` returns exactly those four and also `evictions`, `stale_served`, `timeouts` and
   `deadlocks`. Every `get` call is counted exactly once, as a hit (answered from a valid stored entry) or as a
   miss (every other case, including a call that waited for another thread's load, a call rejected under
   guarantee 5 or 13, a call that timed out, and a call answered with a stale value). `loads` counts loader
   calls started and `failures` counts those that raised. `evictions` counts entries evicted under guarantee 10.
   `stale_served` counts calls answered with a stale value under guarantee 11. `timeouts` counts calls that
   raised `TimeoutError` under guarantee 12. `deadlocks` counts calls rejected with `DeadlockError` under
   guarantee 13. The counters are exact under concurrency; a call is counted in `stale_served` or `timeouts`
   no later than the moment it returns or raises. The only call not counted at all is one rejected by the
   `ValueError` for a negative `timeout`.
9. **No timing tricks.** Waiting is done on locks, events or conditions. The library does not sleep, poll or use
   random numbers, because those only make a race rarer.
10. **Bounded size (LRU).** With `max_size`, when a load stores its entry and the cache then holds more than
    `max_size` stored entries, it evicts entries, least recently used first (by their last use, see
    Definitions), until it holds `max_size` or fewer. Only entries of keys that have no load in flight can be
    evicted: an in-flight key is never evicted, not even if its stored entry is expired and the load in flight
    is refreshing it. If the only entries left to evict are the ones just stored, those are evicted. Eviction
    never cancels or changes a load in flight, and never changes what a waiter receives. Stored entries are
    what is counted: a load in flight without a stored entry takes no space. Storing the value of a key that
    already has an entry replaces it and does not grow the cache. Example with `max_size=1`: `a` is stored and
    expired, its refresh is in flight; a `get("c")` loads and returns `c`, and its entry is evicted at once,
    because `a` is protected; the cache still holds the old `a`.
11. **Stale while error.** With `stale_grace`, when a load fails and, at that moment, the cache holds a stale
    entry for the key (read the clock once, when the failure is recorded), then the `get` that ran the loader
    and every `get` that was waiting for that load return the stale value instead of raising. Each such call
    counts once in `stale_served`; the load still counts in `loads` and `failures`. The entry itself is not
    changed (its `loaded_at` stays, it is not a use), so it ends being stale when the grace period ends and a
    later `get` starts a new load. If the entry was removed by `invalidate`, `invalidate_all` or anything else
    before the failure was recorded, or is no longer inside the grace period, the exception is raised as in
    guarantee 3. A call rejected under guarantee 5, 12 or 13 raises its own error and never receives a stale
    value; only the failure of a load that the call itself ran or waited for can produce one.
12. **Timeout.** `timeout` limits only how long a call waits as a waiter. A call that runs the loader itself is
    never limited by it, and a call answered from a valid entry never waits. A waiter that has waited
    `timeout` real seconds without the load finishing stops waiting and raises the built-in `TimeoutError`;
    `timeout=0` raises it at once when it would have to wait. A waiter that times out does not cancel, detach
    or otherwise change the load: it goes on, its owner and its other waiters are not affected, its result is
    stored as usual and later calls see no trace of the timed-out call. A `TimeoutError` is never replaced by a
    stale value.
13. **Deadlock detection.** Calls in different threads can wait for each other through their loaders: the
    loader for A (running in thread 1) calls `get(B)` while the loader for B (running in thread 2) calls
    `get(A)`; longer chains of threads are possible. A `get` that is about to wait for a load, and whose wait
    would complete such a cycle of waiting threads, does not wait: it raises `DeadlockError`. It does so even
    when it has a `timeout`, including `timeout=0`, and a wait that is only part of a cycle because one of the
    other waits has a timeout is still a cycle. A guarantee 5 situation (the load is owned by the calling
    thread) is not a deadlock and raises `RuntimeError`. The `DeadlockError` leaves the loader like any other
    loader exception (guarantee 3), so every call in the cycle ends with that exception (or with a stale value
    where guarantee 11 allows it) instead of hanging.
    Waiting that does not complete a cycle is normal waiting and never raises `DeadlockError`.

## Order of checks in `get`

When several rules could apply to one call, they apply in this order: (1) a negative `timeout` raises
`ValueError`; (2) a valid entry is a hit and is returned; (3) a load in flight owned by the calling thread
raises `RuntimeError`; (4) a wait that would complete a cycle raises `DeadlockError`; (5) `timeout=0` with a
load in flight raises `TimeoutError`; (6) otherwise the call waits, or runs the loader if no load is in flight;
(7) a failed load that the call ran or waited for is answered with a stale value if guarantee 11 allows it,
else with the loader's exception.
