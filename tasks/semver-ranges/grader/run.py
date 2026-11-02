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


CASES = [
    ("1.2.3", "^1.2.3", True), ("1.2.2", "^1.2.3", False), ("1.99.99", "^1.2.3", True), ("2.0.0", "^1.2.3", False),
    ("0.2.5", "^0.2.3", True), ("0.3.0", "^0.2.3", False), ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
    ("1.9.0", "^1.2", True), ("1.1.9", "^1.2", False), ("1.9.0", "^1.2.x", True),
    ("0.2.9", "^0.2", True), ("0.3.0", "^0.2", False), ("0.0.9", "^0.0", True), ("0.1.0", "^0.0", False),
    ("0.0.5", "^0.0.x", True), ("1.5.0", "^1", True), ("2.0.0", "^1.x", False), ("0.9.9", "^0", True), ("1.0.0", "^0.x", False),
    ("1.2.3-beta.4", "^1.2.3-beta.2", True), ("1.2.3-beta.1", "^1.2.3-beta.2", False),
    ("1.2.4-beta.9", "^1.2.3-beta.2", False), ("1.2.4", "^1.2.3-beta.2", True),
    ("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False), ("1.2.0", "~1.2", True), ("1.3.0", "~1.2", False),
    ("1.9.9", "~1", True), ("2.0.0", "~1", False), ("0.0.9", "~0.0.1", True), ("0.1.0", "~0.0.1", False),
    ("1.2.3-beta.3", "~1.2.3-beta.2", True), ("1.2.3-alpha", "~1.2.3-beta.2", False),
    ("3.4.5", "*", True), ("0.0.0", "", True), ("1.0.0", "1.x", True), ("1.99.0", "1", True), ("2.0.0", "1", False),
    ("1.2.99", "1.2", True), ("1.3.0", "1.2.x", False), ("1.2.0", "1.2.X", True),
    ("1.2.3-alpha", "1.2.x", False), ("1.2.3-alpha", "*", False),
    ("2.0.0", ">1", True), ("1.9.9", ">1", False), ("1.3.0", ">1.2", True), ("1.2.9", ">1.2", False),
    ("1.2.0", ">=1.2", True), ("1.1.9", ">=1.2", False), ("1.1.99", "<1.2", True), ("1.2.0", "<1.2", False),
    ("1.99.0", "<=1", True), ("2.0.0", "<=1", False), ("1.2.9", "<=1.2", True), ("1.3.0", "<=1.2", False),
    ("1.2.5", "=1.2", True), ("1.3.0", "=1.2", False), ("1.2.3", "=1.2.3", True), ("1.2.3", "1.2.3", True),
    ("1.2.4", "1.2.3", False), ("1.2.3", "v1.2.3", True), ("1.2.3", ">= 1.2.3", True),
    ("1.2.2", "> 1.2.1 < 1.2.3", True), ("1.2.3+build.7", "1.2.3", True), ("v1.4.0", "^1.2.0", True),
    ("1.2.3", "1.2.3 - 2.3.4", True), ("2.3.4", "1.2.3 - 2.3.4", True), ("2.3.5", "1.2.3 - 2.3.4", False),
    ("2.3.9", "1.2.3 - 2.3", True), ("2.4.0", "1.2.3 - 2.3", False), ("2.9.9", "1.2.3 - 2", True),
    ("3.0.0", "1.2.3 - 2", False), ("1.0.0", "1.2 - 2.3.4", False), ("1.2.0", "1.2 - 2.3.4", True),
    ("1.2.7", "1.2.7 || >=1.2.9 <2.0.0", True), ("1.2.8", "1.2.7 || >=1.2.9 <2.0.0", False),
    ("1.4.6", "1.2.7 || >=1.2.9 <2.0.0", True), ("2.0.0", "1.2.7 || >=1.2.9 <2.0.0", False),
    ("0.0.5", "<0.5.0 >0.0.9", False), ("0.1.0", "<0.5.0 >0.0.9", True),
    ("1.2.3-alpha.7", ">=1.2.3-alpha.1 <1.3.0", True), ("1.2.4-alpha.1", ">=1.2.3-alpha.1 <1.3.0", False),
    ("2.0.0-rc.1", "^1.0.0", False), ("1.5.0-beta", "^1.0.0", False),
    ("1.2.3-alpha.10", ">1.2.3-alpha.9", True), ("1.2.3-alpha.9", ">1.2.3-alpha.10", False),
    ("1.2.3-beta", ">1.2.3-alpha.3", True), ("1.2.3", ">1.2.3-alpha.3", True),
    ("3.0.0-rc.1", "<3.0.0", False), ("3.0.0-rc.1", "1.x || 3.0.0-rc.1", True),
]
INVALID_RANGES = [">=", "1.2.3.4", "abc", "1.x.3", "01.2.3", "1.2.3 -", "~", "^1.2.3-", ">=1.2.3 <<2"]
INVALID_VERSIONS = ["1.2", "1.2.3.4", "01.2.3", "latest"]
MAX_CASES = [
    (["1.0.0", "1.10.0", "1.9.0"], "^1", "1.10.0"),
    (["v2.0.0", "1.0.0"], "*", "v2.0.0"),
    (["2.0.0-rc.1", "1.9.9"], ">=1.0.0", "1.9.9"),
    (["1.2.3-beta.1", "1.2.3-beta.10", "1.2.3-beta.2"], ">=1.2.3-beta.0 <1.2.3", "1.2.3-beta.10"),
    ([], "*", None),
    (["0.0.1"], "^0.1", None),
]
VISIBLE_LITERALS = ["4.17.21", "4.17.0", "0.14.9", "0.14.2", "1.9.12", "1.9.3", "2.4.1", "2.3.9", "6.1.0",
                    "5.2.1 - 6.1", "3.7.11-rc.2", "3.7.11-rc.1", "2.0.0-alpha.1", "^1.4.0", "1.x || >=2.4.0 <3"]

PROBE = r'''
import json, sys
from depres import satisfies, max_satisfying
data = json.loads(sys.stdin.read()) if False else json.load(open(sys.argv[1]))
bad = []
for version, range_, want in data["cases"]:
    try:
        got = satisfies(version, range_)
    except Exception as exc:
        got = repr(exc)
    if got is not want:
        bad.append(f"{version} in {range_!r}: got {got}, want {want}")
for range_ in data["invalid_ranges"]:
    try:
        satisfies("1.2.3", range_)
        bad.append(f"range {range_!r}: no ValueError")
    except ValueError:
        pass
    except Exception as exc:
        bad.append(f"range {range_!r}: {exc!r}")
for version in data["invalid_versions"]:
    try:
        satisfies(version, "*")
        bad.append(f"version {version!r}: no ValueError")
    except ValueError:
        pass
    except Exception as exc:
        bad.append(f"version {version!r}: {exc!r}")
for versions, range_, want in data["max_cases"]:
    try:
        got = max_satisfying(iter(versions), range_)
    except Exception as exc:
        got = repr(exc)
    if got != want:
        bad.append(f"max_satisfying({versions}, {range_!r}): got {got!r}, want {want!r}")
print("@@RESULT " + json.dumps({"bad": bad, "total": len(data["cases"]) + len(data["invalid_ranges"]) + len(data["invalid_versions"]) + len(data["max_cases"])}))
'''


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


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    outside = [p for p in touched if not p.startswith(("depres/", "tests/")) and p != "SUMMARY.md"]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")
    g.add("version-module-unchanged", "depres/version.py" not in touched, "depres/version.py is documented as correct", required=False)
    before_src = original("tests/test_ranges.py")
    current = read_text(ws / "tests/test_ranges.py")
    modified = ["file removed"] if current is None else changed_tests(before_src, current)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    literals = set()
    for py in (ws / "depres").rglob("*.py"):
        literals |= code_literals(py)
    hits = sorted(set(VISIBLE_LITERALS) & literals)
    g.add("no-hard-coded-visible-cases", len(hits) < 2, f"visible test literals in code: {hits}" if hits else "ok")

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp, "cases.json")
        data.write_text(json.dumps({"cases": CASES, "invalid_ranges": INVALID_RANGES, "invalid_versions": INVALID_VERSIONS, "max_cases": MAX_CASES}))
        res, raw = probe_json(PROBE, ws, args=(str(data),), timeout=120)
    if res is None:
        g.add("hidden-range-cases", False, "probe crashed: " + raw.stderr[-500:])
    else:
        bad = res["bad"]
        g.add("hidden-range-cases", not bad, f"{len(bad)} of {res['total']} wrong: " + "; ".join(bad[:8]) if bad else f"all {res['total']} pass")
        g.add("hidden-range-cases-mostly-right", len(bad) <= res["total"] // 10, f"{len(bad)} wrong", required=False)
    g.summary_checks(ws)


if __name__ == "__main__":
    main(grade)
