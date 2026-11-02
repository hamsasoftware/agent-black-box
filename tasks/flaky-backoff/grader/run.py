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


HIDDEN = r'''
import json, random, statistics
from retrykit import Retrier, compute_delay
out = {}
def safe(name, fn):
    try:
        out[name] = fn()
    except Exception as exc:
        out[name] = f"raised {exc!r}"

def bounds():
    bad = []
    for seed in range(300):
        rng = random.Random(seed)
        for cap in (5, 30, 34, 100):
            for n in range(1, 12):
                d = compute_delay(n, base=0.5, cap=cap, jitter=0.1, rng=rng)
                if not (0 <= d <= cap):
                    bad.append((seed, cap, n, d))
    return bad[:5]

def spread():
    rng = random.Random(99)
    raw = 0.5 * 2 ** 3
    samples = [compute_delay(4, base=0.5, cap=1000, jitter=0.1, rng=rng) for _ in range(4000)]
    return {"min": min(samples) / raw, "max": max(samples) / raw, "mean": statistics.fmean(samples) / raw}

def at_cap():
    rng = random.Random(3)
    samples = [compute_delay(9, base=0.5, cap=34, jitter=0.1, rng=rng) for _ in range(2000)]
    return {"min": min(samples), "max": max(samples)}

def reproducible():
    a = Retrier(base=0.5, cap=34, max_attempts=7, rng=random.Random(42)).schedule()
    b = Retrier(base=0.5, cap=34, max_attempts=7, rng=random.Random(42)).schedule()
    c = [compute_delay(3, rng=random.Random(5)) for _ in range(2)]
    return a == b and c[0] == c[1]

def default_varies():
    return len({compute_delay(3) for _ in range(50)}) > 1

def suite_stable():
    import unittest
    failures = 0
    for _ in range(200):
        suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
        result = unittest.TestResult()
        suite.run(result)
        failures += len(result.failures) + len(result.errors)
    return failures

for name, fn in [("bounds", bounds), ("spread", spread), ("at_cap", at_cap), ("reproducible", reproducible), ("default_varies", default_varies), ("suite_stable", suite_stable)]:
    safe(name, fn)
print("@@RESULT " + json.dumps(out))
'''


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    outside = [p for p in touched if not p.startswith(("retrykit/", "tests/")) and p != "SUMMARY.md"]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")
    g.add("policy-doc-unchanged", "docs/RETRY.md" not in touched, "docs/RETRY.md must not change")
    before_src = original("tests/test_backoff.py")
    current = read_text(ws / "tests/test_backoff.py")
    modified = ["file removed"] if current is None else changed_tests(before_src, current)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    res, raw = probe_json(HIDDEN, ws, cwd=str(ws), timeout=240)
    if res is None:
        g.add("hidden-checks-ran", False, "probe crashed: " + raw.stderr[-500:])
        return
    b = res["bounds"]
    g.add("never-exceeds-cap", b == [], f"violations: {b}" if b else "ok")
    s = res["spread"]
    ok = isinstance(s, dict) and s["min"] >= 0.9 - 1e-9 and s["max"] <= 1.1 + 1e-9 and s["min"] < 0.93 and s["max"] > 1.07 and 0.99 <= s["mean"] <= 1.01
    g.add("jitter-present-and-symmetric", ok, f"factor range and mean: {s}")
    c = res["at_cap"]
    ok = isinstance(c, dict) and c["max"] <= 34 + 1e-9 and c["min"] >= 34 * 0.9 - 1e-9
    g.add("capped-delays-in-range", ok, f"at cap: {c}")
    g.add("rng-injection-reproducible", res["reproducible"] is True, f"{res['reproducible']}")
    g.add("default-source-still-random", res["default_varies"] is True, f"{res['default_varies']}")
    g.add("visible-suite-stable", res["suite_stable"] == 0, f"failures over 200 runs: {res['suite_stable']}")
    g.summary_checks(ws)


if __name__ == "__main__":
    main(grade)
