Fixed the two races in ttlcache/cache.py. Gets for a key now share one in-flight load (a flight object per key
under a short lock that is never held while the loader runs), waiters receive the loader's result or its exception,
and expiry uses the injected clock with age < ttl. Verified with the visible tests and a scratch script that blocks the
loader on an event. Did not verify behaviour under real clock skew.
