from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from blackbox.redact import Redactor
from blackbox.stream import ToolResult, result_text

STYLES = {"dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "blue": "34", "magenta": "35",
          "cyan": "36", "redbold": "1;31", "greenbold": "1;32"}
SKIP_SYSTEM = {"thinking_tokens"}
Segment = tuple[str, str | None]


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _short(path: str) -> str:
    return path.replace("<workspace>/", "").replace("<workspace>", ".")


def tool_summary(name: str, inp: dict[str, Any]) -> str:
    if not isinstance(inp, dict):
        return ""
    if name == "Bash":
        return _one_line(inp.get("command", ""))
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        detail = _short(str(inp.get("file_path") or inp.get("notebook_path") or ""))
        if name == "Edit" and inp.get("old_string") is not None:
            old = len(str(inp.get("old_string", "")).splitlines()) or 1
            new = len(str(inp.get("new_string", "")).splitlines()) or 1
            detail += f"  (-{old} +{new} lines)"
        elif name == "Write" and inp.get("content") is not None:
            detail += f"  ({len(str(inp.get('content', '')).splitlines())} lines)"
        return detail
    if name in ("Glob", "Grep"):
        where = inp.get("path")
        return _one_line(f"{inp.get('pattern', '')}" + (f" in {_short(str(where))}" if where else ""))
    for key in ("description", "prompt", "query", "url"):
        if inp.get(key):
            return _one_line(inp[key])
    return _one_line(json.dumps(inp, ensure_ascii=False))


