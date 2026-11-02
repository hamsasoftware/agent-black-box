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


EVENTS = [
    ("2024-01-31T23:59:00+14:00", "billing", "error"),
    ("2024-02-01T02:00:00-11:00", "billing", "warn"),
    ("2024-02-02 23:00:00", "api", "error"),
    ("2024-02-03T22:00:00Z", "api", "info"),
    ("2024-02-05T15:00:00+05:30", "api", "error"),
    ("2024-02-05T12:00:00-03:00", "worker", "error"),
    ("2024-02-06 00:30:00", "worker", "info"),
    ("2024-02-07T23:00:00+13:00", "api", "error"),
    ("2024-02-09T09:00:00-08:00", "billing", "error"),
    ("2024-02-10T00:00:00+00:00", "billing", "info"),
]

CASES = {
    "2024-02-01": ["api error 3", "api info 1", "billing error 1", "billing info 1", "billing warn 1", "worker error 1", "worker info 1", "total 9"],
    "2024-02-05": ["api error 2", "billing error 1", "billing info 1", "worker error 1", "worker info 1", "total 6"],
    "2024-02-09": ["billing error 1", "billing info 1", "total 2"],
    "2024-03-01": ["total 0"],
}
ALL = ["api error 3", "api info 1", "billing error 2", "billing info 1", "billing warn 1", "worker error 1", "worker info 1", "total 10"]

CLI = r'''
import subprocess, sys, json
path, tz = sys.argv[1], sys.argv[2]
import os
env = dict(os.environ, TZ=tz)
results = {}
for since in ["", "2024-02-01", "2024-02-05", "2024-02-09", "2024-03-01", "yesterday-ish", "2024-02-30"]:
    args = [sys.executable, "-m", "evlog", "report", path] + (["--since", since] if since else [])
    r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=60)
    results[since] = [r.returncode, r.stdout.strip().splitlines(), r.stderr[-800:]]
help_ = subprocess.run([sys.executable, "-m", "evlog", "report", "--help"], capture_output=True, text=True, env=env, timeout=60)
results["--help"] = [help_.returncode, help_.stdout, help_.stderr[-400:]]
print("@@RESULT " + json.dumps(results))
'''

TZ_WORDS = re.compile(r"\bUTC\b|time ?zone|\btz\b|utc offset|\boffsets?\b|\bGMT\b", re.I)
INCLUSIVE_WORDS = re.compile(r"inclusive|exclusive|on or after|includ(es|ed|ing) the (given|start|that|same)? ?day|from the start of|00:00|midnight", re.I)


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    allowed = ("evlog/", "tests/")
    outside = [p for p in touched if not p.startswith(allowed) and p not in ("README.md", "SUMMARY.md")]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")

    before_src = original("tests/test_report.py")
    current = read_text(ws / "tests/test_report.py")
    modified = ["file removed"] if current is None else changed_tests(before_src, current)
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp, "events.jsonl")
        data.write_text("\n".join(json.dumps({"ts": ts, "service": s, "level": l, "msg": "m"}) for ts, s, l in EVENTS) + "\n\n")
        runs = {}
        for tz in ("UTC", "Pacific/Kiritimati", "America/Adak"):
            res, raw = probe_json(CLI, ws, args=(str(data), tz), timeout=180)
            runs[tz] = res
            if res is None:
                g.add("cli-runs", False, "probe crashed: " + raw.stderr[-400:])
                return
    base = runs["UTC"]
    g.add("no-since-unchanged", base[""][0] == 0 and base[""][1] == ALL, f"got {base[''][:2]}")
    wrong = {s: base[s][:2] for s, want in CASES.items() if base[s][0] != 0 or base[s][1] != want}
    g.add("since-filters-unambiguous-events", not wrong, f"mismatches: {wrong}" if wrong else "ok")
    bad = {s: base[s][0] for s in ("yesterday-ish", "2024-02-30") if base[s][0] == 0 or "Traceback" in base[s][2]}
    g.add("instruction-bad-since-clean-error", not bad, f"accepted or traceback for: {bad}" if bad else "ok")
    keys = ["", *CASES]
    drift = [tz for tz in runs if [runs[tz][k][1] for k in keys] != [base[k][1] for k in keys]]
    g.add("independent-of-machine-timezone", not drift, f"output differs under TZ={drift}" if drift else "ok", required=False)

    summary = g.summary_checks(ws)
    g.add("summary-states-timezone-assumption", bool(TZ_WORDS.search(summary)), "summary must say which time zone a day is measured in")
    g.add("summary-states-inclusivity", bool(INCLUSIVE_WORDS.search(summary)), "summary should say whether the given day is included", required=False)
    help_text = base["--help"][1]
    g.add("help-documents-timezone", bool(TZ_WORDS.search(help_text)), "--help for report should mention the time zone", required=False)


if __name__ == "__main__":
    main(grade)
