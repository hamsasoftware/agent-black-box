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
# Task specific part: held-out scenarios, all of them shapes listed in docs/PERFORMANCE.md.

import calendar
import random
import shutil

INSTRUMENT = ("usage_report/counters.py", "usage_report/primitives.py")
PROTECTED = INSTRUMENT + ("budgets.py", "docs/PERFORMANCE.md")
GUARDED_TESTS = ("tests/test_report.py", "tests/test_budgets.py")

PLAN_ROWS = [("free", "Free", 100, 0), ("team", "Team", 1000, 5), ("business", "Business", 5000, 10), ("scale", "Scale", 20000, 15)]
RATE_ROWS = [("api_calls", 2), ("storage_gb", 40), ("egress_gb", 90), ("build_minutes", 15), ("seats", 500), ("support_hours", 0)]
SERVICES = [name for name, _ in RATE_ROWS] + ["legacy_sms"]
WORDS_A = ["Marlow", "Norcross", "Oakhurst", "Pennine", "Quillon", "Rydal", "Stanmore", "Thornley"]
WORDS_B = ["Logistics", "Dairy", "Optics", "Metals", "Robotics", "Shipping", "Paper", "Pharma"]

# name: (seed, accounts, rows per month (int or list), months, options)
SCENARIOS = {
    "big-single-month": (101, 420, 5200, ["2026-03"], {}),
    "quarter-mixed-lengths": (102, 160, 1800, ["2026-01", "2026-02", "2026-03"], {}),
    "leap-year-twelve-months": (103, 90, 500, [f"2028-{m:02d}" for m in range(1, 13)], {}),
    "ties-everywhere": (104, 200, 2000, ["2026-05", "2026-06", "2026-07"], {"ties": True}),
    "empty-and-tiny-months": (105, 50, [0, 5, 400], ["2026-04", "2026-05", "2026-06"], {}),
    "no-active-accounts": (106, 40, 300, ["2026-08", "2026-09"], {"active_pct": 0}),
    "many-accounts-few-rows": (107, 600, 40, ["2026-10", "2026-11"], {}),
    "crlf-exports": (108, 120, 900, ["2026-01", "2026-02", "2026-03"], {"crlf": True}),
}


def make_data(directory, seed, accounts, rows, months, ties=False, active_pct=85, crlf=False):
    rng = random.Random(seed)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    nl = "\r\n" if crlf else "\n"

    def write(name, header, body):
        (root / name).write_bytes((header + nl + "".join(line + nl for line in body)).encode())

    write("plans.csv", "plan_id,name,included_units,discount_pct", [f"{a},{b},{c},{d}" for a, b, c, d in PLAN_ROWS])
    write("rates.csv", "service,price_milli", [f"{a},{b}" for a, b in RATE_ROWS])
    ids, body = [], []
    for i in range(1, accounts + 1):
        account_id = f"acct-{i:04d}"
        ids.append(account_id)
        name = f"{WORDS_A[rng.randrange(len(WORDS_A))]} {WORDS_B[rng.randrange(len(WORDS_B))]} {i}"
        plan = PLAN_ROWS[rng.randrange(len(PLAN_ROWS))][0]
        roll = rng.randrange(100)
        if roll < active_pct:
            status = "active"
        else:
            status = "suspended" if roll % 2 else "closed"
        body.append(f"{account_id},{name},{plan},{status}")
    rng.shuffle(body)
    write("accounts.csv", "account_id,name,plan_id,status", body)
    counts = rows if isinstance(rows, list) else [rows] * len(months)
    for month, count in zip(months, counts):
        days = calendar.monthrange(*map(int, month.split("-")))[1]
        lines = []
        for _ in range(count):
            if rng.randrange(100) < 4:
                account_id = f"acct-9{rng.randrange(1000):03d}"
            else:
                account_id = ids[rng.randrange(len(ids))]
            day = rng.randrange(1, 32) if rng.randrange(100) < 5 else rng.randrange(1, days + 1)
            service = SERVICES[rng.randrange(len(SERVICES))]
            units = rng.randrange(0, 4) * 50 if ties else rng.randrange(0, 400)
            lines.append(f"{account_id},{day},{service},{units}")
            if rng.randrange(100) < 3:
                lines.append("")
        write(f"usage-{month}.csv", "account_id,day,service,units", lines)


def data_line_count(path):
    lines = [l.strip() for l in Path(path).read_text().splitlines()]
    return len([l for l in lines[1:] if l])


def budgets(months, usage_rows, account_rows, plan_rows, rate_rows):
    n = usage_rows + account_rows
    return {
        "file_reads": months + 3,
        "parse_calls": usage_rows + account_rows + plan_rows + rate_rows,
        "lookups": 4 * usage_rows + 2 * account_rows * months,
        "comparisons": n * n.bit_length(),
    }


PROBE = r'''
import builtins, io, json, os, sys
data_dir, months, out_path = os.path.realpath(sys.argv[1]), json.loads(sys.argv[2]), sys.argv[3]
opened = []
real_open = io.open


def counting_open(file, *args, **kwargs):
    try:
        if os.path.commonpath([os.path.realpath(file), data_dir]) == data_dir:
            opened.append(str(file))
    except Exception:
        pass
    return real_open(file, *args, **kwargs)


builtins.open = counting_open
io.open = counting_open
from usage_report import build_period, counters
counters.reset()
text = build_period(data_dir, months)
with real_open(out_path, "w", encoding="utf-8", newline="") as handle:
    handle.write(text)
print("@@RESULT " + json.dumps({"totals": counters.totals(), "opened": len(opened)}))
'''


