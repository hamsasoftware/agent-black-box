# ttlcache

A small thread-safe cache with a time to live. You give it a loader function; it calls the loader on a miss and
remembers the value until it expires.

```python
from ttlcache import TTLCache

cache = TTLCache(load_user, ttl=30)
user = cache.get(42)      # loads on a miss, serves from memory afterwards
cache.invalidate(42)      # forget one key
print(cache.stats())      # {"hits": ..., "misses": ..., "loads": ..., "failures": ...}
```

The guarantees the library makes are in `docs/CONTRACT.md`. Run the tests with `python -m unittest`.
