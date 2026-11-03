#!/usr/bin/env python3
"""Keep the numbers in README.md true.

The block between the facts markers is computed from the repository's own data. Use
`write` to refresh it and `check` to fail when it is out of date.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = "<!-- facts:start -->"
END = "<!-- facts:end -->"


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def facts(root: Path = ROOT) -> dict:
    runs = read_jsonl(root / "runs" / "index.jsonl")
    clean = [run for run in runs if not run.get("confounded_by")]
    by_variant = {}
    for variant in ("bare", "plumbed"):
        picked = [run for run in clean if run["variant"] == variant]
        by_variant[variant] = (sum(1 for run in picked if run["passed"]), len(picked))
    incidents = read_jsonl(root / "ledger" / "incidents.jsonl")
    agents = read_jsonl(root / "ledger" / "agents.jsonl")
    taxonomy = root / "behaviour" / "taxonomy.yaml"
    behaviours = len(re.findall(r"^- id:", taxonomy.read_text(encoding="utf-8"), flags=re.MULTILINE)) if taxonomy.is_file() else 0
    tasks = [path for path in (root / "tasks").glob("*/task.yaml")] if (root / "tasks").is_dir() else []
    return {
        "tasks": len(tasks),
        "runs": len(runs),
        "clean": len(clean),
        "confounded": len(runs) - len(clean),
        "bare": by_variant["bare"],
        "plumbed": by_variant["plumbed"],
        "claimed_failed": sum(1 for run in clean if run.get("claim_outcome") == "claimed-failed"),
        "cost": round(sum(run.get("cost_usd") or 0 for run in runs), 2),
        "builders": sum(1 for agent in agents if agent.get("kind") == "builder"),
        "subjects": sum(1 for agent in agents if agent.get("kind") == "subject"),
        "behaviours": behaviours,
        "incidents": len(incidents),
        "open": sum(1 for incident in incidents if incident.get("status") == "open"),
    }


def block(values: dict) -> str:
    bare, plumbed = values["bare"], values["plumbed"]
    rows = [
        ("Challenging tasks", f"{values['tasks']}, each with a hidden grader"),
        ("Recorded runs", f"{values['runs']}: {values['clean']} clean, {values['confounded']} set aside as confounded"),
        ("Clean runs that passed", f"bare {bare[0]} of {bare[1]}, plumbed {plumbed[0]} of {plumbed[1]}"),
        ("Clean runs that claimed success and failed the hidden grader", f"{values['claimed_failed']} of {values['clean']}"),
        ("Cost of every run", f"${values['cost']:.2f}"),
        ("Agents on the ledger", f"{values['builders']} builders, {values['subjects']} subjects"),
        ("Behaviours catalogued", str(values["behaviours"])),
        ("Errors logged", f"{values['incidents']}, {values['open']} still open"),
    ]
    lines = ["| At a glance | Now |", "|---|---|"] + [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines)


def rendered(readme: str, values: dict) -> str:
    if START not in readme or END not in readme:
        raise ValueError(f"README.md needs the markers {START} and {END}")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{block(values)}\n{END}{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("write", "check"))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    path = root / "README.md"
    try:
        current = path.read_text(encoding="utf-8")
        updated = rendered(current, facts(root))
    except (OSError, ValueError) as error:
        print(f"readme-facts: {error}", file=sys.stderr)
        return 1
    if args.command == "write":
        path.write_text(updated, encoding="utf-8")
        print("readme-facts: README.md refreshed")
        return 0
    if updated != current:
        print("readme-facts: the numbers in README.md are out of date; run python scripts/update_readme_facts.py write", file=sys.stderr)
        return 1
    print("readme-facts: README.md numbers match the data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
