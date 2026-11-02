from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from blackbox import behaviours, claims, confine, ledger, taxonomy
from blackbox.envfile import KEY_NAME, agent_env, clean_env, find_env_file, read_env_values
from blackbox.redact import Redactor
from blackbox.stream import Stream, parse_line

ALLOWED_TOOLS = [
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(python:*)", "Bash(python3:*)", "Bash(pytest:*)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
]
PERMISSION_MODE = "acceptEdits"
SETTING_SOURCES = "project,local"
WORKSPACE_EXCLUDES = "__pycache__/\n*.pyc\n.pytest_cache/\n"
TASK_FIELDS = ["id", "title", "difficulty", "traps", "timeout_seconds", "max_budget_usd", "max_turns"]
GRADER_TIMEOUT = 600


class HarnessError(Exception):
    pass


@dataclass
class RunOptions:
    task_dir: Path
    variant: str
    model: str
    budget_usd: float | None = None
    plumbing_dir: Path | None = None
    root: Path = field(default_factory=Path.cwd)
    env_file: str | None = None
    agent_cli: str = "claude"
    timeout_seconds: float | None = None
    keep_workspace: bool = False
    taxonomy_path: Path | None = None
    sandbox: str = "auto"
    extra_env: dict[str, str] = field(default_factory=dict)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_task(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "task.yaml"
    if not path.is_file():
        raise HarnessError(f"missing {path}")
    task = yaml.safe_load(path.read_text()) or {}
    missing = [f for f in TASK_FIELDS if f not in task]
    if missing:
        raise HarnessError(f"task.yaml lacks {', '.join(missing)}")
    for part in ("PROMPT.md", "fixture", "grader/run.py"):
        if not (task_dir / part).exists():
            raise HarnessError(f"task lacks {part}")
    return task


def default_plumbing_dir(root: Path) -> Path:
    variant = root / "plumbing" / "variants" / "plumbed"
    return variant if variant.is_dir() else root / "plumbing"


def git(ws: Path, *args: str, check: bool = True) -> str:
    env = clean_env()
    env.update({"GIT_AUTHOR_NAME": "blackbox", "GIT_AUTHOR_EMAIL": "blackbox@localhost",
                "GIT_COMMITTER_NAME": "blackbox", "GIT_COMMITTER_EMAIL": "blackbox@localhost",
                "GIT_CONFIG_NOSYSTEM": "1"})
    proc = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                          cwd=ws, env=env, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise HarnessError(f"git {args[0]} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def prepare_workspace(task_dir: Path, variant: str, plumbing_dir: Path | None, base: Path) -> tuple[Path, str]:
    ws = base / "workspace"
    shutil.copytree(task_dir / "fixture", ws, symlinks=True)
    if variant == "plumbed":
        if plumbing_dir is None or not plumbing_dir.is_dir():
            raise HarnessError("plumbed variant needs an existing --plumbing-dir")
        shutil.copytree(plumbing_dir, ws, symlinks=True, dirs_exist_ok=True)
    if (ws / ".git").exists():
        shutil.rmtree(ws / ".git")
    git(ws, "init", "-q", "-b", "main")
    (ws / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (ws / ".git" / "info" / "exclude").write_text(WORKSPACE_EXCLUDES)
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "--allow-empty", "-m", "baseline")
    return ws, git(ws, "rev-parse", "HEAD").strip()


def build_command(cli: str, prompt: str, opts: RunOptions, task: dict[str, Any], session_id: str, budget: float,
                  settings: Path | None = None) -> list[str]:
    extra = ["--settings", str(settings)] if settings else []
    return [cli, "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--model", opts.model,
            "--max-budget-usd", f"{budget:.2f}",
            "--max-turns", str(int(task["max_turns"])),
            "--session-id", session_id,
            "--permission-mode", PERMISSION_MODE,
            "--setting-sources", SETTING_SOURCES,
            "--strict-mcp-config",
            *extra,
            "--allowedTools", *ALLOWED_TOOLS]


@dataclass
class AgentOutcome:
    events: list[dict[str, Any]]
    offsets_ms: list[int]
    exit_code: int | None
    timed_out: bool
    stderr: str
    error: str | None = None


def run_agent(cmd: list[str], cwd: Path, env: dict[str, str], timeout: float) -> AgentOutcome:
    events: list[dict[str, Any]] = []
    offsets: list[int] = []
    start = time.monotonic()
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, errors="replace", start_new_session=True)
    except OSError as exc:
        return AgentOutcome([], [], None, False, "", error=f"could not start the agent CLI: {exc.strerror or exc}")
    err_chunks: list[str] = []

    def read_out() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.strip():
                events.append(parse_line(line.strip()))
                offsets.append(int((time.monotonic() - start) * 1000))

    def read_err() -> None:
        assert proc.stderr is not None
        err_chunks.append(proc.stderr.read())

    readers = [threading.Thread(target=read_out, daemon=True), threading.Thread(target=read_err, daemon=True)]
    for t in readers:
        t.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    for t in readers:
        t.join(timeout=10)
    return AgentOutcome(events, offsets, proc.returncode, timed_out, "".join(err_chunks))


def collect_diff(ws: Path, baseline: str) -> tuple[str, list[dict[str, Any]]]:
    git(ws, "add", "-A")
    patch = git(ws, "diff", "--cached", "--binary", baseline)
    status = {}
    for line in git(ws, "diff", "--cached", "--name-status", "--no-renames", baseline).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            status[parts[-1]] = parts[0][0]
    files = []
    for line in git(ws, "diff", "--cached", "--numstat", "--no-renames", baseline).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            added, deleted, path = parts
            files.append({"path": path, "status": status.get(path, "M"),
                          "added": int(added) if added.isdigit() else 0,
                          "deleted": int(deleted) if deleted.isdigit() else 0})
    return patch, files


def run_grader(task_dir: Path, ws: Path, base: Path) -> dict[str, Any]:
    grader_dir = base / "grader"
    shutil.copytree(task_dir / "grader", grader_dir)
    try:
        proc = subprocess.run([sys.executable, "grader/run.py", str(ws)], cwd=base, env=clean_env(),
                              capture_output=True, text=True, timeout=GRADER_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"passed": False, "score": 0, "checks": [], "error": "grader timed out"}
    finally:
        shutil.rmtree(grader_dir, ignore_errors=True)
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "passed" in data:
            return data
    try:
        data = json.loads(proc.stdout)
        if isinstance(data, dict) and "passed" in data:
            return data
    except json.JSONDecodeError:
        pass
    return {"passed": False, "score": 0, "checks": [],
            "error": f"grader produced no result (exit {proc.returncode}): {proc.stderr.strip()[-500:]}"}


def stop_reason(outcome: AgentOutcome, stream: Stream) -> str:
    if outcome.error:
        return "launch_error"
    if outcome.timed_out:
        return "timeout"
    if stream.result:
        subtype = str(stream.result.get("subtype") or "unknown")
        if subtype == "success" and stream.result.get("is_error"):
            return str(stream.result.get("terminal_reason") or "error")
        return subtype
    return "crash"


def run(opts: RunOptions) -> Path:
    task_dir = opts.task_dir.resolve()
    root = opts.root.resolve()
    task = load_task(task_dir)
    if opts.variant not in ("bare", "plumbed"):
        raise HarnessError("variant must be bare or plumbed")
    plumbing = (opts.plumbing_dir or default_plumbing_dir(root)).resolve() if opts.variant == "plumbed" else None
    env_path = find_env_file(opts.env_file)
    if env_path is None:
        raise HarnessError("no env file found: pass --env-file or set BLACKBOX_ENV_FILE")
    values = read_env_values(env_path)
    if not values.get(KEY_NAME):
        raise HarnessError(f"the env file has no {KEY_NAME}")
    budget = float(opts.budget_usd if opts.budget_usd is not None else task["max_budget_usd"])
    timeout = float(opts.timeout_seconds if opts.timeout_seconds is not None else task["timeout_seconds"])

    name = ledger.next_subject_name(root)
    agent_id = ledger.new_agent_id()
    started = utcnow()
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{task['id']}-{opts.variant}-{name.lower()}"
    run_dir = root / "runs" / run_id
    if run_dir.exists():
        raise HarnessError(f"{run_dir} already exists")
    session_id = str(uuid.uuid4())
    prompt = (task_dir / "PROMPT.md").read_text()

    base = Path(tempfile.mkdtemp(prefix="blackbox-")).resolve()
    redactor = Redactor(values.values(), {str(base / "workspace"): "<workspace>", str(base): "<tmp>"})
    try:
        ws, baseline = prepare_workspace(task_dir, opts.variant, plumbing, base)
        plumbing_files = sorted(str(p.relative_to(plumbing)) for p in plumbing.rglob("*") if p.is_file()) if plumbing else []
        redactor.replacements[str(ws.resolve())] = "<workspace>"
        home = base / "home"
        redactor.replacements[str(home)] = "<agent-home>"
        try:
            conf = confine.prepare(base, ws, home, [root, task_dir], opts.sandbox)
        except confine.ConfinementError as exc:
            raise HarnessError(str(exc)) from exc
        env = agent_env(values)
        env.update(conf.env)
        env["CLAUDE_PROJECT_DIR"] = str(ws)
        env.update(opts.extra_env)
        prefix = confine.python_prefix()
        if prefix:
            env["PATH"] = f"{prefix / 'bin'}:{env.get('PATH', '/usr/bin:/bin')}"
        found_cli = shutil.which(opts.agent_cli)
        cli = Path(found_cli).resolve() if found_cli else None
        t0 = time.monotonic()
        if cli is None:
            outcome = AgentOutcome([], [], None, False, "", error=f"could not start the agent CLI: {opts.agent_cli} not found")
        else:
            inner = build_command(str(cli), prompt, opts, task, session_id, budget, conf.settings_path)
            cmd = conf.command(inner, ws, home, confine.read_only_paths(conf, cli))
            outcome = run_agent(cmd, ws, env, timeout)
        duration_ms = int((time.monotonic() - t0) * 1000)
        ended = utcnow()
        stream = Stream.from_events(outcome.events)
        patch, files = collect_diff(ws, baseline)
        grade = run_grader(task_dir, ws, base)
        reason = stop_reason(outcome, stream)
        ctx = behaviours.Context(stream, patch, files, grade, task, reason, str(ws))
        tax = taxonomy.load(opts.taxonomy_path or root / "behaviour" / "taxonomy.yaml")
        found, undetected = behaviours.detect(ctx, tax)
        claim_list = claims.extract(stream.final_text, stream.final_index)
        verified = claims.verify(claim_list, stream, files, grade)
        usage = stream.usage()
        notes = []
        if outcome.error:
            notes.append(outcome.error)
        if outcome.timed_out:
            notes.append(f"agent killed after the {timeout:g}s wall-clock timeout")
        if stream.malformed:
            notes.append(f"{len(stream.malformed)} malformed stream lines kept as type malformed")
        if stream.session_id and stream.session_id != session_id:
            notes.append("the agent CLI reported a different session id")
        if reason not in ("success", "timeout") and stream.result is None:
            tail = "\n".join(l for l in outcome.stderr.splitlines() if l.strip())[-1000:]
            if tail:
                notes.append("stderr: " + tail)
        if undetected:
            notes.append("no detector for: " + ", ".join(undetected))
        record = {
            "run_id": run_id,
            "agent_id": agent_id,
            "agent_name": name,
            "kind": "subject",
            "model": opts.model,
            "claude_cli_version": stream.cli_version,
            "session_id": session_id,
            "task_id": task["id"],
            "variant": opts.variant,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "started_at": iso(started),
            "ended_at": iso(ended),
            "duration_ms": duration_ms,
            "turns": stream.turns(),
            "tool_calls": stream.tool_counts(),
            **usage,
            "cost_usd": stream.cost(),
            "budget_usd": budget,
            "stop_reason": reason,
            "permission_denials": stream.permission_denials(),
            "hook_blocks": stream.hook_blocks(),
            "files_changed": files,
            "grade": grade,
            "claims": claim_list,
            "verified_claims": verified,
            "behaviours": found,
            "notes": notes,
            "exit_code": outcome.exit_code,
            "max_turns": int(task["max_turns"]),
            "timeout_seconds": timeout,
            "allowed_tools": ALLOWED_TOOLS,
            "permission_mode": PERMISSION_MODE,
            "setting_sources": SETTING_SOURCES,
            "plumbing_files": plumbing_files,
            "event_count": len(outcome.events),
            "confinement": conf.record,
        }
        events = [{"i": i, "t_ms": outcome.offsets_ms[i] if i < len(outcome.offsets_ms) else None, "event": e}
                  for i, e in enumerate(outcome.events)]
        run_dir.mkdir(parents=True)
        ledger.write_jsonl(run_dir / "events.jsonl", events, redactor)
        (run_dir / "diff.patch").write_text(redactor.text(patch))
        ledger.write_json(run_dir / "grade.json", grade, redactor)
        ledger.write_json(run_dir / "run.json", record, redactor)
        ledger.append_agent(root, {
            "agent_id": agent_id, "name": name, "role": "subject", "kind": "subject", "model": opts.model,
            "started_at": iso(started), "ended_at": iso(ended), "duration_ms": duration_ms,
            "tool_uses": sum(record["tool_calls"].values()),
            "tokens": {"input": usage["input_tokens"], "output": usage["output_tokens"],
                       "cache_read": usage["cache_read_tokens"], "cache_creation": usage["cache_creation_tokens"]},
            "pr": None,
            "outcome": "passed" if grade.get("passed") else ("failed" if reason == "success" else reason),
            "blocked_actions": [{"event": d["event"], "tool": d["tool_name"], "reason": "hook" if "reason" in d else "permission"}
                                for d in stream.blocks()],
            "run_id": run_id, "task_id": task["id"], "variant": opts.variant,
        }, redactor)
        return run_dir
    finally:
        if not opts.keep_workspace:
            shutil.rmtree(base, ignore_errors=True)
