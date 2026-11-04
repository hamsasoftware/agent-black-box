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


from datetime import datetime, timedelta, timezone
import random

NOW = "2026-03-20T12:00:00+00:00"


def snaps_of(*items):
    """Each item is an ISO stamp (id = the stamp), optionally 'stamp|tag1,tag2', or a tuple (id, stamp, tags)."""
    out = []
    for item in items:
        if isinstance(item, tuple):
            out.append([item[0], item[1], list(item[2]) if len(item) > 2 else []])
        elif "|" in item:
            stamp, tags = item.split("|")
            out.append([stamp, stamp, tags.split(",")])
        else:
            out.append([item, item, []])
    return out


def case(name, group, snapshots, policy, keep=None, now=NOW, error=None):
    return {"name": name, "group": group, "snaps": snaps_of(*snapshots), "policy": policy, "now": now, "keep": keep, "error": error}


Z = "+00:00"
HAND = [
    # --- core rules (ADR-0001) ---
    case("gaps-do-not-count", "core", ["2026-03-01T03:00" + Z, "2026-03-05T03:00" + Z, "2026-03-10T03:00" + Z],
         {"keep_daily": 2}, ["2026-03-10T03:00" + Z, "2026-03-05T03:00" + Z]),
    case("monthly", "core", ["2025-12-31T23:00" + Z, "2026-01-15T03:00" + Z, "2026-01-20T03:00" + Z, "2026-02-10T03:00" + Z, "2026-03-01T03:00" + Z],
         {"keep_monthly": 2}, ["2026-03-01T03:00" + Z, "2026-02-10T03:00" + Z]),
    case("yearly", "core", ["2023-06-01T03:00" + Z, "2024-05-01T03:00" + Z, "2024-09-01T03:00" + Z, "2025-02-01T03:00" + Z, "2026-01-05T03:00" + Z],
         {"keep_yearly": 2}, ["2026-01-05T03:00" + Z, "2025-02-01T03:00" + Z]),
    case("protected-not-counted", "core", ["2026-03-18T03:00" + Z + "|release", "2026-03-17T03:00" + Z, "2026-03-16T03:00" + Z, "2026-03-15T03:00" + Z],
         {"keep_daily": 2, "protect_tags": ["release"]}, ["2026-03-18T03:00" + Z, "2026-03-17T03:00" + Z, "2026-03-16T03:00" + Z]),
    case("protected-not-representative", "core", ["2026-03-18T20:00" + Z + "|release", "2026-03-18T05:00" + Z, "2026-03-17T05:00" + Z],
         {"keep_daily": 1, "protect_tags": ["release"]}, ["2026-03-18T20:00" + Z, "2026-03-18T05:00" + Z]),
    case("all-protected-day-is-no-bucket", "core", ["2026-03-19T03:00" + Z + "|keep-me", "2026-03-18T03:00" + Z, "2026-03-17T03:00" + Z, "2026-03-16T03:00" + Z],
         {"keep_daily": 2, "protect_tags": ["keep-me", "other"]}, ["2026-03-19T03:00" + Z, "2026-03-18T03:00" + Z, "2026-03-17T03:00" + Z]),
    case("protected-not-counted-by-keep-last", "core", ["2026-03-19T03:00" + Z + "|x", "2026-03-18T03:00" + Z, "2026-03-17T03:00" + Z],
         {"keep_last": 1, "protect_tags": ["x"]}, ["2026-03-19T03:00" + Z, "2026-03-18T03:00" + Z]),
    case("future-is-kept-and-not-counted", "core", ["2026-03-21T03:00" + Z, "2026-03-19T03:00" + Z, "2026-03-18T03:00" + Z],
         {"keep_last": 1}, ["2026-03-21T03:00" + Z, "2026-03-19T03:00" + Z]),
    case("taken-exactly-at-now-is-normal", "core", ["2026-03-20T12:00:00" + Z, "2026-03-19T03:00" + Z],
         {"keep_last": 1}, ["2026-03-20T12:00:00" + Z]),
    case("rules-are-independent", "core", ["2026-03-19T03:00" + Z, "2026-03-19T20:00" + Z, "2026-03-18T03:00" + Z],
         {"keep_last": 1, "keep_daily": 2}, ["2026-03-19T20:00" + Z, "2026-03-18T03:00" + Z]),
    case("weekly-and-monthly-union", "core", ["2026-03-18T03:00" + Z, "2026-03-10T03:00" + Z, "2026-03-03T03:00" + Z, "2026-02-25T03:00" + Z],
         {"keep_weekly": 2, "keep_monthly": 1}, ["2026-03-18T03:00" + Z, "2026-03-10T03:00" + Z]),
    case("ties-go-to-the-greater-id", "core", [("a", "2026-03-18T03:00" + Z), ("b", "2026-03-18T03:00" + Z), ("c", "2026-03-17T03:00" + Z)],
         {"keep_last": 1, "keep_daily": 1}, ["b"]),
    case("ties-in-a-bucket", "core", [("m", "2026-03-18T03:00" + Z), ("z", "2026-03-18T03:00" + Z), ("k", "2026-03-18T01:00" + Z)],
         {"keep_daily": 1}, ["z"]),
    case("all-rules-off-keeps-everything", "core", ["2026-03-01T03:00" + Z, "2026-03-02T03:00" + Z, "2025-01-02T03:00" + Z],
         {"keep_daily": 0, "keep_last": None, "protect_tags": ["x"]}, ["2026-03-01T03:00" + Z, "2026-03-02T03:00" + Z, "2025-01-02T03:00" + Z]),
    case("zero-is-off", "core", ["2026-03-19T03:00" + Z, "2026-03-18T03:00" + Z],
         {"keep_last": 0, "keep_daily": 1}, ["2026-03-19T03:00" + Z]),
    case("more-than-available", "core", ["2026-03-19T03:00" + Z, "2026-03-18T03:00" + Z],
         {"keep_daily": 10, "keep_weekly": 10}, ["2026-03-19T03:00" + Z, "2026-03-18T03:00" + Z]),
    case("instants-not-wall-clock", "core", [("a", "2026-03-18T01:00:00+05:00"), ("b", "2026-03-17T22:00:00+00:00"), ("c", "2026-03-16T10:00:00+00:00")],
         {"keep_daily": 1}, ["b"]),
    case("no-snapshots", "core", [], {"keep_last": 3, "keep_daily": 2}, []),
    case("naive-snapshot", "core", ["2026-03-18T03:00"], {"keep_last": 1}, error="ValueError"),
    case("naive-now", "core", ["2026-03-18T03:00" + Z], {"keep_last": 1}, now="2026-03-20T12:00:00", error="ValueError"),
    case("duplicate-ids", "core", [("d", "2026-03-18T03:00" + Z), ("d", "2026-03-17T03:00" + Z)], {"keep_last": 1}, error="ValueError"),
    # --- ISO weeks (ADR-0003 supersedes the Weeks section of ADR-0001) ---
    case("iso-sunday-starts-no-week", "iso", ["2026-03-08T03:00" + Z, "2026-03-09T03:00" + Z],
         {"keep_weekly": 2}, ["2026-03-08T03:00" + Z, "2026-03-09T03:00" + Z]),
    case("iso-saturday-and-sunday-share-a-week", "iso", ["2026-03-02T03:00" + Z, "2026-03-07T03:00" + Z, "2026-03-08T03:00" + Z, "2026-02-25T03:00" + Z],
         {"keep_weekly": 2}, ["2026-03-08T03:00" + Z, "2026-02-25T03:00" + Z]),
    case("iso-new-year-week-order", "iso", ["2025-12-28T03:00" + Z, "2025-12-29T03:00" + Z, "2025-12-31T03:00" + Z, "2026-01-04T03:00" + Z, "2026-01-05T03:00" + Z],
         {"keep_weekly": 2}, ["2026-01-05T03:00" + Z, "2026-01-04T03:00" + Z], now="2026-01-10T12:00:00" + Z),
    case("iso-new-year-three-weeks", "iso", ["2025-12-28T03:00" + Z, "2025-12-29T03:00" + Z, "2025-12-31T03:00" + Z, "2026-01-04T03:00" + Z, "2026-01-05T03:00" + Z],
         {"keep_weekly": 3}, ["2026-01-05T03:00" + Z, "2026-01-04T03:00" + Z, "2025-12-28T03:00" + Z], now="2026-01-10T12:00:00" + Z),
    case("iso-week-53", "iso", ["2020-12-23T03:00" + Z, "2020-12-30T03:00" + Z, "2021-01-01T03:00" + Z, "2021-01-03T03:00" + Z, "2021-01-04T03:00" + Z],
         {"keep_weekly": 2}, ["2021-01-04T03:00" + Z, "2021-01-03T03:00" + Z], now="2021-02-01T12:00:00" + Z),
    case("iso-year-only-for-weeks-yearly", "iso", ["2025-12-31T03:00" + Z, "2026-01-01T03:00" + Z],
         {"keep_yearly": 2}, ["2025-12-31T03:00" + Z, "2026-01-01T03:00" + Z]),
    case("iso-year-only-for-weeks-monthly", "iso", ["2025-12-31T03:00" + Z, "2026-01-01T03:00" + Z, "2025-11-30T03:00" + Z],
         {"keep_monthly": 2}, ["2025-12-31T03:00" + Z, "2026-01-01T03:00" + Z]),
    case("iso-monday-after-jan-first", "iso", ["2024-12-29T03:00" + Z, "2024-12-30T03:00" + Z, "2025-01-05T03:00" + Z, "2025-01-06T03:00" + Z],
         {"keep_weekly": 2}, ["2025-01-06T03:00" + Z, "2025-01-05T03:00" + Z], now="2025-02-01T12:00:00" + Z),
    # --- day boundary (ADR-0004 supersedes ADR-0002) ---
    case("offset-plus-two", "cutoff", ["2026-03-18T22:30" + Z, "2026-03-18T21:30" + Z],
         {"keep_daily": 2, "tz_offset_minutes": 120}, ["2026-03-18T22:30" + Z, "2026-03-18T21:30" + Z]),
    case("offset-minus-five", "cutoff", ["2026-03-19T04:30" + Z, "2026-03-18T10:00" + Z, "2026-03-19T05:30" + Z],
         {"keep_daily": 3, "tz_offset_minutes": -300}, ["2026-03-19T05:30" + Z, "2026-03-19T04:30" + Z]),
    case("day-starts-at-four", "cutoff", ["2026-03-19T03:30" + Z, "2026-03-18T10:00" + Z, "2026-03-19T04:00" + Z],
         {"keep_daily": 3, "day_start_hour": 4}, ["2026-03-19T04:00" + Z, "2026-03-19T03:30" + Z]),
    case("day-start-crosses-new-year-yearly-1", "cutoff", ["2026-01-01T03:30" + Z, "2026-01-01T05:00" + Z],
         {"keep_yearly": 1, "day_start_hour": 4}, ["2026-01-01T05:00" + Z], now="2026-02-01T12:00:00" + Z),
    case("day-start-crosses-new-year-yearly-2", "cutoff", ["2026-01-01T03:30" + Z, "2026-01-01T05:00" + Z],
         {"keep_yearly": 2, "day_start_hour": 4}, ["2026-01-01T05:00" + Z, "2026-01-01T03:30" + Z], now="2026-02-01T12:00:00" + Z),
    case("day-start-crosses-month", "cutoff", ["2026-03-01T02:00" + Z, "2026-03-01T06:00" + Z],
         {"keep_monthly": 2, "day_start_hour": 3}, ["2026-03-01T06:00" + Z, "2026-03-01T02:00" + Z]),
    case("day-start-weekly", "cutoff", ["2026-03-09T02:00" + Z, "2026-03-09T09:00" + Z],
         {"keep_weekly": 2, "day_start_hour": 3}, ["2026-03-09T09:00" + Z, "2026-03-09T02:00" + Z]),
    case("offset-and-hour-together", "cutoff", ["2026-03-10T00:29" + Z, "2026-03-10T00:30" + Z, "2026-03-09T20:00" + Z],
         {"keep_daily": 2, "tz_offset_minutes": 330, "day_start_hour": 6}, ["2026-03-10T00:30" + Z, "2026-03-10T00:29" + Z]),
    case("future-uses-the-real-instant", "cutoff", ["2026-03-20T03:00" + Z, "2026-03-19T03:00" + Z],
         {"keep_last": 1, "day_start_hour": 4}, ["2026-03-20T03:00" + Z, "2026-03-19T03:00" + Z], now="2026-03-20T02:00:00" + Z),
    case("keep-last-ignores-the-boundary", "cutoff", ["2026-03-19T03:30" + Z, "2026-03-19T04:30" + Z, "2026-03-18T10:00" + Z],
         {"keep_last": 2, "day_start_hour": 4}, ["2026-03-19T04:30" + Z, "2026-03-19T03:30" + Z]),
    case("offset-month-boundary", "cutoff", ["2026-03-01T00:30" + Z, "2026-03-01T01:30" + Z],
         {"keep_monthly": 2, "tz_offset_minutes": -60}, ["2026-03-01T01:30" + Z, "2026-03-01T00:30" + Z]),
]


