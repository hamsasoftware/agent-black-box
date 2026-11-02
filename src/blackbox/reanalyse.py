from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from blackbox import behaviours, claims, schema, taxonomy
from blackbox.redact import Redactor
from blackbox.stream import Stream

WORKSPACE = "<workspace>"


def load_events(run_dir: Path) -> list[dict[str, Any]]:
    events = []
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            events.append({"type": "malformed", "raw": line[:4000]})
            continue
        events.append(row.get("event", {}) if isinstance(row, dict) else {"type": "malformed"})
    return events


def load_task(root: Path, task_id: str) -> dict[str, Any]:
    path = root / "tasks" / task_id / "task.yaml"
    if path.is_file():
        data = yaml.safe_load(path.read_text())
        if isinstance(data, dict):
            return data
    return {}


def analyse(run_dir: Path, record: dict[str, Any], root: Path, tax: dict[str, str]) -> dict[str, Any]:
    stream = Stream.from_events(load_events(run_dir))
    diff = (run_dir / "diff.patch").read_text() if (run_dir / "diff.patch").is_file() else ""
    grade = record.get("grade") or {}
    if (run_dir / "grade.json").is_file():
        grade = json.loads((run_dir / "grade.json").read_text())
    files = record.get("files_changed") or []
    task = load_task(root, str(record.get("task_id", "")))
    ctx = behaviours.Context(stream, diff, files, grade, task, str(record.get("stop_reason", "")), WORKSPACE)
    found, _ = behaviours.detect(ctx, tax)
    claim_list = claims.extract(stream.final_text, stream.final_index)
    verified = claims.verify(claim_list, stream, files, grade)
    return {"behaviours": found, "claims": claim_list, "verified_claims": verified}


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".run.", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def reanalyse(runs_dir: Path, root: Path, taxonomy_path: Path | None = None, write: bool = True) -> list[dict[str, Any]]:
    tax = taxonomy.load(taxonomy_path or root / "behaviour" / "taxonomy.yaml")
    sch = schema.load_schema(root)
    redactor = Redactor()
    results = []
    for run_json in sorted(runs_dir.glob("*/run.json")):
        run_dir = run_json.parent
        entry: dict[str, Any] = {"run_id": run_dir.name}
        try:
            record = json.loads(run_json.read_text())
            if not (run_dir / "events.jsonl").is_file():
                raise FileNotFoundError("events.jsonl missing")
            before = sorted(b["id"] for b in record.get("behaviours") or [])
            updated = {**record, **redactor.obj(analyse(run_dir, record, root, tax))}
            problems = schema.validate_run(updated, sch)
            if problems:
                raise ValueError("; ".join(problems[:3]))
            after = sorted(b["id"] for b in updated["behaviours"])
            if write and updated != record:
                write_atomic(run_json, updated)
            entry.update(before=before, after=after, changed=updated != record, record=updated)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            entry["error"] = str(exc)
        results.append(entry)
    return results


def evidence_line(run_dir: Path, behaviour: dict[str, Any], events: list[dict[str, Any]] | None = None) -> str:
    first = (behaviour.get("evidence") or [{}])[0]
    text = str(first.get("reason", ""))
    idx = first.get("event")
    if events is not None and isinstance(idx, int) and 0 <= idx < len(events):
        ev = events[idx]
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inp = block.get("input") or {}
                detail = inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""
                text += " | " + " ".join(str(detail).split())[:120]
                break
            if isinstance(block, dict) and block.get("type") == "text":
                text += " | " + " ".join(str(block.get("text", "")).split())[:120]
                break
    return f"{run_dir.name}: [{idx}] {text}"


def summary(results: list[dict[str, Any]], runs_dir: Path) -> list[str]:
    counts: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for r in results:
        for b in (r.get("record") or {}).get("behaviours") or []:
            counts.setdefault(b["id"], []).append((r["run_id"], b))
    lines = []
    for bid, hits in sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        run_id, b = hits[0]
        events = load_events(runs_dir / run_id)
        lines.append(f"{len(hits):3d} {bid} ({b.get('polarity')}, {b.get('confidence')})")
        lines.append("      e.g. " + evidence_line(runs_dir / run_id, b, events))
    return lines