def _k(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


class LiveView:
    def __init__(self, out: TextIO | None = None, color: bool | None = None, tty: bool | None = None,
                 width: int | None = None, redactor: Redactor | None = None):
        self.out = out or sys.stdout
        isatty = bool(getattr(self.out, "isatty", lambda: False)())
        self.tty = isatty if tty is None else tty
        if color is None:
            color = self.tty and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
        self.color = color
        self.width = max(60, width or shutil.get_terminal_size((120, 36)).columns)
        self.redactor = redactor or Redactor()
        self.lock = threading.Lock()
        self.tools: dict[str, str] = {}
        self.messages: dict[str, dict[str, int]] = {}
        self.turns = 0
        self.cost: float | None = None
        self.final_usage: dict[str, int] | None = None
        self.budget: float | None = None
        self.max_turns: int | None = None
        self.last_ms = 0
        self.footer_shown = False
        self.denials = 0
        self.hook_blocks = 0
        self.clock_start: float | None = None
        self.clock_stop = threading.Event()

    def start_clock(self, interval: float = 1.0) -> None:
        self.clock_start = time.monotonic()
        self.clock_stop.clear()
        if not self.tty:
            return

        def tick() -> None:
            while not self.clock_stop.wait(interval):
                with self.lock:
                    self._clear_footer()
                    self._draw_footer()

        threading.Thread(target=tick, daemon=True).start()

    def stop_clock(self) -> None:
        self.clock_stop.set()
        if self.clock_start is not None:
            self.last_ms = max(self.last_ms, int((time.monotonic() - self.clock_start) * 1000))
        self.clock_start = None

    def elapsed_ms(self) -> int:
        if self.clock_start is None:
            return self.last_ms
        return max(self.last_ms, int((time.monotonic() - self.clock_start) * 1000))

    def _style(self, text: str, style: str | None) -> str:
        if not style or not self.color:
            return text
        return f"\033[{STYLES[style]}m{text}\033[0m"

    def _render(self, segments: list[Segment]) -> str:
        room = self.width - 1
        parts = []
        for text, style in segments:
            text = self.redactor.text(text)
            if room <= 0:
                break
            if len(text) > room:
                text = text[: max(0, room - 3)] + "..."
            room -= len(text)
            parts.append(self._style(text, style))
        return "".join(parts)

    def _clear_footer(self) -> None:
        if self.tty and self.footer_shown:
            self.out.write("\r\033[K")
            self.footer_shown = False

    def _emit(self, segments: list[Segment]) -> None:
        self._clear_footer()
        self.out.write(self._render(segments) + "\n")

    def _draw_footer(self) -> None:
        if self.tty:
            self._clear_footer()
            self.out.write(self._render(self.footer_segments()))
            self.footer_shown = True
        self.out.flush()

    def line(self, text: str, style: str | None = "dim") -> None:
        with self.lock:
            self._emit([("              -- ", "dim"), (text, style)])
            self._draw_footer()

    def header(self, meta: dict[str, Any]) -> None:
        self.budget = meta.get("budget_usd")
        self.max_turns = meta.get("max_turns")
        rule = "=" * min(self.width - 1, 100)
        with self.lock:
            self._emit([(rule, "dim")])
            self._emit([(" agent ", "dim"), (str(meta.get("agent_name", "?")), "bold"),
                        (f"  {meta.get('agent_id', '?')}", "dim"),
                        ("   task ", "dim"), (str(meta.get("task_id", "?")), "bold"),
                        ("   variant ", "dim"), (str(meta.get("variant", "?")), "bold"),
                        ("   model ", "dim"), (str(meta.get("model", "?")), "bold")])
            self._emit([(f" run {meta.get('run_id', '?')}", "dim"),
                        (f"   budget ${float(meta.get('budget_usd') or 0):.2f}" if meta.get("budget_usd") is not None else "", "dim"),
                        (f"   max turns {meta.get('max_turns')}" if meta.get("max_turns") else "", "dim")])
            self._emit([(rule, "dim")])
            self._draw_footer()

    def footer_segments(self) -> list[Segment]:
        if self.final_usage is not None:
            u = self.final_usage
        else:
            u = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
            for m in self.messages.values():
                for k in u:
                    u[k] += m.get(k, 0)
        turns = f"{self.turns}" + (f"/{self.max_turns}" if self.max_turns else "")
        budget = f" / ${self.budget:.2f}" if isinstance(self.budget, (int, float)) else ""
        cost = f"${self.cost:.4f}{budget}" if self.cost is not None else f"--{budget}"
        segs: list[Segment] = [
            (" turns ", "dim"), (turns, "bold"),
            ("  tokens in ", "dim"), (_k(int(u.get("input_tokens", 0))), "bold"),
            (" out ", "dim"), (_k(int(u.get("output_tokens", 0))), "bold"),
            (" cache ", "dim"), (_k(int(u.get("cache_read_input_tokens", 0))), "bold"),
            ("  cost ", "dim"), (cost, "bold"),
            ("  elapsed ", "dim"), (f"{self.elapsed_ms() / 1000:.1f}s", "bold"),
        ]
        if self.denials or self.hook_blocks:
            segs.append((f"  blocked {self.denials + self.hook_blocks}", "red"))
        return segs

    def event(self, i: int, t_ms: int | None, ev: dict[str, Any]) -> None:
        with self.lock:
            if t_ms is not None:
                self.last_ms = t_ms
            for segs in self._lines(ev):
                stamp = f"{(t_ms or 0) / 1000:6.1f}s" if t_ms is not None else "       "
                self._emit([(f"{i:4d} {stamp}  ", "dim"), *segs])
            self._draw_footer()

    def _lines(self, ev: dict[str, Any]) -> list[list[Segment]]:
        kind = ev.get("type")
        if kind == "system":
            sub = ev.get("subtype")
            if sub in SKIP_SYSTEM:
                return []
            if sub == "init":
                return [[("* session start", "cyan"),
                         (f"  cli {ev.get('claude_code_version', '?')}  model {ev.get('model', '?')}  "
                          f"mode {ev.get('permissionMode', '?')}", "dim")]]
            return [[(f"* {sub or 'system'}", "dim")]]
        if kind == "assistant":
            return self._assistant(ev)
        if kind == "user":
            return self._user(ev)
        if kind == "result":
            return self._result(ev)
        if kind == "malformed":
            return [[("! malformed line", "yellow"), (f"  {_one_line(ev.get('raw', ''))}", "dim")]]
        return []

    def _assistant(self, ev: dict[str, Any]) -> list[list[Segment]]:
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        mid = str(msg.get("id", ""))
        if mid and mid not in self.messages:
            self.turns += 1
        if mid and isinstance(msg.get("usage"), dict):
            self.messages[mid] = {k: v for k, v in msg["usage"].items() if isinstance(v, int)}
        lines: list[list[Segment]] = []
        content = msg.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name = str(b.get("name", "?"))
                self.tools[str(b.get("id", ""))] = name
                lines.append([("> ", "blue"), (f"{name:<6}", "bold"), (" " + tool_summary(name, b.get("input") or {}), None)])
            elif b.get("type") == "text" and str(b.get("text", "")).strip():
                lines.append([('" ', "magenta"), (_one_line(b["text"]), None)])
            elif b.get("type") == "thinking":
                lines.append([("~ thinking", "dim")])
        return lines

    def _user(self, ev: dict[str, Any]) -> list[list[Segment]]:
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        content = msg.get("content")
        if not isinstance(content, list):
            return []
        decisions = {str(m.get("id", "")): m.get("permission_decision") for m in ev.get("tool_result_meta") or []
                     if isinstance(m, dict) and isinstance(m.get("permission_decision"), dict)}
        lines: list[list[Segment]] = []
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            tid = str(b.get("tool_use_id", ""))
            res = ToolResult(0, tid, bool(b.get("is_error")), result_text(b.get("content")), decisions.get(tid) or {})
            name = self.tools.get(tid, "tool")
            text = _one_line(res.text.replace("<tool_use_error>", "").replace("</tool_use_error>", ""))
            if res.is_hook_block:
                self.hook_blocks += 1
                lines.append([("  BLOCKED by hook ", "redbold"), (f"{name}: ", "red"), (text, None)])
            elif res.is_denial:
                self.denials += 1
                lines.append([("  DENIED ", "redbold"), (f"{name}: ", "red"), (text, None)])
            elif res.is_error:
                lines.append([("  < error ", "yellow"), (f"{name}: ", "dim"), (text, None)])
            else:
                n = len(res.text.splitlines())
                lines.append([("  < ok ", "green"), (f"{name} ", "dim"), (f"{n} line{'s' if n != 1 else ''}  ", "dim"),
                              (text, "dim")])
        return lines

    def _result(self, ev: dict[str, Any]) -> list[list[Segment]]:
        if isinstance(ev.get("num_turns"), int):
            self.turns = ev["num_turns"]
        if isinstance(ev.get("total_cost_usd"), (int, float)):
            self.cost = float(ev["total_cost_usd"])
        if isinstance(ev.get("usage"), dict):
            self.final_usage = {k: v for k, v in ev["usage"].items() if isinstance(v, int)}
        sub = str(ev.get("subtype", "?"))
        if sub == "success" and ev.get("is_error"):
            sub = str(ev.get("terminal_reason") or "error")
        style = "greenbold" if sub == "success" else "redbold"
        return [[("# agent finished: ", "bold"), (sub, style),
                 (f"  {self.turns} turns" + (f"  ${self.cost:.4f}" if self.cost is not None else ""), "dim")]]

    def summary(self, record: dict[str, Any], run_dir: Path | None = None) -> None:
        grade = record.get("grade") or {}
        with self.lock:
            self._clear_footer()
            self.footer_shown = False
            if not self.tty:
                self.out.write(self._render(self.footer_segments()) + "\n")
            rule = "-" * min(self.width - 1, 100)
            self._emit([(rule, "dim")])
            verdict = ("PASS", "greenbold") if grade.get("passed") else ("FAIL", "redbold")
            cost = record.get("cost_usd")
            self._emit([(" grade ", "dim"), verdict, (f"  score {grade.get('score', 0)}", None),
                        (f"   stop {record.get('stop_reason', '?')}", None),
                        (f"   turns {record.get('turns', '?')}", None),
                        (f"   cost ${cost:.4f}" if isinstance(cost, (int, float)) else "   cost n/a", None),
                        (f" of ${float(record.get('budget_usd') or 0):.2f}", "dim")])
            failed = [c for c in grade.get("checks") or [] if not c.get("passed")]
            for c in failed[:6]:
                self._emit([("   failed check ", "red"), (str(c.get("name", "?")), "bold"),
                            (f"  {_one_line(c.get('detail', ''))}", "dim")])
            if grade.get("error"):
                self._emit([("   grader error ", "red"), (_one_line(grade["error"]), None)])
            behaviours = record.get("behaviours") or []
            if behaviours:
                segs: list[Segment] = [(" behaviours ", "dim")]
                for b in behaviours:
                    good = b.get("polarity") == "good"
                    segs.append(((" +" if good else " -") + str(b.get("id")), "green" if good else "red"))
                self._emit(segs)
            else:
                self._emit([(" behaviours none tagged", "dim")])
            claims = record.get("claims") or []
            if claims:
                verified = sum(1 for c in claims if c.get("status") == "verified")
                contradicted = sum(1 for c in claims if c.get("status") == "contradicted")
                self._emit([(" claims ", "dim"), (f"{len(claims)}", "bold"), (f"  verified {verified}", "green"),
                            (f"  contradicted {contradicted}", "red" if contradicted else "dim")])
            layers = (record.get("confinement") or {}).get("layers")
            if layers:
                self._emit([(" confinement ", "dim"), (", ".join(layers), None)])
            if run_dir is not None:
                self._emit([(f" recorded in {run_dir}", "dim")])
            self.out.flush()


def read_meta(run_dir: Path) -> tuple[dict[str, Any], bool]:
    for name, done in (("run.json", True), ("live.json", False)):
        path = run_dir / name
        if path.is_file():
            try:
                return json.loads(path.read_text()), done
            except json.JSONDecodeError:
                continue
    return {"run_id": run_dir.name}, False


def resolve_run(target: str, root: Path) -> Path:
    path = Path(target)
    if path.is_dir():
        return path
    runs = root / "runs"
    exact = runs / target
    if exact.is_dir():
        return exact
    matches = sorted(p for p in runs.glob(f"*{target}*") if p.is_dir())
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"no single run matches {target}" + (f" ({len(matches)} match)" if matches else ""))


