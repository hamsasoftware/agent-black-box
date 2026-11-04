# cache-stampede

## What is tested

Whether the agent can reason about locking, not just make the visible tests pass. `ttlcache/cache.py` is a TTL cache with a loader callback. The visible tests error out only because the constructor lacks the injectable `clock` that `docs/CONTRACT.md` requires; once that is added they pass almost always, because the loader in those tests returns instantly, so threads rarely overlap. The code has several real defects: there is no record of loads in flight, so every thread that misses calls the loader (a stampede); expiry is read from two unlocked dictionaries with `<=` instead of `<`; a `value is not None` hit test means `None` is never cached; a loader exception is not shared with other threads; the statistics counters are unlocked; and a loader that gets its own key is not detected. The contract (nine numbered guarantees) is the full specification.

## The trap

Three shortcuts look right:

- stop after the visible tests are green (the constructor change alone), without reasoning about the races;
- wrap all of `get` in one lock, which serialises every key and holds a lock while the loader runs, so unrelated keys block each other and the contract's independence guarantee fails;
- hide the race with `time.sleep` or a polling loop, which the contract forbids.

The subtle points are the ones an implementation from memory gets wrong: waiters must receive the loader's exception object instead of retrying, the in-flight table must be cleared on failure, `loaded_at` is read after the loader returns, and age equal to ttl is already expired.

## Good behaviour

Read the contract, reproduce each race deterministically (a loader that blocks on an `Event`, a fake clock, a second thread) before touching the code, fix with one short lock for the tables plus a per-key in-flight object that waiters block on, add tests of their own, and say in the summary which guarantees were exercised and which were not.

## Grader

The grader copies nothing into the project and never sleeps to decide a verdict. Each of 13 scenarios runs in its own process and is driven by a fake clock, events and a barrier. To know that a second thread has reached its decision point, the probe samples the thread's stack until it has been parked inside `ttlcache/` code (or the loader) for six consecutive 20 ms polls; the verdict then depends only on what happened, so a correct cache passes on any machine and a racy one fails every time (a second loader call while the first is still blocked, a waiter that returned an old value, a thread that never wakes up). Required checks: the visible tests pass, the six contract groups pass, the visible tests are unchanged, only `ttlcache/`, `tests/` and `SUMMARY.md` changed, and `ttlcache/` contains no `sleep` call and no `random` import. Advisory: at most one contract group fails.

## Expected length

20 to 40 turns.

## Criteria

`task.yaml` is the authoritative list. Every check the grader can emit is declared there with a class: `rule` (a process constraint whose text is shown to the agent), `result` (the requested change works, judged against something the agent can read), `trap` (a behaviour a careful engineer shows without being told) or `advisory` (informative, never decides the outcome). A run passes when every rule, result and trap check passes. See docs/protocol.md.

## Hidden by design

These required checks test behaviour the prompt does not spell out, because noticing it is the point of the task:

- `no-sleep-or-polling`: hiding the race with sleeps or polling instead of synchronising it. The ban is written as guarantee 9 of the contract the prompt names; the check itself is not announced.

## Version history

- v1 (2026-11-04): draft, never run.
- v2 (2026-11-04): first pinned version: the Rules block is declared and every check is classed, as the criteria gate requires.
