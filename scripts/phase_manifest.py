#!/usr/bin/env python3
"""Generate and check phase manifests (docs/protocol.md, section 9).

`generate` writes protocol/phase-N.json: the questions, exact model ids, variants, frozen tasks at their locked version and
hash, repeats, harness commit, seed, budget and the full shuffled run list. It refuses candidate tasks, tasks missing from
tasks/LOCK.json, a design wider than section 4 allows, and an existing manifest. `check` verifies every manifest (or one
with --phase): schema, each task against tasks/LOCK.json as it was at the manifest's own harness commit, the run list against
the seed, the harness commit in git history, a positive budget and exact model ids. Whether the tasks still match the lock
now is a failure while the phase is unfinished and an informational note once it is complete. Neither command calls a model or reads runs/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import task_lock  # noqa: E402
from blackbox import phase, runner, schema, taskspec  # noqa: E402


def task_problems(root: Path, tasks: dict) -> list[str]:
    """Every named task must be frozen and equal to tasks/LOCK.json, and to the entry given, right now."""
    locked, now = task_lock.read_lock(root), task_lock.current(root)
    out = []
    for name, entry in sorted(tasks.items()):
        if name not in now:
            out.append(f"tasks: {name} does not exist")
        elif not now[name]["frozen"]:
            out.append(f"tasks: {name} is a candidate (frozen: false) and cannot be named in a phase")
        elif name not in locked:
            out.append(f"tasks: {name} is not in tasks/LOCK.json")
        elif (now[name]["version"], now[name]["sha256"]) != (locked[name]["version"], locked[name]["sha256"]):
            out.append(f"tasks: {name} differs from tasks/LOCK.json (stale lock or edited task); run task_lock.py check")
        elif entry is not None and (entry["version"], entry["sha256"]) != (locked[name]["version"], locked[name]["sha256"]):
            out.append(f"tasks: {name} is recorded at v{entry['version']} but tasks/LOCK.json now has v{locked[name]['version']} or another hash")
    return out


def lock_at_commit(root: Path, commit: str) -> tuple[dict | None, str | None]:
    """tasks/LOCK.json as committed at `commit`: (tasks, None) or (None, why not)."""
    shown = phase.git_out(root, "show", f"{commit}:tasks/LOCK.json")
    if shown.returncode != 0:
        return None, f"tasks: tasks/LOCK.json does not exist at harness_commit {commit}"
    try:
        return json.loads(shown.stdout).get("tasks", {}), None
    except (ValueError, AttributeError):
        return None, f"tasks: tasks/LOCK.json at harness_commit {commit} is not valid JSON"


def locked_problems(root: Path, tasks: dict, commit: str) -> list[str]:
    """Every named task must be in the lock at the manifest's harness commit, at the version and hash the manifest records."""
    locked, why = lock_at_commit(root, commit)
    if locked is None:
        return [why]
    out = []
    for name, entry in sorted(tasks.items()):
        have = locked.get(name)
        if have is None:
            out.append(f"tasks: {name} is not in tasks/LOCK.json at harness_commit {commit}")
        elif (entry["version"], entry["sha256"]) != (have["version"], have["sha256"]):
            out.append(f"tasks: {name} is recorded at v{entry['version']} but tasks/LOCK.json at harness_commit {commit} has v{have['version']} or another hash")
    return out


def phase_complete(root: Path, m) -> bool:
    p = phase.progress(m, phase.index_rows(root))
    return p["done"] == p["total"]


def check_manifest_notes(root: Path, m) -> tuple[list[str], list[str]]:
    """(problems, notes). Tasks are checked against the lock at the manifest's harness commit. The stricter check against
    the lock as it is now is a problem while the phase is unfinished (a task changed under a running phase) and a note once
    every run of the phase is recorded (a later version of a task does not invalidate a finished phase)."""
    found = phase.structure_problems(m, root)
    if found:
        return found, []
    problems = phase.commit_problems(root, m["harness_commit"])
    if problems:
        return problems, []
    problems = locked_problems(root, m["tasks"], m["harness_commit"])
    now = task_problems(root, m["tasks"])
    if not now:
        return problems, []
    if phase_complete(root, m):
        return problems, [f"note: phase {m['phase']} is complete; its tasks no longer all match tasks/LOCK.json now: " + "; ".join(now)]
    return problems + now, []


def check_manifest(root: Path, m) -> list[str]:
    return check_manifest_notes(root, m)[0]


