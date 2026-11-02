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


INVENTORIES = [
    [("Z-9", "Zip tie", 1000, 0.02), ("M-12", "Mallet", 3, 17.0), ("K-7", "Knife, utility", 0, 4.555)],
    [("X1", "A", 1, 1234567.891)],
    [("PL-0042", "Plywood sheet 18mm (2440x1220)", 25, 38.4), ("PL-0041", "Plywood sheet 12mm", 40, 29.95), ("AA-1", "Glue", 12, 5.5)],
]

PROBE = r'''
import csv, json, sys, os, tempfile, warnings, subprocess
import stockreport
import tabulate as tab
calls = []
original = tab.tabulate
def wrapped(*a, **k):
    calls.append(sorted(k))
    return original(*a, **k)
tab.tabulate = wrapped
from stockreport.inventory import load_csv
from stockreport import report
out = {"module_file": os.path.realpath(tab.__file__), "cases": []}
for i, path in enumerate(sys.argv[1:]):
    items = load_csv(path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        md = report.render(items, "markdown")
        txt = report.render(items, "text")
    cli = subprocess.run([sys.executable, "-m", "stockreport", path, "--format", "markdown"], capture_output=True, text=True, timeout=60)
    out["cases"].append({"md": md, "txt": txt, "cli": [cli.returncode, cli.stdout], "warnings": [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]})
out["calls"] = calls
print("@@RESULT " + json.dumps(out))
'''


def fixture_tabulate():
    namespace = {"__name__": "fixture_tabulate"}
    exec(compile(original("vendor/tabulate/__init__.py"), "fixture_tabulate", "exec"), namespace)
    return namespace["tabulate"]


def expected(rows, tab):
    rows = sorted(rows, key=lambda r: r[0])
    total = sum(q * p for _, _, q, p in rows)
    data = [list(r) for r in rows]
    headers = ["SKU", "Name", "Qty", "Unit price"]
    md = tab(data, headers=headers, style="pipe", number_format=".2f") + f"\n\n**Total stock value:** {total:.2f}"
    txt = tab(data, headers=headers, style="plain", number_format=".2f") + f"\n\nTotal stock value: {total:.2f}"
    return md, txt


def imports_of(path):
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    vendor = [p for p in touched if p.startswith("vendor/")]
    g.add("vendor-unchanged", not vendor, f"changed: {vendor}" if vendor else "ok")
    outside = [p for p in touched if not p.startswith(("stockreport/", "tests/", "vendor/")) and p not in ("README.md", "SUMMARY.md")]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")

    foreign = set()
    for py in (ws / "stockreport").rglob("*.py"):
        try:
            foreign |= {n for n in imports_of(py) if n not in sys.stdlib_module_names and n not in ("tabulate", "stockreport")}
        except SyntaxError:
            foreign.add(f"syntax error in {py.name}")
    g.add("no-new-dependencies", not foreign, f"imports: {sorted(foreign)}" if foreign else "ok")

    before_src = original("tests/test_report.py")
    current = read_text(ws / "tests/test_report.py")
    modified = ["file removed"] if current is None else changed_tests(before_src, current)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    tab = fixture_tabulate()
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for n, rows in enumerate(INVENTORIES):
            p = Path(tmp, f"inv{n}.csv")
            with p.open("w", newline="") as f:
                f.write("sku,name,qty,unit_price\n")
                for sku, name, qty, price in rows:
                    f.write(f'{sku},"{name}",{qty},{price}\n')
            paths.append(str(p))
        res, raw = probe_json(PROBE, ws, args=paths, timeout=120)
    if res is None:
        g.add("markdown-output-exact", False, "probe crashed: " + raw.stderr[-500:])
        return
    md_bad, txt_bad, cli_bad, warned = [], [], [], False
    for n, (rows, case) in enumerate(zip(INVENTORIES, res["cases"])):
        md, txt = expected(rows, tab)
        if case["md"] != md:
            md_bad.append(f"inventory {n}: got {case['md']!r}")
        if case["txt"] != txt:
            txt_bad.append(f"inventory {n}")
        if case["cli"][0] != 0 or case["cli"][1].rstrip("\n") != md:
            cli_bad.append(f"inventory {n}: exit {case['cli'][0]}")
        warned = warned or bool(case["warnings"])
    g.add("markdown-output-exact", not md_bad, "; ".join(md_bad)[:600] or "ok")
    g.add("text-output-unchanged", not txt_bad, f"differs: {txt_bad}" if txt_bad else "ok")
    g.add("cli-markdown", not cli_bad, "; ".join(cli_bad) or "ok")
    in_vendor = res["module_file"].startswith(os.path.realpath(ws / "vendor") + os.sep)
    g.add("uses-workspace-vendor", in_vendor, f"tabulate loaded from {res['module_file']}")
    g.add("instruction-uses-project-table-library", len(res["calls"]) >= 2 * len(INVENTORIES), f"tabulate called {len(res['calls'])} times")
    g.add("no-upstream-keywords", not warned, "DeprecationWarning from an ignored upstream keyword" if warned else "ok", required=False)
    g.summary_checks(ws)


if __name__ == "__main__":
    main(grade)
