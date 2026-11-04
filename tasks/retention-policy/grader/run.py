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


from datetime import date, datetime, timedelta, timezone
import calendar
import random

NOW = "2026-03-20T12:00:00+00:00"
Z = "+00:00"
GROUPS = ("core", "iso", "cutoff", "zone", "within", "chain", "tags", "month", "generated")


def snaps_of(*items):
    """Each item is an ISO stamp (id = the stamp), optionally 'stamp|tag1,tag2', or a tuple (id, stamp[, tags[, parent]])."""
    out = []
    for item in items:
        if isinstance(item, tuple):
            out.append([item[0], item[1], list(item[2]) if len(item) > 2 else [], item[3] if len(item) > 3 else None])
        elif "|" in item:
            stamp, tags = item.split("|")
            out.append([stamp, stamp, tags.split(","), None])
        else:
            out.append([item, item, [], None])
    return out


def case(name, group, snapshots, policy, keep=None, now=NOW, error=None):
    return {"name": name, "group": group, "snaps": snaps_of(*snapshots), "policy": policy, "now": now, "keep": keep, "error": error}


def t(day, hm="03:00"):
    """('2026-03-18', '04:00') -> '2026-03-18T04:00+00:00'"""
    return f"{day}T{hm}{Z}"


HAND = [
    # --- core rules (ADR-0001) ---
    case("gaps-do-not-count", "core", [t("2026-03-01"), t("2026-03-05"), t("2026-03-10")],
         {"keep_daily": 2}, [t("2026-03-10"), t("2026-03-05")]),
    case("monthly", "core", [t("2025-12-31", "23:00"), t("2026-01-15"), t("2026-01-20"), t("2026-02-10"), t("2026-03-01")],
         {"keep_monthly": 2}, [t("2026-03-01"), t("2026-02-10")]),
    case("yearly", "core", [t("2023-06-01"), t("2024-05-01"), t("2024-09-01"), t("2025-02-01"), t("2026-01-05")],
         {"keep_yearly": 2}, [t("2026-01-05"), t("2025-02-01")]),
    case("protected-not-counted", "core", [t("2026-03-18") + "|release", t("2026-03-17"), t("2026-03-16"), t("2026-03-15")],
         {"keep_daily": 2, "protect_tags": ["release"]}, [t("2026-03-18"), t("2026-03-17"), t("2026-03-16")]),
    case("protected-not-representative", "core", [t("2026-03-18", "20:00") + "|release", t("2026-03-18", "05:00"), t("2026-03-17", "05:00")],
         {"keep_daily": 1, "protect_tags": ["release"]}, [t("2026-03-18", "20:00"), t("2026-03-18", "05:00")]),
    case("all-protected-day-is-no-bucket", "core", [t("2026-03-19") + "|keep-me", t("2026-03-18"), t("2026-03-17"), t("2026-03-16")],
         {"keep_daily": 2, "protect_tags": ["keep-me", "other"]}, [t("2026-03-19"), t("2026-03-18"), t("2026-03-17")]),
    case("protected-not-counted-by-keep-last", "core", [t("2026-03-19") + "|x", t("2026-03-18"), t("2026-03-17")],
         {"keep_last": 1, "protect_tags": ["x"]}, [t("2026-03-19"), t("2026-03-18")]),
    case("future-is-kept-and-not-counted", "core", [t("2026-03-21"), t("2026-03-19"), t("2026-03-18")],
         {"keep_last": 1}, [t("2026-03-21"), t("2026-03-19")]),
    case("taken-exactly-at-now-is-normal", "core", ["2026-03-20T12:00:00" + Z, t("2026-03-19")],
         {"keep_last": 1}, ["2026-03-20T12:00:00" + Z]),
    case("rules-are-independent", "core", [t("2026-03-19"), t("2026-03-19", "20:00"), t("2026-03-18")],
         {"keep_last": 1, "keep_daily": 2}, [t("2026-03-19", "20:00"), t("2026-03-18")]),
    case("weekly-and-monthly-union", "core", [t("2026-03-18"), t("2026-03-10"), t("2026-03-03"), t("2026-02-25")],
         {"keep_weekly": 2, "keep_monthly": 1}, [t("2026-03-18"), t("2026-03-10")]),
    case("ties-go-to-the-greater-id", "core", [("a", t("2026-03-18")), ("b", t("2026-03-18")), ("c", t("2026-03-17"))],
         {"keep_last": 1, "keep_daily": 1}, ["b"]),
    case("ties-in-a-bucket", "core", [("m", t("2026-03-18")), ("z", t("2026-03-18")), ("k", t("2026-03-18", "01:00"))],
         {"keep_daily": 1}, ["z"]),
    case("all-rules-off-keeps-everything", "core", [t("2026-03-01"), t("2026-03-02"), t("2025-01-02")],
         {"keep_daily": 0, "keep_last": None, "protect_tags": ["x"]}, [t("2026-03-01"), t("2026-03-02"), t("2025-01-02")]),
    case("zero-is-off", "core", [t("2026-03-19"), t("2026-03-18")],
         {"keep_last": 0, "keep_daily": 1}, [t("2026-03-19")]),
    case("more-than-available", "core", [t("2026-03-19"), t("2026-03-18")],
         {"keep_daily": 10, "keep_weekly": 10}, [t("2026-03-19"), t("2026-03-18")]),
    case("instants-not-wall-clock", "core", [("a", "2026-03-18T01:00:00+05:00"), ("b", "2026-03-17T22:00:00+00:00"), ("c", "2026-03-16T10:00:00+00:00")],
         {"keep_daily": 1}, ["b"]),
    case("no-snapshots", "core", [], {"keep_last": 3, "keep_daily": 2}, []),
    case("naive-snapshot", "core", ["2026-03-18T03:00"], {"keep_last": 1}, error="ValueError"),
    case("naive-now", "core", [t("2026-03-18")], {"keep_last": 1}, now="2026-03-20T12:00:00", error="ValueError"),
    case("duplicate-ids", "core", [("d", t("2026-03-18")), ("d", t("2026-03-17"))], {"keep_last": 1}, error="ValueError"),
    # --- ISO weeks (ADR-0003 supersedes the Weeks section of ADR-0001) ---
    case("iso-sunday-starts-no-week", "iso", [t("2026-03-08"), t("2026-03-09")],
         {"keep_weekly": 2}, [t("2026-03-08"), t("2026-03-09")]),
    case("iso-saturday-and-sunday-share-a-week", "iso", [t("2026-03-02"), t("2026-03-07"), t("2026-03-08"), t("2026-02-25")],
         {"keep_weekly": 2}, [t("2026-03-08"), t("2026-02-25")]),
    case("iso-new-year-week-order", "iso", [t("2025-12-28"), t("2025-12-29"), t("2025-12-31"), t("2026-01-04"), t("2026-01-05")],
         {"keep_weekly": 2}, [t("2026-01-05"), t("2026-01-04")], now="2026-01-10T12:00:00" + Z),
    case("iso-new-year-three-weeks", "iso", [t("2025-12-28"), t("2025-12-29"), t("2025-12-31"), t("2026-01-04"), t("2026-01-05")],
         {"keep_weekly": 3}, [t("2026-01-05"), t("2026-01-04"), t("2025-12-28")], now="2026-01-10T12:00:00" + Z),
    case("iso-week-53", "iso", [t("2020-12-23"), t("2020-12-30"), t("2021-01-01"), t("2021-01-03"), t("2021-01-04")],
         {"keep_weekly": 2}, [t("2021-01-04"), t("2021-01-03")], now="2021-02-01T12:00:00" + Z),
    case("iso-year-only-for-weeks-yearly", "iso", [t("2025-12-31"), t("2026-01-01")],
         {"keep_yearly": 2}, [t("2025-12-31"), t("2026-01-01")]),
    case("iso-year-only-for-weeks-monthly", "iso", [t("2025-12-31"), t("2026-01-01"), t("2025-11-30")],
         {"keep_monthly": 2}, [t("2025-12-31"), t("2026-01-01")]),
    case("iso-monday-after-jan-first", "iso", [t("2024-12-29"), t("2024-12-30"), t("2025-01-05"), t("2025-01-06")],
         {"keep_weekly": 2}, [t("2025-01-06"), t("2025-01-05")], now="2025-02-01T12:00:00" + Z),
    # --- day boundary (ADR-0004 supersedes ADR-0002) ---
    case("offset-plus-two", "cutoff", [t("2026-03-18", "22:30"), t("2026-03-18", "21:30")],
         {"keep_daily": 2, "tz_offset_minutes": 120}, [t("2026-03-18", "22:30"), t("2026-03-18", "21:30")]),
    case("offset-minus-five", "cutoff", [t("2026-03-19", "04:30"), t("2026-03-18", "10:00"), t("2026-03-19", "05:30")],
         {"keep_daily": 3, "tz_offset_minutes": -300}, [t("2026-03-19", "05:30"), t("2026-03-19", "04:30")]),
    case("day-starts-at-four", "cutoff", [t("2026-03-19", "03:30"), t("2026-03-18", "10:00"), t("2026-03-19", "04:00")],
         {"keep_daily": 3, "day_start_hour": 4}, [t("2026-03-19", "04:00"), t("2026-03-19", "03:30")]),
    case("day-start-crosses-new-year-yearly-1", "cutoff", [t("2026-01-01", "03:30"), t("2026-01-01", "05:00")],
         {"keep_yearly": 1, "day_start_hour": 4}, [t("2026-01-01", "05:00")], now="2026-02-01T12:00:00" + Z),
    case("day-start-crosses-new-year-yearly-2", "cutoff", [t("2026-01-01", "03:30"), t("2026-01-01", "05:00")],
         {"keep_yearly": 2, "day_start_hour": 4}, [t("2026-01-01", "05:00"), t("2026-01-01", "03:30")], now="2026-02-01T12:00:00" + Z),
    case("day-start-crosses-month", "cutoff", [t("2026-03-01", "02:00"), t("2026-03-01", "06:00")],
         {"keep_monthly": 2, "day_start_hour": 3}, [t("2026-03-01", "06:00"), t("2026-03-01", "02:00")]),
    case("day-start-weekly", "cutoff", [t("2026-03-09", "02:00"), t("2026-03-09", "09:00")],
         {"keep_weekly": 2, "day_start_hour": 3}, [t("2026-03-09", "09:00"), t("2026-03-09", "02:00")]),
    case("offset-and-hour-together", "cutoff", [t("2026-03-10", "00:29"), t("2026-03-10", "00:30"), t("2026-03-09", "20:00")],
         {"keep_daily": 2, "tz_offset_minutes": 330, "day_start_hour": 6}, [t("2026-03-10", "00:30"), t("2026-03-10", "00:29")]),
    case("future-uses-the-real-instant", "cutoff", [t("2026-03-20"), t("2026-03-19")],
         {"keep_last": 1, "day_start_hour": 4}, [t("2026-03-20"), t("2026-03-19")], now="2026-03-20T02:00:00" + Z),
    case("keep-last-ignores-the-boundary", "cutoff", [t("2026-03-19", "03:30"), t("2026-03-19", "04:30"), t("2026-03-18", "10:00")],
         {"keep_last": 2, "day_start_hour": 4}, [t("2026-03-19", "04:30"), t("2026-03-19", "03:30")]),
    case("offset-month-boundary", "cutoff", [t("2026-03-01", "00:30"), t("2026-03-01", "01:30")],
         {"keep_monthly": 2, "tz_offset_minutes": -60}, [t("2026-03-01", "01:30"), t("2026-03-01", "00:30")]),
    # --- named zones (ADR-0005, amending a sentence of ADR-0004) ---
    case("zone-lakeside-summer", "zone", [t("2026-06-10", "22:30"), t("2026-06-10", "21:30")],
         {"keep_daily": 2, "zone": "lakeside"}, [t("2026-06-10", "22:30"), t("2026-06-10", "21:30")], now="2026-07-01T12:00:00" + Z),
    case("zone-lakeside-winter", "zone", [t("2026-01-10", "22:30"), t("2026-01-10", "21:30")],
         {"keep_daily": 2, "zone": "lakeside"}, [t("2026-01-10", "22:30")], now="2026-02-01T12:00:00" + Z),
    case("zone-ignores-tz-offset-minutes", "zone", [t("2026-06-10", "22:30"), t("2026-06-10", "21:30")],
         {"keep_daily": 2, "zone": "lakeside", "tz_offset_minutes": -300}, [t("2026-06-10", "22:30"), t("2026-06-10", "21:30")], now="2026-07-01T12:00:00" + Z),
    case("zone-harbor-transition-instant", "zone", [t("2026-10-03", "16:30"), t("2026-10-03", "16:29")],
         {"keep_daily": 2, "zone": "harbor", "day_start_hour": 3}, [t("2026-10-03", "16:30"), t("2026-10-03", "16:29")], now="2026-10-10T12:00:00" + Z),
    case("zone-lakeside-transition-instant", "zone", [t("2026-03-29", "00:59"), t("2026-03-29", "01:00")],
         {"keep_daily": 2, "zone": "lakeside", "day_start_hour": 3}, [t("2026-03-29", "01:00"), t("2026-03-29", "00:59")], now="2026-04-10T12:00:00" + Z),
    case("zone-month-boundary", "zone", [t("2026-07-31", "22:30"), t("2026-07-31", "21:30")],
         {"keep_monthly": 2, "zone": "lakeside"}, [t("2026-07-31", "22:30"), t("2026-07-31", "21:30")], now="2026-08-15T12:00:00" + Z),
    case("zone-after-the-last-row", "zone", [t("2028-07-10", "22:30"), t("2028-07-10", "21:30")],
         {"keep_daily": 2, "zone": "lakeside"}, [t("2028-07-10", "22:30")], now="2028-08-01T12:00:00" + Z),
    case("zone-harbor-before-the-first-row", "zone", [t("2021-07-10", "13:30"), t("2021-07-10", "13:29")],
         {"keep_daily": 2, "zone": "harbor"}, [t("2021-07-10", "13:30"), t("2021-07-10", "13:29")], now="2021-08-01T12:00:00" + Z),
    # --- keep_within (ADR-0006; its bucket interaction reverted by ADR-0009) ---
    case("within-boundary-is-inclusive", "within", [t("2026-03-19", "12:00"), t("2026-03-19", "11:59")],
         {"keep_within_hours": 24}, [t("2026-03-19", "12:00")]),
    case("within-alone-is-a-rule", "within", [t("2026-03-10"), t("2026-03-11")],
         {"keep_within_hours": 1}, []),
    case("within-zero-is-off", "within", [t("2026-03-20", "11:00"), t("2026-03-20", "10:00")],
         {"keep_within_hours": 0, "keep_last": 1}, [t("2026-03-20", "11:00")]),
    case("within-not-counted-by-daily", "within", [t("2026-03-20", "03:00"), t("2026-03-19", "03:00"), t("2026-03-18", "03:00"), t("2026-03-17", "03:00"), t("2026-03-16", "03:00")],
         {"keep_within_hours": 48, "keep_daily": 2}, [t("2026-03-20", "03:00"), t("2026-03-19", "03:00"), t("2026-03-18", "03:00"), t("2026-03-17", "03:00")]),
    case("within-not-counted-by-keep-last", "within", [t("2026-03-20", "06:00"), t("2026-03-19", "06:00"), t("2026-03-18", "06:00")],
         {"keep_within_hours": 24, "keep_last": 1}, [t("2026-03-20", "06:00"), t("2026-03-19", "06:00")]),
    case("within-not-a-representative", "within", [t("2026-03-19", "20:00"), t("2026-03-19", "05:00"), t("2026-03-18", "05:00")],
         {"keep_within_hours": 24, "keep_daily": 1}, [t("2026-03-19", "20:00"), t("2026-03-19", "05:00")]),
    case("within-does-not-beat-expire", "within", [t("2026-03-20", "06:00") + "|scratch", t("2026-03-20", "07:00"), t("2026-03-15", "05:00")],
         {"keep_within_hours": 24, "keep_daily": 1, "expire_tags": ["scratch"]}, [t("2026-03-20", "07:00"), t("2026-03-15", "05:00")]),
    case("within-uses-real-instants", "within", [t("2026-03-20", "10:00"), t("2026-03-20", "09:59")],
         {"keep_within_hours": 2, "tz_offset_minutes": 600, "day_start_hour": 5}, [t("2026-03-20", "10:00")]),
    # --- snapshot chains (ADR-0007) ---
    case("chain-holds-ancestors", "chain", [("full", t("2026-03-15")), ("inc1", t("2026-03-16"), [], "full"), ("inc2", t("2026-03-17"), [], "inc1"), ("other", t("2026-03-10"))],
         {"keep_last": 1}, ["inc2", "inc1", "full"]),
    case("held-parent-is-not-a-representative", "chain", [("c", t("2026-03-18", "10:00"), [], "p"), ("p", t("2026-03-17", "05:00")), ("q", t("2026-03-17", "20:00")), ("r", t("2026-03-16", "05:00"))],
         {"keep_daily": 2}, ["c", "q", "p"]),
    case("held-parent-does-not-use-keep-last", "chain", [("c", t("2026-03-18", "10:00"), [], "p"), ("x", t("2026-03-17", "20:00")), ("y", t("2026-03-16", "20:00")), ("p", t("2026-03-10"))],
         {"keep_last": 2}, ["c", "x", "p"]),
    case("parent-newer-than-child", "chain", [("q", t("2026-03-19")), ("child", t("2026-03-10"), ["release"], "p"), ("p", t("2026-03-18")), ("z", t("2026-03-17"))],
         {"keep_last": 1, "protect_tags": ["release"]}, ["q", "p", "child"]),
    case("protected-child-parent-still-takes-its-slot", "chain", [("p", t("2026-03-18")), ("z", t("2026-03-17")), ("child", t("2026-03-10"), ["release"], "p")],
         {"keep_last": 1, "protect_tags": ["release"]}, ["p", "child"]),
    case("pruned-child-holds-nothing", "chain", [("new", t("2026-03-19")), ("kid", t("2026-03-18"), [], "base"), ("base", t("2026-03-10"))],
         {"keep_last": 1}, ["new"]),
    case("future-child-holds-its-parent", "chain", [("child", t("2026-03-21"), [], "old"), ("top", t("2026-03-19")), ("mid", t("2026-03-10")), ("old", t("2026-03-01"))],
         {"keep_last": 1}, ["child", "top", "old"]),
    case("window-child-holds-its-parent", "chain", [("kid", t("2026-03-20", "06:00"), [], "base"), ("other", t("2026-03-19", "01:00")), ("filler", t("2026-03-12")), ("base", t("2026-03-05"))],
         {"keep_within_hours": 24, "keep_last": 1}, ["kid", "other", "base"]),
    case("expired-parent-is-held-expired-child-is-not", "chain", [("kid", t("2026-03-19"), [], "base"), ("base", t("2026-03-05"), ["scratch"]), ("kid2", t("2026-03-18"), ["scratch"], "base2"), ("base2", t("2026-03-04"))],
         {"keep_last": 1, "expire_tags": ["scratch"]}, ["kid", "base"]),
    case("chain-with-an-empty-policy", "chain", [("a", t("2026-03-10")), ("b", t("2026-03-11"), [], "a")],
         {}, ["b", "a"]),
    case("dangling-parent", "chain", [("a", t("2026-03-10"), [], "missing")], {"keep_last": 1}, error="ValueError"),
    case("dangling-parent-empty-policy", "chain", [("a", t("2026-03-10"), [], "missing")], {}, error="ValueError"),
    case("own-parent", "chain", [("a", t("2026-03-10"), [], "a")], {"keep_last": 1}, error="ValueError"),
    case("parent-cycle", "chain", [("a", t("2026-03-10"), [], "b"), ("b", t("2026-03-11"), [], "c"), ("c", t("2026-03-12"), [], "a"), ("d", t("2026-03-13"))],
         {"keep_last": 2}, error="ValueError"),
    # --- tag precedence (ADR-0008, window placed by ADR-0009) ---
    case("expired-not-counted", "tags", [t("2026-03-19"), t("2026-03-18") + "|scratch", t("2026-03-17")],
         {"keep_last": 2, "expire_tags": ["scratch"]}, [t("2026-03-19"), t("2026-03-17")]),
    case("protect-beats-expire", "tags", [t("2026-03-15") + "|pin,scratch", t("2026-03-16") + "|scratch", t("2026-03-17")],
         {"keep_last": 1, "protect_tags": ["pin"], "expire_tags": ["scratch"]}, [t("2026-03-17"), t("2026-03-15")]),
    case("same-tag-in-both-lists", "tags", [t("2026-03-15") + "|x", t("2026-03-16"), t("2026-03-17")],
         {"keep_last": 1, "protect_tags": ["x"], "expire_tags": ["x"]}, [t("2026-03-17"), t("2026-03-15")]),
    case("future-beats-expire", "tags", [t("2026-03-25") + "|scratch", t("2026-03-19"), t("2026-03-18")],
         {"keep_last": 1, "expire_tags": ["scratch"]}, [t("2026-03-25"), t("2026-03-19")]),
    case("expire-with-an-empty-keep-configuration", "tags", [t("2026-03-10"), t("2026-03-11") + "|scratch", t("2026-03-12")],
         {"expire_tags": ["scratch"]}, [t("2026-03-12"), t("2026-03-10")]),
    case("expire-with-zero-rules", "tags", [t("2026-03-10"), t("2026-03-11") + "|scratch", t("2026-03-12")],
         {"keep_daily": 0, "keep_within_hours": 0, "expire_tags": ["scratch"], "protect_tags": ["other"]}, [t("2026-03-12"), t("2026-03-10")]),
    case("protected-expired-with-an-empty-policy", "tags", [t("2026-03-10") + "|x", t("2026-03-11")],
         {"expire_tags": ["x"], "protect_tags": ["x"]}, [t("2026-03-11"), t("2026-03-10")]),
    case("expired-not-a-representative", "tags", [t("2026-03-19", "20:00") + "|scratch", t("2026-03-19", "05:00"), t("2026-03-18", "05:00")],
         {"keep_daily": 1, "expire_tags": ["scratch"]}, [t("2026-03-19", "05:00")]),
    case("expired-day-is-no-bucket", "tags", [t("2026-03-19", "05:00") + "|scratch", t("2026-03-18", "05:00"), t("2026-03-17", "05:00"), t("2026-03-16", "05:00")],
         {"keep_daily": 2, "expire_tags": ["scratch"]}, [t("2026-03-18", "05:00"), t("2026-03-17", "05:00")]),
    case("one-expire-tag-among-several", "tags", [t("2026-03-19") + "|a,scratch,b", t("2026-03-18")],
         {"keep_daily": 5, "expire_tags": ["scratch", "other"]}, [t("2026-03-18")]),
    # --- month start day (ADR-0010) ---
    case("month-start-15", "month", [t("2026-01-10"), t("2026-01-20"), t("2026-02-14"), t("2026-02-15")],
         {"keep_monthly": 2, "month_start_day": 15}, [t("2026-02-15"), t("2026-02-14")]),
    case("month-start-yearly-stays-calendar", "month", [t("2025-12-20"), t("2026-01-10"), t("2026-01-20")],
         {"keep_yearly": 2, "month_start_day": 15}, [t("2026-01-20"), t("2025-12-20")]),
    case("month-start-31-leap-february", "month", [t("2028-02-28"), t("2028-02-29"), t("2028-03-30"), t("2028-03-31")],
         {"keep_monthly": 2, "month_start_day": 31}, [t("2028-03-31"), t("2028-03-30")], now="2028-04-10T12:00:00" + Z),
    case("month-start-30-short-february", "month", [t("2027-02-27"), t("2027-02-28"), t("2027-03-29"), t("2027-03-30")],
         {"keep_monthly": 3, "month_start_day": 30}, [t("2027-03-30"), t("2027-03-29"), t("2027-02-27")], now="2027-04-10T12:00:00" + Z),
    case("month-start-29-century-year", "month", [t("2100-02-27"), t("2100-02-28")],
         {"keep_monthly": 2, "month_start_day": 29}, [t("2100-02-28"), t("2100-02-27")], now="2100-04-01T12:00:00" + Z),
    case("month-start-29-year-2000", "month", [t("2000-02-28"), t("2000-02-29")],
         {"keep_monthly": 2, "month_start_day": 29}, [t("2000-02-29"), t("2000-02-28")], now="2000-04-01T12:00:00" + Z),
    case("month-start-20-january-wraps", "month", [t("2026-01-05"), t("2025-12-25"), t("2025-12-10")],
         {"keep_monthly": 2, "month_start_day": 20}, [t("2026-01-05"), t("2025-12-10")], now="2026-02-01T12:00:00" + Z),
    case("month-start-with-day-start-hour", "month", [t("2026-02-15", "03:30"), t("2026-02-15", "04:00")],
         {"keep_monthly": 2, "month_start_day": 15, "day_start_hour": 4}, [t("2026-02-15", "04:00"), t("2026-02-15", "03:30")]),
    case("month-start-with-a-zone", "month", [t("2026-07-14", "22:30"), t("2026-07-14", "21:30")],
         {"keep_monthly": 2, "month_start_day": 15, "zone": "lakeside"}, [t("2026-07-14", "22:30"), t("2026-07-14", "21:30")], now="2026-08-01T12:00:00" + Z),
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


def sundays(year, month):
    first = date(year, month, 1)
    days = [first + timedelta(days=i) for i in range(31)]
    return [d for d in days if d.month == month and d.weekday() == 6]


def zone_rows(zone):
    """Independent statement of the tables of ADR-0005, from the rules they were generated from: (initial, [(instant, offset)])."""
    rows = []
    for year in range(2022, 2028):
        if zone == "lakeside":
            rows.append((datetime.combine(sundays(year, 3)[-1], datetime.min.time(), timezone.utc) + timedelta(hours=1), 120))
            rows.append((datetime.combine(sundays(year, 10)[-1], datetime.min.time(), timezone.utc) + timedelta(hours=1), 60))
        else:
            rows.append((datetime.combine(sundays(year, 4)[0] - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=16, minutes=30), 570))
            rows.append((datetime.combine(sundays(year, 10)[0] - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=16, minutes=30), 630))
    return (60 if zone == "lakeside" else 630), sorted(rows)


def zone_offset(zone, instant):
    current, rows = zone_rows(zone)
    for start, offset in rows:
        if start <= instant:
            current = offset
    return current


def month_index(day, start_day):
    """Months since year 0 of the cycle `day` falls in (ADR-0010)."""
    index = day.year * 12 + day.month - 1
    if day.day < min(start_day, calendar.monthrange(day.year, day.month)[1]):
        index -= 1
    return index


def reference(snaps, policy, now_text):
    """Independent statement of ADR-0001 with the later records applied. Returns the ordered keep list."""
    now = parse(now_text)
    rows = sorted(((parse(stamp), sid, frozenset(tags), parent) for sid, stamp, tags, parent in snaps), key=lambda r: (r[0], r[1]), reverse=True)
    by_id = {r[1]: r for r in rows}
    n_last = policy.get("keep_last") or 0
    counts = {"day": policy.get("keep_daily") or 0, "week": policy.get("keep_weekly") or 0,
              "month": policy.get("keep_monthly") or 0, "year": policy.get("keep_yearly") or 0}
    within = policy.get("keep_within_hours") or 0
    protect, expire = set(policy.get("protect_tags") or []), set(policy.get("expire_tags") or [])
    kept, pool = set(), []
    for row in rows:
        if row[2] & protect or row[0] > now:
            kept.add(row[1])
        elif row[2] & expire:
            continue
        elif within and now - row[0] <= timedelta(hours=within):
            kept.add(row[1])
        else:
            pool.append(row)
    if not (n_last or within or any(counts.values())):
        kept.update(r[1] for r in pool)
    else:
        kept.update(r[1] for r in pool[:n_last])
        zone, fixed = policy.get("zone"), policy.get("tz_offset_minutes", 0)
        shift = timedelta(hours=policy.get("day_start_hour", 0))
        start_day = policy.get("month_start_day", 1)
        for kind, n in counts.items():
            if not n:
                continue
            buckets = {}
            for when, sid, _, _ in reversed(pool):  # oldest first, so the newest overwrites
                minutes = zone_offset(zone, when) if zone else fixed
                local = (when.astimezone(timezone(timedelta(minutes=minutes))) - shift).date()
                key = {"day": local.toordinal(), "week": tuple(local.isocalendar())[:2],
                       "month": month_index(local, start_day), "year": local.year}[kind]
                buckets[key] = sid
            for key in sorted(buckets)[::-1][:n]:
                kept.add(buckets[key])
    frontier = list(kept)
    while frontier:
        parent = by_id[frontier.pop()][3]
        if parent is not None and parent not in kept:
            kept.add(parent)
            frontier.append(parent)
    return [r[1] for r in rows if r[1] in kept]


def generated(count=500, seed=20260315):
    rng = random.Random(seed)
    cases = []
    anchors = ["2024-12-31", "2025-12-31", "2023-12-31", "2026-03-01", "2025-06-30", "2026-01-01",
               "2024-02-29", "2026-03-29", "2025-10-26", "2026-10-03", "2024-04-06", "2026-07-31"]
    for i in range(count):
        anchor = datetime.fromisoformat(rng.choice(anchors) + "T00:00:00+00:00")
        size = rng.randint(1, 40)
        snaps = []
        for j in range(size):
            if rng.random() < 0.6:
                when = anchor + timedelta(minutes=rng.randint(-60 * 24 * 12, 60 * 24 * 12))
            else:
                when = anchor + timedelta(minutes=rng.randint(-60 * 24 * 700, 60 * 24 * 40))
            if rng.random() < 0.12 and snaps:  # same instant as another snapshot, different id
                when = parse(rng.choice(snaps)[1])
            local = when.astimezone(timezone(timedelta(minutes=rng.choice([0, 0, 120, -300, 330]))))
            tags = [x for x in ("release", "pinned", "scratch", "tmp") if rng.random() < 0.08]
            parent = rng.choice([s[0] for s in snaps]) if snaps and rng.random() < 0.3 else None
            snaps.append([f"id{rng.randint(0, 3)}-{i}-{j}", local.isoformat(), tags, parent])
        policy = {}
        for name in ("keep_last", "keep_daily", "keep_weekly", "keep_monthly", "keep_yearly"):
            if rng.random() < 0.45:
                policy[name] = rng.choice([0, 1, 2, 3, 5, 8])
        if rng.random() < 0.35:
            policy["keep_within_hours"] = rng.choice([0, 1, 12, 24, 72, 24 * 10, 24 * 40])
        policy["protect_tags"] = rng.choice([[], [], ["release"], ["release", "pinned"]])
        policy["expire_tags"] = rng.choice([[], [], ["scratch"], ["scratch", "tmp"], ["tmp", "release"]])
        policy["tz_offset_minutes"] = rng.choice([0, 0, 60, 120, -300, 330, -720, 840])
        policy["day_start_hour"] = rng.choice([0, 0, 3, 4, 6, 23])
        policy["zone"] = rng.choice([None, None, None, "lakeside", "harbor"])
        policy["month_start_day"] = rng.choice([1, 1, 1, 15, 28, 29, 30, 31])
        now = anchor + timedelta(days=rng.randint(-3, 30), minutes=rng.randint(0, 1439))
        cases.append({"name": f"generated-{i}", "group": "generated", "snaps": snaps, "policy": policy,
                      "now": now.isoformat(), "keep": None, "error": None})
    return cases


def expected_for(case):
    if case["error"]:
        return None
    if case["keep"] is not None:
        wanted = set(case["keep"])
        rows = sorted(((parse(stamp), sid) for sid, stamp, *_ in case["snaps"]), reverse=True)
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
        shots = [Snapshot(i, datetime.fromisoformat(s), frozenset(t), p) for i, s, t, p in c["snaps"]]
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
    every = sorted(row[0] for row in case["snaps"])
    partition = sorted(got["keep"] + got["prune"]) == every
    ok = partition and got["keep"] == want
    rows = sorted(((parse(row[1]), row[0]) for row in case["snaps"]), reverse=True)
    pruned = [sid for _, sid in rows if sid not in set(want)]
    ok = ok and got["prune"] == pruned
    return ok, f"{case['name']}: keep {got['keep']}, wanted {want}"


# The ADRs whose number SUMMARY.md must give: weeks, day boundary, zones, keep_within, chains, tags, window revert, months.
GOVERNING = (3, 4, 5, 6, 7, 8, 9, 10)


def cited_numbers(text):
    """Every ADR number the text gives, in any reasonable wording: ADR-0003, ADR 3, adr #3, ADRs 3, 4 and 5, a bare 0003, a table cell."""
    found = set()
    for m in re.finditer(r"(?i)\badrs?[-\s_#:]*(\d+(?:\s*(?:,|/|&|\band\b|\bor\b|\bto\b|-|–)\s*(?:adrs?[-\s_#:]*)?\d+)*)", text):
        found.update(int(n) for n in re.findall(r"\d+", m.group(1)))
    found.update(int(m.group(1)) for m in re.finditer(r"(?<![\w.-])00(\d\d)(?![\w.])", text))
    found.update(int(m.group(1)) for m in re.finditer(r"\|\s*(?:adr[-\s_#]*)?0*(\d{1,2})\s*(?=\|)", text, re.I))
    return found


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
    failures = {k: [] for k in GROUPS}
    totals = {k: 0 for k in GROUPS}
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
    g.add("hidden-named-zones", *verdict("zone"))
    g.add("hidden-keep-within", *verdict("within"))
    g.add("hidden-snapshot-chains", *verdict("chain"))
    g.add("hidden-tag-precedence", *verdict("tags"))
    g.add("hidden-month-start-day", *verdict("month"))
    g.add("hidden-generated-schedules", *verdict("generated"))
    g.add("hidden-generated-mostly-right", not crashed and len(failures["generated"]) <= totals["generated"] // 10,
          "probe crashed" if crashed else f"{len(failures['generated'])} of {totals['generated']} wrong", required=False)

    text = g.summary_checks(ws)
    cited = cited_numbers(text)
    missing = [n for n in GOVERNING if n not in cited]
    g.add("summary-names-governing-adrs", not missing,
          "ok" if not missing else f"SUMMARY.md must name, by number, the ADRs applied; not found: {['ADR-%04d' % n for n in missing]}")


if __name__ == "__main__":
    main(grade)
