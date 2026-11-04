Rewrote ttlcache/cache.py against docs/CONTRACT.md. One short lock guards the tables (entries in LRU order, flights,
who waits for what) and is never held while a loader runs or a get waits. Gets for a key share one flight object that
waiters block on; failures reach all of them or turn into the stale value; max_size evicts least recently used entries
that have no load in flight; timeouts are timed waits on the flight's event; a wait that would close a cycle of
waiting threads raises DeadlockError. Verified with the visible tests and scratch scripts that block loaders on
events with a fake clock. Not verified: behaviour with a real clock under heavy load.
