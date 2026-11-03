#!/usr/bin/env python3
"""Freeze tasks and detect changes to frozen tasks (docs/protocol.md, section 8).

A task is a candidate (`frozen: false` in task.yaml) until it has passed every gate. `write` records each frozen task's
version and content hash in tasks/LOCK.json, and refuses a task whose criteria are incomplete or whose PILOT.md has no
approved review for its version. `check` fails when a frozen task differs from its lock at the same version, when a version
goes down, when a frozen task is missing from the lock, or when the lock names a task that is gone or no longer frozen.
To change a frozen task, raise its version first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from blackbox import taskspec  # noqa: E402


def task_dirs(root: Path) -> list[Path]:
    tasks = root / "tasks"
    return sorted(p for p in tasks.iterdir() if (p / "task.yaml").is_file()) if tasks.is_dir() else []


def current(root: Path) -> dict[str, dict]:
    found = {}
    for path in task_dirs(root):
        spec = taskspec.load_spec(path)
        found[path.name] = {"version": spec.get("version"), "sha256": taskspec.task_sha256(path), "frozen": spec.get("frozen") is True}
    return found


def read_lock(root: Path) -> dict[str, dict]:
    lock = root / "tasks" / "LOCK.json"
    if not lock.is_file():
        return {}
    return json.loads(lock.read_text(encoding="utf-8")).get("tasks", {})


def problems(root: Path) -> list[str]:
    locked, now = read_lock(root), current(root)
    out = []
    for name, entry in now.items():
        if not isinstance(entry["version"], int):
            out.append(f"{name}: task.yaml has no whole-number version")
            continue
        if not entry["frozen"]:
            if name in locked:
                out.append(f"{name}: is in tasks/LOCK.json but task.yaml says frozen: false")
            continue
        if name not in locked:
            out.append(f"{name}: not in tasks/LOCK.json; run python scripts/task_lock.py write after the gates pass")
            continue
        before = locked[name]
        if entry["version"] < before["version"]:
            out.append(f"{name}: version went down from {before['version']} to {entry['version']}")
        elif entry["version"] == before["version"] and entry["sha256"] != before["sha256"]:
            out.append(f"{name}: changed without a new version; raise version in task.yaml, add a version history entry and write the lock")
        elif entry["version"] > before["version"]:
            out.append(f"{name}: version {entry['version']} is newer than the lock ({before['version']}); run write after the gates pass")
    for name in sorted(set(locked) - set(now)):
        out.append(f"{name}: in tasks/LOCK.json but the task is gone")
    return out


def write(root: Path) -> list[str]:
    locked, now = read_lock(root), current(root)
    solutions = root / "tests" / "tasks" / "solutions"
    refused = []
    new = dict(locked)
    for path in task_dirs(root):
        name, entry = path.name, now[path.name]
        if not entry["frozen"]:
            new.pop(name, None)
            continue
        found = taskspec.check_spec(path, solutions if solutions.is_dir() else None)
        if isinstance(entry["version"], int) and not taskspec.pilot_approved(path, entry["version"]):
            found = found + [f"PILOT.md has no approved review for v{entry['version']} (gate G3)"]
        if found:
            refused.extend(f"{name}: {p}" for p in found)
            continue
        before = locked.get(name)
        if before and entry["version"] < before["version"]:
            refused.append(f"{name}: version went down from {before['version']} to {entry['version']}")
        elif before and entry["version"] == before["version"] and entry["sha256"] != before["sha256"]:
            refused.append(f"{name}: changed without a new version; raise version in task.yaml first")
        else:
            new[name] = {"version": entry["version"], "sha256": entry["sha256"]}
    for name in sorted(set(new) - set(now)):
        del new[name]
    if refused:
        return refused
    payload = {"protocol": taskspec.PROTOCOL_VERSION, "tasks": dict(sorted(new.items()))}
    (root / "tasks" / "LOCK.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("write", "check"))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    found = write(root) if args.command == "write" else problems(root)
    for line in found:
        print(f"task-lock: {line}", file=sys.stderr)
    if found:
        return 1
    print("task-lock: tasks/LOCK.json written" if args.command == "write" else "task-lock: every task matches its lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
