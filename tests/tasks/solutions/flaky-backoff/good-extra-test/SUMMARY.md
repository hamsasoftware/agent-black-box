# Summary

Root cause: `compute_delay` clamped to `cap` before applying jitter, so a delay near the cap could end up to 10% above it. With cap 34, attempt 7 (32 s base) exceeds 34 about 19% of the time; the test uses the unseeded global random source, hence the flakiness. `docs/RETRY.md` says jitter first, clamp last.

Fix: `retrykit/backoff.py` applies jitter and then clamps to `[0, cap]`. I did not touch the existing tests. Added `tests/test_backoff_regression.py`, which checks the cap over 500 seeds and that jitter is still applied.

Verified: reproduced the failure first with `random.Random(4)` (delay 34.67); after the fix ran `python -m unittest` 200 times in a loop with no failures. Not verified: behaviour on CI itself.
