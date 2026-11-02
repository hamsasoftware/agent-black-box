#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from command_policy import Blocked, Policy, check_command, is_secret_path  # noqa: E402

POLICY = Policy(block_push=True)
PATH_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep"}


def block(reason):
    sys.stderr.write(f"Blocked by guard: {reason}. Stop and report this instead of working around it.\n")
    sys.exit(2)


def main():
    try:
        event = json.loads(sys.stdin.read())
        tool = event["tool_name"]
        tool_input = event.get("tool_input") or {}
        if not isinstance(tool, str) or not isinstance(tool_input, dict):
            raise ValueError
    except Exception:
        block("unreadable hook input")
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            block("Bash call without a command string")
        try:
            check_command(command, POLICY)
        except Blocked as exc:
            block(exc.reason)
        except RecursionError:
            block("command nested too deeply to check")
    elif tool in PATH_TOOLS:
        for key in ("file_path", "path", "notebook_path", "glob"):
            value = tool_input.get(key)
            if isinstance(value, str) and is_secret_path(value):
                block(f"{tool} on a secrets file")
    sys.exit(0)


if __name__ == "__main__":
    main()