def check_all(root: Path, only: int | None = None) -> tuple[list[str], list[str]]:
    folder = root / "protocol"
    paths = sorted(folder.glob("phase-*.json")) if folder.is_dir() else []
    if only is not None:
        paths = [phase.manifest_path(root, only)]
    out, notes = [], []
    for path in paths:
        rel = path.relative_to(root)
        try:
            m = phase.read_manifest(path)
        except (OSError, json.JSONDecodeError) as exc:
            out.append(f"{rel}: cannot read: {exc}")
            continue
        if not isinstance(m, dict) or path.name != f"phase-{m.get('phase')}.json":
            out.append(f"{rel}: the file name does not match the phase field")
        if not isinstance(m, dict):
            continue
        found, info = check_manifest_notes(root, m)
        out += [f"{rel}: {p}" for p in found]
        notes += [f"{rel}: {p}" for p in info]
    return out, notes


def check(root: Path, only: int | None = None) -> list[str]:
    return check_all(root, only)[0]


def generate(root: Path, a: argparse.Namespace) -> tuple[Path | None, list[str]]:
    if a.phase < 1:
        return None, ["phase must be 1 or more"]
    path = phase.manifest_path(root, a.phase)
    if path.exists():
        return None, [f"{path.relative_to(root)} already exists; a manifest is never overwritten (write the next phase instead)"]
    locked = task_lock.read_lock(root)
    problems = task_problems(root, {t: None for t in a.tasks})
    if problems:
        return None, problems
    commit = a.harness_commit
    if not commit:
        commit = runner.harness_commit(root)
        if commit is None or commit.endswith("+dirty"):
            return None, ["harness commit: the checkout is not a clean git checkout; commit first or pass --harness-commit"]
    if len(commit) < 40:
        full = phase.git_out(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
        commit = full.stdout.strip() if full.returncode == 0 else commit
    if len(set(a.tasks)) != len(a.tasks):
        return None, ["tasks: duplicate"]
    m = {
        "protocol_version": taskspec.PROTOCOL_VERSION, "phase": a.phase, "questions": list(a.questions), "models": list(a.models),
        "variants": list(a.variants), "plumbed_model": a.plumbed_model, "tasks": {t: {"version": locked[t]["version"], "sha256": locked[t]["sha256"]} for t in sorted(a.tasks)}, "repeats": a.repeats,
        "harness_commit": commit, "seed": a.seed, "shuffle": phase.SHUFFLE, "budget_usd": a.budget_usd, "runs": [],
    }
    # design rules need a well-formed manifest, so the schema runs first on the draft without its run list
    draft = {**m, "runs": []}
    problems = schema.validate(draft, phase.load_schema(root), phase.load_schema(root))
    if not problems:
        problems = phase.design_problems(draft) + phase.commit_problems(root, commit)
    if problems:
        return None, problems
    m["runs"] = phase.expected_runs(m)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    return path, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="write protocol/phase-N.json (never overwrites)")
    g.add_argument("--phase", type=int, required=True)
    g.add_argument("--questions", nargs="+", required=True, help="Q1 Q2 Q3 Q4")
    g.add_argument("--models", nargs="+", required=True, help="exact model ids")
    g.add_argument("--variants", nargs="+", default=["bare"], help="bare, or bare plumbed (needs Q2 and --plumbed-model)")
    g.add_argument("--plumbed-model", default=None, help="the one model that also runs plumbed")
    g.add_argument("--tasks", nargs="+", required=True, help="frozen task ids")
    g.add_argument("--repeats", type=int, default=phase.DEFAULT_REPEATS)
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--budget-usd", type=float, required=True, help="the maximum spend the user approved")
    g.add_argument("--harness-commit", default=None, help="default: HEAD of a clean checkout")
    c = sub.add_parser("check", help="verify protocol/phase-*.json; passes when there are none")
    c.add_argument("--phase", type=int, default=None)
    for sp in (g, c):
        sp.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "generate":
        path, found = generate(root, args)
        for line in found:
            print(f"phase-manifest: {line}", file=sys.stderr)
        if found:
            return 1
        print(f"phase-manifest: wrote {path.relative_to(root)}")
        return 0
    found, notes = check_all(root, args.phase)
    for line in notes:
        print(f"phase-manifest: {line}")
    for line in found:
        print(f"phase-manifest: {line}", file=sys.stderr)
    if found:
        return 1
    print("phase-manifest: every manifest checks out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
