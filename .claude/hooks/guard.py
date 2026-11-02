#!/usr/bin/env python3
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hooklib import read_event, relative_to_project  # noqa: E402
from command_policy import Blocked, Policy, check_command, is_secret_path  # noqa: E402

PROTECTED_DIRS = ("runs", "ledger")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
PATH_TOOLS = EDIT_TOOLS | {"Read", "Grep"}


def block(reason, instead):
    sys.stderr.write(f"Blocked by the project guard: {reason}. Instead: {instead}.\n")
    sys.exit(2)


def in_protected_dir(event, raw):
    rel = relative_to_project(event, raw)
    return rel is not None and rel.split("/", 1)[0] in PROTECTED_DIRS


def check_path(event, tool, raw):
    rel = relative_to_project(event, raw)
    shown = rel if rel is not None else raw
    if is_secret_path(shown):
        block(f"{tool} on a secrets file ({PurePosixPath(shown).name})",
              "ask a person for the non-secret value you need")
    if tool in EDIT_TOOLS and rel is not None and rel.split("/", 1)[0] in PROTECTED_DIRS:
        block(f"{tool} on {rel}: run and ledger data are written only by the harness",
              "change the harness or run make run-task")


def main():
    try:
        event = read_event()
    except Exception as exc:
        sys.stderr.write(f"Blocked by the project guard: unreadable hook input ({exc.__class__.__name__}).\n")
        sys.exit(2)
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        sys.stderr.write("Blocked by the project guard: hook input lacks tool_name or tool_input.\n")
        sys.exit(2)
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            sys.stderr.write("Blocked by the project guard: Bash call without a command string.\n")
            sys.exit(2)
        policy = Policy(
            repo_rules=True,
            protected=lambda path: in_protected_dir(event, path),
            protected_write_reason="writing run or ledger data directly",
            protected_change_reason="changing run or ledger data directly",
            protected_instead="write run data only through the harness (make run-task)",
        )
        try:
            check_command(command, policy)
        except Blocked as exc:
            block(exc.reason, exc.instead)
        except RecursionError:
            block("command nested too deeply to check", "simplify the command")
    elif tool in PATH_TOOLS:
        for key in ("file_path", "path", "notebook_path", "glob"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                check_path(event, tool, value)
    sys.exit(0)


if __name__ == "__main__":
    main()
