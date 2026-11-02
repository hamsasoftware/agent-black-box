from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from blackbox.redact import Redactor

ROSTER = ["Ember", "Quill", "Rook", "Sable", "Tarn", "Vesper", "Wren", "Yarrow", "Zephyr",
          "Argent", "Birch", "Cinder", "Dune", "Elm", "Flint"]


def agents_path(root: Path) -> Path:
    return root / "ledger" / "agents.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def name_for(n: int) -> str:
    base = ROSTER[n % len(ROSTER)]
    return base if n < len(ROSTER) else f"{base}-{n // len(ROSTER) + 1}"


def next_subject_name(root: Path) -> str:
    count = sum(1 for r in read_jsonl(agents_path(root)) if r.get("kind") == "subject")
    return name_for(count)


def new_agent_id() -> str:
    return "agt-" + secrets.token_hex(4)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=False)


def write_json(path: Path, obj: Any, redactor: Redactor) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redactor.obj(obj), indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[Any], redactor: Redactor) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(dumps(redactor.obj(row)) + "\n")


def append_agent(root: Path, entry: dict[str, Any], redactor: Redactor) -> None:
    path = agents_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(dumps(redactor.obj(entry)) + "\n")


def upsert_agent(root: Path, entry: dict[str, Any], redactor: Redactor) -> None:
    path = agents_path(root)
    rows = [r for r in read_jsonl(path) if r.get("agent_id") != entry["agent_id"]]
    rows.append(entry)
    write_jsonl(path, rows, redactor)
