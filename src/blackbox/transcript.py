from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from blackbox import ledger
from blackbox.redact import Redactor
from blackbox.stream import DENIAL_TEXT, result_text

TEXT_LIMIT = 400
INPUT_LIMIT = 200
RESULT_LIMIT = 200
BLOCK_TEXT = re.compile(r"(?i)(permission for this action was denied|denied by|not allowed|haven't granted|blocked)")
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f"... [{len(text) - limit} more chars]"


def _summarise_input(inp: Any) -> dict[str, Any]:
    if not isinstance(inp, dict):
        return {}
    out = {}
    for key, value in inp.items():
        if isinstance(value, str):
            out[key] = _clip(value, INPUT_LIMIT)
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = _clip(json.dumps(value, ensure_ascii=False), INPUT_LIMIT)
    return out


def _parse_ts(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def convert(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    tools: Counter[str] = Counter()
    tool_names: dict[str, str] = {}
    models: Counter[str] = Counter()
    usage: dict[str, dict[str, int]] = {}
    times: list[dt.datetime] = []
    blocked: list[dict[str, Any]] = []
    prs: list[str] = []
    pr_calls: set[str] = set()
    malformed = 0
    ident = ""
    for raw in path.read_text(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(obj, dict):
            malformed += 1
            continue
        kind = obj.get("type")
        if kind not in ("assistant", "user", "attachment"):
            continue
        ident = ident or str(obj.get("agentId") or obj.get("sessionId") or "")
        ts = _parse_ts(obj.get("timestamp"))
        if ts:
            times.append(ts)
        stamp = obj.get("timestamp")
        if kind == "attachment":
            att = obj.get("attachment") if isinstance(obj.get("attachment"), dict) else {}
            events.append({"i": len(events), "ts": stamp, "type": "attachment", "kind": str(att.get("type", "unknown"))})
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        if kind == "assistant":
            if msg.get("model"):
                models[str(msg["model"])] += 1
            if isinstance(msg.get("usage"), dict):
                usage[str(msg.get("id", len(usage)))] = {k: v for k, v in msg["usage"].items() if isinstance(v, int)}
        content = msg.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content if isinstance(content, list) else [])
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            base = {"i": len(events), "ts": stamp, "type": kind}
            if btype == "text":
                text = str(block.get("text", ""))
                events.append({**base, "kind": "text", "text": _clip(text, TEXT_LIMIT)})
            elif btype == "thinking":
                events.append({**base, "kind": "thinking", "chars": len(str(block.get("thinking", "")))})
            elif btype == "tool_use":
                name = str(block.get("name", "?"))
                tools[name] += 1
                tool_names[str(block.get("id", ""))] = name
                inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                if name == "Bash" and "gh pr create" in str(inp.get("command", "")):
                    pr_calls.add(str(block.get("id", "")))
                events.append({**base, "kind": "tool_use", "tool": name, "tool_use_id": block.get("id"),
                               "input": _summarise_input(block.get("input"))})
            elif btype == "tool_result":
                text = result_text(block.get("content"))
                tid = str(block.get("tool_use_id", ""))
                if tid in pr_calls and not block.get("is_error"):
                    prs += PR_URL.findall(text)
                is_error = bool(block.get("is_error"))
                events.append({**base, "kind": "tool_result", "tool_use_id": tid, "tool": tool_names.get(tid),
                               "is_error": is_error, "chars": len(text), "text": _clip(text, RESULT_LIMIT)})
                if is_error and (BLOCK_TEXT.search(text) or DENIAL_TEXT.search(text)):
                    blocked.append({"event": events[-1]["i"], "tool": tool_names.get(tid), "reason": _clip(text, 160)})
            else:
                events.append({**base, "kind": str(btype or "unknown")})
    totals: Counter[str] = Counter()
    for u in usage.values():
        totals.update(u)
    started = min(times) if times else None
    ended = max(times) if times else None
    summary = {
        "ident": ident or hashlib.sha256(path.read_bytes()).hexdigest(),
        "model": models.most_common(1)[0][0] if models else None,
        "started_at": started.isoformat().replace("+00:00", "Z") if started else None,
        "ended_at": ended.isoformat().replace("+00:00", "Z") if ended else None,
        "duration_ms": int((ended - started).total_seconds() * 1000) if started and ended else None,
        "tool_uses": sum(tools.values()),
        "tool_calls": dict(sorted(tools.items())),
        "tokens": {"input": totals.get("input_tokens", 0), "output": totals.get("output_tokens", 0),
                   "cache_read": totals.get("cache_read_input_tokens", 0),
                   "cache_creation": totals.get("cache_creation_input_tokens", 0)},
        "blocked_actions": blocked,
        "pr": prs[-1] if prs else None,
        "malformed_lines": malformed,
    }
    return events, summary


def ingest(path: Path, name: str, role: str, root: Path, redactor: Redactor,
           pr: str | None = None, outcome: str | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z][\w-]{0,40}", name):
        raise ValueError("name must be a simple identifier")
    events, s = convert(path)
    agent_id = "agt-" + hashlib.sha256(f"{name}:{s['ident']}".encode()).hexdigest()[:8]
    entry = {
        "agent_id": agent_id, "name": name, "role": role, "kind": "builder", "model": s["model"],
        "started_at": s["started_at"], "ended_at": s["ended_at"], "duration_ms": s["duration_ms"],
        "tool_uses": s["tool_uses"], "tokens": s["tokens"], "pr": pr or s["pr"],
        "outcome": outcome or "unknown", "blocked_actions": s["blocked_actions"],
        "tool_calls": s["tool_calls"], "event_count": len(events), "malformed_lines": s["malformed_lines"],
    }
    events_path = root / "ledger" / "builders" / name / "events.jsonl"
    kept = [e for e in ledger.read_jsonl(events_path) if e.get("agent_id") != agent_id]
    ledger.write_jsonl(events_path, kept + [{"agent_id": agent_id, **e} for e in events], redactor)
    ledger.upsert_agent(root, entry, redactor)
    return entry
