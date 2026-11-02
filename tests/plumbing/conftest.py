import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"
VARIANTS = ROOT / "plumbing" / "variants"


class HookResult:
    def __init__(self, proc):
        self.code = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr


def _run(script, payload, env=None, raw=None):
    data = raw if raw is not None else json.dumps(payload)
    full_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "TOOL_CALL_LOG")}
    full_env.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(script)], input=data, capture_output=True, text=True, env=full_env, timeout=20,
    )
    return HookResult(proc)


@pytest.fixture
def project(tmp_path):
    return tmp_path


@pytest.fixture
def run_hook(project):
    def runner(name, payload=None, raw=None, env=None, script=None):
        merged = {"CLAUDE_PROJECT_DIR": str(project)}
        merged.update(env or {})
        return _run(script or HOOKS / name, payload, env=merged, raw=raw)
    return runner


def tool_event(project, tool, **tool_input):
    return {
        "session_id": "s-1",
        "hook_event_name": "PreToolUse",
        "cwd": str(project),
        "tool_name": tool,
        "tool_input": tool_input,
    }
