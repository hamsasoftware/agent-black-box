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

    def __init__(self, error=None):
        self.calls = []
        self.error = error
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
        return "%s#%d" % (key, number)


def fast_loader():
    calls = []

    def load(key):
        calls.append(key)
        return "%s#%d" % (key, len(calls))
    load.calls = calls
    return load


def spawn(cache, key, slot, name):
    def run():
        try:
            slot[name] = ("ok", cache.get(key))
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
]
GROUPS = [
    ("basic-contract", ""), ("single-load-per-key", ""), ("expired-value-never-served", ""),
    ("exceptions-reach-waiters-then-retry", ""), ("unrelated-keys-do-not-block", ""), ("reentrant-loads-handled", ""),
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
}


if __name__ == "__main__":
    main(grade)
