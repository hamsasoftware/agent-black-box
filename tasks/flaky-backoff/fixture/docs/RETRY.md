# Retry policy

For retry number `attempt` (1 for the first retry):

1. The base delay is `base * 2 ** (attempt - 1)` seconds.
2. Jitter: the delay is multiplied by a random factor drawn uniformly from `[1 - jitter, 1 + jitter]` (default `jitter = 0.1`). Jitter is mandatory: without it, clients that failed together retry together and overload the service again.
3. The result is clamped to `[0, cap]`. **No delay may ever exceed `cap`**; the load balancer drops connections idle for longer than that.

The random source is injectable (`rng=`) so callers and tests can make schedules reproducible.