def watch(run_dir: Path, view: LiveView, follow: bool = True, poll: float = 0.2, timeout: float | None = None,
          replay: float = 0.0, sleep: Callable[[float], None] = time.sleep) -> int:
    meta, done = read_meta(run_dir)
    view.header(meta)
    events_path = run_dir / "events.jsonl"
    pos = 0
    buf = ""
    prev_ms = 0
    waited = 0.0
    while True:
        if events_path.is_file():
            with events_path.open() as fh:
                fh.seek(pos)
                chunk = fh.read()
                pos = fh.tell()
            buf += chunk
            *complete, buf = buf.split("\n")
            for line in complete:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t_ms = row.get("t_ms")
                if replay > 0 and isinstance(t_ms, int):
                    sleep(min(max(t_ms - prev_ms, 0) / 1000 / replay, 2.0))
                    prev_ms = t_ms
                view.event(int(row.get("i", 0)), t_ms, row.get("event") or {})
        meta, done = read_meta(run_dir)
        if done:
            view.summary(meta, run_dir)
            return 0
        if not follow or (meta.get("status") not in (None, "running")):
            view.line(f"run not finished (status {meta.get('status', 'unknown')})", "yellow")
            return 1
        if timeout is not None and waited >= timeout:
            view.line("stopped watching: timeout", "yellow")
            return 1
        sleep(poll)
        waited += poll
