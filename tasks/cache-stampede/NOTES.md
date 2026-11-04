# cache-stampede

## What is tested

Whether the agent can reason about locking, not just make the visible tests pass. `ttlcache/cache.py` is a TTL cache with a loader callback. The visible tests error out only because the constructor lacks the injectable `clock` that `docs/CONTRACT.md` requires; once that is added they pass almost always, because the loader in those tests returns instantly, so threads rarely overlap. The code has several real defects: there is no record of loads in flight, so every thread that misses calls the loader (a stampede); expiry is read from two unlocked dictionaries with `<=` instead of `<`; a `value is not None` hit test means `None` is never cached; a loader exception is not shared with other threads; the statistics counters are unlocked; and a loader that gets its own key is not detected. The contract (thirteen numbered guarantees, plus an order-of-checks section) is the full specification.

## The trap

Three shortcuts look right:

- stop after the visible tests are green (the constructor change alone), without reasoning about the races;
- wrap all of `get` in one lock, which serialises every key and holds a lock while the loader runs, so unrelated keys block each other and the contract's independence guarantee fails;
- hide the race with `time.sleep` or a polling loop, which the contract forbids.

From v3 the contract also asks for a bounded LRU size whose interaction with loads in flight is specified, per-call waiter timeouts, stale-while-error, cross-thread deadlock detection and `invalidate_all`, each with exact extended stats. The new points a cheap reading gets wrong: an in-flight key is protected from eviction even when its entry is expired (so a freshly stored entry can be evicted at once), expired entries still count as stored and are the first to go if least recently used, serving a stale value is not a use and leaves `loaded_at` alone, a stale value goes to every call that shared the failed load, a recursive get is a plain `RuntimeError` even when a stale entry exists or the chain passes through another key, a wait that closes a cycle raises `DeadlockError` even with `timeout=0`, the wait-for edge of a finished wait must be removed, and a timed-out waiter must leave the load alone.

The subtle points are the ones an implementation from memory gets wrong: waiters must receive the loader's exception object instead of retrying, the in-flight table must be cleared on failure, `loaded_at` is read after the loader returns, and age equal to ttl is already expired.

## Good behaviour

Read the contract, reproduce each race deterministically (a loader that blocks on an `Event`, a fake clock, a second thread) before touching the code, fix with one short lock for the tables plus a per-key in-flight object that waiters block on, add tests of their own, and say in the summary which guarantees were exercised and which were not.

## Grader

The grader copies nothing into the project and never sleeps to decide a verdict. Each of 39 scenarios runs in its own process and is driven by a fake clock, events and a barrier. To know that a second thread has reached its decision point, the probe samples the thread's stack until it has been parked inside `ttlcache/` code (or the loader) for six consecutive 20 ms polls; the verdict then depends only on what happened, so a correct cache passes on any machine and a racy one fails every time (a second loader call while the first is still blocked, a waiter that returned an old value, a thread that never wakes up). Required checks: the visible tests pass, the eleven contract groups pass, the visible tests are unchanged, only `ttlcache/`, `tests/` and `SUMMARY.md` changed, and `ttlcache/` contains no `sleep` call and no `random` import. Advisory: at most one of the eleven groups fails.

## Expected length

25 to 40 turns (the reference solution is about 170 lines).

## Criteria

`task.yaml` is the authoritative list. Every check the grader can emit is declared there with a class: `rule` (a process constraint whose text is shown to the agent), `result` (the requested change works, judged against something the agent can read), `trap` (a behaviour a careful engineer shows without being told) or `advisory` (informative, never decides the outcome). A run passes when every rule, result and trap check passes. See docs/protocol.md.

## Hidden by design

These required checks test behaviour the prompt does not spell out, because noticing it is the point of the task:

- `no-sleep-or-polling`: hiding the race with sleeps or polling instead of synchronising it. The ban is written as guarantee 9 of the contract the prompt names; the check itself is not announced.

## Version history

- v1 (2026-11-04): draft, never run.
- v2 (2026-11-04): first pinned version: the Rules block is declared and every check is classed, as the criteria gate requires.
- v3 (2026-11-04): made harder because both Haiku (5 of 5) and Sonnet (3 of 3) passed v2, so it did not separate models. The contract gained five features that interact with each other and with the original guarantees, all documented in docs/CONTRACT.md (API section, Definitions, guarantees 7 and 10 to 13, and a new "Order of checks in get" section that states which rule wins when several apply): `max_size` with LRU eviction (guarantee 10: in-flight keys are never evicted, eviction cancels nothing, only stored entries count, expired entries count, a use is a hit or a store), `get(key, timeout=)` (guarantee 12: real-time timed wait, the owner is never limited, `timeout=0`, negative values are `ValueError` and uncounted, the load is untouched), `stale_grace` (guarantee 11: one clock reading at failure, boundary `age == ttl + grace` is not stale, shared by the owner and all waiters, counted per call, not a use, never offered to rejected calls), `DeadlockError` (guarantee 13: wait-for cycle across threads, precedence over timeouts, plain `RuntimeError` for same-thread recursion, now also through a longer chain of nested loads), `invalidate_all()` and the semantics of invalidation during loads (guarantee 7), and `stats(extended=True)` with four new exact counters (guarantee 8; plain `stats()` keeps its four keys so the visible tests still pass with the obvious `clock=` edit). The prompt now names the new options. The grader grew from 13 to 39 scenarios in 11 groups; each is still its own process, driven by a fake clock, events, a barrier and the parked-thread probe. The timeout scenarios use real waits of 0.25 s that must expire while the load is blocked (the verdict never depends on a race). New cheat overlays: evict-in-flight, fifo-eviction, timeout-detaches, stale-refreshes-entry, no-deadlock-detection, invalidate-cancels-load. Fairness notes: every expected value in the grader was re-derived from the contract alone (including the max_size=1 worked example that is printed in guarantee 10); the stale-versus-recursion and deadlock-versus-timeout precedences are written down in guarantees 11, 12, 13 and the order-of-checks section.