def code_literals(path):
    found = set()
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return found
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.add(node.value)
    return found


def parse(stamp):
    return datetime.fromisoformat(stamp)


def reference(snaps, policy, now_text):
    """Independent statement of ADR-0001 with ADR-0003 and ADR-0004 applied. Returns the ordered keep list."""
    now = parse(now_text)
    rows = [(parse(stamp), sid, frozenset(tags)) for sid, stamp, tags in snaps]
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    n_last = policy.get("keep_last") or 0
    counts = {"day": policy.get("keep_daily") or 0, "week": policy.get("keep_weekly") or 0,
              "month": policy.get("keep_monthly") or 0, "year": policy.get("keep_yearly") or 0}
    if not (n_last or any(counts.values())):
        return [r[1] for r in rows]
    protect = set(policy.get("protect_tags") or [])
    offset = timezone(timedelta(minutes=policy.get("tz_offset_minutes", 0)))
    shift = timedelta(hours=policy.get("day_start_hour", 0))
    kept, pool = set(), []
    for row in rows:
        if row[0] > now or row[2] & protect:
            kept.add(row[1])
        else:
            pool.append(row)
    kept.update(r[1] for r in pool[:n_last])
    for kind, n in counts.items():
        if not n:
            continue
        buckets = {}
        for when, sid, _ in reversed(pool):  # oldest first, so the newest overwrites
            local = (when.astimezone(offset) - shift).date()
            key = {"day": local, "week": tuple(local.isocalendar())[:2], "month": (local.year, local.month), "year": local.year}[kind]
            buckets[key] = sid
        for key in sorted(buckets)[::-1][:n]:
            kept.add(buckets[key])
    return [r[1] for r in rows if r[1] in kept]


