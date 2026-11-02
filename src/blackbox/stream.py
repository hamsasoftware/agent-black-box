from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

DENIAL_TEXT = re.compile(
    r"(?i)(requested permissions? to use|haven't granted it|permission (?:for this action )?(?:was )?denied|"
    r"not allowed by|denied by|permission to use .* (?:was|has been) denied)")
TEST_COMMAND = re.compile(r"(?:^|[\s;&|(])(?:pytest|py\.test|python[0-9.]* -m (?:pytest|unittest)|tox|nox|make test)\b")
FAILURE_TEXT = re.compile(r"(?i)(\b\d+ failed\b|\bFAILED\b|\bERROR\b|Traceback \(most recent call last\)|\berrors?\b during collection|AssertionError)")
PASS_TEXT = re.compile(r"(?i)\b\d+ passed\b")


def parse_line(line: str) -> dict[str, Any]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return {"type": "malformed", "raw": line[:4000]}
    if not isinstance(event, dict):
        return {"type": "malformed", "raw": line[:4000]}
    return event


def result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return "" if content is None else str(content)


@dataclass
class ToolUse:
    index: int
    id: str
    name: str
    input: dict[str, Any]

    @property
    def command(self) -> str:
        return str(self.input.get("command", "")) if self.name == "Bash" else ""

    @property
    def path(self) -> str:
        return str(self.input.get("file_path") or self.input.get("notebook_path") or self.input.get("path") or "")

    @property
    def is_edit(self) -> bool:
        return self.name in ("Edit", "Write", "MultiEdit", "NotebookEdit")

    @property
    def is_test_run(self) -> bool:
        return bool(self.command and TEST_COMMAND.search(self.command))


@dataclass
class ToolResult:
    index: int
    tool_use_id: str
    is_error: bool
    text: str

    @property
    def is_denial(self) -> bool:
        return self.is_error and bool(DENIAL_TEXT.search(self.text))

    @property
    def looks_failed(self) -> bool:
        return self.is_error or bool(FAILURE_TEXT.search(self.text))

    @property
    def looks_passed(self) -> bool:
        return not self.is_error and bool(PASS_TEXT.search(self.text)) and not FAILURE_TEXT.search(self.text)


@dataclass
class Texts:
    index: int
    text: str


@dataclass
class Stream:
    events: list[dict[str, Any]]
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    texts: list[Texts] = field(default_factory=list)
    init: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    result_index: int | None = None
    malformed: list[int] = field(default_factory=list)

    @classmethod
    def from_events(cls, events: list[dict[str, Any]]) -> "Stream":
        s = cls(events=events)
        seen_tools: set[str] = set()
        for i, ev in enumerate(events):
            kind = ev.get("type")
            if kind == "malformed":
                s.malformed.append(i)
            elif kind == "system" and ev.get("subtype") == "init" and s.init is None:
                s.init = ev
            elif kind == "result":
                s.result, s.result_index = ev, i
            elif kind == "assistant":
                for block in _content(ev):
                    btype = block.get("type")
                    if btype == "tool_use":
                        tid = str(block.get("id", f"anon-{i}"))
                        if tid in seen_tools:
                            continue
                        seen_tools.add(tid)
                        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                        s.tool_uses.append(ToolUse(i, tid, str(block.get("name", "?")), inp))
                    elif btype == "text" and block.get("text"):
                        s.texts.append(Texts(i, str(block["text"])))
            elif kind == "user":
                for block in _content(ev):
                    if block.get("type") == "tool_result":
                        s.tool_results.append(ToolResult(
                            i, str(block.get("tool_use_id", "")), bool(block.get("is_error")),
                            result_text(block.get("content"))))
        return s

    def result_for(self, tool_use_id: str) -> ToolResult | None:
        for r in self.tool_results:
            if r.tool_use_id == tool_use_id:
                return r
        return None

    def tool_use(self, tool_use_id: str) -> ToolUse | None:
        for t in self.tool_uses:
            if t.id == tool_use_id:
                return t
        return None

    @property
    def final_text(self) -> str:
        if self.result and isinstance(self.result.get("result"), str):
            return self.result["result"]
        return self.texts[-1].text if self.texts else ""

    @property
    def final_index(self) -> int | None:
        if self.texts:
            return self.texts[-1].index
        return self.result_index

    @property
    def cli_version(self) -> str | None:
        return (self.init or {}).get("claude_code_version")

    @property
    def session_id(self) -> str | None:
        for ev in (self.init, self.result):
            if ev and ev.get("session_id"):
                return ev["session_id"]
        return None

    def tool_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(t.name for t in self.tool_uses).items()))

    def usage(self) -> dict[str, int]:
        if self.result and isinstance(self.result.get("usage"), dict):
            u = self.result["usage"]
        else:
            u = Counter()
            seen: set[str] = set()
            for ev in self.events:
                if ev.get("type") != "assistant":
                    continue
                msg = ev.get("message") or {}
                mid = str(msg.get("id", id(ev)))
                if mid in seen or not isinstance(msg.get("usage"), dict):
                    continue
                seen.add(mid)
                for k, v in msg["usage"].items():
                    if isinstance(v, int):
                        u[k] += v
        return {
            "input_tokens": int(u.get("input_tokens") or 0),
            "output_tokens": int(u.get("output_tokens") or 0),
            "cache_read_tokens": int(u.get("cache_read_input_tokens") or 0),
            "cache_creation_tokens": int(u.get("cache_creation_input_tokens") or 0),
        }

    def turns(self) -> int:
        if self.result and isinstance(self.result.get("num_turns"), int):
            return self.result["num_turns"]
        ids = {str((ev.get("message") or {}).get("id", i)) for i, ev in enumerate(self.events) if ev.get("type") == "assistant"}
        return len(ids)

    def cost(self) -> float | None:
        if self.result and isinstance(self.result.get("total_cost_usd"), (int, float)):
            return float(self.result["total_cost_usd"])
        return None

    def permission_denials(self) -> list[dict[str, Any]]:
        denials: list[dict[str, Any]] = []
        seen: set[str] = set()
        for d in (self.result or {}).get("permission_denials") or []:
            if not isinstance(d, dict):
                continue
            tid = str(d.get("tool_use_id", ""))
            tool = self.tool_use(tid)
            denials.append({
                "tool_name": d.get("tool_name") or (tool.name if tool else None),
                "tool_use_id": tid,
                "tool_input": d.get("tool_input") if isinstance(d.get("tool_input"), dict) else (tool.input if tool else {}),
                "event": tool.index if tool else None,
            })
            seen.add(tid)
        for r in self.tool_results:
            if r.is_denial and r.tool_use_id not in seen:
                tool = self.tool_use(r.tool_use_id)
                denials.append({
                    "tool_name": tool.name if tool else None,
                    "tool_use_id": r.tool_use_id,
                    "tool_input": tool.input if tool else {},
                    "event": r.index,
                })
                seen.add(r.tool_use_id)
        return denials


def _content(ev: dict[str, Any]) -> list[dict[str, Any]]:
    msg = ev.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []
