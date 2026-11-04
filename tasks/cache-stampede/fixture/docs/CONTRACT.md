# ttlcache contract

This is the full list of guarantees `ttlcache` makes. The implementation in `ttlcache/` must keep every one of
them, for any number of threads.

## API

- `TTLCache(loader, ttl, clock=time.monotonic)`
  - `loader(key)` returns the value for `key`. It may be slow. It may raise.
  - `ttl` is a number of seconds. A `ttl` of zero or less raises `ValueError`.
  - `clock()` takes no arguments and returns the current time in seconds. Every time decision the cache makes
    uses this clock and nothing else, so tests can inject a fake one. `time.monotonic` is only the default.
- `get(key)` returns the value for `key`, calling the loader when it has no valid value.
- `invalidate(key)` forgets the stored value for `key`. An unknown key is not an error.
- `stats()` returns a plain dict.

## Definitions

- A **load** is one call of the loader for a key. A load is **in flight** from the moment a `get` decides to run
  it until the loader returns or raises.
- A stored entry is a value together with `loaded_at`: one reading of the clock, taken right after the loader
  returned successfully (not before the loader was called).
- An entry is **valid** while `clock() - loaded_at < ttl`. It is **expired** from the moment the age equals
  `ttl`. An entry exactly `ttl` seconds old is expired.

## Guarantees

1. **Single load.** At most one load per key is in flight at any time. A `get` that finds no valid entry while a
   load for the same key is in flight waits for that load and returns its result (or raises its exception). It
   does not call the loader itself. So any number of concurrent `get` calls for a key that is missing or expired
   cause exactly one loader call.
2. **No expired values.** `get` never returns the value of an expired entry. When the entry is expired it
   returns the result of a load: its own, or the one already in flight. A valid entry is returned as it is,
   without calling the loader and without waiting for anything.
3. **Failure.** If the loader raises, nothing is stored for that load. The exception, the very same object, is
   raised by the `get` that ran the loader and by every `get` that was waiting for that load. Waiting calls are
   never left waiting. A `get` that starts after the load has failed starts a new load (a retry), and a failure
   leaves no trace: a later successful load is stored and served as usual.
4. **Independence.** A slow load for one key never delays a call that does not need its result: not a `get` for
   another key (hit or miss), not `invalidate`, not `stats()`. Loads for different keys may run at the same
   time. A loader may itself call `get` on the same cache for a different key.
5. **Recursion.** A loader that calls `get` for the key it is loading is a programming error. That inner `get`
   raises `RuntimeError` instead of waiting for itself. The error leaves the loader like any other loader
   exception (guarantee 3).
6. **Any value.** The loader may return any value, including `None`, `0`, `""` and `False`. All are stored and
   served like any other value.
7. **Invalidate.** `invalidate(key)` removes the stored entry for `key`, if there is one. It does not cancel or
   detach a load in flight: that load's result is stored when it completes and is returned to its waiters. It
   does not change the stats.
8. **Stats.** `stats()` returns a dict with exactly the keys `hits`, `misses`, `loads` and `failures`. Every
   `get` call is counted exactly once, as a hit (answered from a valid stored entry) or as a miss (every other
   case, including a call that waited for another thread's load and a call rejected under guarantee 5). `loads`
   counts loader calls started and `failures` counts those that raised. The counters are exact under
   concurrency.
9. **No timing tricks.** Waiting is done on locks, events or conditions. The library does not sleep, poll or use
   random numbers, because those only make a race rarer.