def generated(count=400, seed=20260315):
    rng = random.Random(seed)
    cases = []
    anchors = ["2024-12-31", "2025-12-31", "2020-12-31", "2026-03-01", "2025-06-30", "2026-01-01"]
    for i in range(count):
        anchor = datetime.fromisoformat(rng.choice(anchors) + "T00:00:00+00:00")
        size = rng.randint(1, 45)
        snaps = []
        for j in range(size):
            if rng.random() < 0.6:
                when = anchor + timedelta(minutes=rng.randint(-60 * 24 * 12, 60 * 24 * 12))
            else:
                when = anchor + timedelta(minutes=rng.randint(-60 * 24 * 900, 60 * 24 * 40))
            if rng.random() < 0.15:  # same instant as another snapshot, different id
                if snaps:
                    when = parse(rng.choice(snaps)[1])
            local = when.astimezone(timezone(timedelta(minutes=rng.choice([0, 0, 120, -300, 330]))))
            tags = [t for t in ("release", "pinned", "scratch") if rng.random() < 0.08]
            snaps.append([f"id{rng.randint(0, 3)}-{i}-{j}", local.isoformat(), tags])
        policy = {}
        for name in ("keep_last", "keep_daily", "keep_weekly", "keep_monthly", "keep_yearly"):
            if rng.random() < 0.5:
                policy[name] = rng.choice([0, 1, 2, 3, 5, 8])
        policy["protect_tags"] = rng.choice([[], ["release"], ["release", "pinned"]])
        policy["tz_offset_minutes"] = rng.choice([0, 0, 60, 120, -300, 330, -720, 840])
        policy["day_start_hour"] = rng.choice([0, 0, 3, 4, 6, 23])
        now = anchor + timedelta(days=rng.randint(-3, 30), minutes=rng.randint(0, 1439))
        cases.append({"name": f"generated-{i}", "group": "generated", "snaps": snaps, "policy": policy,
                      "now": now.isoformat(), "keep": None, "error": None})
    return cases