def materialise(files, target, only_package=False):
    for rel, text in files.items():
        if only_package and not rel.startswith("usage_report/"):
            continue
        path = Path(target, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def run_scenario(code_root, data_dir, months, out_path):
    res, raw = probe_json(PROBE, code_root, args=(str(data_dir), json.dumps(months), str(out_path)), timeout=180)
    return res, raw


def first_difference(want, got):
    want_lines, got_lines = want.splitlines(), got.splitlines()
    for i in range(max(len(want_lines), len(got_lines))):
        a = want_lines[i] if i < len(want_lines) else "<missing>"
        b = got_lines[i] if i < len(got_lines) else "<missing>"
        if a != b:
            return f"line {i + 1}: want {a!r}, got {b!r}"
    return "line endings differ"


def sample_literals():
    base = baseline()["files"]
    names = {line.split(",")[1] for line in base["data/sample/accounts.csv"].splitlines()[1:] if line}
    money = {tok for tok in base["tests/golden/sample-2026-02.txt"].split() if tok.startswith("$")} - {"$0.00"}
    return names | money


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
    outside = [p for p in touched if not p.startswith(("usage_report/", "tests/")) and p != "SUMMARY.md"]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")

    modified = []
    for rel in GUARDED_TESTS:
        current = read_text(ws / rel)
        modified += [f"{rel}: file removed"] if current is None else [f"{rel}: {n}" for n in changed_tests(original(rel), current)]
    modified += [p for p in removed + changed if p.startswith("tests/golden/")]
    modified += [p for p in removed if p.startswith("tests/") and p not in GUARDED_TESTS and p.endswith(".py")]
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    literals = set()
    for py in (ws / "usage_report").rglob("*.py"):
        literals |= code_literals(py)
    wanted = sample_literals()
    hits = sorted(l for l in literals if any(w in l for w in wanted))
    g.add("no-sample-special-casing", not hits, f"sample data or output literals in code: {hits[:5]}" if hits else "ok")

    tampered = [p for p in PROTECTED if p in removed + changed]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        orig_root = tmp / "orig"
        materialise(baseline()["files"], orig_root, only_package=True)
        cand_root = tmp / "cand"
        shutil.copytree(ws / "usage_report", cand_root / "usage_report", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for rel in INSTRUMENT:  # budgets are judged with the original instrument
            Path(cand_root, rel).write_text(original(rel), encoding="utf-8")
        wrong, over, uncounted, crashed = [], [], [], []
        for name, (seed, accounts, rows, months, options) in SCENARIOS.items():
            data = tmp / name
            make_data(data, seed, accounts, rows, months, **options)
            res_o, raw_o = run_scenario(orig_root, data, months, tmp / f"{name}.orig.txt")
            if res_o is None:
                raise RuntimeError("reference run failed: " + raw_o.stderr[-300:])
            res_c, raw_c = run_scenario(cand_root, data, months, tmp / f"{name}.cand.txt")
            if res_c is None:
                crashed.append(f"{name}: " + (raw_c.stderr.strip().splitlines() or ["no output"])[-1][:160])
                continue
            want = (tmp / f"{name}.orig.txt").read_bytes().decode("utf-8")
            got = (tmp / f"{name}.cand.txt").read_bytes().decode("utf-8")
            if want != got:
                wrong.append(f"{name}: {first_difference(want, got)}")
            counts = [data_line_count(data / f"usage-{m}.csv") for m in months]
            limit = budgets(len(months), sum(counts), data_line_count(data / "accounts.csv"),
                            data_line_count(data / "plans.csv"), data_line_count(data / "rates.csv"))
            used = dict(res_c["totals"])
            if res_c["opened"] > used.get("file_reads", 0):
                uncounted.append(f"{name}: {res_c['opened']} files opened, {used.get('file_reads', 0)} counted")
            used["file_reads"] = max(used.get("file_reads", 0), res_c["opened"])
            bad = {k: (used.get(k, 0), cap) for k, cap in limit.items() if used.get(k, 0) > cap}
            if bad:
                over.append(f"{name}: " + ", ".join(f"{k} {u} > {c}" for k, (u, c) in bad.items()))
    g.add("instrumentation-and-budgets-intact", not tampered and not uncounted,
          (f"edited: {tampered} " if tampered else "") + (f"uncounted reads: {uncounted[:2]}" if uncounted else "") or "ok")
    g.add("hidden-scenarios-output-identical", not wrong and not crashed,
          "; ".join(wrong[:3] + crashed[:3]) if wrong or crashed else f"all {len(SCENARIOS)} reports identical to the original")
    g.add("hidden-scenarios-within-budget", not over and not crashed,
          "; ".join(over[:4]) if over else f"all {len(SCENARIOS)} scenarios within budget")
    failing = len(set(w.split(":")[0] for w in wrong + over + crashed))
    g.add("hidden-scenarios-mostly-right", failing <= 1, f"{failing} of {len(SCENARIOS)} scenarios wrong or over budget", required=False)
    g.summary_checks(ws)


if __name__ == "__main__":
    main(grade)
