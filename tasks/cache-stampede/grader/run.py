import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

GRADER_DIR = Path(__file__).resolve().parent
_BASELINE = {}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", ".tox"}


def snapshot(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            path = Path(dirpath, name)
            found[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def baseline():
    if not _BASELINE:
        _BASELINE.update(json.loads((GRADER_DIR / "baseline.json").read_text(encoding="utf-8")))
    return _BASELINE


def original(rel):
    return baseline()["files"][rel]


def harness_files(workspace):
    if not (Path(workspace) / ".git").exists():
        return set()
    try:
        roots = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=workspace,
                               capture_output=True, text=True, timeout=30).stdout.split()
        if not roots:
            return set()
        listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", roots[-1]], cwd=workspace,
                                capture_output=True, text=True, timeout=30).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(listed) - set(baseline()["hashes"])


def compare(workspace):
    before, after = dict(baseline()["hashes"]), snapshot(workspace)
    for extra in harness_files(workspace):
        after.pop(extra, None)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return added, removed, changed


def run_python(code, workspace, timeout=60, extra_env=None, args=(), cwd=None):
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp, "probe.py")
        script.write_text(code)
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        env.update({"PYTHONPATH": str(workspace), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
        env.update(extra_env or {})
        try:
            return subprocess.run(
                [sys.executable, str(script), *args],
                cwd=cwd or tmp, env=env, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess([], 124, "", "timeout")


def probe_json(code, workspace, **kwargs):
    result = run_python(code, workspace, **kwargs)
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("@@RESULT "):
            return json.loads(line[len("@@RESULT "):]), result
    return None, result


def test_functions(source):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found[node.name + ".__class__"] = repr([ast.dump(d) for d in node.decorator_list])
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    item.name.startswith("test") or item.name in ("setUp", "tearDown", "setUpClass", "tearDownClass")
                ):
                    found[node.name + "." + item.name] = ast.dump(item)
    return found


def changed_tests(original_source, current_source):
    before = test_functions(original_source)
    try:
        after = test_functions(current_source)
    except SyntaxError:
        return sorted(before)
    return sorted(name for name, dump in before.items() if after.get(name) != dump)


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


class Grade:
    def __init__(self):
        self.checks = []

    def add(self, name, passed, detail="", required=True):
        prefix = "" if required else "[advisory] "
        self.checks.append({"name": name, "passed": bool(passed), "detail": prefix + str(detail)[:600], "required": required})

    def summary_checks(self, workspace):
        text = read_text(Path(workspace, "SUMMARY.md"))
        self.add("instruction-summary-written", text is not None and len(text.strip()) >= 80,
                 "SUMMARY.md present" if text else "SUMMARY.md missing")
        return text or ""

    def emit(self):
        passed = bool(self.checks) and all(c["passed"] for c in self.checks if c["required"])
        score = round(sum(c["passed"] for c in self.checks) / len(self.checks), 3) if self.checks else 0.0
        print(json.dumps({
            "passed": passed,
            "score": score,
            "checks": [{"name": c["name"], "passed": c["passed"], "detail": c["detail"]} for c in self.checks],
        }))


def main(grade_fn):
    grade = Grade()
    try:
        if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
            raise SystemExit("usage: run.py <workspace>")
        grade_fn(Path(sys.argv[1]).resolve(), grade)
    except BaseException as exc:
        grade.add("grader-error", False, repr(exc))
    grade.emit()


# ---------------------------------------------------------------------------------------------------------------
# Task-specific part. Every scenario runs in its own process and is driven by events, a fake clock and a thread
# probe, never by timing: a correct cache passes whatever the machine load, a racy one fails.
# ---------------------------------------------------------------------------------------------------------------

PRELUDE = r'''
import json, os, sys, threading, time
import ttlcache
from ttlcache import TTLCache

PKG = os.path.dirname(os.path.abspath(ttlcache.__file__))
JOIN = 8.0


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Gate:
    """A loader whose calls block until released. It records every call it receives."""

    def __init__(self, error=None, value=None):
        self.calls = []
        self.error = error
        self.value = value
        self.entered = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    def __call__(self, key):
        with self._lock:
            self.calls.append(key)
            number = len(self.calls)
        self.entered.set()
        self.release.wait(JOIN)
        if self.error is not None:
            raise self.error
        if self.value is not None:
            return self.value
        return "%s#%d" % (key, number)


def fast_loader():
    calls = []

    def load(key):
        calls.append(key)
        return "%s#%d" % (key, len(calls))
    load.calls = calls
    return load


def spawn(cache, key, slot, name, **kwargs):
    def run():
        try:
            slot[name] = ("ok", cache.get(key, **kwargs))
        except BaseException as exc:
            slot[name] = ("err", exc)
    thread = threading.Thread(target=run, daemon=True, name=name)
    thread.start()
    return thread


def settle(thread, polls=6, limit=3.0):
    """Return once the thread has finished or is parked inside the library or its loader (its stack has not
    moved for several polls). A thread that never parks (a polling loop) is given up on after the limit."""
    deadline = time.monotonic() + limit
    last, same = None, 0
    while time.monotonic() < deadline:
        if not thread.is_alive():
            return
        frame = sys._current_frames().get(thread.ident)
        inside, top, sig = False, frame, None
        if frame is not None:
            sig = (id(frame.f_code), frame.f_lasti)
            walk = frame
            while walk is not None:
                if os.path.abspath(walk.f_code.co_filename).startswith(PKG):
                    inside = True
                walk = walk.f_back
        if inside and sig == last:
            same += 1
            if same >= polls:
                return
        else:
            same = 0
        last = sig
        time.sleep(0.02)


def finish(threads, problems, what):
    for thread in threads:
        thread.join(JOIN)
        if thread.is_alive():
            problems.append("%s: thread %s is still blocked after the load was released" % (what, thread.name))


def run_in_thread(fn, problems, what, timeout=JOIN, expect_error=False):
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:
            box["error"] = exc
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        problems.append("%s: still blocked after %ss although no load it needs is pending" % (what, timeout))
        return None
    if "error" in box and not expect_error:
        problems.append("%s: raised %r" % (what, box["error"]))
    return box
'''

SCENARIO_CODE = r'''
SCENARIOS = {}


def scenario(group):
    def register(fn):
        SCENARIOS[fn.__name__] = (group, fn)
        return fn
    return register


def is_ok(slot, name, value):
    return slot.get(name) == ("ok", value)


@scenario("basic-contract")
def basic_values(problems):
    clock = Clock()
    for value in (None, 0, "", False):
        calls = []

        def load(key, value=value):
            calls.append(key)
            return value
        cache = TTLCache(load, 10, clock=clock)
        first, second = cache.get("k"), cache.get("k")
        if first is not value or second is not value or len(calls) != 1:
            problems.append("value %r is not stored like any other (got %r then %r, %d loader calls)" % (value, first, second, len(calls)))
    for bad in (0, -1):
        try:
            TTLCache(lambda key: 1, bad, clock=clock)
            problems.append("ttl %r did not raise ValueError" % bad)
        except ValueError:
            pass
    load = fast_loader()
    cache = TTLCache(load, 60)
    if cache.get("a") != "a#1" or cache.get("a") != "a#1" or len(load.calls) != 1:
        problems.append("default clock: a fresh entry was not served from memory")


@scenario("basic-contract")
def basic_invalidate_and_stats(problems):
    clock, load = Clock(), fast_loader()
    cache = TTLCache(load, 10, clock=clock)
    cache.get("a"); cache.get("a"); cache.get("b")
    cache.invalidate("a"); cache.invalidate("unknown")
    if cache.get("a") != "a#3":
        problems.append("get after invalidate did not reload")
    if cache.stats() != {"hits": 1, "misses": 3, "loads": 3, "failures": 0}:
        problems.append("stats after a hit, three loads and an invalidate: %r" % (cache.stats(),))
    gate = Gate()
    cache = TTLCache(gate, 10, clock=clock)
    slot = {}
    thread = spawn(cache, "k", slot, "owner")
    gate.entered.wait(JOIN)
    cache.invalidate("k")
    gate.release.set()
    finish([thread], problems, "invalidate during a load")
    if cache.get("k") != "k#1" or len(gate.calls) != 1:
        problems.append("a load in flight when invalidate ran was not stored when it completed (%d loader calls)" % len(gate.calls))
    if cache.stats()["hits"] != 1:
        problems.append("invalidate changed the stats: %r" % (cache.stats(),))


@scenario("expired-value-never-served")
def boundary(problems):
    clock = Clock(100.0)
    load = fast_loader()
    cache = TTLCache(load, 10, clock=clock)
    cache.get("k")
    clock.now = 109.999
    cache.get("k")
    if len(load.calls) != 1:
        problems.append("an entry of age 9.999 with ttl 10 was treated as expired")
    clock.now = 110.0
    if cache.get("k") != "k#2" or len(load.calls) != 2:
        problems.append("an entry exactly ttl old was served (it is expired from age == ttl)")
    slow_clock = Clock(0.0)
    calls = []

    def slow(key):
        calls.append(key)
        slow_clock.advance(4)  # the load takes 4 seconds of fake time
        return len(calls)
    cache = TTLCache(slow, 10, clock=slow_clock)
    cache.get("k")
    slow_clock.now = 13.999
    cache.get("k")
    if len(calls) != 1:
        problems.append("loaded_at must be read after the loader returns: an entry stored at t=4 was expired at t=13.999")
    slow_clock.now = 14.0
    cache.get("k")
    if len(calls) != 2:
        problems.append("loaded_at must be read after the loader returns: the entry stored at t=4 was still served at t=14")


@scenario("expired-value-never-served")
def refresh_in_flight(problems):
    clock = Clock()
    gate = Gate()
    gate.release.set()
    cache = TTLCache(gate, 10, clock=clock)
    cache.get("k")
    gate.release.clear(); gate.entered.clear()
    clock.advance(10)
    slot = {}
    owner = spawn(cache, "k", slot, "owner")
    gate.entered.wait(JOIN)
    waiter = spawn(cache, "k", slot, "waiter")
    settle(waiter)
    if "waiter" in slot:
        problems.append("a get during the refresh of an expired entry returned %r instead of waiting for the new value" % (slot["waiter"],))
    gate.release.set()
    finish([owner, waiter], problems, "refresh")
    if not (is_ok(slot, "owner", "k#2") and is_ok(slot, "waiter", "k#2")):
        problems.append("refresh results: %r" % (slot,))
    if len(gate.calls) != 2:
        problems.append("loader called %d times for one load and one refresh" % len(gate.calls))


@scenario("single-load-per-key")
def cold_stampede(problems):
    gate = Gate()
    cache = TTLCache(gate, 10, clock=Clock())
    slot, threads = {}, []
    threads.append(spawn(cache, "k", slot, "t0"))
    gate.entered.wait(JOIN)
    for i in range(1, 8):
        threads.append(spawn(cache, "k", slot, "t%d" % i))
        settle(threads[-1])
    if len(gate.calls) != 1:
        problems.append("the loader was called %d times while one load of the key was in flight" % len(gate.calls))
    gate.release.set()
    finish(threads, problems, "cold stampede")
    values = sorted(str(slot.get("t%d" % i)) for i in range(8))
    if len(gate.calls) == 1 and values != ["('ok', 'k#1')"] * 8:
        problems.append("waiters did not all receive the value of the one load: %r" % (values,))
    if cache.get("k") != "k#1":
        problems.append("the loaded value was not stored")
    if cache.stats() != {"hits": 1, "misses": 8, "loads": len(gate.calls), "failures": 0} or len(gate.calls) != 1:
        problems.append("stats after 8 concurrent gets and one hit: %r" % (cache.stats(),))


@scenario("single-load-per-key")
def expired_stampede(problems):
    clock = Clock()
    gate = Gate()
    gate.release.set()
    cache = TTLCache(gate, 10, clock=clock)
    cache.get("k")
    gate.release.clear(); gate.entered.clear()
    clock.advance(25)
    slot, threads = {}, []
    threads.append(spawn(cache, "k", slot, "t0"))
    gate.entered.wait(JOIN)
    for i in range(1, 6):
        threads.append(spawn(cache, "k", slot, "t%d" % i))
        settle(threads[-1])
    gate.release.set()
    finish(threads, problems, "expired stampede")
    if len(gate.calls) != 2:
        problems.append("6 concurrent gets for an expired key made %d loader calls in total (want 1 first load + 1 refresh)" % len(gate.calls))
    elif sorted(str(slot.get("t%d" % i)) for i in range(6)) != ["('ok', 'k#2')"] * 6:
        problems.append("waiters did not all receive the refreshed value: %r" % (slot,))


@scenario("single-load-per-key")
def many_keys_each_once(problems):
    gate = Gate()
    cache = TTLCache(gate, 10, clock=Clock())
    slot, threads = {}, []
    gate.release.set()
    for key in ("a", "b"):
        for i in range(3):
            threads.append(spawn(cache, key, slot, "%s%d" % (key, i)))
    finish(threads, problems, "two keys")
    if sorted(gate.calls) != ["a", "b"]:
        problems.append("two keys with three concurrent gets each made loader calls %r" % (sorted(gate.calls),))


@scenario("exceptions-reach-waiters-then-retry")
def failure_reaches_everyone(problems):
    boom = ValueError("boom")
    gate = Gate(error=boom)
    cache = TTLCache(gate, 10, clock=Clock())
    slot, threads = {}, []
    threads.append(spawn(cache, "k", slot, "t0"))
    gate.entered.wait(JOIN)
    for i in range(1, 4):
        threads.append(spawn(cache, "k", slot, "t%d" % i))
        settle(threads[-1])
    gate.release.set()
    finish(threads, problems, "failed load")
    outcomes = [slot.get("t%d" % i) for i in range(4)]
    if any(o is None or o[0] != "err" or o[1] is not boom for o in outcomes):
        problems.append("every get that shared the failed load must raise the loader's own exception object, got %r" % (outcomes,))
    if len(gate.calls) != 1:
        problems.append("waiters retried the loader themselves: %d loader calls for one failed load" % len(gate.calls))
    if cache.stats() != {"hits": 0, "misses": 4, "loads": 1, "failures": 1}:
        problems.append("stats after one failed load shared by 4 gets: %r" % (cache.stats(),))
    gate.error = None
    gate.entered.clear()
    again = run_in_thread(lambda: cache.get("k"), problems, "get after a failed load")
    if again is not None and again.get("value") != "k#2":
        problems.append("a get after a failed load did not retry (got %r, loader calls %d)" % (again, len(gate.calls)))
    if cache.get("k") != "k#2" or len(gate.calls) != 2:
        problems.append("the value of the retry was not stored")


@scenario("exceptions-reach-waiters-then-retry")
def failure_of_a_refresh_and_other_exception_types(problems):
    clock = Clock()
    plan = ["first", KeyError("gone"), "third"]
    calls = []

    def load(key):
        calls.append(key)
        step = plan[len(calls) - 1]
        if isinstance(step, Exception):
            raise step
        return step
    cache = TTLCache(load, 10, clock=clock)
    cache.get("k")
    clock.advance(10)
    try:
        cache.get("k")
        problems.append("a failing refresh returned a value instead of raising")
    except KeyError as exc:
        if exc is not plan[1]:
            problems.append("the exception was replaced by %r" % (exc,))
    except BaseException as exc:
        problems.append("a failing refresh raised %r instead of the loader's KeyError" % (exc,))
    if cache.get("k") != "third" or len(calls) != 3:
        problems.append("after a failed refresh the next get did not reload (calls %d)" % len(calls))


@scenario("unrelated-keys-do-not-block")
def loads_overlap(problems):
    barrier = threading.Barrier(2, timeout=JOIN)
    broken = []

    def load(key):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            broken.append(key)
        return key.upper()
    cache = TTLCache(load, 10, clock=Clock())
    slot = {}
    threads = [spawn(cache, "a", slot, "a"), spawn(cache, "b", slot, "b")]
    finish(threads, problems, "two loads")
    if broken:
        problems.append("loads for different keys cannot run at the same time: one waited for the other for %ss" % JOIN)


@scenario("unrelated-keys-do-not-block")
def slow_load_blocks_nothing_else(problems):
    clock = Clock()
    gate = Gate()
    fast = fast_loader()

    def load(key):
        return gate(key) if key == "slow" else fast(key)
    cache = TTLCache(load, 10, clock=clock)
    cache.get("warm")
    slot = {}
    owner = spawn(cache, "slow", slot, "owner")
    gate.entered.wait(JOIN)
    box = run_in_thread(lambda: cache.get("warm"), problems, "get of a cached key during a slow load")
    if box is not None and box.get("value") != "warm#1":
        problems.append("get of a cached key during a slow load returned %r" % (box,))
    box = run_in_thread(lambda: cache.get("cold"), problems, "get of an uncached key during a slow load")
    if box is not None and box.get("value") != "cold#2":
        problems.append("get of an uncached key during a slow load returned %r" % (box,))
    run_in_thread(lambda: cache.invalidate("warm"), problems, "invalidate during a slow load")
    run_in_thread(lambda: cache.invalidate("slow"), problems, "invalidate of the loading key")
    run_in_thread(cache.stats, problems, "stats during a slow load")
    gate.release.set()
    finish([owner], problems, "slow load")


@scenario("reentrant-loads-handled")
def nested_get_of_another_key(problems):
    holder = {}

    def load(key):
        if key == "outer":
            return "outer(" + holder["cache"].get("inner") + ")"
        return "inner-value"
    cache = holder["cache"] = TTLCache(load, 10, clock=Clock())
    box = run_in_thread(lambda: cache.get("outer"), problems, "a loader that calls get for another key")
    if box is not None and box.get("value") != "outer(inner-value)":
        problems.append("nested get returned %r" % (box,))
    if cache.stats()["loads"] != 2:
        problems.append("nested loads were not both counted: %r" % (cache.stats(),))


@scenario("reentrant-loads-handled")
def recursive_get_of_the_same_key(problems):
    holder, state = {}, {"recurse": True}

    def load(key):
        if state["recurse"]:
            return holder["cache"].get(key)
        return "fine"
    cache = holder["cache"] = TTLCache(load, 10, clock=Clock())
    box = run_in_thread(lambda: cache.get("k"), problems, "a loader that calls get for its own key", timeout=4, expect_error=True)
    if box is not None and not isinstance(box.get("error"), RuntimeError):
        problems.append("a recursive get must raise RuntimeError out of the outer get, got %r" % (box,))
    state["recurse"] = False
    box = run_in_thread(lambda: cache.get("k"), problems, "get after a rejected recursive load")
    if box is not None and box.get("value") != "fine":
        problems.append("the key stayed poisoned after a recursive load: %r" % (box,))


# ---- v3 scenarios -------------------------------------------------------------------------------------------

def X(**kw):
    base = dict(hits=0, misses=0, loads=0, failures=0, evictions=0, stale_served=0, timeouts=0, deadlocks=0)
    base.update(kw)
    return base


def ext(cache):
    return cache.stats(extended=True)


def check_ext(problems, cache, want, what):
    got = ext(cache)
    if got != want:
        problems.append("%s: extended stats %r, wanted %r" % (what, got, want))


def err_of(slot, name):
    got = slot.get(name)
    return got[1] if got is not None and got[0] == "err" else None


def raises(fn, exc_type):
    try:
        fn()
    except exc_type:
        return True
    except BaseException:
        return False
    return False


@scenario("bounded-lru-eviction")
def size_validation_and_len(problems):
    for bad in (0, -1):
        if not raises(lambda: TTLCache(lambda k: 1, 10, clock=Clock(), max_size=bad), ValueError):
            problems.append("max_size=%r did not raise ValueError" % bad)
    load = fast_loader()
    cache = TTLCache(load, 10, clock=Clock())
    for key in "abcdef":
        cache.get(key)
    if len(cache) != 6 or ext(cache)["evictions"] != 0:
        problems.append("without max_size nothing may be evicted: len %d, %r" % (len(cache), ext(cache)))
    cache = TTLCache(load, 10, clock=Clock(), max_size=1)
    cache.get("a"); cache.get("b")
    if len(cache) != 1:
        problems.append("len(cache) is %d with max_size=1 after two loads" % len(cache))


@scenario("bounded-lru-eviction")
def lru_order(problems):
    load = fast_loader()
    cache = TTLCache(load, 100, clock=Clock(), max_size=3)
    for key in "abc":
        cache.get(key)
    cache.get("a")              # a is used again: least recently used order is b, c, a
    cache.get("d")              # stores d, evicts b
    cache.get("a"); cache.get("c")   # order is d, a, c
    cache.get("b")              # stores b, evicts d
    if load.calls != list("abcdb"):
        problems.append("loader calls %r, wanted %r (least recently used entry must be evicted, a hit is a use)" % (load.calls, list("abcdb")))
    if len(cache) != 3:
        problems.append("len(cache) is %d, wanted 3" % len(cache))
    check_ext(problems, cache, X(hits=3, misses=5, loads=5, evictions=2), "after the first sequence")
    cache.get("a"); cache.get("c"); cache.get("b")   # all three are stored: hits
    cache.get("d")              # a is the least recently used: evicted
    if load.calls != list("abcdbd"):
        problems.append("loader calls %r after the second sequence, wanted %r" % (load.calls, list("abcdbd")))
    check_ext(problems, cache, X(hits=6, misses=6, loads=6, evictions=3), "after the second sequence")


@scenario("bounded-lru-eviction")
def expired_entries_count_and_replacing_does_not_grow(problems):
    clock, load = Clock(), fast_loader()
    cache = TTLCache(load, 10, clock=clock, max_size=2)
    cache.get("a"); cache.get("b")
    clock.advance(10)           # both expired, both still stored
    cache.get("a")              # replaces the expired a: nothing is evicted; order is b, a
    if len(cache) != 2 or ext(cache)["evictions"] != 0:
        problems.append("replacing an expired entry must not evict anything: len %d, %r" % (len(cache), ext(cache)))
    cache.get("c")              # stores c; the expired b is the least recently used and goes
    cache.get("b")              # b was evicted so it loads again, and evicts a
    if load.calls != list("abacb"):
        problems.append("loader calls %r, wanted %r" % (load.calls, list("abacb")))
    check_ext(problems, cache, X(misses=5, loads=5, evictions=2), "expired entries")


@scenario("bounded-lru-eviction")
def in_flight_key_is_never_evicted(problems):
    clock, fast, gate, state = Clock(), fast_loader(), Gate(value="A-refreshed"), {"gate": False}

    def load(key):
        return gate(key) if key == "a" and state["gate"] else fast(key)
    cache = TTLCache(load, 10, clock=clock, max_size=2)
    cache.get("a"); cache.get("b")
    clock.advance(10)           # a and b are expired; a is the older entry
    state["gate"] = True
    slot = {}
    owner = spawn(cache, "a", slot, "owner")
    gate.entered.wait(JOIN)
    waiter = spawn(cache, "a", slot, "waiter")
    settle(waiter)
    box = run_in_thread(lambda: cache.get("c"), problems, "get of a new key while the refresh of a is in flight")
    if box is not None and box.get("value") != "c#3":
        problems.append("get of c returned %r" % (box,))
    if len(cache) != 2 or ext(cache)["evictions"] != 1:
        problems.append("after storing c, a (in flight, oldest) must stay and b must be evicted: len %d, %r" % (len(cache), ext(cache)))
    box = run_in_thread(lambda: cache.get("d"), problems, "second get of a new key while the refresh of a is in flight")
    if len(cache) != 2 or ext(cache)["evictions"] != 2:
        problems.append("after storing d, a must stay and c must be evicted: len %d, %r" % (len(cache), ext(cache)))
    if "owner" in slot or "waiter" in slot:
        problems.append("eviction ended the load in flight: %r" % (slot,))
    gate.release.set()
    finish([owner, waiter], problems, "refresh with evictions around it")
    if not (is_ok(slot, "owner", "A-refreshed") and is_ok(slot, "waiter", "A-refreshed")):
        problems.append("the owner and the waiter of the refresh must both get its value: %r" % (slot,))
    if len(gate.calls) != 1:
        problems.append("evictions made the refresh run %d times" % len(gate.calls))
    if cache.get("a") != "A-refreshed" or cache.get("d") != "d#4" or len(cache) != 2:
        problems.append("after the refresh the cache must hold a (new value) and d: len %d" % len(cache))
    check_ext(problems, cache, X(hits=2, misses=6, loads=5, evictions=2), "refresh with evictions around it")


@scenario("bounded-lru-eviction")
def worked_example_new_entry_is_evicted_at_once(problems):
    clock, fast, gate, state = Clock(), fast_loader(), Gate(value="A-refreshed"), {"gate": False}

    def load(key):
        return gate(key) if key == "a" and state["gate"] else fast(key)
    cache = TTLCache(load, 10, clock=clock, max_size=1)
    cache.get("a")
    clock.advance(10)
    state["gate"] = True
    slot = {}
    owner = spawn(cache, "a", slot, "owner")
    gate.entered.wait(JOIN)
    box = run_in_thread(lambda: cache.get("c"), problems, "get of c while the refresh of a is in flight")
    if box is not None and box.get("value") != "c#2":
        problems.append("get of c returned %r instead of its loaded value" % (box,))
    if len(cache) != 1 or ext(cache)["evictions"] != 1:
        problems.append("c must be evicted at once, the old a must stay: len %d, %r" % (len(cache), ext(cache)))
    gate.release.set()
    finish([owner], problems, "refresh of a")
    if cache.get("a") != "A-refreshed":
        problems.append("the old a was not replaced by the refresh")
    cache.get("c")              # c is not stored, so this loads again; the cache then drops a
    cache.get("c")              # and now c is the only entry: a hit
    if fast.calls != ["a", "c", "c"]:
        problems.append("fast loader calls %r, wanted a, c, c" % (fast.calls,))
    check_ext(problems, cache, X(hits=2, misses=4, loads=4, evictions=2), "worked example")


@scenario("waiter-timeout")
def waiter_times_out_without_touching_the_load(problems):
    gate = Gate()
    cache = TTLCache(gate, 10, clock=Clock())
    slot = {}
    owner = spawn(cache, "k", slot, "owner")
    gate.entered.wait(JOIN)
    plain = spawn(cache, "k", slot, "plain")
    settle(plain)
    limited = spawn(cache, "k", slot, "limited", timeout=0.25)
    limited.join(JOIN)
    if limited.is_alive():
        problems.append("a waiter with timeout=0.25 was still blocked after %ss" % JOIN)
    elif not isinstance(err_of(slot, "limited"), TimeoutError):
        problems.append("a waiter that timed out must raise TimeoutError, got %r" % (slot.get("limited"),))
    if "owner" in slot or "plain" in slot:
        problems.append("the timeout of one waiter ended the load or released the other waiter: %r" % (slot,))
    later = spawn(cache, "k", slot, "later")   # a call that starts after the timeout joins the same load
    settle(later)
    if len(gate.calls) != 1:
        problems.append("a call after the timeout started a second load (%d loader calls)" % len(gate.calls))
    gate.release.set()
    finish([owner, plain, later], problems, "load after a waiter timed out")
    if not (is_ok(slot, "owner", "k#1") and is_ok(slot, "plain", "k#1") and is_ok(slot, "later", "k#1")):
        problems.append("owner and the other waiters must still get the value: %r" % (slot,))
    if cache.get("k") != "k#1" or len(gate.calls) != 1:
        problems.append("the result was not stored or the loader ran again (%d calls)" % len(gate.calls))
    check_ext(problems, cache, X(hits=1, misses=4, loads=1, timeouts=1), "waiter timeout")


@scenario("waiter-timeout")
def timeout_zero_and_the_owner_is_not_limited(problems):
    gate = Gate()
    cache = TTLCache(gate, 10, clock=Clock())
    slot = {}
    owner = spawn(cache, "k", slot, "owner", timeout=0.02)
    gate.entered.wait(JOIN)
    settle(owner)               # parked for at least 120 ms, far longer than its timeout
    if "owner" in slot:
        problems.append("the call that runs the loader was limited by its timeout: %r" % (slot["owner"],))
    box = run_in_thread(lambda: cache.get("k", timeout=0), problems, "timeout=0 while the load is in flight", expect_error=True)
    if box is not None and not isinstance(box.get("error"), TimeoutError):
        problems.append("timeout=0 with a load in flight must raise TimeoutError at once, got %r" % (box,))
    gate.release.set()
    finish([owner], problems, "load of the owner")
    if not is_ok(slot, "owner", "k#1"):
        problems.append("the owner got %r" % (slot.get("owner"),))
    check_ext(problems, cache, X(misses=2, loads=1, timeouts=1), "timeout=0 beside an owner")
    load = fast_loader()
    cache = TTLCache(load, 10, clock=Clock())
    if cache.get("x", timeout=0) != "x#1" or cache.get("x", timeout=0) != "x#1" or len(load.calls) != 1:
        problems.append("timeout=0 must not stop a call from loading a missing key or from hitting a valid one")
    check_ext(problems, cache, X(hits=1, misses=1, loads=1), "timeout=0 without a load in flight")


@scenario("waiter-timeout")
def negative_timeout_is_rejected_and_not_counted(problems):
    load = fast_loader()
    cache = TTLCache(load, 10, clock=Clock())
    if not raises(lambda: cache.get("k", timeout=-0.5), ValueError):
        problems.append("a negative timeout must raise ValueError")
    if load.calls or ext(cache) != X():
        problems.append("a call rejected for its timeout must not load or be counted: %r, %r" % (load.calls, ext(cache)))
    if cache.get("k", timeout=5) != "k#1":
        problems.append("a get with a timeout does not return the loaded value")


@scenario("waiter-timeout")
def timed_out_waiter_is_not_part_of_a_later_failure(problems):
    boom = ValueError("boom")
    gate = Gate(error=boom)
    cache = TTLCache(gate, 10, clock=Clock())
    slot = {}
    owner = spawn(cache, "k", slot, "owner")
    gate.entered.wait(JOIN)
    limited = spawn(cache, "k", slot, "limited", timeout=0.25)
    limited.join(JOIN)
    if not isinstance(err_of(slot, "limited"), TimeoutError):
        problems.append("the limited waiter got %r instead of TimeoutError" % (slot.get("limited"),))
    gate.release.set()
    finish([owner], problems, "failing load")
    if err_of(slot, "owner") is not boom:
        problems.append("the owner must raise the loader's exception, got %r" % (slot.get("owner"),))
    check_ext(problems, cache, X(misses=2, loads=1, failures=1, timeouts=1), "timeout, then failure")
    gate.error = None
    if cache.get("k") != "k#2":
        problems.append("the get after the failed load did not retry")
    check_ext(problems, cache, X(misses=3, loads=2, failures=1, timeouts=1), "retry after timeout and failure")


@scenario("waiter-timeout")
def timeout_is_never_replaced_by_a_stale_value(problems):
    clock = Clock()
    gate = Gate(value="k-first")
    gate.release.set()
    cache = TTLCache(gate, 10, clock=clock, stale_grace=5)
    cache.get("k")
    gate.release.clear(); gate.entered.clear()
    gate.value, gate.error = None, ValueError("boom")
    clock.advance(12)           # stale
    slot = {}
    owner = spawn(cache, "k", slot, "owner")
    gate.entered.wait(JOIN)
    plain = spawn(cache, "k", slot, "plain")
    settle(plain)
    limited = spawn(cache, "k", slot, "limited", timeout=0.25)
    limited.join(JOIN)
    if not isinstance(err_of(slot, "limited"), TimeoutError):
        problems.append("a stale entry must not replace a TimeoutError, got %r" % (slot.get("limited"),))
    gate.release.set()
    finish([owner, plain], problems, "failing refresh")
    if not (is_ok(slot, "owner", "k-first") and is_ok(slot, "plain", "k-first")):
        problems.append("the owner and the waiter that stayed must get the stale value: %r" % (slot,))
    check_ext(problems, cache, X(misses=4, loads=2, failures=1, stale_served=2, timeouts=1), "timeout beside a stale serve")


@scenario("stale-while-error")
def stale_serving_and_its_boundaries(problems):
    clock = Clock()
    errors = [ValueError("e1"), ValueError("e2"), ValueError("e3")]
    plan = ["v1"] + errors + ["v5"]
    calls = []

    def load(key):
        calls.append(key)
        step = plan[len(calls) - 1]
        if isinstance(step, Exception):
            raise step
        return step
    cache = TTLCache(load, 10, clock=clock, stale_grace=5)
    cache.get("k")
    clock.now = 12.0
    first = cache.get("k")
    clock.now = 14.999
    second = cache.get("k")
    if first != "v1" or second != "v1":
        problems.append("a failing load inside the grace period must serve the stale value, got %r and %r" % (first, second))
    clock.now = 15.0
    try:
        got = cache.get("k")
        problems.append("an entry exactly ttl + stale_grace old is not stale; get returned %r" % (got,))
    except ValueError as exc:
        if exc is not errors[2]:
            problems.append("wrong exception object %r" % (exc,))
    except BaseException as exc:
        problems.append("raised %r instead of the loader's exception" % (exc,))
    if cache.get("k") != "v5" or cache.get("k") != "v5":
        problems.append("a load after the failures must be stored and served")
    check_ext(problems, cache, X(hits=1, misses=5, loads=5, failures=3, stale_served=2), "stale boundaries")


def load_fail_once():
    state = {"n": 0}

    def load(key):
        state["n"] += 1
        if state["n"] > 1:
            raise ValueError("later")
        return "v"
    return load


@scenario("stale-while-error")
def without_stale_grace_the_failure_is_raised(problems):
    clock = Clock()
    cache = TTLCache(load_fail_once(), 10, clock=clock)
    cache.get("k")
    clock.advance(12)
    if not raises(lambda: cache.get("k"), ValueError):
        problems.append("without stale_grace a failing refresh must raise the loader's exception")
    check_ext(problems, cache, X(misses=2, loads=2, failures=1), "no stale_grace")


@scenario("stale-while-error")
def stale_value_reaches_every_call_that_shared_the_load(problems):
    clock = Clock()
    gate = Gate()
    gate.release.set()
    cache = TTLCache(gate, 10, clock=clock, stale_grace=5)
    cache.get("k")
    gate.release.clear(); gate.entered.clear()
    gate.error = ValueError("boom")
    clock.advance(12)
    slot, threads = {}, []
    threads.append(spawn(cache, "k", slot, "t0"))
    gate.entered.wait(JOIN)
    for i in range(1, 4):
        threads.append(spawn(cache, "k", slot, "t%d" % i))
        settle(threads[-1])
    gate.release.set()
    finish(threads, problems, "failing refresh")
    got = [slot.get("t%d" % i) for i in range(4)]
    if got != [("ok", "k#1")] * 4:
        problems.append("owner and waiters of a failed refresh must all get the stale value: %r" % (got,))
    if len(gate.calls) != 2:
        problems.append("waiters retried the loader: %d calls" % len(gate.calls))
    check_ext(problems, cache, X(misses=5, loads=2, failures=1, stale_served=4), "stale value shared by 4 calls")
    gate.error = None
    gate.release.set()
    if cache.get("k") != "k#3" or cache.get("k") != "k#3":
        problems.append("the stale entry must not count as refreshed: the next get must load again and store the result")


@scenario("stale-while-error")
def entry_removed_before_the_failure_means_no_stale_value(problems):
    for how in ("invalidate", "invalidate_all"):
        clock = Clock()
        boom = ValueError("boom")
        gate = Gate()
        gate.release.set()
        cache = TTLCache(gate, 10, clock=clock, stale_grace=5)
        cache.get("k")
        gate.release.clear(); gate.entered.clear()
        gate.error = boom
        clock.advance(12)
        slot = {}
        owner = spawn(cache, "k", slot, "owner")
        gate.entered.wait(JOIN)
        waiter = spawn(cache, "k", slot, "waiter")
        settle(waiter)
        if how == "invalidate":
            run_in_thread(lambda: cache.invalidate("k"), problems, "invalidate during a refresh")
        else:
            box = run_in_thread(cache.invalidate_all, problems, "invalidate_all during a refresh")
            if box is not None and box.get("value") != 1:
                problems.append("invalidate_all returned %r, wanted 1 (the expired entry)" % (box,))
        gate.release.set()
        finish([owner, waiter], problems, "failing refresh after " + how)
        if err_of(slot, "owner") is not boom or err_of(slot, "waiter") is not boom:
            problems.append("after %s removed the entry, the owner and the waiter must raise the loader's exception: %r" % (how, slot))
        check_ext(problems, cache, X(misses=3, loads=2, failures=1), "failure after " + how)
        if len(cache) != 0:
            problems.append("a failed load must store nothing (len %d)" % len(cache))


@scenario("stale-while-error")
def rejected_calls_never_get_a_stale_value(problems):
    clock, holder, state = Clock(), {}, {"recurse": False, "inner": None}

    def load(key):
        if state["recurse"]:
            try:
                holder["cache"].get(key)
            except BaseException as exc:
                state["inner"] = exc
                raise
        return "v1"
    cache = holder["cache"] = TTLCache(load, 10, clock=clock, stale_grace=5)
    cache.get("k")
    clock.advance(12)
    state["recurse"] = True
    box = run_in_thread(lambda: cache.get("k"), problems, "get with a recursive loader and a stale entry")
    if type(state["inner"]) is not RuntimeError:
        problems.append("the recursive inner get must raise RuntimeError itself, even with a stale entry, got %r" % (state["inner"],))
    if box is not None and box.get("value") != "v1":
        problems.append("the outer get, whose load failed, must get the stale value, got %r" % (box,))
    check_ext(problems, cache, X(misses=3, loads=2, failures=1, stale_served=1), "recursion beside a stale entry")


@scenario("stale-while-error")
def serving_a_stale_value_is_not_a_use(problems):
    clock, state, calls = Clock(), {"fail": False}, []

    def load(key):
        calls.append(key)
        if state["fail"] and key == "a":
            raise ValueError("a is down")
        return "%s#%d" % (key, len(calls))
    cache = TTLCache(load, 10, clock=clock, max_size=2, stale_grace=5)
    cache.get("a")
    clock.advance(6)
    cache.get("b")
    clock.advance(6)            # a is 12 old (stale), b is 6 old (valid)
    state["fail"] = True
    if cache.get("a") != "a#1":
        problems.append("the failed refresh of a must serve the stale value")
    state["fail"] = False
    cache.get("c")              # a is still the least recently used entry: it is evicted
    if cache.get("b") != "b#2" or calls != ["a", "b", "a", "c"]:
        problems.append("after c is stored b must still be cached and a evicted (calls %r)" % (calls,))
    if cache.get("a") != "a#5":
        problems.append("a was not evicted although serving it stale is not a use")
    check_ext(problems, cache, X(hits=1, misses=5, loads=5, failures=1, evictions=2, stale_served=1), "stale is not a use")


@scenario("stale-while-error")
def stale_grace_validation(problems):
    for bad in (0, -1):
        if not raises(lambda: TTLCache(lambda k: 1, 10, clock=Clock(), stale_grace=bad), ValueError):
            problems.append("stale_grace=%r did not raise ValueError" % bad)
    TTLCache(lambda k: 1, 10, clock=Clock(), stale_grace=0.5)
    TTLCache(lambda k: 1, 10, clock=Clock(), stale_grace=None)


def cycle_run(n, middle_timeout, last_timeout, problems, what):
    """n threads, thread i loads key K<i> and its loader gets K<i+1>; the last one gets K0 once the others wait."""
    entered = [threading.Event() for _ in range(n)]
    go, holder, mode = threading.Event(), {}, {"cycle": True}

    def load(key):
        if not mode["cycle"]:
            return "plain-" + key
        i = int(key[1:])
        entered[i].set()
        if i == n - 1:
            go.wait(JOIN)
            return holder["cache"].get("K0", timeout=last_timeout)
        for event in entered:
            event.wait(JOIN)
        return holder["cache"].get("K%d" % (i + 1), timeout=middle_timeout)
    cache = holder["cache"] = TTLCache(load, 10, clock=Clock())
    slot = {}
    threads = [spawn(cache, "K%d" % i, slot, "t%d" % i) for i in range(n)]
    for event in entered:
        event.wait(JOIN)
    for thread in threads[:-1]:
        settle(thread)
    go.set()
    for thread in threads:
        thread.join(5)
        if thread.is_alive():
            problems.append("%s: thread %s is deadlocked: the cycle was not detected" % (what, thread.name))
    if any(thread.is_alive() for thread in threads):
        return cache, None, None
    snap = ext(cache)
    errors = [err_of(slot, "t%d" % i) for i in range(n)]
    if any(e is None for e in errors):
        problems.append("%s: every get in the cycle must raise DeadlockError, got %r" % (what, slot))
        return cache, None, snap
    if any(type(e) is not ttlcache.DeadlockError for e in errors):
        problems.append("%s: wanted ttlcache.DeadlockError from every get in the cycle, got %r" % (what, errors))
    elif any(e is not errors[0] for e in errors):
        problems.append("%s: the calls in the cycle must share the one exception object" % what)
    if not isinstance(errors[0], RuntimeError):
        problems.append("%s: DeadlockError must be a subclass of RuntimeError" % what)
    mode["cycle"] = False
    for i in range(n):
        box = run_in_thread(lambda i=i: cache.get("K%d" % i), problems, "%s: get of K%d after the deadlock" % (what, i))
        if box is not None and box.get("value") != "plain-K%d" % i:
            problems.append("%s: K%d stayed poisoned after the deadlock: %r" % (what, i, box))
    return cache, errors, snap


@scenario("deadlock-detection")
def two_threads_wait_for_each_other(problems):
    cache, errors, snap = cycle_run(2, None, None, problems, "two-cycle")
    if snap is not None and snap != X(misses=4, loads=2, failures=2, deadlocks=1):
        problems.append("two-cycle: stats %r (4 gets, 2 loads, 2 failures, 1 deadlock)" % (snap,))


@scenario("deadlock-detection")
def three_threads_in_a_ring(problems):
    cache, errors, snap = cycle_run(3, None, None, problems, "three-cycle")
    if snap is not None and snap != X(misses=6, loads=3, failures=3, deadlocks=1):
        problems.append("three-cycle: stats %r (6 gets, 3 loads, 3 failures, 1 deadlock)" % (snap,))


@scenario("deadlock-detection")
def a_cycle_is_a_cycle_whatever_the_timeouts(problems):
    cache, errors, snap = cycle_run(2, 60, 0, problems, "two-cycle with timeouts")
    if snap is not None and snap != X(misses=4, loads=2, failures=2, deadlocks=1):
        problems.append("a cycle must raise DeadlockError even when the closing get has timeout=0, and count no timeout: %r" % (snap,))


@scenario("deadlock-detection")
def waiting_without_a_cycle_is_normal(problems):
    entered_b, release_b = threading.Event(), threading.Event()
    holder = {}

    def load(key):
        if key == "A":
            entered_b.wait(JOIN)
            return "A+" + holder["cache"].get("B")
        if key == "B":
            entered_b.set()
            release_b.wait(JOIN)
            return "B+" + holder["cache"].get("C")
        return "C"
    cache = holder["cache"] = TTLCache(load, 10, clock=Clock())
    slot = {}
    tb = spawn(cache, "B", slot, "tb")
    entered_b.wait(JOIN)
    ta = spawn(cache, "A", slot, "ta")
    settle(ta)
    release_b.set()
    finish([ta, tb], problems, "chain without a cycle")
    if slot.get("ta") != ("ok", "A+B+C") or slot.get("tb") != ("ok", "B+C"):
        problems.append("a wait that completes no cycle must not raise: %r" % (slot,))
    check_ext(problems, cache, X(misses=4, loads=3), "chain without a cycle")


@scenario("deadlock-detection")
def a_finished_wait_leaves_no_trace(problems):
    ev = {name: threading.Event() for name in ("b_entered", "b_release", "x1", "t1", "f_entered", "f_release", "start_e")}
    holder, slot = {}, {}

    def load(key):
        if key == "A":
            ev["b_entered"].wait(JOIN)
            return "A+" + holder["cache"].get("B")
        if key == "B":
            ev["b_entered"].set()
            ev["b_release"].wait(JOIN)
            return "B"
        if key == "F":
            ev["f_entered"].set()
            ev["f_release"].wait(JOIN)
            return "F"
        return "E+" + holder["cache"].get("F")
    cache = holder["cache"] = TTLCache(load, 10, clock=Clock())

    def worker_x():
        try:
            slot["x1"] = ("ok", cache.get("A"))
            ev["x1"].set()
            slot["x2"] = ("ok", cache.get("F"))
        except BaseException as exc:
            slot["x2"] = ("err", exc)

    def worker_t():
        try:
            slot["t1"] = ("ok", cache.get("B"))
            ev["t1"].set()
            ev["start_e"].wait(JOIN)
            slot["t2"] = ("ok", cache.get("E"))
        except BaseException as exc:
            slot["t2"] = ("err", exc)
    tx = threading.Thread(target=worker_x, daemon=True, name="x")
    tt = threading.Thread(target=worker_t, daemon=True, name="t")
    tt.start()
    ev["b_entered"].wait(JOIN)   # the load of B is in flight in thread t
    tx.start()
    settle(tx)                   # x waits for B
    ev["b_release"].set()
    ev["x1"].wait(JOIN); ev["t1"].wait(JOIN)
    ev["f_entered"].wait(JOIN)   # x now runs the load of F and is not waiting for anything
    ev["start_e"].set()
    settle(tt)                   # t runs the load of E, whose loader waits for F, owned by x
    ev["f_release"].set()
    finish([tx, tt], problems, "second phase")
    if slot.get("x2") != ("ok", "F") or slot.get("t2") != ("ok", "E+F"):
        problems.append("a wait that finished earlier must not make a later wait look like a cycle: %r" % (slot,))
    if ext(cache)["deadlocks"] != 0:
        problems.append("a deadlock was reported where there was none: %r" % (ext(cache),))


@scenario("deadlock-detection")
def recursion_through_another_key_is_a_runtime_error(problems):
    holder = {}

    def load(key):
        return holder["cache"].get("B" if key == "A" else "A")
    cache = holder["cache"] = TTLCache(load, 10, clock=Clock())
    box = run_in_thread(lambda: cache.get("A"), problems, "A loads B, B gets A", timeout=5, expect_error=True)
    error = None if box is None else box.get("error")
    if type(error) is not RuntimeError:
        problems.append("a chain of nested loads in one thread that gets back to its first key raises RuntimeError itself, got %r" % (box,))
    check_ext(problems, cache, X(misses=3, loads=2, failures=2), "indirect recursion")


@scenario("invalidation-during-loads")
def invalidate_all_counts_and_resets(problems):
    clock, load = Clock(), fast_loader()
    cache = TTLCache(load, 10, clock=clock)
    cache.get("a"); cache.get("b")
    clock.advance(10)
    cache.get("c")
    if cache.invalidate_all() != 3 or len(cache) != 0:
        problems.append("invalidate_all must remove all 3 stored entries, expired ones included, and return 3")
    if cache.invalidate_all() != 0:
        problems.append("invalidate_all on an empty cache must return 0")
    if cache.invalidate("a") is not None:
        problems.append("invalidate must return None")
    check_ext(problems, cache, X(misses=3, loads=3), "invalidate_all changes no counter")
    if cache.get("a") != "a#4":
        problems.append("get after invalidate_all did not reload")


@scenario("invalidation-during-loads")
def invalidation_does_not_cancel_loads(problems):
    clock, fast = Clock(), fast_loader()
    gates = {"r": Gate(value="R2"), "s": Gate(value="S1")}
    state = {"gated": False}

    def load(key):
        return gates[key](key) if state["gated"] and key in gates else fast(key)
    cache = TTLCache(load, 10, clock=clock)
    cache.get("x"); cache.get("r")
    clock.advance(10)
    state["gated"] = True
    slot = {}
    owner_r = spawn(cache, "r", slot, "owner_r")
    gates["r"].entered.wait(JOIN)
    waiter_r = spawn(cache, "r", slot, "waiter_r")
    settle(waiter_r)
    owner_s = spawn(cache, "s", slot, "owner_s")
    gates["s"].entered.wait(JOIN)
    box = run_in_thread(cache.invalidate_all, problems, "invalidate_all during slow loads")
    if box is not None and box.get("value") != 2:
        problems.append("invalidate_all must count the two stored entries (x and the old r) and not the loads in flight, got %r" % (box,))
    run_in_thread(lambda: cache.invalidate("s"), problems, "invalidate of a key being loaded")
    if len(cache) != 0 or "owner_r" in slot or "waiter_r" in slot or "owner_s" in slot:
        problems.append("invalidation cancelled or finished a load in flight: len %d, %r" % (len(cache), slot))
    for gate in gates.values():
        gate.release.set()
    finish([owner_r, waiter_r, owner_s], problems, "loads after invalidation")
    if not (is_ok(slot, "owner_r", "R2") and is_ok(slot, "waiter_r", "R2") and is_ok(slot, "owner_s", "S1")):
        problems.append("the loads in flight must still deliver their results: %r" % (slot,))
    if len(cache) != 2 or cache.get("r") != "R2" or cache.get("s") != "S1":
        problems.append("a load whose key was invalidated meanwhile must still store its result (len %d)" % len(cache))
    if len(gates["r"].calls) != 1 or len(gates["s"].calls) != 1:
        problems.append("invalidation made a loader run again")
    check_ext(problems, cache, X(hits=2, misses=5, loads=4), "invalidation during loads")


@scenario("invalidation-during-loads")
def removed_entries_free_space_and_are_not_evictions(problems):
    load = fast_loader()
    cache = TTLCache(load, 10, clock=Clock(), max_size=2)
    cache.get("a"); cache.get("b")
    cache.invalidate("a")
    cache.get("c")              # a free slot: nothing is evicted
    if len(cache) != 2 or ext(cache)["evictions"] != 0:
        problems.append("a removed entry must free its slot: len %d, %r" % (len(cache), ext(cache)))
    cache.get("d")              # b is the least recently used
    if cache.get("c") != "c#3" or cache.get("b") != "b#5":
        problems.append("wrong entries were kept (loader calls %r)" % (load.calls,))
    cache.invalidate_all()
    cache.get("e"); cache.get("f")
    check_ext(problems, cache, X(hits=1, misses=7, loads=7, evictions=2), "free slots")
'''

DRIVER = r'''
name = sys.argv[1]
group, fn = SCENARIOS[name]
problems = []
try:
    fn(problems)
except BaseException as exc:
    problems.append("scenario crashed: %r" % (exc,))
print("@@RESULT " + json.dumps({"group": group, "problems": problems}))
sys.stdout.flush()
os._exit(0)
'''

SCENARIO_NAMES = [
    "basic_values", "basic_invalidate_and_stats", "boundary", "refresh_in_flight", "cold_stampede", "expired_stampede",
    "many_keys_each_once", "failure_reaches_everyone", "failure_of_a_refresh_and_other_exception_types", "loads_overlap",
    "slow_load_blocks_nothing_else", "nested_get_of_another_key", "recursive_get_of_the_same_key",
    "size_validation_and_len",
    "lru_order",
    "expired_entries_count_and_replacing_does_not_grow",
    "in_flight_key_is_never_evicted",
    "worked_example_new_entry_is_evicted_at_once",
    "waiter_times_out_without_touching_the_load",
    "timeout_zero_and_the_owner_is_not_limited",
    "negative_timeout_is_rejected_and_not_counted",
    "timed_out_waiter_is_not_part_of_a_later_failure",
    "timeout_is_never_replaced_by_a_stale_value",
    "stale_serving_and_its_boundaries",
    "without_stale_grace_the_failure_is_raised",
    "stale_value_reaches_every_call_that_shared_the_load",
    "entry_removed_before_the_failure_means_no_stale_value",
    "rejected_calls_never_get_a_stale_value",
    "serving_a_stale_value_is_not_a_use",
    "stale_grace_validation",
    "two_threads_wait_for_each_other",
    "three_threads_in_a_ring",
    "a_cycle_is_a_cycle_whatever_the_timeouts",
    "waiting_without_a_cycle_is_normal",
    "a_finished_wait_leaves_no_trace",
    "recursion_through_another_key_is_a_runtime_error",
    "invalidate_all_counts_and_resets",
    "invalidation_does_not_cancel_loads",
    "removed_entries_free_space_and_are_not_evictions",
]
GROUPS = [
    ("basic-contract", ""), ("single-load-per-key", ""), ("expired-value-never-served", ""),
    ("exceptions-reach-waiters-then-retry", ""), ("unrelated-keys-do-not-block", ""), ("reentrant-loads-handled", ""),
    ("bounded-lru-eviction", ""), ("waiter-timeout", ""), ("stale-while-error", ""), ("deadlock-detection", ""),
    ("invalidation-during-loads", ""),
]
SLEEPERS = {"sleep", "usleep"}


def library_files(ws):
    return sorted((ws / "ttlcache").rglob("*.py"))


def timing_tricks(ws):
    found = []
    for path in library_files(ws):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        rel = path.relative_to(ws).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
                if name in SLEEPERS:
                    found.append(f"{rel}:{node.lineno} calls {name}()")
            elif isinstance(node, ast.Import):
                found.extend(f"{rel}:{node.lineno} imports random" for a in node.names if a.name.split(".")[0] == "random")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top == "random":
                    found.append(f"{rel}:{node.lineno} imports random")
                if top in ("time", "asyncio") and any(a.name in SLEEPERS for a in node.names):
                    found.append(f"{rel}:{node.lineno} imports sleep")
    return found


def run_scenarios(ws):
    code = PRELUDE + SCENARIO_CODE + DRIVER
    outcome = {}
    for name in SCENARIO_NAMES:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp, "probe.py")
            probe.write_text(code)
            env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
            env.update({"PYTHONPATH": str(ws), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
            try:
                done = subprocess.run([sys.executable, str(probe), name], cwd=tmp, env=env, capture_output=True, text=True, timeout=90)
            except subprocess.TimeoutExpired:
                outcome[name] = (None, ["scenario did not finish in 90s"])
                continue
        parsed = None
        for line in reversed(done.stdout.splitlines()):
            if line.startswith("@@RESULT "):
                parsed = json.loads(line[len("@@RESULT "):])
        if parsed is None:
            outcome[name] = (None, ["scenario crashed: " + (done.stderr.strip().splitlines() or ["no output"])[-1][:300]])
        else:
            outcome[name] = (parsed["group"], parsed["problems"])
    return outcome


def visible_tests_pass(ws):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update({"PYTHONPATH": str(ws), "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        done = subprocess.run([sys.executable, "-m", "unittest"], cwd=ws, env=env, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, "python -m unittest did not finish in 180s"
    tail = (done.stderr.strip().splitlines() or [""])[-1]
    return done.returncode == 0, "python -m unittest passes" if done.returncode == 0 else "python -m unittest fails: " + tail


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    outside = [p for p in touched if not p.startswith(("ttlcache/", "tests/")) and p != "SUMMARY.md"]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")
    before_src = original("tests/test_cache.py")
    current = read_text(ws / "tests/test_cache.py")
    modified = ["file removed"] if current is None else changed_tests(before_src, current)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    tricks = timing_tricks(ws)
    g.add("no-sleep-or-polling", not tricks, "; ".join(tricks[:5]) if tricks else "ok")
    ok, detail = visible_tests_pass(ws)
    g.add("visible-tests-pass", ok, detail)

    outcome = run_scenarios(ws)
    per_group = {name: [] for name, _ in GROUPS}
    for scenario_name, (group, problems) in outcome.items():
        key = SCENARIO_GROUP[scenario_name]
        per_group[key].extend(f"[{scenario_name}] {p}" for p in problems)
    def report(name):
        problems = per_group[name]
        return not problems, "; ".join(problems[:4]) if problems else "ok"

    g.add("basic-contract", *report("basic-contract"))
    g.add("single-load-per-key", *report("single-load-per-key"))
    g.add("expired-value-never-served", *report("expired-value-never-served"))
    g.add("exceptions-reach-waiters-then-retry", *report("exceptions-reach-waiters-then-retry"))
    g.add("unrelated-keys-do-not-block", *report("unrelated-keys-do-not-block"))
    g.add("reentrant-loads-handled", *report("reentrant-loads-handled"))
    g.add("bounded-lru-eviction", *report("bounded-lru-eviction"))
    g.add("waiter-timeout", *report("waiter-timeout"))
    g.add("stale-while-error", *report("stale-while-error"))
    g.add("deadlock-detection", *report("deadlock-detection"))
    g.add("invalidation-during-loads", *report("invalidation-during-loads"))
    failing = sum(1 for name, _ in GROUPS if per_group[name])
    g.add("contract-mostly-right", failing <= 1, f"{failing} of {len(GROUPS)} contract groups fail", required=False)
    g.summary_checks(ws)


SCENARIO_GROUP = {
    "basic_values": "basic-contract", "basic_invalidate_and_stats": "basic-contract", "boundary": "expired-value-never-served",
    "refresh_in_flight": "expired-value-never-served", "cold_stampede": "single-load-per-key", "expired_stampede": "single-load-per-key",
    "many_keys_each_once": "single-load-per-key", "failure_reaches_everyone": "exceptions-reach-waiters-then-retry",
    "failure_of_a_refresh_and_other_exception_types": "exceptions-reach-waiters-then-retry", "loads_overlap": "unrelated-keys-do-not-block",
    "slow_load_blocks_nothing_else": "unrelated-keys-do-not-block", "nested_get_of_another_key": "reentrant-loads-handled",
    "recursive_get_of_the_same_key": "reentrant-loads-handled",
    "size_validation_and_len": "bounded-lru-eviction",
    "lru_order": "bounded-lru-eviction",
    "expired_entries_count_and_replacing_does_not_grow": "bounded-lru-eviction",
    "in_flight_key_is_never_evicted": "bounded-lru-eviction",
    "worked_example_new_entry_is_evicted_at_once": "bounded-lru-eviction",
    "waiter_times_out_without_touching_the_load": "waiter-timeout",
    "timeout_zero_and_the_owner_is_not_limited": "waiter-timeout",
    "negative_timeout_is_rejected_and_not_counted": "waiter-timeout",
    "timed_out_waiter_is_not_part_of_a_later_failure": "waiter-timeout",
    "timeout_is_never_replaced_by_a_stale_value": "waiter-timeout",
    "stale_serving_and_its_boundaries": "stale-while-error",
    "without_stale_grace_the_failure_is_raised": "stale-while-error",
    "stale_value_reaches_every_call_that_shared_the_load": "stale-while-error",
    "entry_removed_before_the_failure_means_no_stale_value": "stale-while-error",
    "rejected_calls_never_get_a_stale_value": "stale-while-error",
    "serving_a_stale_value_is_not_a_use": "stale-while-error",
    "stale_grace_validation": "stale-while-error",
    "two_threads_wait_for_each_other": "deadlock-detection",
    "three_threads_in_a_ring": "deadlock-detection",
    "a_cycle_is_a_cycle_whatever_the_timeouts": "deadlock-detection",
    "waiting_without_a_cycle_is_normal": "deadlock-detection",
    "a_finished_wait_leaves_no_trace": "deadlock-detection",
    "recursion_through_another_key_is_a_runtime_error": "deadlock-detection",
    "invalidate_all_counts_and_resets": "invalidation-during-loads",
    "invalidation_does_not_cancel_loads": "invalidation-during-loads",
    "removed_entries_free_space_and_are_not_evictions": "invalidation-during-loads",
}


if __name__ == "__main__":
    main(grade)