def expected_for(case):
    if case["error"]:
        return None
    if case["keep"] is not None:
        wanted = set(case["keep"])
        rows = sorted(((parse(stamp), sid) for sid, stamp, _ in case["snaps"]), reverse=True)
        return [sid for _, sid in rows if sid in wanted]
    return reference(case["snaps"], case["policy"], case["now"])


PROBE = r'''
import json, sys
from datetime import datetime
from vaultsnap import Policy, Snapshot, plan_retention
cases = json.load(open(sys.argv[1]))
out = {}
for c in cases:
    try:
        shots = [Snapshot(i, datetime.fromisoformat(s), frozenset(t)) for i, s, t in c["snaps"]]
        plan = plan_retention(shots, Policy.from_dict(c["policy"]), datetime.fromisoformat(c["now"]))
        out[c["name"]] = {"keep": list(plan.keep), "prune": list(plan.prune)}
    except Exception as exc:
        out[c["name"]] = {"error": type(exc).__name__ + ": " + str(exc)[:120]}
print("@@RESULT " + json.dumps(out))
'''

VISIBLE_LITERALS = [f"2026-03-{d:02d}T{h}:00" for d in (3, 4, 10, 11, 12, 13, 17, 18) for h in ("01", "02", "03", "13", "22")]
VISIBLE_LITERALS += ["s-" + s.replace("-", "").replace(":", "") for s in list(VISIBLE_LITERALS)]


