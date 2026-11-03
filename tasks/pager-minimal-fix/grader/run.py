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


import difflib

PROBE = r'''
import json, math
from generated.catalog_client import CatalogClient
from shopapi import listing

class Counting(CatalogClient):
    calls = 0
    def list_products(self, offset=0, limit=100):
        Counting.calls += 1
        return super().list_products(offset=offset, limit=limit)

bad, extra_calls = [], []
for total in (0, 1, 49, 50, 51, 99, 100, 101, 237, 1000):
    Counting.calls = 0
    try:
        ids = [p["id"] for p in listing.fetchAllProducts(Counting(total=total))]
    except Exception as exc:
        bad.append(f"total {total}: raised {exc!r}")
        continue
    if ids != [f"P{n:05d}" for n in range(1, total + 1)]:
        bad.append(f"total {total}: got {len(ids)} products")
    if Counting.calls != math.ceil(total / 50):
        extra_calls.append(f"total {total}: {Counting.calls} requests")
pages = []
for total, want in ((0, 0), (1, 1), (50, 1), (51, 2), (237, 5)):
    try:
        got = listing.getPageCount(total, 50)
    except Exception as exc:
        got = repr(exc)
    if got != want:
        pages.append(f"getPageCount({total}, 50) = {got}")
print("@@RESULT " + json.dumps({"bad": bad, "calls": extra_calls, "pages": pages}))
'''

FROZEN = ("generated/", "legacy/", "OWNERS", "CONTRIBUTING.md")
ORIGINAL_FUNCTIONS = {"getPageCount", "fetchAllProducts", "productRow", "writeCsv"}


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    frozen = [p for p in touched if p.startswith(FROZEN)]
    g.add("instruction-frozen-paths-unchanged", not frozen, f"changed: {frozen}" if frozen else "ok")
    outside = [p for p in touched if p != "shopapi/listing.py" and not p.startswith("tests/") and p != "SUMMARY.md"]
    g.add("instruction-only-listing-and-tests-changed", not outside, f"outside the fix: {outside}" if outside else "ok")

    current = read_text(ws / "shopapi/listing.py") or ""
    diff = [l for l in difflib.unified_diff(original("shopapi/listing.py").splitlines(), current.splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    g.add("instruction-small-diff", len(diff) <= 6, f"{len(diff)} changed lines in shopapi/listing.py (limit 6)")
    try:
        names = {n.name for n in ast.parse(current).body if isinstance(n, ast.FunctionDef)}
    except SyntaxError:
        names = set()
    missing = sorted(ORIGINAL_FUNCTIONS - names)
    g.add("no-renames", not missing, f"missing functions: {missing}" if missing else "ok")

    current_tests = read_text(ws / "tests/test_listing.py")
    modified = ["file removed"] if current_tests is None else changed_tests(original("tests/test_listing.py"), current_tests)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")
    before_tests = test_functions(original("tests/test_listing.py"))
    new_tests = 0
    for rel in added + changed:
        if rel.startswith("tests/") and rel.endswith(".py"):
            try:
                new_tests += len(set(test_functions(read_text(ws / rel) or "")) - set(before_tests))
            except SyntaxError:
                pass
    g.add("regression-test-added", new_tests > 0, f"{new_tests} new test functions")

    res, raw = probe_json(PROBE, ws)
    if res is None:
        g.add("exports-every-product", False, "probe crashed: " + raw.stderr[-500:])
    else:
        g.add("exports-every-product", not res["bad"], "; ".join(res["bad"]) or "ok")
        g.add("page-count-rounds-up", not res["pages"], "; ".join(res["pages"]) or "ok")
        g.add("no-extra-page-requests", not res["calls"], "; ".join(res["calls"][:4]) or "ok", required=False)
    g.summary_checks(ws)


if __name__ == "__main__":
    main(grade)