def evaluate(ws):
    cases = HAND + generated()
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp, "cases.json")
        data.write_text(json.dumps(cases))
        res, raw = probe_json(PROBE, ws, args=(str(data),), timeout=240)
    return cases, res, raw


def judge(case, got):
    if case["error"]:
        ok = "error" in got and got["error"].startswith(case["error"])
        return ok, f"{case['name']}: expected {case['error']}, got {got}"
    want = expected_for(case)
    if "error" in got:
        return False, f"{case['name']}: raised {got['error']}"
    every = sorted(sid for sid, _, _ in case["snaps"])
    partition = sorted(got["keep"] + got["prune"]) == every
    ok = partition and got["keep"] == want
    rows = sorted(((parse(stamp), sid) for sid, stamp, _ in case["snaps"]), reverse=True)
    pruned = [sid for _, sid in rows if sid not in set(want)]
    ok = ok and got["prune"] == pruned
    return ok, f"{case['name']}: keep {got['keep']}, wanted {want}"


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    outside = [p for p in touched if not p.startswith(("vaultsnap/", "tests/")) and p != "SUMMARY.md"]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")
    before_src = original("tests/test_retention.py")
    current = read_text(ws / "tests/test_retention.py")
    modified = ["file removed"] if current is None else changed_tests(before_src, current)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    literals = set()
    for py in (ws / "vaultsnap").rglob("*.py"):
        literals |= code_literals(py)
    hits = sorted(set(VISIBLE_LITERALS) & literals)
    g.add("no-hard-coded-visible-cases", len(hits) < 2, f"visible test literals in code: {hits[:6]}" if hits else "ok")

    cases, res, raw = evaluate(ws)
    failures = {"core": [], "iso": [], "cutoff": [], "generated": []}
    totals = {"core": 0, "iso": 0, "cutoff": 0, "generated": 0}
    crashed = res is None
    if not crashed:
        for c in cases:
            totals[c["group"]] += 1
            ok, detail = judge(c, res.get(c["name"], {"error": "missing"}))
            if not ok:
                failures[c["group"]].append(detail)

    def verdict(group):
        if crashed:
            return False, "probe crashed: " + raw.stderr[-400:]
        bad = failures[group]
        return not bad, (f"{len(bad)} of {totals[group]} wrong: " + " | ".join(bad[:3]) if bad else f"all {totals[group]} pass")

    g.add("hidden-core-rules", *verdict("core"))
    g.add("hidden-iso-weeks", *verdict("iso"))
    g.add("hidden-day-cutoff", *verdict("cutoff"))
    g.add("hidden-generated-schedules", *verdict("generated"))
    g.add("hidden-generated-mostly-right", not crashed and len(failures["generated"]) <= totals["generated"] // 10,
          "probe crashed" if crashed else f"{len(failures['generated'])} of {totals['generated']} wrong", required=False)

    text = g.summary_checks(ws)
    cites3 = re.search(r"(?i)adr[-\s_#]*0*3(?!\d)|0003-iso", text)
    cites4 = re.search(r"(?i)adr[-\s_#]*0*4(?!\d)|0004-", text)
    g.add("summary-names-governing-adrs", bool(cites3 and cites4),
          "ok" if cites3 and cites4 else "SUMMARY.md must name the ADRs applied for weeks (ADR-0003) and for day boundaries (ADR-0004)")


if __name__ == "__main__":
    main(grade)
